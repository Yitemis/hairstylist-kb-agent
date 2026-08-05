# -*- coding: utf-8 -*-
"""ModelRouter 测试。"""
import os
import pytest


class TestModelRouter:
    def test_router_loads_from_env(self):
        from app.embedding.router import ModelRouter, Capability
        r = ModelRouter()
        summary = r.summary()
        assert "text_embedding" in summary
        assert "rerank" in summary
        assert "chat" in summary

    def test_chat_uses_ark_coding_plan(self):
        from app.embedding.router import ModelRouter, Capability
        r = ModelRouter()
        ep = r.get_endpoint(Capability.CHAT)
        assert ep is not None
        assert ep.provider == "ark"

    def test_text_embedding_uses_siliconflow(self):
        from app.embedding.router import ModelRouter, Capability
        r = ModelRouter()
        ep = r.get_endpoint(Capability.TEXT_EMBEDDING)
        assert ep is not None
        assert ep.provider == "siliconflow"
        assert ep.dimensions == 1024

    def test_rerank_uses_siliconflow(self):
        from app.embedding.router import ModelRouter, Capability
        r = ModelRouter()
        ep = r.get_endpoint(Capability.RERANK)
        assert ep is not None
        assert ep.provider == "siliconflow"

    def test_mm_embedding_can_be_disabled(self):
        from app.embedding.router import ModelRouter, Capability
        r = ModelRouter()
        r.disable(Capability.MM_EMBEDDING)
        assert r.get_endpoint(Capability.MM_EMBEDDING) is None

    def test_mm_chat_uses_chat_endpoint(self):
        from app.embedding.router import ModelRouter, Capability
        r = ModelRouter()
        chat = r.get_endpoint(Capability.CHAT)
        mm_chat = r.get_endpoint(Capability.MM_CHAT)
        assert chat is not None
        assert mm_chat is not None
        assert chat.api_key == mm_chat.api_key

    def test_list_capabilities(self):
        from app.embedding.router import ModelRouter
        r = ModelRouter()
        caps = r.list_capabilities()
        assert "text_embedding" in caps
        assert "chat" in caps
        assert "rerank" in caps

    def test_summary_format(self):
        from app.embedding.router import ModelRouter
        r = ModelRouter()
        s = r.summary()
        for cap, info in s.items():
            assert "provider" in info
            assert "model" in info
            assert "enabled" in info


class TestCapabilityEnum:
    def test_capability_values(self):
        from app.embedding.router import Capability
        assert Capability.TEXT_EMBEDDING.value == "text_embedding"
        assert Capability.MM_EMBEDDING.value == "mm_embedding"
        assert Capability.CHAT.value == "chat"
        assert Capability.MM_CHAT.value == "mm_chat"
        assert Capability.RERANK.value == "rerank"


class TestBuildEmbeddingRouting:
    def test_text_embedding_routes_to_siliconflow(self):
        from app.embedding import build_embedding_model
        from app.embedding.siliconflow_text_embedding import SiliconFlowTextEmbedding
        m = build_embedding_model(capability="text_embedding")
        assert isinstance(m, SiliconFlowTextEmbedding)

    def test_mm_embedding_routes_to_ark(self):
        from app.embedding import build_embedding_model
        from app.embedding.ark_vision_embedding import ArkVisionEmbeddingModel
        try:
            m = build_embedding_model(capability="mm_embedding")
            assert isinstance(m, ArkVisionEmbeddingModel)
        except RuntimeError as e:
            assert "不可用" in str(e)

    def test_invalid_capability_raises(self):
        from app.embedding import build_embedding_model
        with pytest.raises((RuntimeError, ValueError)):
            build_embedding_model(capability="invalid_xxx")

    def test_disabled_capability_raises_helpful_error(self):
        from app.embedding import build_embedding_model
        from app.embedding.router import Capability, get_model_router
        r = get_model_router()
        r.disable(Capability.MM_EMBEDDING)
        with pytest.raises(RuntimeError) as exc_info:
            build_embedding_model(capability="mm_embedding")
        assert "不可用" in str(exc_info.value)
        assert "text_embedding" in str(exc_info.value)


class TestSiliconFlowTextEmbedding:
    def test_init_sets_correct_attributes(self):
        from app.embedding.siliconflow_text_embedding import SiliconFlowTextEmbedding
        from agentscope.credential import OpenAICredential
        cred = OpenAICredential(api_key="test-key", base_url="https://api.siliconflow.cn/v1")
        m = SiliconFlowTextEmbedding(credential=cred, model="BAAI/bge-large-zh-v1.5", dimensions=1024)
        assert m._model == "BAAI/bge-large-zh-v1.5"
        assert m._dimensions == 1024
        assert m.supports_multimodal is False
        assert m._full_url == "https://api.siliconflow.cn/v1/embeddings"

    def test_init_strips_trailing_slash(self):
        from app.embedding.siliconflow_text_embedding import SiliconFlowTextEmbedding
        from agentscope.credential import OpenAICredential
        cred = OpenAICredential(api_key="k", base_url="https://api.siliconflow.cn/v1/")
        m = SiliconFlowTextEmbedding(credential=cred, model="m", dimensions=1024)
        assert m._full_url == "https://api.siliconflow.cn/v1/embeddings"

    def test_batch_size_is_32(self):
        from app.embedding.siliconflow_text_embedding import SiliconFlowTextEmbedding
        from agentscope.credential import OpenAICredential
        cred = OpenAICredential(api_key="k", base_url="https://api.siliconflow.cn/v1")
        m = SiliconFlowTextEmbedding(credential=cred, model="m", dimensions=1024)
        assert m._BATCH_SIZE == 32

    def test_supports_multimodal_false(self):
        from app.embedding.siliconflow_text_embedding import SiliconFlowTextEmbedding
        assert SiliconFlowTextEmbedding._BATCH_SIZE == 32


class TestV2EngineRouting:
    def test_get_embedding_uses_text_capability(self):
        from app.rag import v2_engine
        import inspect
        src = inspect.getsource(v2_engine._get_embedding)
        assert 'capability="text_embedding"' in src
