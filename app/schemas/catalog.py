# -*- coding: utf-8 -*-
"""发型师 / 服务项目 的 Pydantic 模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

import json


class StylistPublic(BaseModel):
    """发型师对外信息。"""

    id: int
    branch_id: int | None = None
    name: str
    avatar: str | None = None
    specialties: list[str] = Field(default_factory=list)
    description: str | None = None
    max_daily_hours: int = 8
    is_active: bool = True

    model_config = {"from_attributes": True}

    @field_validator("specialties", mode="before")
    @classmethod
    def _parse_specialties(cls, v: Any) -> list[str]:
        """DB 里存的是 JSON 字符串，这里反序列化。"""
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


class ServicePublic(BaseModel):
    """服务项目对外信息。"""

    id: int
    name: str
    category: str
    duration_minutes: int
    price: float | None = None
    description: str | None = None
    is_active: bool = True

    model_config = {"from_attributes": True}
