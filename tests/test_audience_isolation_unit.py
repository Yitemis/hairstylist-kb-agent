# -*- coding: utf-8 -*-
"""Audience 隔离 - 纯单元测试（不调 embedding API，避免欠费）。"""
import pytest

from app.rag.multimodal_chat import (
    get_audience_for_user, get_system_prompt,
    build_image_blocks, build_multimodal_messages, encode_image_to_b64,
)


# ===================================================================
# RBAC 隔离 - 核心逻辑
# ===================================================================

class TestAudienceMapping:
    def test_user_role_maps_to_user_audience(self):
        assert get_audience_for_user(is_staff=False) == "user"

    def test_staff_role_maps_to_staff_audience(self):
        assert get_audience_for_user(is_staff=True) == "staff"

    def test_admin_role_maps_to_staff_audience(self):
        # admin 视为 staff (有操作权限)
        assert get_audience_for_user(is_staff=True) == "staff"


class TestAudienceFilter:
    """C 端只看 user + all，商家看 staff + all。"""

    def test_user_audience_filter_includes_user_and_all(self):
        is_staff = False
        audience = get_audience_for_user(is_staff)
        audience_filter = [audience, "all"]
        assert "user" in audience_filter
        assert "all" in audience_filter
        assert "staff" not in audience_filter  # 看不到商家

    def test_staff_audience_filter_includes_staff_and_all(self):
        is_staff = True
        audience = get_audience_for_user(is_staff)
        audience_filter = [audience, "all"]
        assert "staff" in audience_filter
        assert "all" in audience_filter
        assert "user" not in audience_filter  # 看不到 C 端专属

    def test_filter_safety_no_cross_contamination(self):
        """核心安全测试：user 和 staff 的 filter 完全不同。"""
        user_filter = [get_audience_for_user(False), "all"]
        staff_filter = [get_audience_for_user(True), "all"]
        # user filter 不含 staff
        assert "staff" not in user_filter
        # staff filter 不含 user
        assert "user" not in staff_filter
        # 唯一交集 = all
        assert set(user_filter) & set(staff_filter) == {"all"}


class TestSystemPromptIsolation:
    def test_user_prompt_friendly_avoid_tech(self):
        p = get_system_prompt(is_staff=False)
        assert "C 端" in p
        assert "友好" in p or "易懂" in p

    def test_staff_prompt_professional_detailed(self):
        p = get_system_prompt(is_staff=True)
        assert "商家" in p or "员工" in p
        assert "专业" in p or "详细" in p

    def test_prompts_are_different(self):
        assert get_system_prompt(False) != get_system_prompt(True)


class TestMultimodalMessageBuilding:
    def test_text_only_message(self):
        msgs = build_multimodal_messages(text="hello", system_prompt="sys")
        assert len(msgs) == 2
        assert msgs[1]["content"] == [{"type": "text", "text": "hello"}]

    def test_message_with_knowledge_context(self):
        msgs = build_multimodal_messages(
            text="q", knowledge_context="水温 38-40 度",
        )
        assert "知识库参考" in msgs[0]["content"]
        assert "38-40 度" in msgs[0]["content"]

    def test_image_blocks_from_b64(self):
        blocks = build_image_blocks([], ["data:image/jpeg;base64,abc"])
        assert len(blocks) == 1
        assert blocks[0]["type"] == "image_url"
        assert "image/jpeg" in blocks[0]["image_url"]["url"]

    def test_image_blocks_from_bare_b64(self):
        # 长度 > 100 才会被认为是有效 base64
        b64 = "a" * 200
        blocks = build_image_blocks([], [b64])
        assert len(blocks) == 1
        assert blocks[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    def test_image_blocks_empty(self):
        assert build_image_blocks([], []) == []

    def test_image_blocks_nonexistent_path_skipped(self):
        # 不存在的路径应该被跳过
        blocks = build_image_blocks(["/nonexistent/xxx.jpg"], [])
        assert blocks == []


class TestDocumentAudienceModel:
    """Document / ImageChunk 模型的 audience 字段。"""
    def test_document_has_audience_field(self):
        from app.db.models import Document
        from sqlalchemy import inspect
        cols = {c.name: c for c in inspect(Document).columns}
        assert "audience" in cols
        assert cols["audience"].nullable is False
        # default 应是 "all"
        assert cols["audience"].default.arg == "all"

    def test_image_chunk_has_audience_field(self):
        from app.db.models import ImageChunk
        from sqlalchemy import inspect
        cols = {c.name: c for c in inspect(ImageChunk).columns}
        assert "audience" in cols
        assert cols["audience"].nullable is False
        assert cols["audience"].default.arg == "all"


class TestRAGSignature:
    """RAG 函数签名支持 audience 过滤。"""
    def test_retrieve_accepts_audience_filter(self):
        from app.rag.v2_engine import retrieve
        import inspect
        sig = inspect.signature(retrieve)
        assert "audience_filter" in sig.parameters
        # 默认值应是 None (不过滤)
        assert sig.parameters["audience_filter"].default is None

    def test_index_document_accepts_audience(self):
        from app.rag.v2_engine import index_document
        import inspect
        sig = inspect.signature(index_document)
        assert "audience" in sig.parameters
        assert sig.parameters["audience"].default == "all"


class TestMilvusStoreAudienceSupport:
    """MilvusStore 支持 audience filter。"""
    def test_milvus_store_has_audience_key(self):
        from app.rag.milvus_store import AUDIENCE_KEY
        assert AUDIENCE_KEY == "audience"

    def test_search_accepts_audience_filter(self):
        from app.rag.milvus_store import MilvusStore
        import inspect
        sig = inspect.signature(MilvusStore.search)
        assert "audience_filter" in sig.parameters
