# -*- coding: utf-8 -*-
"""长期记忆：跨会话事实提取 + 注入。

借鉴 AgentScope 2.0 的"应用层长期记忆"模式：
- 框架不存跨会话信息（v2.0 移除了 LongTermMemory）
- 应用层自己提取"用户偏好"事实
- 下次对话注入到 system prompt
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def extract_facts_with_llm(
    user_id: int,
    user_message: str,
    ai_message: str,
) -> list[dict[str, Any]]:
    """用 LLM 从一轮对话中提取用户偏好事实。

    Returns: [{"key": str, "value": str, "confidence": float}, ...]
    """
    from app.core.model_factory import get_model
    from agentscope.message import TextBlock, UserMsg

    system = """你是用户偏好事实提取器。从用户和 AI 的一轮对话中，识别并提取用户提到的个人偏好、事实、习惯。

    严格按以下 JSON 格式输出（数组），不要任何额外文字、解释、问候、代码块标记：
    [{"key": "<类型>", "value": "<内容>", "confidence": 0~1}]

    字段说明：
    - key: 类型，使用 snake_case 英文（preferred_stylist / allergic_to / address / birthday / hair_concern / preferred_branch 等）
    - value: 事实内容（中文）
    - confidence: 置信度（0~1 浮点数）

    关键要求：
    1. 只输出 JSON 数组，不要任何解释
    2. 数组里每个对象必须有 key 和 value 字段
    3. 没有明确偏好时输出 []

    示例：
    输入：用户："我以前都是找张托尼剪的"
    输出：[{"key":"preferred_stylist","value":"张托尼","confidence":0.95}]

    输入：用户："我对阿摩尼亚过敏"
    输出：[{"key":"allergic_to","value":"阿摩尼亚","confidence":1.0}]

    输入：用户："我住徐汇区"
    输出：[{"key":"address","value":"上海徐汇区","confidence":0.9}]

    输入：用户："今天天气真好"
    输出：[]
    """
    user = f"用户: {user_message}\nAI: {ai_message[:500]}"

    try:
        model = get_model("chat")
        sys_msg = UserMsg(name="system", content=[TextBlock(text=system)])
        user_msg = UserMsg(name="user", content=[TextBlock(text=user)])
        resp = await model([sys_msg, user_msg])
        text = ""
        if hasattr(resp, "__aiter__"):
            async for item in resp:
                if hasattr(item, "content") and item.content:
                    for block in item.content:
                        if hasattr(block, "text") and block.text:
                            text += block.text
        elif hasattr(resp, "content") and resp.content:
            for block in resp.content:
                if hasattr(block, "text") and block.text:
                    text += block.text

        text = text.strip()
        # 解析 JSON（支持 markdown ```json 包装 + 重复输出容错）
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        # 优先用 json_repair 容错解析（处理重复输出、不规范 JSON）
        facts = []
        try:
            import json_repair
            parsed = json_repair.loads(text)
            if isinstance(parsed, list):
                facts = parsed
            elif isinstance(parsed, dict):
                facts = [parsed]
        except ImportError:
            # 退化到原生 json
            if text.startswith("["):
                # 截取第一个完整 JSON 数组（容错 LLM 重复输出）
                end = text.find("]", 0) + 1
                if end > 0:
                    text = text[:end]
                facts = json.loads(text) if text.startswith("[") else []
        if not isinstance(facts, list):
            return []
        return [f for f in facts if isinstance(f, dict) and "key" in f and "value" in f]
    except Exception as e:
        logger.warning("事实提取失败: %s", e)
        return []


async def save_facts(user_id: int, facts: list[dict[str, Any]]) -> int:
    """保存事实到 user_profiles 表。"""
    if not facts:
        return 0
    from app.db.models import UserProfile
    from app.db.session import async_session_maker
    from sqlalchemy import select

    count = 0
    async with async_session_maker() as session:
        for fact in facts:
            key = fact.get("key", "").strip()
            value = str(fact.get("value", "")).strip()
            confidence = float(fact.get("confidence", 1.0))
            if not key or not value:
                continue
            # upsert
            stmt = select(UserProfile).where(
                UserProfile.user_id == user_id,
                UserProfile.fact_key == key,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                existing.fact_value = value
                existing.confidence = confidence
            else:
                session.add(UserProfile(
                    user_id=user_id,
                    fact_key=key,
                    fact_value=value,
                    confidence=confidence,
                ))
            count += 1
        await session.commit()
    logger.info("保存了 %d 条用户事实 (user=%d)", count, user_id)
    return count


async def get_user_facts(user_id: int) -> list[dict[str, str]]:
    """获取用户所有事实（按 key 去重，取最高 confidence）。"""
    from app.db.models import UserProfile
    from app.db.session import async_session_maker
    from sqlalchemy import select

    async with async_session_maker() as session:
        stmt = (
            select(UserProfile)
            .where(UserProfile.user_id == user_id)
            .order_by(UserProfile.confidence.desc())
        )
        rows = (await session.execute(stmt)).scalars().all()
    return [
        {"key": r.fact_key, "value": r.fact_value, "confidence": r.confidence}
        for r in rows
    ]


def build_facts_injection(facts: list[dict[str, str]]) -> str:
    """把事实渲染成可注入到 system prompt 的格式。"""
    if not facts:
        return ""
    lines = ["# 用户已知偏好（重要，请参考）"]
    for f in facts:
        lines.append(f"- {f['key']}: {f['value']}")
    return "\n".join(lines)


async def extract_and_save_facts(user_id: int, user_message: str, ai_message: str) -> int:
    """一键提取并保存事实。"""
    facts = await extract_facts_with_llm(user_id, user_message, ai_message)
    if not facts:
        return 0
    return await save_facts(user_id, facts)
