# -*- coding: utf-8 -*-
"""Booking Intake Router - 智能识别用户意图.

借鉴 JavaGuide §1.1 "范式选型"：
- 预约下单路径确定 → Agentic Workflows（状态机）
- 但每个节点的"用户输入"可能不是字段值（题外话、改字段、取消、查询）
- 用"intake_router"做 LLM 意图分类 → 路由到不同处理路径

借鉴 JavaGuide §3.5 "Context Assembler"：
- 每次 LLM 调用前组装上下文（当前 step + 已填字段 + 用户输入）
- 让 LLM 看到完整状态做决策

借鉴 JavaGuide §5.6 "工作流的安全风险"：
- 高风险步骤（confirm）必须收紧自由度
- 低风险步骤（字段填充）可以允许题外话

支持的意图：
- continue: 继续填当前字段
- change_branch / change_service / change_stylist / change_datetime / change_phone / change_name: 改其他字段
- side_question: 题外话（知识问答），回答后回原节点
- cancel: 取消预约
- query_status: 查询当前订单状态
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.core.model_factory import get_model
from agentscope.message import TextBlock, UserMsg

logger = logging.getLogger(__name__)


# ============ 意图类型常量 ============

INTENT_CONTINUE = "continue"
INTENT_CHANGE_BRANCH = "change_branch"
INTENT_CHANGE_SERVICE = "change_service"
INTENT_CHANGE_STYLIST = "change_stylist"
INTENT_CHANGE_DATETIME = "change_datetime"
INTENT_CHANGE_PHONE = "change_phone"
INTENT_CHANGE_NAME = "change_name"
INTENT_SIDE_QUESTION = "side_question"
INTENT_CANCEL = "cancel"
INTENT_QUERY_STATUS = "query_status"

ALL_INTENTS = [
    INTENT_CONTINUE,
    INTENT_CHANGE_BRANCH, INTENT_CHANGE_SERVICE, INTENT_CHANGE_STYLIST,
    INTENT_CHANGE_DATETIME, INTENT_CHANGE_PHONE, INTENT_CHANGE_NAME,
    INTENT_SIDE_QUESTION, INTENT_CANCEL, INTENT_QUERY_STATUS,
]


# ============ 快速意图识别（关键词，无需 LLM）============

_CANCEL_KEYWORDS = ["取消预约", "算了吧", "不约了", "放弃", "cancel", "退出", "算啦"]
_QUERY_KEYWORDS = ["我的订单", "当前状态", "现在到哪", "查一下", "进度", "订单状态", "我填到", "我约到", "现在啥"]
_KNOWLEDGE_HINTS = [
    "原理", "为什么", "怎么", "如何", "是什么", "区别",
    "伤", "会", "能", "吗", "好不好", "怎么样",
    "过敏", "副作用", "护理", "保养", "受损",
]


def _quick_intent_classify(user_input: str) -> Optional[str]:
    """快速意图分类（关键词匹配，节省 LLM 调用）.

    Returns:
        识别的意图, None 表示需要 LLM 分类
    """
    text = user_input.strip()
    text_lower = text.lower()
    if not text:
        return None

    # 1. 取消意图（高优先级）
    if any(kw in text for kw in _CANCEL_KEYWORDS):
        return INTENT_CANCEL

    # 2. 查询状态
    if any(kw in text for kw in _QUERY_KEYWORDS):
        return INTENT_QUERY_STATUS

    # 3. 改字段意图（"换" + 字段）
    if "换" in text or "改" in text or "重新" in text:
        if "分店" in text or "店" in text:
            return INTENT_CHANGE_BRANCH
        if "项目" in text or "服务" in text or "烫" in text or "染" in text or "剪" in text:
            return INTENT_CHANGE_SERVICE
        if "发型师" in text:
            return INTENT_CHANGE_STYLIST
        if "时间" in text or "日期" in text or "几点" in text:
            return INTENT_CHANGE_DATETIME
        if "电话" in text or "手机" in text:
            return INTENT_CHANGE_PHONE
        if "姓名" in text or "名字" in text:
            return INTENT_CHANGE_NAME

    return None  # 需要 LLM 分类


# ============ LLM 意图分类 ============

async def classify_intent_with_llm(
    user_input: str,
    current_step: str,
    filled_fields: dict[str, Any],
    max_retries: int = 1,
) -> str:
    """用 LLM 分类用户意图.

    Args:
        user_input: 用户本轮输入
        current_step: 当前状态机所在 step
        filled_fields: 已填的字段 dict
        max_retries: 失败重试次数

    Returns:
        意图字符串 (ALL_INTENTS 之一)
    """
    fields_text = "\n".join(
        f"- {k}: {v if v is not None else '(未填)'}"
        for k, v in filled_fields.items()
        if k in ("branch_id", "service_type", "stylist_id", "appointment_date",
                "appointment_time", "customer_phone", "customer_name")
    )

    prompt = f"""你是预约流程的智能路由器。分析用户输入属于哪种意图。

当前状态机 step: {current_step}
已填字段:
{fields_text}

用户输入: "{user_input}"

意图分类（重要：仔细判断用户是在回答当前问题，还是在做其他事）:

1. **continue** - 用户在回答当前 step 的问题
   - 例（current_step=checkin_branch）: "1" / "人民广场店" / "人民广场那家"
   - 例（current_step=checkin_service）: "热烫" / "染发" / "剪发"
   - 例（current_step=checkin_datetime）: "明天下午3点" / "下周六10:30"

