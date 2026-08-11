# -*- coding: utf-8 -*-
"""订单工具集：list_branches/list_stylists/create_draft_order 等。"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, time
from typing import Optional

from sqlalchemy import select, func

from app.db.models import Order, Service, Stylist, Branch
from app.db.session import async_session_maker


async def create_draft_order(user_id: int) -> str:
    """创建一个草稿订单（进行中），绑定当前登录用户，供后续填写信息。

    当用户开始预约新单，第一步必须调用此工具。返回草稿订单 ID。

    Args:
        user_id: 当前登录用户的 ID（从对话上下文获取）
    """
    async with async_session_maker() as session:
        # P2-1: 统一调用 utils.generate_order_no（与 orders.py 共一份实现）
        from app.utils.order_utils import generate_order_no
        order_no = generate_order_no()

        order = Order(
            order_no=order_no,
            user_id=user_id,
            status="draft",  # draft → 草稿，还没确认
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return f"已创建新草稿订单，订单编号：{order.order_no}，ID：{order.id}。请开始填写项目、发型师、时间等信息。"


async def update_order_fields(
    user_id: int,
    order_id: int,
    branch_id: int | None = None,
    service_id: int | None = None,
    service_type: str | None = None,
    service_details: str | None = None,
    stylist_id: int | None = None,
    appointment_date: str | None = None,  # 格式 YYYY-MM-DD
    appointment_time: str | None = None,  # 格式 HH:MM
    duration_minutes: int | None = None,
    total_price: float | None = None,
    customer_phone: str | None = None,
    customer_name: str | None = None,
    address: str | None = None,
    note: str | None = None,
) -> str:
    """增量更新草稿订单的字段，每次可以更新一个或多个字段。

    调用时机：用户说了新信息（选了分店、选了发型师、定了时间、给了电话），立刻更新。
    如果选了具体 service_id，自动填充时长和价格。
    返回更新成功后的订单摘要，Agent 可以直接展示给用户。

    Args:
        user_id: 当前登录用户的 ID
        order_id: 草稿订单ID（来自 create_draft_order 返回）
        branch_id: 预约分店ID
        service_id: 选中服务项目ID
        service_type: 服务项目名称（如"热烫""染发""剪发"）
        service_details: 服务细节备注（比如"齐肩发""遮白发"）
        stylist_id: 选中的发型师ID
        appointment_date: 预约日期，格式必须是 YYYY-MM-DD（如 2026-08-01）
        appointment_time: 预约时间段，格式必须是 HH:MM（如 10:00）
        duration_minutes: 服务时长（分钟，选service_id后自动填充）
        total_price: 订单总价（选service_id后自动填充）
        customer_phone: 用户联系电话
        customer_name: 用户姓名
        address: 店铺地址备注
        note: 用户额外备注
    """
    async with async_session_maker() as session:
        # 权限校验：只能改自己的订单
        stmt = select(Order).where(Order.id == order_id, Order.user_id == user_id)
        result = await session.execute(stmt)
        order = result.scalar_one_or_none()
        if order is None:
            return f"错误：找不到订单 {order_id}，或你无权限修改。"

        # 增量更新
        updates = {
            "branch_id": branch_id,
            "service_id": service_id,
            "service_type": service_type,
            "service_details": service_details,
            "stylist_id": stylist_id,
            "duration_minutes": duration_minutes,
            "total_price": total_price,
            "customer_phone": customer_phone,
            "customer_name": customer_name,
            "address": address,
            "note": note,
        }

        # 如果选了 service_id，自动拉取时长和价格
        if service_id is not None:
            service_stmt = select(Service).where(Service.id == service_id, Service.is_active == True)
            service_result = await session.execute(service_stmt)
            service = service_result.scalar_one_or_none()
            if service:
                updates["duration_minutes"] = service.duration_minutes
                updates["total_price"] = float(service.price) if service.price else None
                if not service_type:
                    updates["service_type"] = service.name

        # 日期时间特殊处理（解析一下方便DB存）
        if appointment_date:
            try:
                updates["appointment_date"] = date.fromisoformat(appointment_date)
            except ValueError:
                return f"日期格式错误：{appointment_date}，请使用 YYYY-MM-DD 格式（例如 2026-08-01）"
        if appointment_time:
            try:
                dt = datetime.strptime(appointment_time, "%H:%M")
                updates["appointment_time"] = dt.time()
                # 如果有了时长，自动计算 end_time
                if updates.get("duration_minutes") or order.duration_minutes:
                    dur = updates.get("duration_minutes") or order.duration_minutes
                    end_dt = dt + timedelta(minutes=dur)
                    updates["end_time"] = end_dt.time()
            except ValueError:
                return f"时间格式错误：{appointment_time}，请使用 HH:MM 格式（例如 10:00）"

        for k, v in updates.items():
            if v is not None:
                setattr(order, k, v)

        await session.commit()
        await session.refresh(order)

        # 预加载关联数据
        if order.branch_id:
            await session.refresh(order, ["branch"])
        if order.stylist_id:
            await session.refresh(order, ["stylist"])

        # 生成摘要给用户看
        lines = ["✅ 订单更新成功。当前订单："]
        lines.append(f"- 编号：{order.order_no}")
        if order.branch and hasattr(order, 'branch') and order.branch:
            lines.append(f"- 分店：{order.branch.name}")
        if order.service_type:
            lines.append(f"- 项目：{order.service_type}")
        if order.stylist_id and hasattr(order, 'stylist') and order.stylist:
            lines.append(f"- 发型师：{order.stylist.name}")
        elif order.stylist_id:
            lines.append(f"- 发型师 ID：{order.stylist_id}")
        if order.appointment_date:
            lines.append(f"- 日期：{order.appointment_date.isoformat()}")
        if order.appointment_time:
            if order.end_time:
                lines.append(f"- 时间：{order.appointment_time.strftime('%H:%M')} - {order.end_time.strftime('%H:%M')}")
            else:
                lines.append(f"- 时间：{order.appointment_time.strftime('%H:%M')}")
        if order.duration_minutes:
            lines.append(f"- 时长：{order.duration_minutes} 分钟")
        if order.total_price:
            lines.append(f"- 总价：{order.total_price:.2f} 元")
        if order.customer_phone:
            lines.append(f"- 电话：{order.customer_phone}")
        if order.note:
            lines.append(f"- 备注：{order.note}")
        lines.append("\n状态：草稿（未确认），所有信息填完后调用 confirm_order 确认下单。")
        return "\n".join(lines)


async def confirm_order(user_id: int, order_id: int) -> str:
    """用户确认所有信息无误后，调用此工具将订单状态改为 pending（待店家确认）。

    会做三重检查：1. 门店当日容量 2. 发型师当日容量 3. 时间段冲突，确保不超约。
    确认后订单出现在店家后台，可供店家处理。
    返回最终订单详情文本。

    Args:
        user_id: 当前登录用户的 ID
        order_id: 要确认的草稿订单ID
    """
    # P1-9: PermissionEngine 接入（危险操作需 HITL 确认）
    try:
        from app.core.permission import engine, PermissionRequest, PermissionDecision
        req = PermissionRequest(
            user_id=user_id,
            tool_name="confirm_order",
            tool_args={"order_id": order_id},
        )
        result = await engine.evaluate(req)
        if result.decision == PermissionDecision.DENIED:
            return f"权限拒绝：{result.reason or '该操作被禁止'}"
        if result.decision == PermissionDecision.ASKING:
            # P1-9 修复: 闭环 ASKING - 创建 ask_id，前端可调 /api/permission/resolve
            ask_id = engine.create_pending_ask(req, result)
            return (
                f"⚠️ [需要确认] {result.reason or '此操作需要您确认'}。\n"
                f"ask_id={ask_id}\n"
                f"请确认后再次提交订单。"
            )
    except ImportError:
        pass  # 权限模块未就绪时降级

    async with async_session_maker() as session:
        # 权限校验：只能确认自己的订单
        stmt = select(Order).where(Order.id == order_id, Order.user_id == user_id)
        result = await session.execute(stmt)
        order = result.scalar_one_or_none()
        if order is None:
            return f"错误：找不到订单 {order_id}，或你无权限确认。"

        # 必填字段校验
        required = [
            (order.branch_id, "分店"),
            (order.service_type, "服务项目"),
            (order.stylist_id, "发型师"),
            (order.appointment_date, "预约日期"),
            (order.appointment_time, "预约时间"),
            (order.duration_minutes, "服务时长"),
            (order.customer_phone, "联系电话"),
        ]
        missing = [name for (val, name) in required if val is None]
        if missing:
            return f"还有必填信息未填写：{', '.join(missing)}，请补充完整再确认。"

        # ========== 三重检查开始 ==========
        # 1. 检查门店今日容量
        if order.branch_id:
            branch_stmt = select(Branch).where(Branch.id == order.branch_id)
            branch_result = await session.execute(branch_stmt)
            branch = branch_result.scalar_one_or_none()
            if branch:
                today = order.appointment_date
                # 统计今日已确认订单数
                count_stmt = select(func.count(Order.id)).where(
                    Order.branch_id == branch.id,
                    Order.appointment_date == today,
                    Order.status == "confirmed",
                )
                count_result = await session.execute(count_stmt)
                booked_count = count_result.scalar_one() or 0
                if branch.max_daily_appointments and branch.max_daily_appointments > 0:
                    if booked_count >= branch.max_daily_appointments:
                        return f"❌ 预约失败：{branch.name}今日预约已满，请选择其他分店或日期。"

        # 2. 检查发型师今日容量
        if order.stylist_id:
            stylist_stmt = select(Stylist).where(Stylist.id == order.stylist_id)
            stylist_result = await session.execute(stylist_stmt)
            stylist = stylist_result.scalar_one_or_none()
            if stylist:
                today = order.appointment_date
                # 统计今日已确认订单总时长
                duration_stmt = select(func.sum(Order.duration_minutes)).where(
                    Order.stylist_id == stylist.id,
                    Order.appointment_date == today,
                    Order.status == "confirmed",
                )
                duration_result = await session.execute(duration_stmt)
                booked_minutes = duration_result.scalar_one() or 0
                max_minutes = stylist.max_daily_hours * 60
                if booked_minutes + (order.duration_minutes or 0) > max_minutes:
                    return f"❌ 预约失败：{stylist.name}今日预约时长已满，请选择其他发型师或日期。"

        # 3. 检查时间段重叠冲突（同一发型师同一天）
        if order.stylist_id and order.appointment_date and order.appointment_time and order.duration_minutes:
            # 计算结束时间
            start_dt = datetime.combine(order.appointment_date, order.appointment_time)
            end_dt = start_dt + timedelta(minutes=order.duration_minutes)
            end_time = end_dt.time()
            # 更新订单 end_time
            order.end_time = end_time

            # 查询该发型师同一天所有已确认/待确认订单，看是否重叠
            # 重叠条件: 新开始 < 已有结束 AND 新结束 > 已有开始
            conflict_stmt = select(Order).where(
                Order.stylist_id == order.stylist_id,
                Order.appointment_date == order.appointment_date,
                Order.status.in_(["pending", "confirmed"]),
                Order.id != order.id,
                # 重叠条件 SQL 版本
                order.appointment_time < Order.end_time,
                end_time > Order.appointment_time,
            )
            conflict_result = await session.execute(conflict_stmt)
            conflict_order = conflict_result.scalar_one_or_none()
            if conflict_order:
                return (f"❌ 预约失败：该发型师此时间段已有预约冲突 "
                        f"（已有订单 {conflict_order.order_no} 预约 {conflict_order.appointment_time} - {conflict_order.end_time}），"
                        f"请换一个时间段或换一位发型师。")

        # ========== 三重检查通过 ==========
        order.status = "pending"
        await session.commit()
        await session.refresh(order)

        # 预加载关联数据
        if order.branch_id:
            await session.refresh(order, ["branch"])
        if order.stylist_id:
            await session.refresh(order, ["stylist"])

        # 生成最终确认信息
        lines = [
            "🎉 预约成功！订单已提交，等待店家最终确认。",
            "",
            f"订单编号：{order.order_no}",
        ]
        if order.branch and hasattr(order, 'branch') and order.branch:
            lines.append(f"分店：{order.branch.name}")
        lines.append(f"服务项目：{order.service_type}")
        if order.stylist_id and hasattr(order, 'stylist') and order.stylist:
            lines.append(f"发型师：{order.stylist.name}")
        if order.appointment_date:
            lines.append(f"预约日期：{order.appointment_date.isoformat()}")
        if order.appointment_time and order.end_time:
            lines.append(f"时间：{order.appointment_time.strftime('%H:%M')} - {order.end_time.strftime('%H:%M')}")
        if order.total_price:
            lines.append(f"总价：{order.total_price:.2f} 元")
        if order.customer_phone:
            lines.append(f"联系电话：{order.customer_phone}")
        if order.note:
            lines.append(f"备注：{order.note}")
        lines.append("\n店家会尽快联系你确认，请保持手机畅通。")
        return "\n".join(lines)


async def list_branches(
    user_id: int,
    user_latitude: float | None = None,
    user_longitude: float | None = None,
) -> str:
    """列出所有营业分店，按距离用户位置从近到远排序，标注今日是否约满。

    用户选择分店时调用，如果用户提供了位置，按距离排序；否则按ID排序。

    Args:
        user_id: 当前登录用户的 ID（占位，鉴权用）
        user_latitude: 用户当前位置纬度（可选，用于排序）
        user_longitude: 用户当前位置经度（可选，用于排序）
    """
    del user_id  # 不需要过滤用户，公开列表
    async with async_session_maker() as session:
        # 获取所有活跃分店
        stmt = select(Branch).where(Branch.is_active == True).order_by(Branch.id)
        result = await session.execute(stmt)
        branches = result.scalars().all()
        if not branches:
            return "目前暂无营业分店，请稍后再试。"

        # 计算每个分店今日已预约数
        today = date.today()
        branch_data = []
        for branch in branches:
            # 统计今日已确认订单数
            count_stmt = select(func.count(Order.id)).where(
                Order.branch_id == branch.id,
                Order.appointment_date == today,
                Order.status == "confirmed",
            )
            count_result = await session.execute(count_stmt)
            booked_count = count_result.scalar_one() or 0

            # 是否约满
            is_full = False
            if branch.max_daily_appointments and branch.max_daily_appointments > 0:
                is_full = booked_count >= branch.max_daily_appointments

            # 计算距离（如果有用户位置）
            distance = None
            if user_latitude is not None and user_longitude is not None \
               and branch.latitude is not None and branch.longitude is not None:
                # Haversine formula 计算距离（单位公里）
                R = 6371  # Earth radius in km
                dLat = math.radians(branch.latitude - user_latitude)
                dLon = math.radians(branch.longitude - user_longitude)
                a = math.sin(dLat/2)**2 + \
                    math.cos(math.radians(user_latitude)) * \
                    math.cos(math.radians(branch.latitude)) * \
                    math.sin(dLon/2)**2
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                distance = R * c

            branch_data.append({
                "branch": branch,
                "booked_count": booked_count,
                "is_full": is_full,
                "distance": distance,
            })

        # 排序：有距离则按距离，否则按ID
        if user_latitude is not None and user_longitude is not None:
            branch_data.sort(key=lambda x: x["distance"] if x["distance"] is not None else float('inf'))
        # 否则不排序（已经按ID了）

        # 生成输出
        output = "当前营业分店列表：\n\n"
        for item in branch_data:
            b = item["branch"]
            dist_str = f" ({item['distance']:.1f}km)" if item["distance"] is not None else ""
            full_tag = " 🔴 今日约满" if item["is_full"] else ""
            output += f"- 📍 **{b.name}**{dist_str}{full_tag}\n"
            output += f"  地址：{b.address}\n"
            if b.description:
                output += f"  {b.description}\n"
        output += "\n请告诉我你想预约哪家分店，我帮你登记。"
        return output


async def list_stylists(
    user_id: int,
    branch_id: int | None = None,
) -> str:
    """列出指定分店所有可用发型师，标注今日是否约满，供用户选择。

    用户选择发型师时调用，如果指定分店，只列出该分店的发型师。

    Args:
        user_id: 当前登录用户的 ID（占位，鉴权用）
        branch_id: 分店ID（可选，过滤指定分店的发型师）
    """
    del user_id  # 不需要过滤用户，公开列表
    async with async_session_maker() as session:
        # 构建查询：过滤分店 + 只显示活跃
        stmt = select(Stylist).where(Stylist.is_active == True)
        if branch_id is not None:
            stmt = stmt.where(Stylist.branch_id == branch_id)
        stmt = stmt.order_by(Stylist.id)

        result = await session.execute(stmt)
        stylists = result.scalars().all()
        if not stylists:
            return "该分店目前暂无可用发型师，请选择其他分店。"

        # 计算每个发型师今日已预约总时长
        today = date.today()
        stylist_data = []
        for stylist in stylists:
            # 求和今日已确认订单总时长
            duration_stmt = select(func.sum(Order.duration_minutes)).where(
                Order.stylist_id == stylist.id,
                Order.appointment_date == today,
                Order.status == "confirmed",
            )
            duration_result = await session.execute(duration_stmt)
            booked_minutes = duration_result.scalar_one() or 0
            max_minutes = stylist.max_daily_hours * 60
            is_full = booked_minutes >= max_minutes

            stylist_data.append({
                "stylist": stylist,
                "booked_minutes": booked_minutes,
                "is_full": is_full,
            })

        # 生成输出
        output = "当前可预约发型师列表：\n\n"
        for item in stylist_data:
            s = item["stylist"]
            # 解析 specialties JSON
            specialties: list[str] = []
            if s.specialties:
                try:
                    specialties = json.loads(s.specialties)
                except json.JSONDecodeError:
                    specialties = [s.specialties]
            spec_str = "，".join(specialties)
            desc = f"（{s.description}）" if s.description else ""
            full_tag = " 🔴 今日已约满" if item["is_full"] else ""
            output += f"- **{s.name}** {desc}{full_tag}\n  擅长：{spec_str}\n"
        output += "\n请告诉我你想选哪位发型师，我帮你更新订单。"
        return output


async def recommend_services(user_id: int, user_description: str) -> str:
    """根据用户描述推荐适合的服务项目。

    用户说"我想染发但不知道选哪种"或"推荐一个适合我的项目"，调用此工具。
    返回推荐列表，带价格和时长，Agent 可以直接展示给用户。

    Args:
        user_id: 当前登录用户的 ID
        user_description: 用户需求描述（如"我想染蓝色头发，适合上班族"）
    """
    del user_id  # 不需要过滤用户，公开推荐
    async with async_session_maker() as session:
        stmt = (
            select(Service)
            .where(Service.is_active == True)
            .order_by(Service.category, Service.id)
        )
        result = await session.execute(stmt)
        services = result.scalars().all()
        if not services:
            return "目前暂无上架服务，请稍后再试。"

        output = f"根据你的需求「{user_description}」，为你推荐以下服务：\n\n"
        for s in services:
            price_str = f"{s.price:.2f}元" if s.price else "价格咨询门店"
            output += (
                f"- **{s.name}**（{s.category}）\n"
                f"  时长：{s.duration_minutes}分钟  价格：{price_str}\n"
                f"  {s.description or ''}\n\n"
            )
        output += "你可以告诉我你确定选哪个，我帮你更新到订单里。"
        return output
