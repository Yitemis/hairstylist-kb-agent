# -*- coding: utf-8 -*-
"""IndexAlias 单测 (Harness v2 sec 7.3)."""
import pytest

from app.rag.index_alias import (
    IndexAlias, AliasSwitchResult, get_index_alias,
)


class TestAliasSwitchResult:
    def test_default_values(self):
        r = AliasSwitchResult(action="switch", from_alias="v1", to_alias="v2")
        assert r.action == "switch"
        assert r.from_alias == "v1"
        assert r.to_alias == "v2"
        assert r.switched_count == 0
        assert r.dry_run is True
        assert r.error is None
        assert r.timestamp == ""


class TestIndexAliasClass:
    def test_constants(self):
        assert IndexAlias.DEFAULT_ALIAS == "prod"
        assert IndexAlias.ROLLBACK_WINDOW_DAYS == 7

    def test_init(self):
        m = IndexAlias()
        assert m._history == []

    def test_get_history_empty(self):
        m = IndexAlias()
        assert m.get_history() == []


class TestGetIndexAlias:
    def test_singleton(self):
        m1 = get_index_alias()
        m2 = get_index_alias()
        assert m1 is m2

    def test_returns_index_alias(self):
        m = get_index_alias()
        assert isinstance(m, IndexAlias)


class TestDryRunSwitch:
    @pytest.mark.asyncio
    async def test_dry_run_no_change(self):
        m = IndexAlias()
        result = await m.switch(
            new_index="index_v2_test", old_index="index_v1_test",
            dry_run=True,
        )
        assert result.action == "dry_run"
        assert result.dry_run is True
        # History should NOT be updated in dry run
        assert m.get_history() == []
