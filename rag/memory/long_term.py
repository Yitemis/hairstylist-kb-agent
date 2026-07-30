# -*- coding: utf-8 -*-
"""长期记忆：跨会话沉淀的用户事实与偏好。

对应记忆架构中的"长期记忆"：从对话中提炼出稳定、可复用的个性化信息
（如"用户是干性发质""上次染栗棕色"），持久保存并在每次对话时回填给模型，
解决跨会话遗忘问题。

存储采用可插拔后端：

* :class:`InMemoryFactStore` —— 进程内字典，开发/测试用；
* 生产可扩展为向量库后端（相似性检索个性化经验），接口保持一致。

事实抽取（从对话中识别用户事实）由 :mod:`.manager` 调用大模型完成，本模块
只负责存储与检索。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Fact:
    """一条用户事实 / 偏好。"""

    key: str        # 事实维度，如 "发质" / "染发历史"
    value: str      # 事实内容，如 "干性" / "栗棕色，距今3个月"
    tenant_id: str = "default"
    user_id: str = "default"


class FactStoreBase:
    """长期记忆存储抽象接口。"""

    def upsert(self, fact: Fact) -> None:
        """写入或更新一条事实（按 key 覆盖）。"""
        raise NotImplementedError

    def list_facts(self, tenant_id: str, user_id: str) -> list[Fact]:
        """列出某用户的全部事实。"""
        raise NotImplementedError

    def clear(self, tenant_id: str, user_id: str) -> None:
        """清空某用户的事实。"""
        raise NotImplementedError


@dataclass
class InMemoryFactStore(FactStoreBase):
    """进程内事实存储（开发 / 测试）。

    以 ``(tenant_id, user_id)`` 分区，区内按 ``key`` 去重覆盖，保证同一维度
    只保留最新事实。
    """

    _data: dict[tuple[str, str], dict[str, Fact]] = field(default_factory=dict)

    def upsert(self, fact: Fact) -> None:
        bucket = self._data.setdefault((fact.tenant_id, fact.user_id), {})
        bucket[fact.key] = fact

    def list_facts(self, tenant_id: str, user_id: str) -> list[Fact]:
        return list(self._data.get((tenant_id, user_id), {}).values())

    def clear(self, tenant_id: str, user_id: str) -> None:
        self._data.pop((tenant_id, user_id), None)


def render_facts(facts: list[Fact]) -> str:
    """把事实列表渲染为可嵌入 Prompt 的文本块。"""
    if not facts:
        return ""
    lines = [f"· {f.key}：{f.value}" for f in facts]
    return "【已确认的用户信息】\n" + "\n".join(lines)
