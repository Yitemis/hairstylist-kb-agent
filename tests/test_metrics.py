# -*- coding: utf-8 -*-
"""Prometheus 监控端点测试。"""
import pytest
from fastapi.testclient import TestClient

from app.server.api import app
from app.core.metrics import (
    chat_requests_total,
    tool_calls_total,
    llm_tokens_total,
    rag_retrievals_total,
)


def test_metrics_endpoint_exists():
    """/metrics 端点存在 + 返回 Prometheus 格式。"""
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    # Prometheus text format content-type
    ct = r.headers.get("content-type", "")
    assert "text/plain" in ct or "openmetrics" in ct
    body = r.text
    # 必须有 HELP 和 TYPE 注释（标准 Prometheus 格式）
    assert "# HELP" in body
    assert "# TYPE" in body


def test_metrics_includes_core_counters():
    """/metrics 暴露核心 Counter 指标。"""
    client = TestClient(app)
    # 先触发一些指标
    chat_requests_total.labels(mode="test", result="success").inc()
    tool_calls_total.labels(tool_name="test", result="ok").inc()
    llm_tokens_total.labels(model="test-model", role="prompt").inc()
    rag_retrievals_total.labels(tenant_id="test", result="success").inc()

    r = client.get("/metrics")
    body = r.text
    assert "chat_requests_total" in body
    assert "tool_calls_total" in body
    assert "llm_tokens_total" in body
    assert "rag_retrievals_total" in body


def test_metrics_includes_histograms():
    """/metrics 暴露 Histogram（chat_request_duration_seconds 等）。"""
    client = TestClient(app)
    chat_request_duration_seconds = pytest.importorskip("app.core.metrics").chat_request_duration_seconds
    chat_request_duration_seconds.labels(mode="test").observe(0.5)
    r = client.get("/metrics")
    body = r.text
    assert "chat_request_duration_seconds" in body
    # Histogram 一定有 _bucket / _count / _sum
    assert "chat_request_duration_seconds_bucket" in body
    assert "chat_request_duration_seconds_count" in body
    assert "chat_request_duration_seconds_sum" in body


def test_metrics_includes_gauges():
    """/metrics 暴露 Gauge 指标。"""
    client = TestClient(app)
    from app.core.metrics import active_sessions, memory_facts_total
    active_sessions.set(10)
    memory_facts_total.labels(user_id="1").set(5)
    r = client.get("/metrics")
    body = r.text
    assert "active_sessions" in body
    assert "memory_facts_total" in body


def test_rag_retrieval_increments_counter():
    """RAG retrieve 后 rag_retrievals_total 增加。"""
    import asyncio
    from app.rag.v2_engine import index_document, retrieve, reset_state
    from app.core.metrics import rag_retrievals_total

    reset_state()
    # 获取测试前的 counter 值
    before = _get_counter_value(rag_retrievals_total, tenant_id="metrics_test", result="success")
    after_expected = before + 1

    async def run():
        await index_document(
            "metrics_doc", "## 测试\n## 内容",
            filename="m.pdf", tenant_id="metrics_test", category="test",
        )
        r = await retrieve("测试", "metrics_test", top_k=2)
        return r

    asyncio.run(run())
    after = _get_counter_value(rag_retrievals_total, tenant_id="metrics_test", result="success")
    assert after >= after_expected, f"counter 未增加: before={before}, after={after}"


def _get_counter_value(counter, **labels) -> float:
    """Helper: 读 Counter 当前值。"""
    try:
        return counter.labels(**labels)._value.get()
    except (KeyError, AttributeError):
        return 0.0
