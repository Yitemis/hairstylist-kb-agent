# -*- coding: utf-8 -*-
"""分店 Pydantic 模型。"""
from __future__ import annotations

from pydantic import BaseModel

class BranchPublic(BaseModel):
    """分店对外公开信息。"""

    id: int
    name: str
    address: str
    phone: str | None = None
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    max_daily_appointments: int | None = None
    is_active: bool = True

    model_config = {"from_attributes": True}


class BranchCreate(BaseModel):
    """B端创建分店请求。"""

    name: str
    address: str
    phone: str | None = None
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    max_daily_appointments: int | None = None


class BranchUpdate(BaseModel):
    """B端更新分店请求。"""

    name: str | None = None
    address: str | None = None
    phone: str | None = None
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    max_daily_appointments: int | None = None
    is_active: bool | None = None
