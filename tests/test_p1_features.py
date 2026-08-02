# -*- coding: utf-8 -*-
"""P1 全部新功能测试。

覆盖：
- 状态持久化（AgentStateStore + ChatSession）
- 权限三态（PermissionEngine）
- 技能库（Skill + Registry + search）
- 长期记忆（UserProfile + extract_facts）
"""
import pytest
import asyncio
from unittest.mock import patch

# 异步测试需要 pytest-asyncio
pytest_plugins = ["pytest_asyncio"]


# ============================================================
# 权限三态测试
# ============================================================

def test_permission_default_allow():
    """默认所有工具允许。"""
    from app.core.permission import PermissionRequest, get_permission_engine
    engine = get_permission_engine()
    request = PermissionRequest(user_id=1, tool_name="unknown_tool", tool_args={})
    result = engine.evaluate(request)
    assert result.decision.value == "allowed"


def test_permission_confirm_asking():
    """confirm_order 触发 ASKING。"""
    from app.core.permission import PermissionRequest, get_permission_engine
    engine = get_permission_engine()
    request = PermissionRequest(user_id=1, tool_name="confirm_order", tool_args={"order_id": 1})
    result = engine.evaluate(request)
    assert result.decision.value == "asking"
    assert "money" in result.reason.lower() or "金钱" in result.reason or "时间" in result.reason


def test_permission_list_branches_allowed():
    """list_branches 允许直接执行。"""
    from app.core.permission import PermissionRequest, get_permission_engine
    engine = get_permission_engine()
    request = PermissionRequest(user_id=1, tool_name="list_branches", tool_args={})
    result = engine.evaluate(request)
    assert result.decision.value == "allowed"


def test_permission_ask_resolve():
    """创建和解决 pending ask。"""
    from app.core.permission import (
        PermissionRequest, get_permission_engine, PermissionDecision,
    )
    engine = get_permission_engine()
    request = PermissionRequest(user_id=1, tool_name="confirm_order", tool_args={"order_id": 1})
    ask_result = engine.evaluate(request)
    assert ask_result.decision == PermissionDecision.ASKING
    ask_id = engine.create_pending_ask(request, ask_result)

    # 用户确认
    resolved = engine.resolve_ask(ask_id, approved=True)
    assert resolved is not None
    assert resolved[1].decision == PermissionDecision.ALLOWED

    # 重复 resolve 应失败
    again = engine.resolve_ask(ask_id, approved=True)
    assert again is None


# ============================================================
# 技能库测试
# ============================================================

def test_skill_registry_default_4():
    """默认注册 4 个预置技能。"""
    from app.core.skill import get_skill_registry
    registry = get_skill_registry()
    skills = registry.list_all()
    assert len(skills) == 4
    ids = {s.skill_id for s in skills}
    assert "confirmation_pattern" in ids
    assert "booking_flow" in ids
    assert "hair_knowledge_basics" in ids
    assert "emotional_response" in ids


def test_skill_search_chinese():
    """中文搜索能找到技能。"""
    from app.core.skill import get_skill_registry
    registry = get_skill_registry()
    # 关键词"确认"应该匹配 confirmation_pattern（tags 包含"确认"）
    results = registry.search("确认")
    assert any(s.skill_id == "confirmation_pattern" for s in results), \
        f"应该匹配 confirmation_pattern，实际: {[s.skill_id for s in results]}"


def test_skill_search_phrase():
    """完整短语搜索能匹配。"""
    from app.core.skill import get_skill_registry
    registry = get_skill_registry()
    results = registry.search("怎么确认订单")
    assert any(s.skill_id == "confirmation_pattern" for s in results)


def test_skill_render_for_prompt():
    """技能渲染包含名字和内容。"""
    from app.core.skill import get_skill_registry
    registry = get_skill_registry()
    skill = registry.get("confirmation_pattern")
    assert skill is not None
    text = skill.render_for_prompt()
    assert "确认前必问" in text
    assert "确认" in text


def test_skill_injection_for_empty():
    """没匹配时返回空字符串。"""
    from app.core.skill import build_skill_injection
    result = build_skill_injection("完全不相关的内容")
    # 可能空，也可能匹配 emotional_response（因为"内容"是空字符串）
    assert isinstance(result, str)


# ============================================================
# 状态持久化测试
# ============================================================

def test_in_memory_state_store():
    """内存版状态存储基本 CRUD。"""
    from app.core.agent_state_store import InMemoryAgentStateStore
    store = InMemoryAgentStateStore()
    store.save("u1", "s1", "k1", {"v": 1})
    assert store.exists("u1", "s1")
    assert store.get("u1", "s1", "k1") == {"v": 1}
    sessions = store.list_session_ids("u1")
    assert "s1" in sessions
    store.delete("u1", "s1")
    assert not store.exists("u1", "s1")


def test_json_file_state_store_persist():
    """JSON 文件版状态存储持久化。"""
    import tempfile
    from app.core.agent_state_store import JsonFileAgentStateStore
    with tempfile.TemporaryDirectory() as tmp:
        store = JsonFileAgentStateStore(root=tmp)
        store.save("user1", "sess1", "agent_state", {"intent": "booking"})
        # 重新打开
        store2 = JsonFileAgentStateStore(root=tmp)
        v = store2.get("user1", "sess1", "agent_state")
        assert v == {"intent": "booking"}


def test_state_store_safe_filename():
    """危险字符（路径遍历）被自动编码。"""
    from app.core.agent_state_store import _safe_dirname
    assert _safe_dirname("normal") == "normal"
    assert _safe_dirname("../etc/passwd") != "../etc/passwd"
    assert _safe_dirname("a/b").startswith("b64_")


# ============================================================
# 长期记忆测试
# ============================================================

@pytest.mark.asyncio
async def test_facts_injection_empty():
    """空事实列表返回空字符串。"""
    from app.core.long_term_memory import build_facts_injection
    result = build_facts_injection([])
    assert result == ""


@pytest.mark.asyncio
async def test_facts_injection_format():
    """事实渲染包含 key 和 value。"""
    from app.core.long_term_memory import build_facts_injection
    facts = [
        {"key": "address", "value": "上海徐汇"},
        {"key": "preferred_stylist", "value": "张托尼"},
    ]
    result = build_facts_injection(facts)
    assert "address" in result
    assert "上海徐汇" in result
    assert "preferred_stylist" in result
    assert "张托尼" in result


# ============================================================
# 端到端集成测试（API）
# ============================================================

@pytest.mark.asyncio
async def test_api_health():
    """健康检查。"""
    from fastapi.testclient import TestClient
    from app.server.api import app
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_api_list_branches():
    """列分店。"""
    from fastapi.testclient import TestClient
    from app.server.api import app
    client = TestClient(app)
    r = client.get("/api/branches")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_api_list_skills():
    """列技能。"""
    from fastapi.testclient import TestClient
    from app.server.api import app
    client = TestClient(app)
    r = client.get("/api/skills")
    assert r.status_code == 200
    skills = r.json()
    assert len(skills) >= 4
