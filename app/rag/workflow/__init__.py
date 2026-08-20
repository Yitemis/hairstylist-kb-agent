"""Booking 状态机模块.

公开接口：
- run_booking_turn: 跑一轮 booking 对话
- get_booking_graph: 获取全局 Graph 单例
- BookingState: 状态 schema
- make_initial_state: 构造初始 state
"""
from app.rag.workflow.booking_graph import (
    build_booking_graph,
    get_booking_graph,
    reset_booking_graph,
    run_booking_turn,
)
from app.rag.workflow.booking_state import (
    CHECKIN_ORDER,
    BookingState,
    BookingStep,
    get_missing_required_fields,
    make_initial_state,
    REQUIRED_FIELDS,
)

__all__ = [
    "build_booking_graph",
    "get_booking_graph",
    "reset_booking_graph",
    "run_booking_turn",
    "BookingState",
    "BookingStep",
    "CHECKIN_ORDER",
    "make_initial_state",
    "get_missing_required_fields",
    "REQUIRED_FIELDS",
]
