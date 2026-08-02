# -*- coding: utf-8 -*-
"""Pydantic 请求/响应模型。"""
from datetime import datetime
from pydantic import BaseModel


class ChatMessagePublic(BaseModel):
    """对话消息对外信息。"""
    id: int
    user_id: int
    role: str
    content: str
    order_id: int | None = None
    mode: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatHistoryResponse(BaseModel):
    """对话历史响应。"""
    messages: list[ChatMessagePublic]
    total: int


class ChatSessionCreate(BaseModel):
    """创建会话请求。"""
    session_id: str
    title: str | None = None
    state_json: str | None = None
    pending_order_id: int | None = None


class ChatSessionPublic(BaseModel):
    """会话对外信息。"""
    id: int
    session_id: str
    user_id: int
    title: str | None = None
    state_json: str | None = None
    pending_order_id: int | None = None
    interrupted: bool = False
    last_iter: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
