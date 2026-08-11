# -*- coding: utf-8 -*-
"""意图抽取服务（P0-3 替换手写 regex）。

为什么用 LLM 替代 regex：
- regex 永远覆盖不完（英文日期 "next Monday"、空格电话、英文名字等）
- LLM 1 次调用成本 0.001 元，比维护 10 个 regex 便宜
- LLM 能处理歧义（"周六晚上" = 周六 19:00 还是 22:00？）
- 业务方改格式不用改代码

借鉴 AgentScope: 让 LLM 抽取结构化字段，配合 Pydantic 校验。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# 极简 fallback：仅识别最基础的格式
_FALLBACK_DATE = re.compile(r"(\d{4}-\d{1,2}-\d{1,2})")
_FALLBACK_TIME = re.compile(r"(\d{1,2}):(\d{2})")
_FALLBACK_PHONE = re.compile(r"1[3-9]\d{9}")


class ExtractedFields:
    """从用户消息抽取的字段。"""
    def __init__(self):
        self.appointment_date: Optional[str] = None
        self.appointment_time: Optional[str] = None
        self.customer_phone: Optional[str] = None
        self.customer_name: Optional[str] = None
        self.branch_name: Optional[str] = None
        self.stylist_name: Optional[str] = None
        self.service_name: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


async def extract_with_llm(message: str) -> ExtractedFields:
    """用 LLM 抽取用户消息中的结构化字段。

    Returns:
        ExtractedFields 实例（只填识别到的字段）
    """
    fields = ExtractedFields()
    try:
        from app.core.model_factory import get_model
        from agentscope.message import UserMsg
        model = get_model("chat")

        # 极简 prompt（生产应放外部配置）
        prompt = f"""从用户消息中提取预约相关信息，输出 JSON：
{{
  "appointment_date": "YYYY-MM-DD 格式，今天={date.today().isoformat()}",
  "appointment_time": "HH:MM 24小时制",
  "customer_phone": "11位手机号",
  "customer_name": "用户姓名"
}}

只输出识别到的字段，没识别到的不填。绝对不要编造。

用户消息: {message}
JSON:"""

        reply = await model(
            [UserMsg(content=prompt, role="user")],
            system_prompt="你是信息抽取助手，只输出 JSON。",
        )
        text = ""
        for blk in reply.content or []:
            if hasattr(blk, "text"):
                text += blk.text
        # 提取 JSON
        m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            fields.appointment_date = _norm_date(data.get("appointment_date"))
            fields.appointment_time = _norm_time(data.get("appointment_time"))
            fields.customer_phone = _norm_phone(data.get("customer_phone"))
            fields.customer_name = data.get("customer_name")
    except Exception as e:
        logger.warning("LLM 抽取失败, 用 regex fallback: %s", e)
        # 降级：只识别最基础的格式
        m = _FALLBACK_DATE.search(message)
        if m:
            fields.appointment_date = m.group(0)
        m = _FALLBACK_TIME.search(message)
        if m:
            fields.appointment_time = f"{int(m.group(1)):02d}:{m.group(2)}"
        m = _FALLBACK_PHONE.search(message)
        if m:
            fields.customer_phone = m.group(0)
        # 姓名 fallback
        nm = re.search(r"我叫(\S{1,5})", message) or re.search(r"我是(\S{1,5})", message)
        if nm:
            fields.customer_name = nm.group(1).strip()

    return fields


def _norm_date(s) -> Optional[str]:
    if not s:
        return None
    s = str(s).strip()
    today = date.today()
    if "今天" in s:
        return today.isoformat()
    if "明天" in s:
        return (today + timedelta(days=1)).isoformat()
    if "后天" in s:
        return (today + timedelta(days=2)).isoformat()
    # 周X 处理
    m = re.search(r"周([一二三四五六日末])", s)
    if m:
        weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "末": 6}
        target = weekday_map[m.group(1)]
        days_ahead = (target - today.weekday()) % 7 or 7
        return (today + timedelta(days=days_ahead)).isoformat()
    # YYYY-MM-DD 格式
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    return None


def _norm_time(s) -> Optional[str]:
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r"(\d{1,2}):(\d{2})", s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    # 处理 "下午3点" / "上午10点" / "3点"
    if "下午" in s or "晚上" in s:
        m = re.search(r"(\d+)", s)
        if m:
            h = int(m.group(1))
            if h < 12:
                h += 12
            return f"{h:02d}:00"
    if "上午" in s or "早上" in s:
        m = re.search(r"(\d+)", s)
        if m:
            h = int(m.group(1)) % 12
            return f"{h:02d}:00"
    m = re.match(r"(\d+)点", s)
    if m:
        return f"{int(m.group(1)):02d}:00"
    return None


def _norm_phone(s) -> Optional[str]:
    if not s:
        return None
    s = str(s).replace(" ", "").replace("-", "")
    m = re.match(r"(1[3-9]\d{9})", s)
    return m.group(1) if m else None
