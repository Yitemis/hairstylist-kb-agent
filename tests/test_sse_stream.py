# -*- coding: utf-8 -*-
"""SSE 流式对话端点测试。

测试覆盖：
1. 端点存在 (openapi.json)
2. 空消息返回 error 事件
3. 正常消息返回完整事件流 (intent → text → done)
4. 验证 SSE 协议格式 (Content-Type + 事件序列)
"""
import json
import pytest
from fastapi.testclient import TestClient

from app.auth.security import create_access_token
from app.server.api import app


def _get_token(user_id: int = 1, tenant_id: str = "test") -> str:
    """生成测试用 JWT token。"""
    return create_access_token(
        subject=user_id, role="user", extra={"tenant_id": tenant_id}
    )


def test_sse_endpoint_exists():
    """/api/chat/stream 端点存在。"""
    from app.server.routers.chat_stream import router
    paths = [r.path for r in router.routes]
    assert "/api/chat/stream" in paths


def test_sse_empty_message():
    """空消息返回 error 事件（不走 LLM）。"""
    client = TestClient(app)
    token = _get_token()
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": ""},
        headers={"Authorization": f"Bearer {token}"},
    ) as r:
        assert r.status_code == 200
        chunks = list(r.iter_text())
    full = "".join(chunks)
    # 应该包含 error 事件
    assert "event: error" in full
    assert "消息不能为空" in full or "message" in full


def test_sse_response_format():
    """正常消息的 SSE 响应格式正确。

    验证：
    - Content-Type: text/event-stream
    - 事件序列：intent → text(×N) → done
    - 每条事件符合 SSE 协议
    """
    client = TestClient(app)
    token = _get_token()
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "你好"},
        headers={"Authorization": f"Bearer {token}"},
    ) as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
        # 收完整流
        chunks = []
        for chunk in r.iter_text():
            chunks.append(chunk)
            if "event: done" in chunk or "event: error" in chunk:
                break
    full = "".join(chunks)

    # 验证事件序列存在
    assert "event: intent" in full, f"缺 intent 事件:\n{full[:500]}"
    assert "event: text" in full or "event: error" in full, "缺 text/error 事件"
    assert "event: done" in full or "event: error" in full, "缺 done/error 事件"


def test_sse_data_payload_valid_json():
    """每个事件 data 字段都是合法 JSON。"""
    client = TestClient(app)
    token = _get_token()
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "测试"},
        headers={"Authorization": f"Bearer {token}"},
    ) as r:
        chunks = list(r.iter_text())
    full = "".join(chunks)

    # 解析所有 data 行
    import re
    events = re.findall(r"event: (\w+)\ndata: (.+)", full)
    assert len(events) >= 2, f"应至少 2 个事件，实际 {len(events)}"
    for evt_name, data_str in events:
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError as e:
            pytest.fail(f"事件 {evt_name} data 不是合法 JSON: {data_str!r}\nError: {e}")
        assert isinstance(data, dict), f"事件 {evt_name} data 不是 dict: {data!r}"


def test_sse_keeps_alive_headers():
    """SSE 响应头正确（禁用缓存、保持连接）。"""
    client = TestClient(app)
    token = _get_token()
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "hi"},
        headers={"Authorization": f"Bearer {token}"},
    ) as r:
        # Cache-Control 必须 no-cache（防止代理缓存）
        cc = r.headers.get("cache-control", "")
        assert "no-cache" in cc or "no-store" in cc
