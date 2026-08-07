# -*- coding: utf-8 -*-
"""订单管理路由：用户端创建/查询/取消；店家端改状态。"""
from __future__ import annotations

import random
from typing import Annotated
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.deps import CurrentUser, get_current_user, require_staff, require_user
from app.core.middleware_idempotency import idempotent
from app.db.models import Order, Stylist, Service
from app.db.session import get_session
from app.schemas.order import (
    OrderCreate,
    OrderListItem,
    OrderPublic,
    OrderStatusUpdate,
)

router = APIRouter(prefix="/api", tags=["订单管理"])


def _generate_order_no() -> str:
    """生成订单号：YYMMDD + 6位随机。"""
    prefix = datetime.now().strftime("%y%m%d")
    suffix = str(random.randint(100000, 999999))
    return f"{prefix}{suffix}"


@router.get("/orders", summary="获取当前用户订单列表", response_model=list[OrderListItem])
async def list_my_orders(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status: str | None = Query(None, description="按状态过滤"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[OrderListItem]:
    """当前登录用户自己的订单列表，按创建时间倒序。"""
    stmt = (
        select(
            Order.id,
            Order.order_no,
            Order.branch_id,
            Order.stylist_id,
            Order.service_type,
            Order.appointment_date,
            Order.appointment_time,
            Order.end_time,
            Order.total_price,
            Order.status,
            Order.created_at,
            Stylist.name.label("stylist_name"),
        )
        .outerjoin(Order.stylist)
        .where(Order.user_id == current.id)
    )
    if status is not None:
        stmt = stmt.where(Order.status == status)
    stmt = stmt.order_by(Order.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(stmt)
    rows = result.all()

    return [OrderListItem(**row._mapping) for row in rows]


@router.get("/orders/{order_id}", summary="获取订单详情", response_model=OrderPublic)
async def get_order_detail(
    order_id: int,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderPublic:
    """获取单个订单详情，自己才能看自己的。"""
    stmt = (
        select(Order)
        .options(joinedload(Order.stylist))
        .where(Order.id == order_id, Order.user_id == current.id)
    )
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到该订单，或你无权限查看",
        )
    return OrderPublic(
        id=order.id,
        order_no=order.order_no,
        user_id=order.user_id,
        branch_id=order.branch_id,
        branch_name=None,
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        stylist_id=order.stylist_id,
        stylist_name=order.stylist.name if order.stylist else None,
        service_id=order.service_id,
        service_type=order.service_type,
        service_details=order.service_details,
        appointment_date=order.appointment_date,
        appointment_time=order.appointment_time,
        end_time=order.end_time,
        duration_minutes=order.duration_minutes,
        total_price=order.total_price,
        address=order.address,
        note=order.note,
        status=order.status,
        conversation_history=order.conversation_history,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


@router.post("/orders", summary="创建订单（幂等）", response_model=OrderPublic)
@idempotent("create_order")
async def create_order(
    body: OrderCreate,
    current: Annotated[CurrentUser, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderPublic:
    """直接创建订单（非对话场景也能创建）。"""
    # 校验发型师存在且可用
    if body.stylist_id is not None:
        stylist = await session.get(Stylist, body.stylist_id)
        if stylist is None or not stylist.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="所选发型师不存在或已下架",
            )

    # 校验服务项目
    duration_minutes = body.duration_minutes
    total_price = body.total_price
    if body.service_id is not None:
        service = await session.get(Service, body.service_id)
        if service is None or not service.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="所选服务项目不存在或已下架",
            )
        # 自动从服务项填充
        if duration_minutes is None:
            duration_minutes = service.duration_minutes
        if total_price is None and service.price is not None:
            total_price = float(service.price)

    # 计算 end_time
    end_time = None
    if body.appointment_time and duration_minutes:
        dt = datetime.combine(body.appointment_date, body.appointment_time)
        end_time = (dt + timedelta(minutes=duration_minutes)).time()

    order = Order(
        order_no=_generate_order_no(),
        user_id=current.id,
        branch_id=body.branch_id,
        stylist_id=body.stylist_id,
        service_id=body.service_id,
        service_type=body.service_type,
        service_details=body.service_details,
        appointment_date=body.appointment_date,
        appointment_time=body.appointment_time,
        duration_minutes=duration_minutes,
        end_time=end_time,
        total_price=total_price,
        customer_phone=body.customer_phone,
        customer_name=body.customer_name,
        address=body.address,
        note=body.note,
        status="pending",
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)

    return await admin_get_order_detail(order.id, current, session)


@router.patch("/admin/orders/{order_id}/status", summary="店家更新订单状态")
async def update_order_status(
    order_id: int,
    body: OrderStatusUpdate,
    current: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """店家更新订单状态（confirm / complete / cancel）。"""
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到该订单",
        )
    order.status = body.status
    if body.note:
        order.note = (order.note or "") + f"\n[{datetime.now().isoformat()}] {body.note}"
    await session.commit()
    return {"status": "ok", "new_status": body.status}


@router.get("/admin/orders", summary="店家获取所有订单", response_model=list[OrderListItem])
async def admin_list_orders(
    current: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status: str | None = Query(None, description="按状态过滤"),
) -> list[OrderListItem]:
    """店家查看所有订单，可按状态过滤。"""
    stmt = (
        select(
            Order.id,
            Order.order_no,
            Order.branch_id,
            Order.stylist_id,
            Order.service_type,
            Order.appointment_date,
            Order.appointment_time,
            Order.end_time,
            Order.total_price,
            Order.status,
            Order.created_at,
            Stylist.name.label("stylist_name"),
        )
        .outerjoin(Order.stylist)
    )
    if status is not None:
        stmt = stmt.where(Order.status == status)
    stmt = stmt.order_by(Order.created_at.desc()).limit(100)

    result = await session.execute(stmt)
    rows = result.all()
    return [OrderListItem(**row._mapping) for row in rows]


@router.get("/admin/orders/{order_id}", summary="店家获取订单详情", response_model=OrderPublic)
async def admin_get_order_detail(
    order_id: int,
    current: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderPublic:
    """店家查看任意订单详情。"""
    stmt = (
        select(Order)
        .options(joinedload(Order.stylist))
        .where(Order.id == order_id)
    )
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到该订单",
        )
    return OrderPublic(
        id=order.id,
        order_no=order.order_no,
        user_id=order.user_id,
        branch_id=order.branch_id,
        branch_name=None,
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        stylist_id=order.stylist_id,
        stylist_name=order.stylist.name if order.stylist else None,
        service_id=order.service_id,
        service_type=order.service_type,
        service_details=order.service_details,
        appointment_date=order.appointment_date,
        appointment_time=order.appointment_time,
        end_time=order.end_time,
        duration_minutes=order.duration_minutes,
        total_price=order.total_price,
        address=order.address,
        note=order.note,
        status=order.status,
        conversation_history=order.conversation_history,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


@router.post("/orders/{order_id}/cancel", summary="用户取消预约", response_model=dict)
async def cancel_my_order(
    order_id: int,
    current: Annotated[CurrentUser, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """用户取消自己未完成的订单。"""
    stmt = select(Order).where(Order.id == order_id, Order.user_id == current.id)
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
       raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到该订单，或你无权限取消",
        )
    if order.status in ("completed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"订单已是{order.status}状态，无法取消",
        )
    order.status = "cancelled"
    await session.commit()
    return {"status": "ok", "message": "已取消预约", "order_id": order_id}


@router.post("/admin/orders/{order_id}/status", summary="店家更新订单状态")
async def admin_update_order_status(
    order_id: int,
    body: dict,  # {"new_status": "confirmed", "note": "..."}
    current: Annotated[CurrentUser, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """状态机: draft -> pending -> confirmed -> done / cancelled.

    合法转换:
      - draft -> pending (草稿已确认)
      - draft -> cancelled (直接取消草稿)
      - pending -> confirmed (店家确认)
      - pending -> cancelled (店家拒绝)
      - confirmed -> done (完成服务)
      - confirmed -> cancelled (店家取消)
    """
    from app.db.models import Order as OrderModel

    new_status = body.get("new_status", "").strip()
    note = body.get("note", "").strip() or None

    ALLOWED = {
        "draft":     ["pending", "cancelled"],
        "pending":   ["confirmed", "cancelled"],
        "confirmed": ["done", "cancelled"],
        "done":      [],
        "cancelled": [],
    }
    VALID_STATUSES = {"draft", "pending", "confirmed", "done", "cancelled"}

    if new_status not in VALID_STATUSES:
        raise HTTPException(400, f"无效状态: {new_status}")

    order = await session.get(OrderModel, order_id)
    if order is None:
        raise HTTPException(404, "订单不存在")

    if new_status not in ALLOWED.get(order.status, []):
        raise HTTPException(400, f"订单当前状态 {order.status} 不能转 {new_status}")

    order.status = new_status
    await session.commit()
    await session.refresh(order)
    return {
        "status": "ok",
        "order_id": order_id,
        "old_status": order.status,
        "new_status": new_status,
        "note": note,
    }
