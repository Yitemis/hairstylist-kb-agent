# -*- coding: utf-8 -*-
"""订单的 Pydantic 模型。"""
from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, Field, field_validator


class OrderCreate(BaseModel):
    """直接下单（非对话场景）请求体。"""

    branch_id: int | None = None
    service_id: int | None = None
    service_type: str = Field(..., min_length=1, max_length=100)
    stylist_id: int = Field(..., gt=0)
    appointment_date: date
    appointment_time: time
    duration_minutes: int | None = None
    total_price: float | None = None
    customer_phone: str = Field(..., min_length=7, max_length=20)
    customer_name: str | None = Field(None, max_length=50)
    address: str | None = Field(None, max_length=500)
    note: str | None = None
    service_details: str | None = None


class OrderStatusUpdate(BaseModel):
    """店家更新订单状态。"""

    status: str = Field(..., pattern="^(pending|confirmed|completed|cancelled)$")
    note: str | None = None


class OrderPublic(BaseModel):
    """订单对外信息（含关联信息扁平化）。"""

    id: int
    order_no: str
    user_id: int
    branch_id: int | None = None
    branch_name: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    stylist_id: int | None = None
    stylist_name: str | None = None
    service_id: int | None = None
    service_type: str | None = None
    service_details: str | None = None
    appointment_date: date | None = None
    appointment_time: time | None = None
    end_time: time | None = None
    duration_minutes: int | None = None
    total_price: float | None = None
    address: str | None = None
    note: str | None = None
    status: str
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("conversation_history", mode="before")
    @classmethod
    def _parse_history(cls, v: Any) -> list[dict[str, Any]]:
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return []


class OrderListItem(BaseModel):
    """订单列表项（精简字段，加速列表渲染）。"""

    id: int
    order_no: str
    branch_id: int | None = None
    branch_name: str | None = None
    stylist_id: int | None = None
    stylist_name: str | None = None
    service_type: str | None = None
    appointment_date: date | None = None
    appointment_time: time | None = None
    end_time: time | None = None
    total_price: float | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
