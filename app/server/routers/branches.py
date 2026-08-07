# -*- coding: utf-8 -*-
"""分店管理路由：列出可用分店，后台增删改。

公开接口：
- GET /api/branches → 列出所有营业分店 → 给用户端选分店用

管理员接口（需要店家权限）：
- POST /api/admin/branches → 新增
- PATCH /api/admin/branches/{id} → 修改
- DELETE /api/admin/branches/{id} → 下架
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, require_staff
from app.db.models import Branch
from app.db.session import get_session
from app.schemas.branch import BranchPublic, BranchCreate, BranchUpdate

router = APIRouter(prefix="/api", tags=["分店目录"])


@router.get("/branches", summary="列出营业分店")
async def list_branches(
    session: Annotated[AsyncSession, Depends(get_session)],
    only_active: bool = True,
) -> list[BranchPublic]:
    """列出所有营业分店（用户端选预约）。

    - only_active=true → 只返回正在营业的
    """
    stmt = select(Branch)
    if only_active:
        stmt = stmt.where(Branch.is_active == True)
    stmt = stmt.order_by(Branch.id)

    result = await session.execute(stmt)
    branches = result.scalars().all()

    return [BranchPublic.model_validate(b) for b in branches]


@router.post("/admin/branches", summary="新增分店", response_model=BranchPublic)
async def create_branch(
    body: BranchCreate,
    _: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BranchPublic:
    """店家新增分店。"""
    branch = Branch(**body.model_dump())
    session.add(branch)
    await session.commit()
    await session.refresh(branch)
    return BranchPublic.model_validate(branch)


@router.patch("/admin/branches/{branch_id}", summary="修改分店信息", response_model=BranchPublic)
async def update_branch(
    branch_id: int,
    body: BranchUpdate,
    _: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BranchPublic:
    """修改分店信息。"""
    branch = await session.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到ID为{branch_id}的分店",
        )
    # 只更新提供了的字段
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(branch, key):
            setattr(branch, key, value)
    await session.commit()
    await session.refresh(branch)
    return BranchPublic.model_validate(branch)


@router.delete("/admin/branches/{branch_id}", summary="下架分店")
async def delete_branch(
    branch_id: int,
    _: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """下架分店（软删除：is_active=False）。"""
    branch = await session.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到ID为{branch_id}的分店",
        )
    branch.is_active = False
    await session.commit()
    return {"status": "ok", "message": f"已下架分店 {branch.name}"}


@router.get("/branches/nearby", summary="按距离查找最近分店")
async def list_branches_nearby(
    session: Annotated[AsyncSession, Depends(get_session)],
    lat: float = Query(..., ge=-90, le=90, description="用户纬度"),
    lng: float = Query(..., ge=-180, le=180, description="用户经度"),
    only_active: bool = True,
) -> list[BranchPublic]:
    """按距离从近到远返回分店（用户端选预约用）。

    - 使用 Haversine 公式计算球面距离
    - 距离单位：米
    - 如果分店没经纬度，按 ID 顺序排后面
    """
    import math

    def haversine(lat1, lon1, lat2, lon2):
        R = 6371000  # 地球半径 (米)
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return 2 * R * math.asin(math.sqrt(a))

    stmt = select(Branch)
    if only_active:
        stmt = stmt.where(Branch.is_active == True)
    result = await session.execute(stmt)
    branches = list(result.scalars().all())

    # 按距离排序
    def distance(b):
        if b.latitude is None or b.longitude is None:
            return float("inf")
        return haversine(lat, lng, float(b.latitude), float(b.longitude))

    branches.sort(key=distance)
    return [BranchPublic.model_validate(b) for b in branches]
