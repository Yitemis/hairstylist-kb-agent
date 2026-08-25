# -*- coding: utf-8 -*-
"""意图分类 (P1-8 booking sub-intent + P0-3 顶层 intent 路由).

复用了 booking intent 内的细分（看订单/继续编辑/开始新预约）。
顶层意图: knowledge / booking
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ============================================================
# P0-3: 顶层意图分类 (路由到不同 Agent)
# ============================================================

# 关键词规则 (快速路径, 不调 LLM)
_KNOWLEDGE_KEYWORDS = (
    "什么是", "为什么", "怎么", "如何", "原理", "区别", "比较",
    "染", "烫", "剪", "护", "卷", "造型", "发色", "颜色", "色号",
    "美发", "理发", "造型", "头皮", "头发", "护发素", "染膏", "烫发水",
    "过敏", "皮炎", "过敏应急", "护发", "洗发",
)

_BOOKING_KEYWORDS = (
    "预约", "下单", "改期", "退款",
    "我想约", "我要约", "帮我约", "能约", "可以约",
    "时间", "几点", "明天", "后天", "周一", "周二", "周三", "周四", "周五", "周六", "周日",
    "现在有空", "还有位置", "档期", "门店",
)

# P0-3: 业务管理类关键词 (B 端后台查/改订单 + 查员工/客户/分店)
_MANAGEMENT_KEYWORDS = (
    "查订单", "看订单", "订单列表", "订单数", "订单量",
    "查分店", "看分店", "分店列表", "哪家分店",
    "查员工", "查发型师", "员工列表", "员工信息",
    "查用户", "查客户", "用户列表", "客户列表", "查电话",
    "营收", "营业额", "统计", "业务", "dashboard", "看数据", "总览",
    "改状态", "改成", "标记为", "设为",
    "确认订单", "取消订单", "完成订单", "开始服务",
    # 单词级 (P0-3: 防止 "查订单" 不匹配, 用单词触发)
    "订单", "分店", "员工", "客户", "用户",
)


async def classify_top_intent(message: str, history: str = "") -> str:
    """顶层意图分类: knowledge / booking / management / chitchat.

    Strategy:
      1. 关键词规则快速匹配 (95% 场景够用)
      2. 兜底 LLM 分类
      3. 默认 knowledge (安全)
    """
    msg = (message or "").strip()
    if not msg:
        return "knowledge"

    has_booking = any(kw in msg for kw in _BOOKING_KEYWORDS)
    has_knowledge = any(kw in msg for kw in _KNOWLEDGE_KEYWORDS)
    has_management = any(kw in msg for kw in _MANAGEMENT_KEYWORDS)

    # 规则 0 (P0-3 高优先级): 时间词 + 动作词 → 强信号 booking
    # 防止 "明天下午 3 点预约王五剪头发" 被知识类误判
    import re as _re
    has_time = bool(_re.search(r"(明|今晚|后天|周[一二三四五六日]|下?周|大?后天|上午|下午|晚上|\d+点|\d+:\d+)", msg))
    has_action = bool(_re.search(r"(预约|约|剪|染|烫|做|弄|订)", msg))
    if has_time and has_action:
        return "booking"

    # 规则 1: 明确 management 词 → management (B 端查/改)
    if has_management and not has_booking and not has_knowledge:
        return "management"
    # 规则 2: 明确 booking 词 → booking
    if has_booking and not has_knowledge and not has_management:
        return "booking"
    # 规则 3: 明确 knowledge 词 → knowledge
    if has_knowledge and not has_booking and not has_management:
        return "knowledge"
    # 规则 4: 多类混合, 取数量最多
    counts = {
        "knowledge": sum(1 for kw in _KNOWLEDGE_KEYWORDS if kw in msg),
        "booking": sum(1 for kw in _BOOKING_KEYWORDS if kw in msg),
        "management": sum(1 for kw in _MANAGEMENT_KEYWORDS if kw in msg),
    }
    max_intent = max(counts, key=lambda k: counts[k])
    if counts[max_intent] > 0:
        return max_intent

    # 兜底: LLM 分类 (5% 模糊场景)
    try:
        from app.core.model_factory import get_model
        from agentscope.message import UserMsg, SystemMsg, TextBlock
        model = get_model("chat")
        prompt = f"""判断用户消息属于以下四类之一:
- knowledge: 用户在问知识/原理/方法/解释(美发的, 或一般知识)
- booking: 用户要预约/查档期 (C 端预约流程)
- management: B 端后台管理 (查订单/改状态/查员工/查用户/看数据)
- chitchat: 闲聊/问候/其他

用户: {msg}
只回答一个英文单词: knowledge / booking / management / chitchat"""
        resp = await model([
            SystemMsg(name="system",
                      content=[TextBlock(text="你是意图分类器。")]),
            UserMsg(name="user", content=[TextBlock(text=prompt)]),
        ])
        text = ""
        if hasattr(resp, "content") and resp.content:
            for blk in resp.content:
                if hasattr(blk, "text"):
                    text += blk.text
        result = text.strip().lower()
        if "management" in result:
            return "management"
        if "booking" in result:
            return "booking"
        if "chitchat" in result:
            return "chitchat"
        return "knowledge"
    except Exception as e:
        logger.warning("LLM 意图分类失败: %s, 降级为 knowledge", e)
        return "knowledge"


async def classify_booking_sub(message: str) -> str:
    """细分 booking intent。

    Returns:
        "view_order" | "continue_edit" | "new_booking"
    """
    from app.core.model_factory import get_model
    from agentscope.message import TextBlock, UserMsg, SystemMsg
    try:
        model = get_model("chat")
        prompt = f"""判断用户消息属于以下三类之一：
- view_order: 用户想看/了解自己当前订单状态（"我的订单""看看""现在的状态"）
- continue_edit: 用户想继续填写/接着上次的订单（"继续""接着填""帮我继续"）
- new_booking: 用户要新开始预约（其他情况，如"我要预约""明天10点..."）

用户: {message}
只回答一个英文单词: view_order / continue_edit / new_booking"""
        resp = await model([
            SystemMsg(name="system",
                      content=[TextBlock(text="你是意图分类器。")]),
            UserMsg(name="user", content=[TextBlock(text=prompt)]),
        ])
        text = ""
        if hasattr(resp, "content") and resp.content:
            for blk in resp.content:
                if hasattr(blk, "text"):
                    text += blk.text
        result = text.strip().lower()
        if "view" in result:
            return "view_order"
        if "continue" in result:
            return "continue_edit"
        return "new_booking"
    except Exception as e:
        logger.warning("sub-intent 分类失败: %s", e)
        return "new_booking"
