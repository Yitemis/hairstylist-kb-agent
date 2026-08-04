"""MinerU 多后端客户端测试。

覆盖：
- 工厂方法（get_mineru_backend）按环境变量返回正确后端
- 3 种后端在不可用时返回空列表（不抛异常）
- 默认是 local 后端
- 重置缓存
"""
import os
import pytest
from unittest.mock import patch


def test_default_backend_is_local():
    """默认环境变量下应该是 local 后端。"""
    from app.rag.parsers.mineru_backends import (
        get_mineru_backend, reset_mineru_backend
    )
    reset_mineru_backend()
    os.environ.pop("MINERU_BACKEND", None)
    backend = get_mineru_backend()
    assert "local" in backend.name.lower(), f"默认应该是 local，实际: {backend.name}"
    assert "默认" in backend.name or "default" in backend.name.lower()


def test_cloud_backend_requires_token():
    """cloud 后端必须有 token，否则抛 ValueError。"""
    from app.rag.parsers.mineru_backends import (
        MinerUCloudBackend, reset_mineru_backend
    )
    reset_mineru_backend()
    with pytest.raises(ValueError, match="MINERU_API_TOKEN"):
        MinerUCloudBackend("")


def test_http_backend_requires_url():
    """http 后端必须有 URL，否则抛 ValueError。"""
    from app.rag.parsers.mineru_backends import (
        MinerUHttpBackend, reset_mineru_backend
    )
    reset_mineru_backend()
    with pytest.raises(ValueError, match="MINERU_HTTP_URL"):
        MinerUHttpBackend("")


def test_local_backend_fallback_when_not_installed():
    """mineru[all] 没装时，local 后端返回空列表。"""
    from app.rag.parsers.mineru_backends import (
        MinerULocalBackend, reset_mineru_backend
    )
    reset_mineru_backend()
    backend = MinerULocalBackend()
    if not backend._available:
        result = backend.parse(b"fake pdf binary", "test.pdf")
        assert result == []


def test_factory_respects_env():
    """工厂方法根据 MINERU_BACKEND 环境变量返回对应后端。"""
    from app.rag.parsers.mineru_backends import (
        get_mineru_backend, reset_mineru_backend,
        MinerUCloudBackend, MinerUHttpBackend, MinerULocalBackend,
    )

    # 测 local
    reset_mineru_backend()
    os.environ["MINERU_BACKEND"] = "local"
    backend = get_mineru_backend()
    assert isinstance(backend, MinerULocalBackend)

    # 测 http
    reset_mineru_backend()
    os.environ["MINERU_BACKEND"] = "http"
    os.environ["MINERU_HTTP_URL"] = "http://test:30000"
    backend = get_mineru_backend()
    assert isinstance(backend, MinerUHttpBackend)

    # 测 cloud
    reset_mineru_backend()
    os.environ["MINERU_BACKEND"] = "cloud"
    os.environ["MINERU_API_TOKEN"] = "test_token"
    backend = get_mineru_backend()
    assert isinstance(backend, MinerUCloudBackend)

    # 清理
    reset_mineru_backend()
    os.environ.pop("MINERU_BACKEND", None)
    os.environ.pop("MINERU_HTTP_URL", None)
    os.environ.pop("MINERU_API_TOKEN", None)


def test_reset_clears_cache():
    """reset_mineru_backend 应该清除缓存，下次重新创建。"""
    from app.rag.parsers import mineru_backends as mb
    mb.reset_mineru_backend()
    assert mb._cache is None
    b1 = mb.get_mineru_backend()
    assert mb._cache is b1
    mb.reset_mineru_backend()
    assert mb._cache is None
    b2 = mb.get_mineru_backend()
    assert b1 is not b2  # 新实例


def test_cloud_backend_parse_handles_network_error():
    """cloud 后端网络错误时返回空列表，不抛异常。"""
    from app.rag.parsers.mineru_backends import (
        MinerUCloudBackend, reset_mineru_backend
    )
    reset_mineru_backend()
    backend = MinerUCloudBackend("fake_token")
    # 不 mock，让它真的去连网络（应该会失败但不抛）
    result = backend.parse(b"fake", "test.pdf")
    assert result == []  # 不抛异常，返回空


def test_http_backend_parse_handles_network_error():
    """http 后端连接失败时返回空列表。"""
    from app.rag.parsers.mineru_backends import (
        MinerUHttpBackend, reset_mineru_backend
    )
    reset_mineru_backend()
    backend = MinerUHttpBackend("http://nonexistent-host-12345:9999")
    result = backend.parse(b"fake", "test.pdf")
    assert result == []  # 不抛异常