2. **change_branch/service/stylist/datetime/phone/name** - 用户在修改已填字段
   - 例: "我想换发型师" / "改时间" / "分店换一下"

3. **side_question** - 用户在问专业知识，与当前预约流程无关
   - 例: "热烫伤头发吗？" / "染发原理是什么" / "染发有什么副作用" / "什么发质适合烫"
   - 特征：含"原理/为什么/怎么/区别/伤/会/吗/好不好/怎么样/过敏/副作用/护理"
   - 当前 step 在问分店/服务/发型师/时间/电话/姓名，但用户问的是专业知识

4. **cancel** - 用户想取消预约
   - 例: "取消吧" / "算了吧" / "不约了" / "放弃"

5. **query_status** - 用户想查看当前进度
   - 例: "我填到哪了" / "现在什么状态" / "查一下订单"

只输出一个英文单词，不要其他解释。"""

    for attempt in range(max_retries + 1):
        try:
            model = get_model("chat")
            resp = await model([
                UserMsg(name="user", content=[TextBlock(text=prompt)]),
            ])
            text = ""
            if hasattr(resp, "content") and resp.content:
                for block in resp.content:
                    if hasattr(block, "text") and block.text:
                        text += block.text
            text = text.strip().lower()

            # 解析意图
            for intent in ALL_INTENTS:
                if intent in text:
                    return intent
            # 兜底
            return INTENT_CONTINUE
        except Exception as e:
            logger.warning("classify_intent_with_llm attempt %d failed: %s", attempt, e)
            if attempt == max_retries:
                return INTENT_CONTINUE
    return INTENT_CONTINUE


# ============ 主要 API ============

async def intake_route(
    user_input: str,
    current_step: str,
    filled_fields: dict[str, Any],
) -> dict[str, Any]:
    """Intake Router 主入口.

    Returns:
        dict, 包含:
        - intent: 识别的意图
        - side_answer: (side_question 时) 知识问答的回答
        - status_text: (query_status 时) 当前订单状态文本
    """
    text = user_input.strip()
    if not text:
        return {"intent": INTENT_CONTINUE}

    # 1. 快速识别 - 明确意图（关键词）
    quick_intent = _quick_intent_classify(text)
    if quick_intent in (INTENT_CANCEL, INTENT_QUERY_STATUS):
        return {"intent": quick_intent}
    if quick_intent in (INTENT_CHANGE_BRANCH, INTENT_CHANGE_SERVICE, INTENT_CHANGE_STYLIST,
                       INTENT_CHANGE_DATETIME, INTENT_CHANGE_PHONE, INTENT_CHANGE_NAME):
        return {"intent": quick_intent}

    # 2. 知识问答快速识别（如果包含明显知识词）
    knowledge_score = sum(1 for kw in _KNOWLEDGE_HINTS if kw in text)
    if knowledge_score >= 2 and len(text) > 8:
        return {"intent": INTENT_SIDE_QUESTION}

    # 3. LLM 分类 - 失败则 fallback 到 quick_intent (可能为 None, 当作 continue)
    try:
        intent = await classify_intent_with_llm(text, current_step, filled_fields)
        # 如果 LLM 返回 continue 但 quick_intent 有具体意图, 信任 quick
        if intent == INTENT_CONTINUE and quick_intent is not None:
            return {"intent": quick_intent}
        return {"intent": intent}
    except Exception as e:
        logger.warning("intake_route LLM failed, fallback to quick: %s", e)
        return {"intent": quick_intent or INTENT_CONTINUE}


async def handle_side_question(
    user_input: str,
    user_id: int,
    session_id: str,
) -> str:
    """处理题外话（调 knowledge_agent）.

    Returns:
        知识问答的答案
    """
    from app.core.knowledge_agent_factory import get_knowledge_agent
    from agentscope.message import TextBlock, UserMsg
    from app.utils.llm_extract import extract_text

    agent = await get_knowledge_agent()
    user_msg = UserMsg(
        name="user",
        content=[TextBlock(text=user_input)],
    )
    resp = await agent.reply([user_msg])
    return extract_text(resp) or "(暂时无法回答)"


def format_status(filled_fields: dict[str, Any]) -> str:
    """格式化当前订单状态（用于 query_status）."""
    lines = ["📋 当前订单进度："]
    FIELD_CN = {
        "branch_id": "分店", "service_type": "服务项目", "stylist_id": "发型师",
        "appointment_date": "日期", "appointment_time": "时间",
        "customer_phone": "电话", "customer_name": "姓名",
    }
    filled = 0
    for k, cn in FIELD_CN.items():
        v = filled_fields.get(k)
        if v is not None:
            lines.append(f"✅ {cn}：{v}")
            filled += 1
        else:
            lines.append(f"⬜ {cn}：未填")
    lines.append(f"\n进度：{filled}/{len(FIELD_CN)} 字段已填")
    return "\n".join(lines)


__all__ = [
    "INTENT_CONTINUE", "INTENT_CHANGE_BRANCH", "INTENT_CHANGE_SERVICE",
    "INTENT_CHANGE_STYLIST", "INTENT_CHANGE_DATETIME",
    "INTENT_CHANGE_PHONE", "INTENT_CHANGE_NAME",
    "INTENT_SIDE_QUESTION", "INTENT_CANCEL", "INTENT_QUERY_STATUS",
    "ALL_INTENTS",
    "intake_route", "handle_side_question", "format_status",
    "classify_intent_with_llm", "_quick_intent_classify",
]
