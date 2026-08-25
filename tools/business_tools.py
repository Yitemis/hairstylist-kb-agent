# -*- coding: utf-8 -*-
"""业务管理工具 (P0-3)."""
from __future__ import annotations
import json
from datetime import datetime, date, timedelta
from typing import Optional
from sqlalchemy import select, func
from app.db.models import Order, Stylist, Branch, Staff, User, Document
from app.db.session import async_session_maker

def _serialize_order(o):
    return {
        "id": o.id, "order_no": o.order_no,
        "customer_name": o.customer_name, "customer_phone": o.customer_phone,
        "branch_id": o.branch_id, "stylist_id": o.stylist_id,
        "service_type": o.service_type,
        "appointment_date": str(o.appointment_date) if o.appointment_date else None,
        "appointment_time": str(o.appointment_time) if o.appointment_time else None,
        "total_price": float(o.total_price) if o.total_price else None,
        "status": o.status, "note": o.note,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }

async def list_orders(status=None, branch_id=None, phone=None, days=7, limit=20):
    async with async_session_maker() as session:
        since = datetime.now() - timedelta(days=days)
        stmt = select(Order).where(Order.created_at >= since)
        if status: stmt = stmt.where(Order.status == status)
        if branch_id: stmt = stmt.where(Order.branch_id == branch_id)
        if phone: stmt = stmt.where(Order.customer_phone.like(f"%{phone}%"))
        stmt = stmt.order_by(Order.created_at.desc()).limit(min(limit, 100))
        orders = (await session.scalars(stmt)).all()
        branch_map = {}
        stylist_map = {}
        if orders:
            bids = {o.branch_id for o in orders if o.branch_id}
            sids = {o.stylist_id for o in orders if o.stylist_id}
            if bids:
                bm = (await session.execute(select(Branch).where(Branch.id.in_(bids)))).scalars().all()
                branch_map = {b.id: b.name for b in bm}
            if sids:
                sm = (await session.execute(select(Stylist).where(Stylist.id.in_(sids)))).scalars().all()
                stylist_map = {s.id: s.name for s in sm}
        results = []
        for o in orders:
            d = _serialize_order(o)
            d["branch_name"] = branch_map.get(o.branch_id, "?")
            d["stylist_name"] = stylist_map.get(o.stylist_id, "未指定")
            results.append(d)
        return json.dumps({"count": len(results), "filters": {"status": status, "branch_id": branch_id, "phone": phone, "days": days}, "orders": results}, ensure_ascii=False, default=str)

async def get_order_detail(order_id):
    async with async_session_maker() as session:
        from sqlalchemy.orm import joinedload
        stmt = select(Order).options(joinedload(Order.stylist)).where(Order.id == order_id)
        o = (await session.scalars(stmt)).first()
        if not o:
            return json.dumps({"error": f"订单 #{order_id} 不存在"}, ensure_ascii=False)
        d = _serialize_order(o)
        if o.branch_id:
            b = await session.get(Branch, o.branch_id)
            d["branch_name"] = b.name if b else "?"
            d["branch_address"] = b.address if b else None
        if o.stylist:
            d["stylist_name"] = o.stylist.name
        return json.dumps(d, ensure_ascii=False, default=str)

async def update_order_status(order_id, new_status, note=None):
    if new_status not in ("pending", "confirmed", "done", "cancelled"):
        return json.dumps({"error": f"无效状态: {new_status}"}, ensure_ascii=False)
    async with async_session_maker() as session:
        o = await session.get(Order, order_id)
        if not o:
            return json.dumps({"error": f"订单 #{order_id} 不存在"}, ensure_ascii=False)
        old = o.status
        o.status = new_status
        if note:
            o.note = (o.note or "") + f"\\n[{datetime.now().isoformat()}] {note}"
        await session.commit()
        return json.dumps({"status": "ok", "order_id": order_id, "order_no": o.order_no, "old_status": old, "new_status": new_status}, ensure_ascii=False)

async def list_branches():
    async with async_session_maker() as session:
        branches = (await session.scalars(select(Branch).order_by(Branch.id))).all()
        today = date.today()
        today_orders = (await session.scalars(select(Order).where(Order.appointment_date == today, Order.status.in_(["pending", "confirmed"])))).all()
        cnt = {}
        for o in today_orders:
            if o.branch_id: cnt[o.branch_id] = cnt.get(o.branch_id, 0) + 1
        return json.dumps({"count": len(branches), "branches": [{"id": b.id, "name": b.name, "address": b.address, "phone": b.phone, "is_active": b.is_active, "today_pending_count": cnt.get(b.id, 0)} for b in branches]}, ensure_ascii=False, default=str)

async def list_staffs(branch_id=None):
    async with async_session_maker() as session:
        stmt = select(Staff)
        if branch_id: stmt = stmt.where(Staff.branch_id == branch_id)
        staffs = (await session.scalars(stmt.order_by(Staff.id))).all()
        return json.dumps({"count": len(staffs), "staffs": [{"id": s.id, "name": s.name, "phone": s.phone, "branch_id": s.branch_id, "is_active": s.is_active} for s in staffs]}, ensure_ascii=False, default=str)

async def list_users(phone=None, days=30, limit=20):
    async with async_session_maker() as session:
        stmt = select(User)
        if phone: stmt = stmt.where(User.phone.like(f"%{phone}%"))
        users = (await session.scalars(stmt.order_by(User.id.desc()).limit(min(limit, 100)))).all()
        return json.dumps({"count": len(users), "users": [{"id": u.id, "name": u.name, "phone": u.phone, "created_at": u.created_at.isoformat() if u.created_at else None} for u in users]}, ensure_ascii=False, default=str)

async def get_business_stats(days=7):
    async with async_session_maker() as session:
        since = datetime.now() - timedelta(days=days)
        sc = (await session.execute(select(Order.status, func.count(Order.id)).where(Order.created_at >= since).group_by(Order.status))).all()
        sd = {s: c for s, c in sc}
        rev = (await session.scalar(select(func.coalesce(func.sum(Order.total_price), 0)).where(Order.status == "done", Order.created_at >= since))) or 0
        return json.dumps({
            "period_days": days,
            "orders": {"total": sum(sd.values()), "by_status": sd},
            "revenue": float(rev),
            "totals": {
                "documents": (await session.scalar(select(func.count(Document.id)))) or 0,
                "users": (await session.scalar(select(func.count(User.id)))) or 0,
                "staffs": (await session.scalar(select(func.count(Staff.id)))) or 0,
                "branches": (await session.scalar(select(func.count(Branch.id)))) or 0,
            },
        }, ensure_ascii=False, default=str)
