# -*- coding: utf-8 -*-
"""Booking 状态机的 8 个核心 Node + 1 个 Abort 节点.

借鉴 JavaGuide §5.2 "Graph 三元素" + §5.5 "Node 抽象职责边界"：
- Node 只做一件事，读取 State、执行逻辑、写回结果
- 抽象"产出"而不是"调了哪个 API"
- 每个 CHECKIN 节点都遵循 4 个标准阶段

借鉴 JavaGuide §5.4 "错误处理四类"：
- 瞬时错误：重试
- LLM 可恢复错误：把错误塞 State，retry 边
- 用户可修复错误：把错误告诉用户，停留当前节点
- 意外错误：让异常冒泡
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from app.core.tools.order_tools import (
    confirm_order,
    create_draft_order,
    list_branches,
    list_stylists,
    recommend_services,
    update_order_fields,
)
from app.services.booking_service import (
    get_branches_dict,
    get_services_dict,
    get_stylist_options,
)
from app.rag.workflow.booking_parsers import (
    detect_change_intent,
    parse_branch_choice,
    parse_datetime,
    parse_intent_to_book,
    parse_phone,
    parse_service_choice,
    parse_stylist_choice,
    parse_yes_no,
)
from app.rag.workflow.booking_state import (
    CHECKIN_ORDER,
    BookingState,
    get_missing_required_fields,
)

logger = logging.getLogger(__name__)


# ============ 公共辅助 ============

async def _check_iteration_limit(state: BookingState) -> dict:
    """检查迭代次数是否超限（安全边界，参考 JavaGuide §5.3）.

    Returns:
        超限返回 aborted 状态，否则返回空 dict
    """
    count = state.get("iteration_count", 0) + 1
    max_iter = state.get("max_iterations", 10)
    if count > max_iter:
        logger.warning("Booking iteration limit reached: %d/%d", count, max_iter)
        return {
            "current_step": "aborted",
            "iteration_count": count,
            "final_message": "抱歉，预约流程异常中止，请重新开始。",
        }
    return {"iteration_count": count}


def _format_yes_no_question(question: str) -> str:
    """格式化一个 yes/no 问题."""
    return question


# ============ Node 1: IDLE ============

async def node_idle(state: BookingState, runtime: Runtime) -> dict:
    """IDLE 节点：等待用户开始预约.

    行为：
    - 已有草稿订单 → 直接跳到 draft 节点（恢复）
    - 用户说要预约 → 跳到 draft
    - 用户在问问题/闲聊 → aborted（路由回主 Agent）
    """
    inc = await _check_iteration_limit(state)
    if inc.get("current_step") == "aborted":
        return inc

    # 已有草稿订单 → 恢复
    if state.get("order_id") is not None:
        # 用 state 里保存的 current_step 恢复
        saved_step = state.get("current_step", "checkin_branch")
        # 如果保存的 step 还在 CHECKIN_ORDER, 就用
        if saved_step not in ("checkin_branch", "checkin_service", "checkin_stylist",
                              "checkin_datetime", "checkin_phone", "checkin_name", "confirm"):
            saved_step = "checkin_branch"
        return {
            "current_step": saved_step,
            "final_message": f"你有一个进行中的订单（{state.get('order_no')}），继续填写。",
        }

    user_input = state.get("user_input", "").strip()
    if not user_input:
        return {
            "current_step": "idle",
            "needs_retry": True, "final_message": "想预约什么服务？我可以帮你选分店、发型师和时间。",
        }

    # 意图识别
    if await parse_intent_to_book(user_input):
        return {
            "current_step": "draft",
            "user_input": user_input,
        }

    # 不是预约意图 → aborted
    return {
        "current_step": "aborted",
        "final_message": None,  # 让主 Agent 处理
    }


# ============ Node 2: DRAFT ============

async def node_draft(state: BookingState, runtime: Runtime) -> dict:
    """DRAFT 节点：创建草稿订单.

    行为：
    - 调 create_draft_order(user_id)
    - 拿到 order_id + order_no
    - 推进到 checkin_branch
    """
    inc = await _check_iteration_limit(state)
    if inc.get("current_step") == "aborted":
        return inc

    if state.get("order_id") is not None:
        return {"current_step": "checkin_branch"}

    user_id = state.get("user_id")
    if not user_id:
        return {
            "current_step": "aborted",
            "final_message": "未登录，无法创建订单。",
        }

    try:
        result_str = await create_draft_order(user_id=int(user_id))
        # 解析 "订单编号：XXX，ID：YYY"
        import re
        m = re.search(r"订单编号：([\w-]+)，ID：(\d+)", result_str)
        if not m:
            logger.error("create_draft_order returned unexpected: %s", result_str)
            return {
                "current_step": "aborted",
                "final_message": "创建订单失败，请重试。",
            }
        order_no = m.group(1)
        order_id = int(m.group(2))

        return {
            "order_id": order_id,
            "order_no": order_no,
            "current_step": "checkin_branch",
            "final_message": (
                f"好的，帮你创建了一个草稿订单（{order_no}）。\n"
                "请问你想预约哪家分店？"
            ),
        }
    except Exception as e:
        logger.exception("create_draft_order failed: %s", e)
        return {
            "current_step": "aborted",
            "last_error": str(e),
            "final_message": f"创建订单失败：{e}",
        }


# ============ Node 3: CHECKIN_BRANCH ============

async def node_checkin_branch(state: BookingState, runtime: Runtime) -> dict:
    """CHECKIN_BRANCH 节点：选分店.

    4 阶段：Detect → Prepare → Parse → Update
    """
    inc = await _check_iteration_limit(state)
    if inc.get("current_step") == "aborted":
        return inc

    # Phase 1: Detect（已有值 → 跳过）
    if state.get("branch_id") is not None:
        return {"current_step": "checkin_service"}

    user_input = state.get("user_input", "").strip()
    if not user_input:
        return {
            "current_step": "checkin_branch",
            "needs_retry": True, "final_message": "请告诉我你想预约哪家分店。",
            "user_input": "",
        }

    # Phase 2: Prepare（拉取候选 - 用结构化数据，保留真实 ID）
    if not state.get("branches_cache"):
        try:
            # 用 booking_service 直接拿结构化数据（带真实 ID）
            branches_raw = await get_branches_dict()
            if not branches_raw:
                return {
                    "current_step": "aborted",
                    "final_message": "暂无可用分店，请稍后再试。",
                    "user_input": "",
                }
            branches = [
                {
                    "id": b["id"],
                    "name": b.get("name", ""),
                    "address": b.get("address", ""),
                }
                for b in branches_raw
            ]
        except Exception as e:
            logger.exception("get_branches_dict failed: %s", e)
            return {
                "needs_retry": True,
                "last_error": str(e),
                "final_message": "获取分店列表失败，请重试。",
                "user_input": "",
            }
    else:
        branches = state["branches_cache"]

    # Phase 3: Parse（局部 ReAct 解析）
    parsed = await parse_branch_choice(user_input, branches)
    if not parsed:
        return {
            "current_step": "checkin_branch",
            "needs_retry": True,
            "branches_cache": branches,
            "final_message": f"我没理解你的选择。当前可选：\n{_format_branches(branches)}\n请再说一次。",
            "user_input": "",
        }

    # Phase 4: Update（写库 + 推进）
    try:
        await update_order_fields(
            user_id=int(state["user_id"]),
            order_id=int(state["order_id"]),
            branch_id=parsed["id"],
        )
        return {
            "branch_id": parsed["id"],
            "branch_name": parsed["name"],
            "current_step": "checkin_service",
            "needs_retry": False,
            "last_error": None,
            "final_message": f"好的，已选定 {parsed['name']}。请问你想做什么项目？",
            "user_input": "",
        }
    except Exception as e:
        logger.exception("update_order_fields (branch) failed: %s", e)
        return {
            "needs_retry": True,
            "last_error": str(e),
            "final_message": f"更新分店失败：{e}",
            "user_input": "",
        }


def _format_branches(branches: list[dict[str, Any]]) -> str:
    """格式化分店列表给用户看."""
    lines = []
    for i, b in enumerate(branches, 1):
        lines.append(f"[{i}] {b['name']}（{b.get('address', '')}）")
    return "\n".join(lines)


def _format_services(services: list[dict[str, Any]]) -> str:
    """格式化服务列表给用户看."""
    lines = []
    for i, s in enumerate(services, 1):
        price = s.get("total_price")
        duration = s.get("duration_minutes", 0)
        price_str = f" ¥{price:.0f}" if price else ""
        duration_str = f" / {duration}分钟" if duration else ""
        lines.append(f"[{i}] {s['name']}{price_str}{duration_str}")
    return "\n".join(lines)


# ============ Node 4: CHECKIN_SERVICE ============

async def node_checkin_service(state: BookingState, runtime: Runtime) -> dict:
    """CHECKIN_SERVICE 节点：选服务项目."""
    inc = await _check_iteration_limit(state)
    if inc.get("current_step") == "aborted":
        return inc

    if state.get("service_type") is not None:
        return {"current_step": "checkin_stylist"}

    user_input = state.get("user_input", "").strip()
    if not user_input:
        # 第一次进来：拉取服务列表 + 展示
        try:
            services_raw = await get_services_dict()
            services = [
                {
                    "id": s["id"],
                    "name": s.get("name", ""),
                    "duration_minutes": s.get("duration_minutes", 0),
                    "total_price": s.get("price"),
                }
                for s in (services_raw or [])
            ]
            formatted = _format_services(services) if services else "（暂无可用服务项目，直接说项目名也行）"
            return {
                "current_step": "checkin_service",
                "needs_retry": True,
                "services_cache": services,
                "final_message": (
                    f"请选择服务项目：\n{formatted}\n\n"
                    "可以直接说项目名（例：热烫、染发）或回复「你推荐」让我帮你选。"
                ),
                "user_input": "",
            }
        except Exception as e:
            logger.exception("get_services_dict failed: %s", e)
            return {
                "current_step": "checkin_service",
                "needs_retry": True,
                "final_message": "获取服务列表失败，请直接告诉我项目名。",
                "user_input": "",
            }

    # 用户说"推荐" → 调 recommend_services
    if "推荐" in user_input or "不知道" in user_input or "你帮" in user_input or "你选" in user_input:
        try:
            rec_text = await recommend_services(
                user_id=int(state["user_id"]),
                user_description=user_input,
            )
            return {
                "needs_retry": False,
                "recommended_services": [{"raw_text": rec_text}],
                "final_message": rec_text + "\n\n请告诉我你想选哪个项目（说名字或编号都行）。",
                "user_input": "",
            }
        except Exception as e:
            logger.exception("recommend_services failed: %s", e)
            return {
                "needs_retry": True,
                "last_error": str(e),
                "final_message": "推荐服务失败，请直接告诉我项目名。",
                "user_input": "",
            }

    # 解析用户输入 → service_id 或 service_type
    services_cache = state.get("services_cache") or []
    if not services_cache:
        try:
            services_raw = await get_services_dict()
            services_cache = [
                {
                    "id": s["id"],
                    "name": s.get("name", ""),
                    "duration_minutes": s.get("duration_minutes", 0),
                    "total_price": s.get("price"),
                }
                for s in services_raw
            ]
        except Exception:
            services_cache = []

    parsed = await parse_service_choice(user_input, services_cache)

    if parsed and parsed.get("id"):
        # 匹配到具体服务
        try:
            await update_order_fields(
                user_id=int(state["user_id"]),
                order_id=int(state["order_id"]),
                service_id=parsed["id"],
            )
            return {
                "service_id": parsed["id"],
                "service_type": parsed["name"],
                "current_step": "checkin_stylist",
                "needs_retry": False,
                "final_message": f"好的，项目「{parsed['name']}」已记录。请问你想选哪位发型师？",
                "user_input": "",
            }
        except Exception as e:
            logger.exception("update_order_fields (service_id) failed: %s", e)
            return {
                "needs_retry": True,
                "last_error": str(e),
                "final_message": f"更新服务失败：{e}",
                "user_input": "",
            }

    # 没匹配到 → 作为自由文本（service_type）记录
    try:
        await update_order_fields(
            user_id=int(state["user_id"]),
            order_id=int(state["order_id"]),
            service_type=user_input,
            service_details=user_input,
        )
        return {
            "service_type": user_input,
            "service_details": user_input,
            "current_step": "checkin_stylist",
            "needs_retry": False,
            "final_message": f"好的，项目「{user_input}」已记录。请问你想选哪位发型师？",
        "user_input": "",
        }
    except Exception as e:
        logger.exception("update_order_fields (service_type) failed: %s", e)
        return {
            "needs_retry": True,
            "last_error": str(e),
            "final_message": f"更新服务项目失败：{e}",
            "user_input": "",
        }


# ============ Node 5: CHECKIN_STYLIST ============

async def node_checkin_stylist(state: BookingState, runtime: Runtime) -> dict:
    """CHECKIN_STYLIST 节点：选发型师."""
    inc = await _check_iteration_limit(state)
    if inc.get("current_step") == "aborted":
        return inc

    logger.info("DEBUG checkin_stylist: state.stylist_id=%s, user_input=%r, branch_id=%s",
                state.get("stylist_id"), state.get("user_input"), state.get("branch_id"))

    if state.get("stylist_id") is not None:
        return {"current_step": "checkin_datetime"}

    user_input = state.get("user_input", "").strip()
    if not user_input:
        return {
            "current_step": "checkin_stylist",
            "needs_retry": True, "final_message": "请告诉我你想选哪位发型师（说姓名或编号都行）。",
            "user_input": "",
        }

    # 拉候选 - 用结构化数据
    branch_id = state.get("branch_id")
    cache_key = str(branch_id) if branch_id else "all"
    stylists_cache = state.get("stylists_cache") or {}

    if cache_key not in stylists_cache:
        try:
            # 用 get_stylist_options 拿结构化数据（带真实 ID + 名字 + 描述）
            stylists_raw = await get_stylist_options(int(branch_id)) if branch_id else []
            if not stylists_raw:
                return {
                    "current_step": "aborted",
                    "final_message": "该分店暂无可用发型师，请选择其他分店。",
                    "user_input": "",
                }
            stylists = [
                {
                    "id": s["id"],
                    "name": s.get("title", s.get("name", "")),
                    "description": s.get("subtitle", ""),
                }
                for s in stylists_raw
            ]
            stylists_cache[cache_key] = stylists
        except Exception as e:
            logger.exception("get_stylist_options failed: %s", e)
            return {
                "needs_retry": True,
                "last_error": str(e),
                "final_message": "获取发型师列表失败，请重试。",
                "user_input": "",
            }
    else:
        stylists = stylists_cache[cache_key]

    # 解析
    parsed = await parse_stylist_choice(user_input, stylists)

    # 用户说"随便"/"都行"/"你选" → 自动选第一个
    skip_keywords = ["随便", "都行", "你选", "都可以", "随便吧", "无所谓"]
    is_skip = any(kw in user_input for kw in skip_keywords)

    if not parsed and is_skip:
        # 跳过发型师选择，用第一个
        if stylists:
            first = stylists[0]
            try:
                await update_order_fields(
                    user_id=int(state["user_id"]),
                    order_id=int(state["order_id"]),
                    stylist_id=first["id"],
                )
                return {
                    "stylist_id": first["id"],
                    "stylist_name": first["name"],
                    "current_step": "checkin_datetime",
                    "needs_retry": False,
                    "last_error": None,
                    "final_message": f"好的，已选 {first['name']} 发型师。请问你想约什么时间？",
                    "user_input": "",
                }
            except Exception as e:
                logger.exception("update_order_fields (stylist skip) failed: %s", e)

    if not parsed:
        return {
            "current_step": "checkin_stylist",
            "needs_retry": True,
            "stylists_cache": stylists_cache,
            "final_message": f"我没理解你想选的发型师。当前可选：\n{_format_stylists(stylists)}\n（回复「随便」跳过）",
            "user_input": "",
        }

    # 写库
    try:
        await update_order_fields(
            user_id=int(state["user_id"]),
            order_id=int(state["order_id"]),
            stylist_id=parsed["id"],
        )
        return {
            "stylist_id": parsed["id"],
            "stylist_name": parsed["name"],
            "current_step": "checkin_datetime",
            "needs_retry": False,
            "last_error": None,
            "final_message": f"好的，已选 {parsed['name']} 发型师。请问你想约什么时间？",
            "user_input": "",
        }
    except Exception as e:
        logger.exception("update_order_fields (stylist) failed: %s", e)
        return {
            "needs_retry": True,
            "last_error": str(e),
            "final_message": f"更新发型师失败：{e}",
            "user_input": "",
        }


def _format_stylists(stylists: list[dict[str, Any]]) -> str:
    """格式化发型师列表."""
    return "\n".join(
        f"[{i}] {s['name']}"
        for i, s in enumerate(stylists, 1)
    )


# ============ Node 6: CHECKIN_DATETIME ============

async def node_checkin_datetime(state: BookingState, runtime: Runtime) -> dict:
    """CHECKIN_DATETIME 节点：选时间."""
    inc = await _check_iteration_limit(state)
    if inc.get("current_step") == "aborted":
        return inc

    if state.get("appointment_date") is not None and state.get("appointment_time") is not None:
        return {"current_step": "checkin_phone"}

    user_input = state.get("user_input", "").strip()
    if not user_input:
        return {
            "current_step": "checkin_datetime",
            "needs_retry": True, "final_message": "请告诉我你想约哪天几点（例：明天下午 3 点）。",
            "user_input": "",
        }

    parsed = await parse_datetime(user_input)
    if not parsed:
        return {
            "current_step": "checkin_datetime",
            "needs_retry": True,
            "final_message": "我没理解你的时间，请说清楚（例：明天下午 3 点、下周六 10:30）。",
            "user_input": "",
        }

    # 写库
    try:
        kwargs: dict[str, Any] = {
            "user_id": int(state["user_id"]),
            "order_id": int(state["order_id"]),
            "appointment_date": parsed["date"],
            "appointment_time": parsed["time"],
        }
        # 如果 service_id 已知，duration_minutes 自动算
        if state.get("service_type") and not state.get("duration_minutes"):
            # 默认 60 分钟（保守值）
            kwargs["duration_minutes"] = 60
        await update_order_fields(**kwargs)

        return {
            "appointment_date": parsed["date"],
            "appointment_time": parsed["time"],
            **({"duration_minutes": 60} if not state.get("duration_minutes") and state.get("service_type") else {}),
            "current_step": "checkin_phone",
            "needs_retry": False,
            "last_error": None,
            "final_message": f"好的，时间已记 {parsed['date']} {parsed['time']}。请留个联系电话。",
            "user_input": "",
        }
    except Exception as e:
        logger.exception("update_order_fields (datetime) failed: %s", e)
        return {
            "needs_retry": True,
            "last_error": str(e),
            "final_message": f"更新时间失败：{e}",
            "user_input": "",
        }


# ============ Node 7: CHECKIN_PHONE ============

async def node_checkin_phone(state: BookingState, runtime: Runtime) -> dict:
    """CHECKIN_PHONE 节点：留电话."""
    inc = await _check_iteration_limit(state)
    if inc.get("current_step") == "aborted":
        return inc

    if state.get("customer_phone") is not None:
        return {"current_step": "checkin_name"}

    user_input = state.get("user_input", "").strip()
    if not user_input:
        return {
            "current_step": "checkin_phone",
            "needs_retry": True, "final_message": "请留 11 位手机号，方便店家联系。",
            "user_input": "",
        }

    phone = await parse_phone(user_input)
    if not phone:
        return {
            "current_step": "checkin_phone",
            "needs_retry": True,
            "final_message": "手机号格式不对（需 11 位，1 开头），请重新输入。",
            "user_input": "",
        }

    try:
        await update_order_fields(
            user_id=int(state["user_id"]),
            order_id=int(state["order_id"]),
            customer_phone=phone,
        )
        return {
            "customer_phone": phone,
            "current_step": "checkin_name",
            "needs_retry": False,
            "last_error": None,
            "final_message": f"好的，电话 {phone} 已记录。请问怎么称呼你？",
            "user_input": "",
        }
    except Exception as e:
        logger.exception("update_order_fields (phone) failed: %s", e)
        return {
            "needs_retry": True,
            "last_error": str(e),
            "final_message": f"更新电话失败：{e}",
            "user_input": "",
        }


# ============ Node 8: CHECKIN_NAME ============

async def node_checkin_name(state: BookingState, runtime: Runtime) -> dict:
    """CHECKIN_NAME 节点：留姓名（可选）.

    姓名是可选的。如果用户说"不用" / "随便" → 跳过。
    """
    inc = await _check_iteration_limit(state)
    if inc.get("current_step") == "aborted":
        return inc

    if state.get("customer_name") is not None:
        return {"current_step": "confirm"}

    user_input = state.get("user_input", "").strip()

    # 用户说不需要
    skip_keywords = ["不用", "随便", "算了", "skip", "匿名", "不填"]
    if any(kw in user_input for kw in skip_keywords):
        return {
            "customer_name": None,
            "current_step": "confirm",
            "needs_retry": False,
            "final_message": "好的，跳过姓名。",
            "user_input": "",
        }

    if not user_input:
        return {
            "current_step": "checkin_name",
            "needs_retry": True, "final_message": "请问怎么称呼你？（可回复「不用」跳过）",
            "user_input": "",
        }

    # 校验姓名（2-20 字符）
    name = user_input.strip()
    if len(name) > 20:
        return {
            "current_step": "checkin_name",
            "needs_retry": True,
            "final_message": "姓名太长了，请简化（20 字以内）。",
            "user_input": "",
        }

    try:
        await update_order_fields(
            user_id=int(state["user_id"]),
            order_id=int(state["order_id"]),
            customer_name=name,
        )
        return {
            "customer_name": name,
            "current_step": "confirm",
            "needs_retry": False,
            "last_error": None,
            "final_message": f"好的，{name}。最后确认下订单信息：",
            "user_input": "",
        }
    except Exception as e:
        logger.exception("update_order_fields (name) failed: %s", e)
        return {
            "needs_retry": True,
            "last_error": str(e),
            "final_message": f"更新姓名失败：{e}",
            "user_input": "",
        }


# ============ Node 9: CONFIRM ============

async def node_confirm(state: BookingState, runtime: Runtime) -> dict:
    """CONFIRM 节点：确认下单.

    行为：
    - 校验所有必填字段
    - 用户确认 → 调 confirm_order
    - 用户说"等下" → 返回 checkin_name 让用户检查
    """
    inc = await _check_iteration_limit(state)
    if inc.get("current_step") == "aborted":
        return inc

    # 校验必填
    missing = get_missing_required_fields(state)
    if missing:
        return {
            "current_step": "aborted",
            "last_error": f"缺少必填字段: {', '.join(missing)}",
            "final_message": f"订单信息不完整，缺少：{', '.join(missing)}。",
        "user_input": "",
        }

    user_input = state.get("user_input", "").strip()

    # 用户还没确认 → 展示订单摘要
    if not user_input:
        summary = _format_order_summary(state)
        return {
            "current_step": "confirm",
            "final_message": f"{summary}\n\n确认无误回复「确认」提交，回复「取消」放弃。",
        "user_input": "",
        }

    # 用户说"等下" / "改" → 回到 checkin_name
    back_keywords = ["等下", "等等", "改", "重新", "看一下"]
    if any(kw in user_input for kw in back_keywords):
        return {
            "current_step": "checkin_name",
            "final_message": "好的，请检查信息。需要改哪一项直接说。",
        "user_input": "",
        }

    # 解析 yes/no
    yn = await parse_yes_no(user_input)
    if yn is False:
        return {
            "current_step": "aborted",
            "final_message": "已取消订单。",
        "user_input": "",
        }
    if yn is None:
        return {
            "current_step": "confirm",
            "needs_retry": True,
            "final_message": "我没理解。请明确说「确认」或「取消」。",
        "user_input": "",
        }

    # ========== L6: 用 safe_call_tool 统一处理权限 + HITL ==========
    from app.core.tool_permission import safe_call_tool

    safe_result = await safe_call_tool(
        confirm_order,
        user_id=int(state["user_id"]),
        tool_name="confirm_order",
        order_id=int(state["order_id"]),
    )

    if safe_result.get("needs_asking"):
        # HITL: 等待用户确认
        return {
            "current_step": "confirm",
            "pending_ask_id": safe_result["ask_id"],
            "needs_retry": True,
            "last_error": safe_result.get("reason"),
            "final_message": f"⚠️ {safe_result.get('ask_message', '此操作需您确认')}\n（ask_id: {safe_result['ask_id']}）\n回复「确认」继续，「取消」放弃。",
        "user_input": "",
        }

    if not safe_result.get("ok"):
        # 错误（DENIED 或工具异常）
        return {
            "current_step": "aborted",
            "last_error": safe_result.get("error"),
            "final_message": f"❌ 订单提交失败：{safe_result.get('error')}",
        "user_input": "",
        }

    # 成功
    return {
        "current_step": "confirm",  # 边函数会路由到 END
        "needs_retry": False,
        "last_error": None,
        "final_message": safe_result["result"],
    "user_input": "",
    }


def _format_order_summary(state: BookingState) -> str:
    """格式化订单摘要."""
    lines = ["📋 订单摘要："]
    if state.get("order_no"):
        lines.append(f"编号：{state['order_no']}")
    if state.get("branch_name"):
        lines.append(f"分店：{state['branch_name']}")
    if state.get("service_type"):
        lines.append(f"项目：{state['service_type']}")
    if state.get("stylist_name"):
        lines.append(f"发型师：{state['stylist_name']}")
    if state.get("appointment_date"):
        time_str = state["appointment_time"] or ""
        lines.append(f"时间：{state['appointment_date']} {time_str}")
    if state.get("duration_minutes"):
        lines.append(f"时长：{state['duration_minutes']} 分钟")
    if state.get("total_price"):
        lines.append(f"总价：¥{state['total_price']:.0f}")
    if state.get("customer_phone"):
        lines.append(f"电话：{state['customer_phone']}")
    if state.get("customer_name"):
        lines.append(f"姓名：{state['customer_name']}")
    return "\n".join(lines)


# ============ Node 10: ABORTED ============

async def node_aborted(state: BookingState, runtime: Runtime) -> dict:
    """ABORTED 节点：流程中止，路由回主 Agent."""
    return {
        "current_step": "aborted",
        "final_message": state.get("final_message"),
    }


# ============ Node 11: INTAKE_ROUTER ============

async def node_intake_router(state: BookingState, runtime: Runtime) -> dict:
    """Intake Router - 智能识别用户意图.

    借鉴 JavaGuide §1.1 "范式选型" + §3.5 "Context Assembler":
    - 状态机路径确定，但每个节点的用户输入可能是题外话
    - 用 LLM 分类意图，再路由到对应处理

    支持的意图（详见 booking_intake.py）:
    - continue: 继续填当前字段
    - change_X: 改其他字段
    - side_question: 题外话（调 knowledge_agent 回答后回原节点）
    - cancel: 取消预约
    - query_status: 查询当前订单进度
    """
    from app.rag.workflow.booking_intake import (
        intake_route, handle_side_question, format_status,
        INTENT_CANCEL, INTENT_QUERY_STATUS, INTENT_SIDE_QUESTION,
        INTENT_CONTINUE,
    )

    user_input = state.get("user_input", "").strip()
    if not user_input:
        return {"current_step": state.get("current_step", "checkin_branch")}

    # 收集已填字段
    filled_fields = {
        k: state.get(k) for k in (
            "branch_id", "branch_name", "service_type", "stylist_id", "stylist_name",
            "appointment_date", "appointment_time", "customer_phone", "customer_name",
        )
    }

    # Intake 分类
    result = await intake_route(user_input, state.get("current_step", ""), filled_fields)
    intent = result["intent"]
    logger.info("IntakeRouter: user_input=%r -> intent=%s", user_input[:30], intent)

    if intent == INTENT_CANCEL:
        return {
            "current_step": "aborted",
            "pending_intent": intent,
            "needs_retry": False,
            "final_message": "好的，已为你取消预约。如果改主意了随时告诉我。",
        }

    if intent == INTENT_QUERY_STATUS:
        return {
            "current_step": state.get("current_step", "checkin_branch"),
            "pending_intent": intent,
            "needs_retry": True,
            "status_text": format_status(filled_fields),
            "final_message": format_status(filled_fields) + "\n\n（继续说就行）",
        }

    if intent == INTENT_SIDE_QUESTION:
        # 调 knowledge_agent 回答
        try:
            answer = await handle_side_question(
                user_input,
                user_id=int(state.get("user_id", 0)),
                session_id=str(state.get("order_no", "")),
            )
            # 临时回答，但停留在原 step
            return {
                "current_step": state.get("current_step", "checkin_branch"),
                "pending_intent": intent,
                "needs_retry": True,
                "side_answer": answer,
                "final_message": f"{answer}\n\n💡（以上是知识问答，不影响预约流程。{_step_prompt(state.get('current_step'))}）",
            }
        except Exception as e:
            logger.exception("handle_side_question failed: %s", e)
            return {
                "current_step": state.get("current_step", "checkin_branch"),
                "pending_intent": INTENT_CONTINUE,  # 失败就当作继续
                "needs_retry": True,
                "final_message": "知识问答失败，请继续填写预约信息。",
            }

    # change_X 意图: pending_intent 标记, 路由函数会处理
    if intent != INTENT_CONTINUE:
        return {
            "current_step": state.get("current_step", "checkin_branch"),
            "pending_intent": intent,
            "needs_retry": False,
        }

    # continue 意图: 继续当前 step
    return {
        "current_step": state.get("current_step", "checkin_branch"),
        "pending_intent": intent,
        "needs_retry": False,
    }


def _step_prompt(current_step: str) -> str:
    """返回当前 step 的提示."""
    prompts = {
        "checkin_branch": "请告诉我你想预约哪家分店",
        "checkin_service": "请告诉我你想做什么项目",
        "checkin_stylist": "请告诉我你想选哪位发型师",
        "checkin_datetime": "请告诉我你想约什么时间",
        "checkin_phone": "请留个联系电话",
        "checkin_name": "请问怎么称呼你",
        "confirm": "回复「确认」提交",
    }
    return prompts.get(current_step, "请继续")


__all__ = [
    "node_idle",
    "node_draft",
    "node_intake_router",
    "node_checkin_branch",
    "node_checkin_service",
    "node_checkin_stylist",
    "node_checkin_datetime",
    "node_checkin_phone",
    "node_checkin_name",
    "node_confirm",
    "node_aborted",
]
