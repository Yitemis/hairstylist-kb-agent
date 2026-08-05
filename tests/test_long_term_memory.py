# -*- coding: utf-8 -*-
"""长期记忆测试。"""
import asyncio
import pytest
from sqlalchemy import delete

from app.core.long_term_memory import (
    extract_facts_with_llm, save_facts, get_user_facts,
    build_facts_injection, extract_and_save_facts,
)
from app.core.long_term_memory_v2 import (
    delete_user_fact, get_recent_facts, fact_count_per_user,
    merge_similar_facts, extract_and_save_facts_v2,
)
from app.db.models import UserProfile, User
from sqlalchemy import select
from app.db.session import async_session_maker





@pytest.fixture(autouse=True)
def ensure_test_users():
    """每个测试前创建测试 user（避免 FK 错误）。"""
    asyncio.run(_create_test_users())
    yield


async def _create_test_users():
    from app.db.models import User
    from app.auth.security import hash_password
    async with async_session_maker() as s2:
        for uid in [9901, 9902, 9903, 9904, 9905, 9906, 9907, 9908, 9909, 99999]:
            existing = (await s2.execute(select(User).where(User.id == uid))).scalar_one_or_none()
            if not existing:
                s2.add(User(id=uid, phone=f'test{uid}', name=f'test{uid}', password_hash=hash_password('test')))
        await s2.commit()


async def _cleanup(user_id: int):
    async with async_session_maker() as s:
        await s.execute(delete(UserProfile).where(UserProfile.user_id == user_id))
        await s.commit()


# ===================================================================
# L1: 基础功能
# ===================================================================

@pytest.mark.asyncio
async def test_save_facts_inserts_new():
    """新 fact 插入。"""
    await _cleanup(9901)
    n = await save_facts(9901, [
        {"key": "preferred_stylist", "value": "张托尼", "confidence": 0.9},
        {"key": "allergic_to", "value": "阿摩尼亚", "confidence": 1.0},
    ])
    assert n == 2

    facts = await get_user_facts(9901)
    assert len(facts) == 2
    keys = {f["key"] for f in facts}
    assert "preferred_stylist" in keys
    assert "allergic_to" in keys


@pytest.mark.asyncio
async def test_save_facts_updates_existing():
    """同 key 第二次保存 = update。"""
    await _cleanup(9902)
    await save_facts(9902, [
        {"key": "preferred_stylist", "value": "张托尼", "confidence": 0.5},
    ])
    await save_facts(9902, [
        {"key": "preferred_stylist", "value": "李明", "confidence": 0.95},
    ])
    facts = await get_user_facts(9902)
    assert len(facts) == 1
    assert facts[0]["value"] == "李明"
    assert facts[0]["confidence"] == 0.95


@pytest.mark.asyncio
async def test_save_facts_skips_empty():
    """空 key / value 跳过。"""
    await _cleanup(9903)
    n = await save_facts(9903, [
        {"key": "", "value": "x", "confidence": 1.0},
        {"key": "y", "value": "", "confidence": 1.0},
        {"key": "real", "value": "valid", "confidence": 0.8},
    ])
    assert n == 1


@pytest.mark.asyncio
async def test_get_user_facts_orders_by_confidence():
    """get_user_facts 按 confidence 降序。"""
    await _cleanup(9904)
    await save_facts(9904, [
        {"key": "k1", "value": "v1", "confidence": 0.3},
        {"key": "k2", "value": "v2", "confidence": 0.9},
        {"key": "k3", "value": "v3", "confidence": 0.6},
    ])
    facts = await get_user_facts(9904)
    assert facts[0]["confidence"] == 0.9
    assert facts[1]["confidence"] == 0.6
    assert facts[2]["confidence"] == 0.3


def test_build_facts_injection_format():
    """build_facts_injection 输出格式。"""
    facts = [
        {"key": "preferred_stylist", "value": "张托尼", "confidence": 0.9},
        {"key": "allergic_to", "value": "阿摩尼亚", "confidence": 1.0},
    ]
    text = build_facts_injection(facts)
    assert "preferred_stylist" in text
    assert "张托尼" in text
    assert "allergic_to" in text
    assert "阿摩尼亚" in text


def test_build_facts_injection_empty():
    """空 facts 返回空字符串。"""
    assert build_facts_injection([]) == ""


# ===================================================================
# L2: 高级功能
# ===================================================================

@pytest.mark.asyncio
async def test_delete_user_fact():
    """用户删除某条 fact。"""
    await _cleanup(9905)
    await save_facts(9905, [
        {"key": "k1", "value": "v1", "confidence": 0.9},
        {"key": "k2", "value": "v2", "confidence": 0.9},
    ])
    deleted = await delete_user_fact(9905, "k1")
    assert deleted
    facts = await get_user_facts(9905)
    assert len(facts) == 1
    assert facts[0]["key"] == "k2"


@pytest.mark.asyncio
async def test_delete_user_fact_not_found():
    """删除不存在的 fact 返回 False。"""
    deleted = await delete_user_fact(99999, "nonexistent")
    assert deleted is False


@pytest.mark.asyncio
async def test_get_recent_facts():
    """时间窗口过滤。"""
    await _cleanup(9906)
    await save_facts(9906, [
        {"key": "recent", "value": "today", "confidence": 0.9},
    ])
    facts = await get_recent_facts(9906, days=30)
    assert any(f["key"] == "recent" for f in facts)

    facts_old = await get_recent_facts(9906, days=0)
    # 0 days 范围 = 几乎空
    assert not any(f["key"] == "recent" for f in facts_old)


@pytest.mark.asyncio
async def test_fact_count_per_user():
    """统计每用户 fact 数。"""
    await _cleanup(9907)
    await save_facts(9907, [
        {"key": "k1", "value": "v1", "confidence": 0.9},
        {"key": "k2", "value": "v2", "confidence": 0.9},
    ])
    counts = await fact_count_per_user()
    assert counts.get(9907) == 2


@pytest.mark.asyncio
async def test_merge_similar_facts():
    """相似 fact 自动合并。"""
    await _cleanup(9908)
    # 两条语义极相似的 fact（用 unique key 避免 save_facts 视为 update）
    await save_facts(9908, [
        {"key": "hair_concern_a", "value": "我不喜欢短刘海", "confidence": 0.5},
        {"key": "hair_concern_b", "value": "短刘海显脸大不喜欢", "confidence": 0.8},
    ])
    before = await get_user_facts(9908)
    assert len(before) == 2
    # 自动合并
    await merge_similar_facts(9908, similarity_threshold=0.7)
    after = await get_user_facts(9908)
    # 1 个被合并 = 剩 1 个
    assert len(after) == 1
    # 保留高 confidence 的
    assert after[0]["confidence"] == 0.8
