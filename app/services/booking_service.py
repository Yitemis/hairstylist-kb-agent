# -*- coding: utf-8 -*-
"""Booking 业务服务（P0-1 从 api.py 抽出）。

下划线开头的 helper 函数从 api.py 搬过来，api.py 只留端点。
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select

from app.core.tools.order_tools import (
    list_branches, list_stylists, recommend_services,
)
from app.db.models import Order, Branch, Stylist, Service
from app.db.session import async_session_maker

logger = logging.getLogger(__name__)


async def get_branches_dict() -> list[dict]:
    """所有分店 → [{id, name, address, lat, lng}, ...]。"""
    async with async_session_maker() as session:
        rows = (await session.scalars(select(Branch).where(Branch.is_active == True))).all()
        return [
            {"id": b.id, "name": b.name, "address": b.address or "",
             "latitude": b.latitude, "longitude": b.longitude}
            for b in rows
        ]


async def get_stylists_dict() -> list[dict]:
    """所有发型师 → [{id, name, branch_id, is_active}, ...]。"""
    async with async_session_maker() as session:
        rows = (await session.scalars(select(Stylist).where(Stylist.is_active == True))).all()
        return [
            {"id": s.id, "name": s.name, "branch_id": s.branch_id, "is_active": s.is_active}
            for s in rows
        ]


async def get_services_dict() -> list[dict]:
    """所有服务 → [{id, name, price, duration_minutes}, ...]。"""
    async with async_session_maker() as session:
        rows = (await session.scalars(select(Service).where(Service.is_active == True))).all()
        return [
            {"id": sv.id, "name": sv.name, "price": float(sv.price) if sv.price else None,
             "duration_minutes": sv.duration_minutes}
            for sv in rows
        ]


async def get_branch_options() -> list[dict]:
    """分店选项卡 (前端可点)。"""
    return [
        {"type": "branch", "id": b["id"], "title": b["name"], "subtitle": b["address"]}
        for b in await get_branches_dict()
    ]


async def get_stylist_options(branch_id: int) -> list[dict]:
    """P1-8: 指定分店的发型师选项卡。"""
    async with async_session_maker() as session:
        rows = (await session.scalars(
            select(Stylist).where(Stylist.is_active == True, Stylist.branch_id == branch_id)
        )).all()
        result = []
        for s in rows:
            result.append({
                "type": "stylist",
                "id": s.id,
                "title": s.name,
                "subtitle": s.description or "发型师",
                "badge": f"{s.max_daily_hours}h/天" if s.max_daily_hours else None,
            })
        return result


async def get_service_options() -> list[dict]:
    """服务选项卡。"""
    return [
        {"type": "service", "id": sv["id"], "title": sv["name"],
         "subtitle": f"¥{sv['price']:.0f} · {sv['duration_minutes']}分钟" if sv.get("price") else sv["name"]}
        for sv in await get_services_dict()
    ]


async def get_latest_draft_id(user_id: int) -> int | None:
    """最新 draft 订单 ID。"""
    async with async_session_maker() as session:
        stmt = (
            select(Order)
            .where(Order.user_id == user_id, Order.status == "draft")
            .order_by(Order.id.desc())
            .limit(1)
        )
        o = (await session.scalars(stmt)).first()
        return o.id if o else None


async def show_current_order_text(order_id: int) -> str:
    """格式化显示当前订单（前端友好）。"""
    async with async_session_maker() as session:
        order = await session.get(Order, order_id)
        if order is None:
            return "订单不存在"
        if order.branch_id:
            await session.refresh(order, ["branch"])
        if order.stylist_id:
            await session.refresh(order, ["stylist"])
        lines = ["📋 你当前订单："]
        lines.append(f"- 编号：{order.order_no}")
        if order.branch:
            lines.append(f"- 分店：{order.branch.name}")
        if order.stylist:
            lines.append(f"- 发型师：{order.stylist.name}")
        if order.service_id:
            sv = await session.get(Service, order.service_id)
            if sv:
                lines.append(f"- 服务：{sv.name}")
        if order.appointment_date:
            lines.append(f"- 日期：{order.appointment_date} {order.appointment_time or ''}")
        if order.customer_phone:
            lines.append(f"- 电话：{order.customer_phone}")
        if order.customer_name:
            lines.append(f"- 姓名：{order.customer_name}")
        return "\n".join(lines)


async def handle_booking_flow(message: str, user_id: int, session_id: str):
    """P1-8: 让 Booking Agent 接管整个预约流程（6 个工具真被 Agent 调）。

    之前: 280 行手写 if-else + regex（拆自 api.py）
    现在: 全部走 Booking Agent (含 6 个工具)，由 Agent 自主决定调哪个。
    """
    from app.core.booking_agent_factory import get_booking_agent
    from app.core.tool_registry import registry
    from app.db.session import async_session_maker
    from app.db.models import Order
    from sqlalchemy import select
    from app.core.tools.order_tools import (
        confirm_order, create_draft_order, list_branches,
        list_stylists, recommend_services, update_order_fields,
    )

    # 先判断是否是查订单 / 继续编辑（这些不需要 Agent 介入）
    intent = await _classify_booking_sub_intent(message)

    if intent == "view_order":
        return await _handle_view_order(user_id)
    if intent == "continue_edit":
        return await _handle_continue_edit(user_id)

    # 主体流程：Booking Agent 接管
    try:
        from agentscope.message import TextBlock, UserMsg, SystemMsg
        agent = await get_booking_agent()
        sys_msg = SystemMsg(
            name="system", role="system",
            content=[TextBlock(text="你是美发预约助手，遵循系统提示的工作流。")],
        )
        user_msg = UserMsg(
            name="user", role="user",
            content=[TextBlock(text=message)],
        )
        resp = await agent.reply([sys_msg, user_msg])
        text = ""
        if hasattr(resp, "content") and resp.content:
            for blk in resp.content:
                if hasattr(blk, "text") and blk.text:
                    text += blk.text

        # 从 agent 的工具调用里提取 options（点选卡片）
        options = await _extract_options_from_agent(message, user_id)

        return (text or "正在处理您的请求...", options)
    except Exception as e:
        logger.exception("Booking Agent 调用失败，fallback 手写流程: %s", e)
        return await _legacy_handle_booking_flow(message, user_id, session_id)


async def _classify_booking_sub_intent(message: str) -> str:
    """P1-8: 区分"查订单 / 继续编辑 / 开始新预约"。"""
    from app.core.intent_classifier import classify_booking_sub
    try:
        return await classify_booking_sub(message)
    except Exception:
        return "new_booking"


async def _handle_view_order(user_id: int):
    """显示当前订单。"""
    from app.db.session import async_session_maker
    from app.db.models import Order
    from sqlalchemy import select
    async with async_session_maker() as session:
        stmt = (
            select(Order)
            .where(Order.user_id == user_id, Order.status == "draft")
            .order_by(Order.id.desc())
            .limit(1)
        )
        o = (await session.scalars(stmt)).first()
        if o is None:
            return ("您当前没有进行中的订单。", None)
        return (await show_current_order_text(o.id), None)


async def _handle_continue_edit(user_id: int):
    """继续编辑：返回当前订单状态 + 下一步选项。"""
    from app.db.session import async_session_maker
    from app.db.models import Order
    from sqlalchemy import select
    async with async_session_maker() as session:
        stmt = (
            select(Order)
            .where(Order.user_id == user_id, Order.status == "draft")
            .order_by(Order.id.desc())
            .limit(1)
        )
        o = (await session.scalars(stmt)).first()
        if o is None:
            return ("您没有草稿订单，请先说'我要预约'开始。", None)
        text = await show_current_order_text(o.id)
        # 下一步引导
        if not o.branch_id:
            options = await get_branch_options()
            text += "\n\n请选择分店："
        elif not o.stylist_id:
            options = await get_stylist_options(o.branch_id)
            text += "\n\n请选择发型师："
        elif not o.service_id:
            options = await get_service_options()
            text += "\n\n请选择服务："
        else:
            options = None
            text += "\n\n请提供预约日期和时间（YYYY-MM-DD HH:MM）。"
        return (text, options)


async def _extract_options_from_agent(message: str, user_id: int):
    """P1-8: 从 Agent 的工具调用历史里提取 options（点选卡片）。

    实现: 调 list_branches / list_stylists / recommend_services 时返回 options。
    """
    from app.core.tools.order_tools import list_branches
    try:
        # 简单启发式：如果消息提到"分店/门店/附近"，返回分店选项
        if any(k in message for k in ["分店", "门店", "附近", "店", "哪里"]):
            return await get_branch_options()
        # 提到"发型师/师傅/Tony"
        if any(k in message for k in ["发型师", "师傅", "tony", "tony老师"]):
            from app.db.session import async_session_maker
            from app.db.models import Order
            from sqlalchemy import select
            async with async_session_maker() as session:
                stmt = select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(1)
                o = (await session.scalars(stmt)).first()
                if o and o.branch_id:
                    return await get_stylist_options(o.branch_id)
        # 提到"服务/项目/烫/染/剪"
        if any(k in message for k in ["服务", "项目", "烫", "染", "剪"]):
            return await get_service_options()
    except Exception:
        pass
    return None


async def _legacy_handle_booking_flow(message: str, user_id: int, session_id: str):
    """P1-8: 兜底用旧的 if-else 流程（Agent 失败时降级）。"""
    from app.db.session import async_session_maker
    from sqlalchemy import select
    from app.db.models import Order

    msg = message.lower()

    # 取当前订单
    async with async_session_maker() as session:
        current_order = None
        stmt = (
            select(Order)
            .where(Order.user_id == user_id)
            .where(Order.status.in_(["draft", "pending"]))
            .order_by(Order.updated_at.desc())
        )
        r = await session.execute(stmt)
        current_order = r.scalar_one_or_none()
        order_id = current_order.id if current_order else None

        # 1. 用户开始预约 (P0-3: 用 LLM 意图分类替代 19 个硬编码关键词)
        booking_intent = await _is_booking_intent(message)
        if (not current_order) and booking_intent:
            # 创建草稿
            draft_result = await create_draft_order(user_id=user_id)
            order_id = await booking_service.get_latest_draft_id(user_id)
            # 列出分店 + 选项
            branches_result = await list_branches(user_id=user_id)
            options = await booking_service.get_branch_options()
            return (f"{draft_result}\n\n{branches_result}", options)

        # 2. 有订单，提取信息
        if current_order:
            updated_fields = {}

            # 选分店
            for branch in await booking_service.get_branches_dict():
                if branch["name"] in message and current_order.branch_id != branch["id"]:
                    updated_fields["branch_id"] = branch["id"]
                    break

            # 选发型师
            for s in await booking_service.get_stylists_dict():
                if s["name"] in message and current_order.stylist_id != s["id"]:
                    updated_fields["stylist_id"] = s["id"]
                    break

            # 选服务（只在用户消息明确包含完整服务名时才匹配，否则不填）
            service_matched = False
            for sv in await booking_service.get_services_dict():
                if sv["name"] in message and current_order.service_id != sv["id"]:
                    updated_fields["service_id"] = sv["id"]
                    service_matched = True
                    break
            # 如果用户消息包含烫/染/剪等大类别关键词，但没匹配上服务名 → 返回服务选项
            if not service_matched:
                service_intent_keywords = ["做", "想要", "想", "烫", "染", "剪", "护理", "造型"]
                if any(k in message for k in service_intent_keywords) and not current_order.service_id:
                    services_text = (
                        f"暂时没有找到「{message}」这个具体服务项目。请从以下服务项目中选择："
                    )
                    options = await booking_service.get_service_options()
                    return (services_text, options)

            # 询问服务（用户说了一个未知服务名）
            if not updated_fields.get("service_id") and current_order.branch_id and current_order.stylist_id and not current_order.service_id:
                # 看是不是说"想做烫发/染发"这类大类别
                service_keywords = ["做", "想要", "烫", "染", "剪", "护理", "造型", "项目", "服务"]
                if any(k in message for k in service_keywords):
                    services_text = await recommend_services(user_id=user_id, user_description=message)
                    options = await booking_service.get_service_options()
                    return (services_text, options)

            # 提取日期/时间/电话/姓名 (P0-3: 改用 LLM 抽取，60 行 regex → 1 次 LLM 调用)
            from app.services.intent_extractor import extract_with_llm
            extracted = await extract_with_llm(message)
            if extracted.appointment_date:
                updated_fields["appointment_date"] = extracted.appointment_date
            if extracted.appointment_time:
                updated_fields["appointment_time"] = extracted.appointment_time
            if extracted.customer_phone:
                updated_fields["customer_phone"] = extracted.customer_phone
            if extracted.customer_name:
                updated_fields["customer_name"] = extracted.customer_name

            if updated_fields:
                # service_type 字段必须由 service_id 自动填，不允许直接覆盖
                if "service_id" in updated_fields:
                    # 通过 service_id 自动获取服务名
                    services_dict = await booking_service.get_services_dict()
                    for sv in services_dict:
                        if sv["id"] == updated_fields["service_id"]:
                            updated_fields["service_type"] = sv["name"]
                            break
                result = await update_order_fields(
                    user_id=user_id,
                    order_id=current_order.id,
                    **updated_fields,
                )
                return result

            # 没有任何字段匹配：引导用户
            # 还没选分店
            if not current_order.branch_id:
                branches_text = await list_branches(user_id=user_id)
                options = await booking_service.get_branch_options()
                return (branches_text, options)
            # 还没选发型师
            if not current_order.stylist_id:
                stylists_text = await list_stylists(user_id=user_id, branch_id=current_order.branch_id)
                options = await _get_stylist_options(current_order.branch_id)
                return (stylists_text, options)
            # 还没选服务
            if not current_order.service_id:
                services_text = await recommend_services(user_id=user_id, user_description=message)
                options = await booking_service.get_service_options()
                return (services_text, options)
            # 还没选日期
            if not current_order.appointment_date:
                return '请告诉我您希望哪天到店？可以说"明天"、"下周六"、"8月10日"等。'
            # 还没选时间
            if not current_order.appointment_time:
                return '请告诉我您希望几点到店？比如"下午2点"、"10:00"等。'
            # 还没留电话
            if not current_order.customer_phone:
                return '请留下您的联系电话（11位手机号），店家会联系您确认。'

            # 询问分店
            if "分店" in message or "门店" in message or "店" in message and not current_order.branch_id:
                branches_text = await list_branches(user_id=user_id)
                options = await booking_service.get_branch_options()
                return (branches_text, options)

            # 询问发型师
            if ("发型师" in message or "师傅" in message or "谁" in message) and current_order.branch_id and not current_order.stylist_id:
                stylists_text = await list_stylists(user_id=user_id, branch_id=current_order.branch_id)
                options = await _get_stylist_options(current_order.branch_id)
                return (stylists_text, options)

            # 询问服务
            if ("服务" in message or "项目" in message or "做什么" in message) and not current_order.service_id:
                services_text = await recommend_services(user_id=user_id, user_description=message)
                options = await booking_service.get_service_options()
                return (services_text, options)

            # 确认
            if "确认" in message or ("好的" in message and current_order.branch_id and current_order.stylist_id) or "可以" in message or "就这样" in message:
                if current_order.status == "draft":
                    return await confirm_order(user_id=user_id, order_id=current_order.id)
                elif current_order.status == "pending":
                    return "订单已提交，等待店家确认，无需重复操作。"
                else:
                    return f"订单当前状态：{current_order.status}，无法再次确认。"

            # 查看当前订单 / 继续编辑 (P0-3: 9 关键词 → LLM 意图)
            if await _is_continue_edit_intent(message):
                return await _continue_editing(current_order)
            if await _is_view_order_intent(message):
                return await _show_current_order(current_order)

        # 走到这里：booking intent 但没匹配上具体规则
        # 自动创建草稿订单（如果还没有），并引导选分店
        if not current_order:
            draft_result = await create_draft_order(user_id=user_id)
            order_id = await booking_service.get_latest_draft_id(user_id)
            branches_text = await list_branches(user_id=user_id)
            options = await booking_service.get_branch_options()
            return (f"{draft_result}\n\n{branches_text}", options)

        # 走到这里：booking intent，没匹配上任何更新规则，但有 current_order
        # 智能引导：列出还缺什么
        return await _continue_editing(current_order)



async def _show_current_order(order) -> str:
    from app.db.session import async_session_maker
    async with async_session_maker() as session:
        order = await session.get(order.__class__, order.id)
        # 加载关联
        if order.branch_id:
            await session.refresh(order, ["branch"])
        if order.stylist_id:
            await session.refresh(order, ["stylist"])
        lines = ["📋 你当前订单："]
        lines.append(f"- 编号：{order.order_no}")
        if order.branch and hasattr(order, 'branch') and order.branch:
            lines.append(f"- 分店：{order.branch.name}")
        if order.stylist and hasattr(order, 'stylist') and order.stylist:
            lines.append(f"- 发型师：{order.stylist.name}")
        if order.service_type:
            lines.append(f"- 项目：{order.service_type}")
        if order.appointment_date:
            t = order.appointment_time.strftime('%H:%M') if order.appointment_time else ''
            e = order.end_time.strftime('%H:%M') if order.end_time else ''
            lines.append(f"- 时间：{order.appointment_date} {t} - {e}")
        if order.total_price:
            lines.append(f"- 总价：¥{order.total_price}")
        if order.customer_phone:
            lines.append(f"- 电话：{order.customer_phone}")
        lines.append(f"- 状态：{order.status}")
        return "\n".join(lines)


async def _continue_editing(current_order) -> tuple[str, list[dict] | None]:
    """继续编辑：智能列出当前草稿还缺什么字段，并返回对应选项。"""
    from app.db.session import async_session_maker
    from app.db.models import Order
    from app.core.tools.order_tools import list_branches, list_stylists, recommend_services

    if current_order is None:
        return ('你没有进行中的订单。请先说"我要预约"或"想烫头发"等开始下单。', None)

    # 重新加载以保证是最新
    async with async_session_maker() as session:
        fresh = await session.get(Order, current_order.id)
        if fresh:
            if fresh.branch_id:
                await session.refresh(fresh, ["branch"])
            if fresh.stylist_id:
                await session.refresh(fresh, ["stylist"])
            current_order = fresh

    lines = [f"📋 帮你继续编辑订单 {current_order.order_no}："]
    if current_order.branch and hasattr(current_order, 'branch') and current_order.branch:
        lines.append(f"✅ 分店：{current_order.branch.name}")
    else:
        lines.append("❌ 分店：未选择")
    if current_order.stylist and hasattr(current_order, 'stylist') and current_order.stylist:
        lines.append(f"✅ 发型师：{current_order.stylist.name}")
    else:
        lines.append("❌ 发型师：未选择")
    if current_order.service_type:
        lines.append(f"✅ 项目：{current_order.service_type}")
    else:
        lines.append("❌ 项目：未选择")
    if current_order.appointment_date:
        t = current_order.appointment_time.strftime('%H:%M') if current_order.appointment_time else ''
        e = current_order.end_time.strftime('%H:%M') if current_order.end_time else ''
        lines.append(f"✅ 时间：{current_order.appointment_date} {t} - {e}")
    else:
        lines.append("❌ 时间：未选择")
    if current_order.customer_phone:
        lines.append(f"✅ 电话：{current_order.customer_phone}")
    else:
        lines.append("❌ 电话：未填写")

    # 决定下一步要给出什么选项
    options: list[dict] | None = None
    text = "\n".join(lines)
    if not current_order.branch_id:
        text += "\n\n请选择分店："
        options = await booking_service.get_branch_options()
    elif not current_order.stylist_id:
        text += f"\n\n{current_order.branch.name}有以下发型师："
        options = await _get_stylist_options(current_order.branch_id)
    elif not current_order.service_id:
        text += "\n\n请选择服务项目："
        options = await booking_service.get_service_options()
    elif not current_order.appointment_date or not current_order.appointment_time:
        text += '\n\n请告诉我您希望哪天几点到店？可以说"明天10点"、"下周六14:00"等。'
    elif not current_order.customer_phone:
        text += '\n\n请留下您的联系电话（11位手机号），店家会联系您确认。'
    else:
        text += '\n\n所有信息都齐了，回复"确认"提交订单。'

    return (text, options)

