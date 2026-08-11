# -*- coding: utf-8 -*-
"""意图分类 (P1-8 booking sub-intent)。

复用了 booking intent 内的细分（看订单/继续编辑/开始新预约）。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def classify_booking_sub(message: str) -> str:
    """细分 booking intent。

    Returns:
        "view_order" | "continue_edit" | "new_booking"
    """
    from app.core.model_factory import get_model
    from agentscope.message import TextBlock, UserMsg
    try:
        model = get_model("chat")
        prompt = f"""判断用户消息属于以下三类之一：
- view_order: 用户想看/了解自己当前订单状态（"我的订单""看看""现在的状态"）
- continue_edit: 用户想继续填写/接着上次的订单（"继续""接着填""帮我继续"）
- new_booking: 用户要新开始预约（其他情况，如"我要预约""明天10点..."）

用户: {message}
只回答一个英文单词: view_order / continue_edit / new_booking"""
        resp = await model(
            [UserMsg(content=prompt, role="user")],
            system_prompt="你是意图分类器。",
        )
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
