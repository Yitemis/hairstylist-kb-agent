# -*- coding: utf-8 -*-
"""Permission tag unit tests (P0)."""
import pytest

from app.db.enums import (
    PermissionTag,
    ROLE_PERMISSION_MATRIX,
    can_access,
    filter_by_role,
)


class TestPermissionTag:
    def test_all_tags(self):
        assert PermissionTag.PUBLIC.value == "public"
        assert PermissionTag.INTERNAL.value == "internal"
        assert PermissionTag.CONFIDENTIAL.value == "confidential"

    def test_tag_count(self):
        assert len(PermissionTag) == 3


class TestCanAccess:
    """Test role-based access control (借鉴九阳 POC §5)."""

    def test_user_can_access_public(self):
        assert can_access("user", "public") is True

    def test_user_cannot_access_internal(self):
        assert can_access("user", "internal") is False

    def test_user_cannot_access_confidential(self):
        assert can_access("user", "confidential") is False

    def test_staff_can_access_public(self):
        assert can_access("staff", "public") is True

    def test_staff_can_access_internal(self):
        assert can_access("staff", "internal") is True

    def test_staff_cannot_access_confidential(self):
        assert can_access("staff", "confidential") is False

    def test_admin_can_access_all(self):
        for tag in ["public", "internal", "confidential"]:
            assert can_access("admin", tag) is True

    def test_unknown_role_cannot_access(self):
        assert can_access("unknown_role", "public") is False

    def test_unknown_tag_returns_false(self):
        """未知 tag 保守处理: 拒绝."""
        assert can_access("user", "unknown_tag") is False


class TestRoleMatrix:
    def test_user_only_public(self):
        assert ROLE_PERMISSION_MATRIX["user"] == {PermissionTag.PUBLIC}

    def test_staff_public_internal(self):
        assert ROLE_PERMISSION_MATRIX["staff"] == {
            PermissionTag.PUBLIC, PermissionTag.INTERNAL
        }

    def test_admin_all_three(self):
        assert ROLE_PERMISSION_MATRIX["admin"] == {
            PermissionTag.PUBLIC,
            PermissionTag.INTERNAL,
            PermissionTag.CONFIDENTIAL,
        }


class TestFilterByRole:
    """Test document list filtering by role."""

    def test_dict_input(self):
        docs = [
            {"id": 1, "permission_tag": "public"},
            {"id": 2, "permission_tag": "internal"},
            {"id": 3, "permission_tag": "confidential"},
        ]
        out = filter_by_role(docs, "user")
        assert len(out) == 1
        assert out[0]["id"] == 1

    def test_staff_filter(self):
        docs = [
            {"id": 1, "permission_tag": "public"},
            {"id": 2, "permission_tag": "internal"},
            {"id": 3, "permission_tag": "confidential"},
        ]
        out = filter_by_role(docs, "staff")
        assert len(out) == 2
        assert {d["id"] for d in out} == {1, 2}

    def test_admin_sees_all(self):
        docs = [
            {"id": 1, "permission_tag": "public"},
            {"id": 2, "permission_tag": "internal"},
            {"id": 3, "permission_tag": "confidential"},
        ]
        out = filter_by_role(docs, "admin")
        assert len(out) == 3

    def test_default_tag_is_public(self):
        """无 permission_tag 字段, 默认为 public."""
        docs = [{"id": 1}]  # no permission_tag
        out = filter_by_role(docs, "user")
        assert len(out) == 1  # user can see public

    def test_empty_list(self):
        assert filter_by_role([], "user") == []
