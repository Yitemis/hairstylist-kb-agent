# -*- coding: utf-8 -*-
"""记忆管理器：统一编排短期 + 长期记忆。

对应记忆架构的"记忆循环：短期 → 长期 → 短期"：

* 追加对话进短期窗口，窗口溢出的旧对话交给大模型**摘要压缩**（上下文卸载）；
* 定期从对话中**抽取用户事实**沉淀进长期记忆；
* 每次对话前把「长期事实 + 会话摘要 + 当前窗口」渲染成记忆块，回填给模型。

大模型调用（摘要、事实抽取）均可降级：模型不可用时跳过压缩与抽取，仅保留
滑动窗口，保证主流程不中断。
"""
from __future__ import annotations

import json
import logging

from .long_term import Fact, FactStoreBase, InMemoryFactStore, render_facts
from .short_term import ShortTermMemory, Turn

logger = logging.getLogger(__name__)

# 每累积多少轮触发一次摘要与事实抽取
_SUMMARY_EVERY_TURNS = 6


class MemoryManager:
    """单会话记忆管理器。"""

    def __init__(
        self,
        tenant_id: str = "default",
        user_id: str = "default",
        window_budget: int = 1500,
        fact_store: FactStoreBase | None = None,
    ) -> None:
        """初始化。

        Args:
            tenant_id: 租户 ID。
            user_id: 用户 ID（长期记忆分区）。
            window_budget: 短期窗口 token 预算。
            fact_store: 长期事实存储，缺省用进程内实现。
        """
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.short = ShortTermMemory(budget=window_budget)
        self.facts = fact_store or InMemoryFactStore()
        self.summary = ""  # 滚动会话摘要
        self._pending: list[Turn] = []  # 已溢出、待摘要的旧对话
        self._turn_count = 0

    # ------------------------------------------------------------------
    # 写入侧
    # ------------------------------------------------------------------

    async def add_user(self, content: str) -> None:
        """记录一条用户消息。"""
        self._pending += self.short.add("user", content)
        self._turn_count += 1

    async def add_assistant(self, content: str) -> None:
        """记录一条助手消息，并按周期触发压缩与事实抽取。"""
        self._pending += self.short.add("assistant", content)
        if self._turn_count and self._turn_count % _SUMMARY_EVERY_TURNS == 0:
            await self._compress()
            await self._extract_facts()

    async def _compress(self) -> None:
        """把溢出的旧对话摘要卸载进滚动摘要。"""
        if not self._pending:
            return
        dialog = self._render_turns(self._pending)
        prompt = (
            "请把下面的对话历史压缩成简洁的中文摘要，保留关键事实、用户诉求与"
            "结论，去除寒暄。若已有旧摘要，请融合更新。\n\n"
            f"旧摘要：{self.summary or '（无）'}\n\n对话历史：\n{dialog}\n\n摘要："
        )
        result = await self._chat(prompt)
        if result:
            self.summary = result.strip()
        self._pending.clear()

    async def _extract_facts(self) -> None:
        """从当前窗口对话中抽取稳定的用户事实，写入长期记忆。"""
        dialog = self.short.render()
        prompt = (
            "从下面的对话中抽取关于用户的**稳定事实与偏好**（如发质、过敏、"
            "偏好风格、历史记录等），忽略一次性的临时问题。以 JSON 数组输出，"
            "每项形如 {\"key\":\"发质\",\"value\":\"干性\"}，无可抽取则输出 []。"
            "只输出被 <json_output></json_output> 包裹的 JSON。\n\n"
            f"对话：\n{dialog}"
        )
        result = await self._chat(prompt)
        for item in self._parse_facts(result):
            self.facts.upsert(
                Fact(
                    key=str(item.get("key", "")).strip(),
                    value=str(item.get("value", "")).strip(),
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                ),
            )

    # ------------------------------------------------------------------
    # 读取侧
    # ------------------------------------------------------------------

    def render_memory_block(self) -> str:
        """渲染完整记忆块（长期事实 + 会话摘要 + 当前窗口）。"""
        parts: list[str] = []

        fact_block = render_facts(
            self.facts.list_facts(self.tenant_id, self.user_id),
        )
        if fact_block:
            parts.append(fact_block)
        if self.summary:
            parts.append(f"【会话摘要】\n{self.summary}")
        window = self.short.render()
        if window:
            parts.append(window)
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _render_turns(turns: list[Turn]) -> str:
        lines = []
        for t in turns:
            speaker = "用户" if t.role == "user" else "助手"
            lines.append(f"{speaker}：{t.content}")
        return "\n".join(lines)

    @staticmethod
    def _parse_facts(text: str | None) -> list[dict]:
        """从模型输出中解析事实 JSON 数组，容错。"""
        if not text:
            return []
        import re

        match = re.search(r"<json_output>(.*?)</json_output>", text, re.DOTALL)
        payload = match.group(1).strip() if match else text.strip()
        try:
            import json_repair

            data = json_repair.loads(payload)
        except Exception:  # noqa: BLE001
            try:
                data = json.loads(payload)
            except Exception:  # noqa: BLE001
                return []
        return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []

    async def _chat(self, prompt: str) -> str | None:
        """调用对话模型；未配置或失败时返回 None（降级）。"""
        try:
            from openai import AsyncOpenAI

            from app.core.config import chat_config

            if not chat_config.is_valid:
                return None
            client = AsyncOpenAI(
                api_key=chat_config.api_key, base_url=chat_config.base_url,
            )
            resp = await client.chat.completions.create(
                model=chat_config.model,
                messages=[{"role": "user", "content": prompt}],
                timeout=60,
            )
            return resp.choices[0].message.content
        except Exception as exc:  # noqa: BLE001
            logger.warning("记忆模块大模型调用失败，降级跳过: %s", exc)
            return None
