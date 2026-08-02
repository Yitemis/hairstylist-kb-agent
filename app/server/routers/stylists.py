# -*- coding: utf-8 -*-
"""发型师管理路由：列出可用发型师，后台增删改。

公开接口：
- GET /api/stylists → 列出所有可用（is_active）发型师 → 给用户端选发型师用

管理员接口（需要店家权限）：
- POST /api/stylists → 新增
- PATCH /api/stylists/{id} → 修改
- DELETE /api/stylists/{id} → 下架（不是真删，is_active=False）
"""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, require_staff
from app.db.models import Stylist
from app.db.session import get_session
from app.schemas.catalog import StylistPublic

router = APIRouter(prefix="/api", tags=["发型师目录"])


class StylistCreateUpdate(BaseModel):
    """B端创建/更新发型师。"""
    branch_id: int | None = None
    name: str | None = None
    avatar: str | None = None
    specialties: list[str] | None = None
    description: str | None = None
    max_daily_hours: int | None = None
    is_active: bool | None = None


@router.get("/stylists", summary="列出可用发型师")
async def list_stylists(
    session: Annotated[AsyncSession, Depends(get_session)],
    only_active: bool = True,
    branch_id: int | None = None,
) -> list[StylistPublic]:
    """列出所有可用的发型师（用户端选预约）。

    - only_active=true → 只返回在职的
    - branch_id → 只返回该分店的发型师
    """
    stmt = select(Stylist)
    if only_active:
        stmt = stmt.where(Stylist.is_active == True)
    if branch_id is not None:
        stmt = stmt.where(Stylist.branch_id == branch_id)
    stmt = stmt.order_by(Stylist.id)

    result = await session.execute(stmt)
    stylists = result.scalars().all()

    return [StylistPublic.model_validate(s) for s in stylists]


@router.post("/stylists", summary="新增发型师", response_model=StylistPublic)
async def create_stylist(
    body: StylistCreateUpdate,
    _: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StylistPublic:
    """店家新增发型师。"""
    data = body.model_dump(exclude_unset=True)
    if "specialties" in data and isinstance(data["specialties"], list):
        data["specialties"] = json.dumps(data["specialties"], ensure_ascii=False)
    stylist = Stylist(**data)
    session.add(stylist)
    await session.commit()
    await session.refresh(stylist)
    return StylistPublic.model_validate(stylist)


@router.patch("/stylists/{stylist_id}", summary="修改发型师信息", response_model=StylistPublic)
async def update_stylist(
    stylist_id: int,
    body: StylistCreateUpdate,
    _: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StylistPublic:
    """修改发型师信息（包括名称、头像、擅长、简介、是否在职）。"""
    stylist = await session.get(Stylist, stylist_id)
    if stylist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到ID为{stylist_id}的发型师",
        )
    data = body.model_dump(exclude_unset=True)
    if "specialties" in data and isinstance(data["specialties"], list):
        data["specialties"] = json.dumps(data["specialties"], ensure_ascii=False)
    for key, value in data.items():
        if hasattr(stylist, key):
            setattr(stylist, key, value)
    await session.commit()
    await session.refresh(stylist)
    return StylistPublic.model_validate(stylist)


@router.delete("/stylists/{stylist_id}", summary="下架发型师")
async def delete_stylist(
    stylist_id: int,
    _: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """下架发型师（软删除：is_active=False）。"""
    stylist = await session.get(Stylist, stylist_id)
    if stylist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到ID为{stylist_id}的发型师",
        )
    stylist.is_active = False
    await session.commit()
    return {"status": "ok", "message": f"已下架发型师 {stylist.name}"}
