# -*- coding: utf-8 -*-
"""服务项目路由：列出所有服务，后台增删改。

公开接口：
- GET /api/services → 列出所有可用（is_active）服务 → 给推荐用

管理员接口：
- POST /api/services → 新增
- PATCH /api/services/{id} → 修改
- DELETE /api/services/{id} → 下架
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, require_staff
from app.db.models import Service
from app.db.session import get_session
from app.schemas.catalog import ServicePublic

router = APIRouter(prefix="/api", tags=["服务项目目录"])


@router.get("/services", summary="列出可用服务项目")
async def list_services(
    session: Annotated[AsyncSession, Depends(get_session)],
    category: str | None = None,
    only_active: bool = True,
) -> list[ServicePublic]:
    """列出所有可用的服务项目。

    可选按 category 过滤。
    """
    stmt = select(Service)
    if only_active:
        stmt = stmt.where(Service.is_active == True)
    if category is not None:
        stmt = stmt.where(Service.category == category)
    stmt = stmt.order_by(Service.category, Service.id)

    result = await session.execute(stmt)
    services = result.scalars().all()

    return [ServicePublic.model_validate(s) for s in services]


@router.post("/services", summary="新增服务项目", response_model=ServicePublic)
async def create_service(
    body: dict,
    _: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ServicePublic:
    """店家新增服务项目。"""
    service = Service(**body)
    session.add(service)
    await session.commit()
    await session.refresh(service)
    return ServicePublic.model_validate(service)


@router.patch("/services/{service_id}", summary="修改服务项目", response_model=ServicePublic)
async def update_service(
    service_id: int,
    body: dict,
    _: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ServicePublic:
    """修改服务项目信息（价格、时长、分类、是否上架）。"""
    service = await session.get(Service, service_id)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到ID为{service_id}的服务项目",
        )
    for key, value in body.items():
        if hasattr(service, key):
            setattr(service, key, value)
    await session.commit()
    await session.refresh(service)
    return ServicePublic.model_validate(service)


@router.delete("/services/{service_id}", summary="下架服务项目")
async def delete_service(
    service_id: int,
    _: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """下架服务项目（软删除：is_active=False）。"""
    service = await session.get(Service, service_id)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到ID为{service_id}的服务项目",
        )
    service.is_active = False
    await session.commit()
    return {"status": "ok", "message": f"已下架服务 {service.name}"}
