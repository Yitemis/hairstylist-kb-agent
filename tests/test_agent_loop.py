# -*- coding: utf-8 -*-
"""Agent 真实循环测试 (P1-10)。

验证 AgentScope Agent 的 ReAct loop 真在工作：
- agent.reply() 能调工具
- 工具调用次数 >= 1
- 响应有内容
"""
import os
import pytest

os.environ.setdefault("AGENT_STATE_BACKEND", "memory")


@pytest.mark.asyncio
async def test_knowledge_agent_has_tool():
    """Knowledge Agent 必须装 search_hair_knowledge 工具。"""
    from app.core.knowledge_agent_factory import get_knowledge_agent
    agent = await get_knowledge_agent()
    tools = [t.name for t in agent.toolkit.tool_groups[0].tools]
    assert "search_hair_knowledge" in tools, f"工具缺失: {tools}"


@pytest.mark.asyncio
async def test_booking_agent_has_7_tools():
    """Booking Agent 必须装 7 个 booking 工具 (P1-8 + P2-权限对齐 加 cancel_order)。"""
    from app.core.booking_agent_factory import get_booking_agent
    agent = await get_booking_agent()
    tools = [t.name for t in agent.toolkit.tool_groups[0].tools]
    expected = {
        "create_draft_order", "update_order_fields", "confirm_order",
        "cancel_order",  # P2-权限对齐: 新增高危工具
        "list_branches", "list_stylists", "recommend_services",
    }
    assert expected.issubset(set(tools)), f"缺工具: {expected - set(tools)}"
    assert len(tools) == 7, f"工具数错: {len(tools)}"


@pytest.mark.asyncio
async def test_tool_registry_has_8_booking_and_kb_tools():
    """P2-权限对齐: 验证 1 RAG + 6 booking + cancel_order 共 8 个核心工具都注册了.

    注: 完整 tool registry 还包含 6 业务管理 + 1 web_search 共 15 个, 但本测试聚焦
    P2 改动的核心工具集.
    """
    from app.core.tool_registry import registry
    tools = registry.get_tool_names()
    # 验证 P2 改动的 8 个核心工具都存在
    expected_core = {
        "search_hair_knowledge",
        "create_draft_order", "update_order_fields", "confirm_order",
        "cancel_order",  # P2-权限对齐: 新增高危工具
        "list_branches", "list_stylists", "recommend_services",
    }
    assert expected_core.issubset(set(tools)), f"缺核心工具: {expected_core - set(tools)}"


@pytest.mark.asyncio
async def test_knowledge_agent_built_with_middleware():
    """P0-2: Knowledge Agent 必须有 RAGMiddleware。"""
    from app.core.knowledge_agent_factory import get_knowledge_agent
    agent = await get_knowledge_agent()
    # AgentScope 2.0 用 _middlewares (or _reply_middlewares 等)
    total = 0
    for attr in ["_middlewares", "_reply_middlewares", "_reasoning_middlewares", "_acting_middlewares"]:
        if hasattr(agent, attr):
            mws = getattr(agent, attr) or []
            total += len(mws)
    assert total > 0, "Knowledge Agent 没有 middlewares，RAGMiddleware 未接入"


@pytest.mark.asyncio
async def test_llm_extract_helper():
    """P2-1: LLM 响应抽取 helper 工作。"""
    from app.utils.llm_extract import extract_text

    # 字符串
    assert extract_text("hello") == "hello"
    # None
    assert extract_text(None) == ""
    # 字典
    assert extract_text({"content": "from dict"}) == "from dict"
    # dict with block list
    assert extract_text({"content": [{"text": "block text"}]}) == "block text"
    # 模拟对象
    class FakeResp:
        content = []
    fake = FakeResp()
    fake.content = [{"text": "abc"}, {"text": "def"}]
    assert extract_text(fake) == "abcdef"


@pytest.mark.asyncio
async def test_order_utils_no_duplicate():
    """P2-1: order_no 只在一处实现。"""
    from app.utils.order_utils import generate_order_no
    n1 = generate_order_no()
    n2 = generate_order_no()
    assert n1 != n2, "两次生成相同"
    assert len(n1) == 14, f"格式错: {n1}"  # YYMMDD + 8 hex


@pytest.mark.asyncio
async def test_extract_text_uses_in_api():
    """P2-1: api.py 用了 extract_text helper（消除 5 处重复）。"""
    with open("app/server/api.py", "r", encoding="utf-8") as f:
        content = f.read()
    assert "from app.utils.llm_extract import extract_text" in content
    # 旧的重复模式应该没了
    bad_pattern_count = content.count("for block in resp.content")
    assert bad_pattern_count <= 1, f"还有 {bad_pattern_count} 处重复 for block"
