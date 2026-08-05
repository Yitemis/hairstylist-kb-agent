# -*- coding: utf-8 -*-
"""HITL (Human-in-the-Loop) 测试。"""
import asyncio
from datetime import datetime, timedelta
import pytest

from app.safety.hitl import (
    ActionStatus, PendingAction, HIGH_RISK_ACTIONS,
    generate_token, hash_token, is_high_risk, is_expired,
    build_confirmation_prompt, HITLService, get_hitl_service,
)
from app.db.models import User, PendingAction as DBPA
from app.db.session import async_session_maker
from sqlalchemy import delete, select


def test_token_generation_unique():
    tokens = {generate_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(t) >= 30 for t in tokens)


def test_token_hash_consistent():
    t = generate_token()
    assert hash_token(t) == hash_token(t)
    assert len(hash_token(t)) == 64


def test_token_hash_different_for_different_tokens():
    t1, t2 = generate_token(), generate_token()
    assert hash_token(t1) != hash_token(t2)


def test_is_high_risk():
    assert is_high_risk("cancel_order")
    assert is_high_risk("refund")
    assert is_high_risk("delete_user_data")
    assert not is_high_risk("list_branches")
    assert not is_high_risk("create_draft_order")


def test_high_risk_actions_have_descriptions():
    for action in HIGH_RISK_ACTIONS:
        assert HIGH_RISK_ACTIONS[action]


def test_is_expired():
    past = PendingAction(expires_at=datetime.now() - timedelta(minutes=1))
    assert is_expired(past)
    future = PendingAction(expires_at=datetime.now() + timedelta(minutes=5))
    assert not is_expired(future)
    no_exp = PendingAction(expires_at=None)
    assert not is_expired(no_exp)


def test_build_confirmation_prompt_includes_action():
    action = PendingAction(action_type="cancel_order", action_params={"order_id": 123})
    prompt = build_confirmation_prompt(action)
    assert "cancel_order" in prompt


@pytest.fixture(autouse=True)
def ensure_test_users():
    asyncio.run(_create_test_users())
    yield


async def _create_test_users():
    from app.auth.security import hash_password
    async with async_session_maker() as s:
        for uid in [9901, 9902, 9903, 9904, 9905]:
            existing = (await s.execute(select(User).where(User.id == uid))).scalar_one_or_none()
            if not existing:
                s.add(User(id=uid, phone=f'hitl{uid}', name=f'hitl{uid}', password_hash=hash_password('test')))
        await s.commit()


async def _cleanup_actions(user_id):
    async with async_session_maker() as s:
        await s.execute(delete(DBPA).where(DBPA.user_id == user_id))
        await s.commit()


@pytest.mark.asyncio
async def test_create_pending_returns_token_and_action():
    await _cleanup_actions(9901)
    svc = get_hitl_service()
    raw_token, action = await svc.create_pending(
        user_id=9901, action_type="cancel_order", action_params={"order_id": 123}
    )
    assert raw_token and len(raw_token) >= 30
    assert action.id is not None
    assert action.user_id == 9901
    assert action.action_type == "cancel_order"
    assert action.status == ActionStatus.PENDING.value
    assert action.expires_at > datetime.now() + timedelta(minutes=4)


@pytest.mark.asyncio
async def test_token_hash_stored_in_db_not_raw():
    await _cleanup_actions(9902)
    svc = get_hitl_service()
    raw_token, action = await svc.create_pending(
        user_id=9902, action_type="refund", action_params={"amount": 100}
    )
    async with async_session_maker() as s:
        db_action = (await s.execute(select(DBPA).where(DBPA.id == action.id))).scalar_one()
    assert db_action.token_hash != raw_token
    assert db_action.token_hash == hash_token(raw_token)


@pytest.mark.asyncio
async def test_confirm_approve():
    await _cleanup_actions(9903)
    svc = get_hitl_service()
    raw_token, action = await svc.create_pending(user_id=9903, action_type="refund")
    result_action, status = await svc.confirm(raw_token, user_id=9903, approve=True)
    assert status == "confirmed"
    assert result_action.status == ActionStatus.CONFIRMED.value
    assert result_action.confirmed_at is not None


@pytest.mark.asyncio
async def test_confirm_reject():
    await _cleanup_actions(9904)
    svc = get_hitl_service()
    raw_token, action = await svc.create_pending(user_id=9904, action_type="cancel_order")
    result_action, status = await svc.confirm(raw_token, user_id=9904, approve=False)
    assert status == "rejected"
    assert result_action.status == ActionStatus.REJECTED.value


@pytest.mark.asyncio
async def test_confirm_wrong_user_unauthorized():
    await _cleanup_actions(9905)
    svc = get_hitl_service()
    raw_token, _ = await svc.create_pending(user_id=9905, action_type="delete_user_data")
    _, status = await svc.confirm(raw_token, user_id=9901, approve=True)
    assert status == "unauthorized"


@pytest.mark.asyncio
async def test_confirm_invalid_token_not_found():
    svc = get_hitl_service()
    _, status = await svc.confirm("invalid_token_xyz", user_id=9901, approve=True)
    assert status == "not_found"


@pytest.mark.asyncio
async def test_confirm_expired_action():
    await _cleanup_actions(9902)
    async with async_session_maker() as s:
        s.add(DBPA(
            user_id=9902, action_type="refund", action_params={},
            token_hash=hash_token("test_expired_token"),
            status="pending",
            expires_at=datetime.now() - timedelta(minutes=1),
        ))
        await s.commit()
    svc = get_hitl_service()
    _, status = await svc.confirm("test_expired_token", user_id=9902, approve=True)
    assert status == "expired"


@pytest.mark.asyncio
async def test_confirm_twice_returns_already():
    await _cleanup_actions(9903)
    svc = get_hitl_service()
    raw_token, _ = await svc.create_pending(user_id=9903, action_type="send_email")
    _, status1 = await svc.confirm(raw_token, user_id=9903, approve=True)
    assert status1 == "confirmed"
    _, status2 = await svc.confirm(raw_token, user_id=9903, approve=True)
    assert status2.startswith("already_")


@pytest.mark.asyncio
async def test_mark_executed():
    await _cleanup_actions(9901)
    svc = get_hitl_service()
    raw_token, action = await svc.create_pending(user_id=9901, action_type="refund")
    await svc.confirm(raw_token, user_id=9901, approve=True)
    await svc.mark_executed(action.id, result={"refund_id": "R123"}, success=True)
    async with async_session_maker() as s:
        db_action = (await s.execute(select(DBPA).where(DBPA.id == action.id))).scalar_one()
    assert db_action.status == ActionStatus.EXECUTED.value
    assert db_action.executed_at is not None
    assert db_action.result == {"refund_id": "R123"}


@pytest.mark.asyncio
async def test_cleanup_expired():
    await _cleanup_actions(9904)
    async with async_session_maker() as s:
        s.add(DBPA(
            user_id=9904, action_type="cancel_order", action_params={},
            token_hash=hash_token("expired1"), status="pending",
            expires_at=datetime.now() - timedelta(minutes=1),
        ))
        s.add(DBPA(
            user_id=9904, action_type="cancel_order", action_params={},
            token_hash=hash_token("active1"), status="pending",
            expires_at=datetime.now() + timedelta(minutes=5),
        ))
        await s.commit()
    svc = get_hitl_service()
    n = await svc.cleanup_expired()
    assert n >= 1
