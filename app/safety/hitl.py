# -*- coding: utf-8 -*-
"""HITL 状态机 + Token 机制。

借鉴 AgentScope 2.0 PermissionEngine + 自研 token 流程。
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ActionStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXECUTED = "executed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"


HIGH_RISK_ACTIONS = {
    "cancel_order": "取消订单",
    "refund": "退款",
    "delete_user_data": "删除用户数据",
    "update_payment": "修改支付方式",
    "send_email": "发送邮件",
    "share_data": "分享数据",
}

DEFAULT_EXPIRY_MINUTES = 5


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class PendingAction:
    id: int | None = None
    user_id: int = 0
    action_type: str = ""
    action_params: dict[str, Any] | None = None
    token_hash: str = ""
    status: str = ActionStatus.PENDING.value
    created_at: datetime | None = None
    expires_at: datetime | None = None
    confirmed_at: datetime | None = None
    result: dict[str, Any] | None = None


def is_high_risk(action_type: str) -> bool:
    return action_type in HIGH_RISK_ACTIONS


def is_expired(action: PendingAction, now: datetime | None = None) -> bool:
    if action.expires_at is None:
        return False
    return (now or datetime.now()) > action.expires_at


def build_confirmation_prompt(action: PendingAction) -> str:
    desc = HIGH_RISK_ACTIONS.get(action.action_type, action.action_type)
    return f"WARNING: {desc}\nType: {action.action_type}\n请确认是否执行？"


class HITLService:
    def __init__(self, expiry_minutes: int = DEFAULT_EXPIRY_MINUTES):
        self.expiry_minutes = expiry_minutes

    async def create_pending(
        self,
        user_id: int,
        action_type: str,
        action_params: dict[str, Any] | None = None,
    ) -> tuple[str, PendingAction]:
        from app.db.models import PendingAction as PAPending
        from app.db.session import async_session_maker

        raw_token = generate_token()
        token_hash = hash_token(raw_token)
        now = datetime.now()
        expires_at = now + timedelta(minutes=self.expiry_minutes)

        async with async_session_maker() as session:
            db_action = PAPending(
                user_id=user_id,
                action_type=action_type,
                action_params=action_params or {},
                token_hash=token_hash,
                status=ActionStatus.PENDING.value,
                expires_at=expires_at,
            )
            session.add(db_action)
            await session.commit()
            await session.refresh(db_action)
            action = PendingAction(
                id=db_action.id,
                user_id=db_action.user_id,
                action_type=db_action.action_type,
                action_params=db_action.action_params,
                token_hash=db_action.token_hash,
                status=db_action.status,
                created_at=db_action.created_at,
                expires_at=db_action.expires_at,
            )
        return raw_token, action

    async def confirm(
        self,
        raw_token: str,
        user_id: int,
        approve: bool,
    ) -> tuple[PendingAction, str]:
        from app.db.models import PendingAction as PAPending
        from app.db.session import async_session_maker
        from sqlalchemy import select

        token_hash = hash_token(raw_token)
        now = datetime.now()

        async with async_session_maker() as session:
            stmt = select(PAPending).where(PAPending.token_hash == token_hash)
            db_action = (await session.execute(stmt)).scalar_one_or_none()
            if db_action is None:
                return PendingAction(), "not_found"

            action = PendingAction(
                id=db_action.id,
                user_id=db_action.user_id,
                action_type=db_action.action_type,
                action_params=db_action.action_params,
                token_hash=db_action.token_hash,
                status=db_action.status,
                created_at=db_action.created_at,
                expires_at=db_action.expires_at,
            )

            if action.user_id != user_id:
                return action, "unauthorized"
            if action.status != ActionStatus.PENDING.value:
                return action, f"already_{action.status}"
            if is_expired(action, now):
                db_action.status = ActionStatus.EXPIRED.value
                await session.commit()
                return action, "expired"

            if approve:
                db_action.status = ActionStatus.CONFIRMED.value
                db_action.confirmed_at = now
                action.status = ActionStatus.CONFIRMED.value
                action.confirmed_at = now
            else:
                db_action.status = ActionStatus.REJECTED.value
                action.status = ActionStatus.REJECTED.value
            await session.commit()
        return action, "confirmed" if approve else "rejected"

    async def mark_executed(
        self,
        action_id: int,
        result: dict[str, Any] | None = None,
        success: bool = True,
    ) -> None:
        from app.db.models import PendingAction as PAPending
        from app.db.session import async_session_maker

        async with async_session_maker() as session:
            db_action = await session.get(PAPending, action_id)
            if db_action is None:
                return
            db_action.status = ActionStatus.EXECUTED.value if success else ActionStatus.FAILED.value
            db_action.executed_at = datetime.now()
            db_action.result = result or {}
            await session.commit()

    async def cleanup_expired(self) -> int:
        from app.db.models import PendingAction as PAPending
        from app.db.session import async_session_maker
        from sqlalchemy import update

        async with async_session_maker() as session:
            stmt = (
                update(PAPending)
                .where(
                    PAPending.status == ActionStatus.PENDING.value,
                    PAPending.expires_at < datetime.now(),
                )
                .values(status=ActionStatus.EXPIRED.value)
            )
            result = await session.execute(stmt)
            await session.commit()
        return result.rowcount


_hitl_service: HITLService | None = None


def get_hitl_service() -> HITLService:
    global _hitl_service
    if _hitl_service is None:
        _hitl_service = HITLService()
    return _hitl_service
