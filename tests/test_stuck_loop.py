# -*- coding: utf-8 -*-
"""StuckLoopDetector 鍗曟祴."""
import pytest

from app.core.stuck_loop_detector import StuckLoopDetector


class TestContentStuck:
    def test_different_content_ok(self):
        d = StuckLoopDetector(max_consecutive=3)
        assert d.check_content("hi") is False
        assert d.check_content("hello") is False
        assert d.check_content("浣犲ソ") is False

    def test_consecutive_same_triggers(self):
        d = StuckLoopDetector(max_consecutive=3)
        assert d.check_content("hi") is False
        assert d.check_content("hi") is False
        assert d.check_content("hi") is True

    def test_consecutive_with_whitespace(self):
        d = StuckLoopDetector(max_consecutive=3)
        d.check_content("hi")
        d.check_content("  hi  ")
        d.check_content("hi")
        assert d.check_content("hi") is True

    def test_consecutive_case_insensitive(self):
        d = StuckLoopDetector(max_consecutive=3)
        d.check_content("Hello")
        d.check_content("HELLO")
        d.check_content("hello")
        assert d.check_content("Hello") is True

    def test_empty_content_not_stuck(self):
        d = StuckLoopDetector(max_consecutive=3)
        d.check_content("hi")
        d.check_content("hi")
        assert d.check_content("") is False
        assert d.check_content("") is False

    def test_disable_normalize(self):
        d = StuckLoopDetector(max_consecutive=3, content_normalize=False)
        d.check_content("Hello")
        assert d.check_content("hello") is False


class TestToolStuck:
    def test_different_tools_ok(self):
        d = StuckLoopDetector()
        assert d.check_tool_call("search") is False
        assert d.check_tool_call("list_branches") is False
        assert d.check_tool_call("search", {"q": "a"}) is False

    def test_same_tool_same_args_stuck(self):
        d = StuckLoopDetector(max_tool_repeat=3)
        assert d.check_tool_call("search", {"q": "a"}) is False
        assert d.check_tool_call("search", {"q": "a"}) is False
        assert d.check_tool_call("search", {"q": "a"}) is True

    def test_same_tool_different_args_ok(self):
        d = StuckLoopDetector(max_tool_repeat=3)
        d.check_tool_call("search", {"q": "a"})
        d.check_tool_call("search", {"q": "b"})
        d.check_tool_call("search", {"q": "c"})
        assert d.check_tool_call("search", {"q": "d"}) is False

    def test_no_args_tool(self):
        d = StuckLoopDetector(max_tool_repeat=3)
        assert d.check_tool_call("get_time") is False
        assert d.check_tool_call("get_time") is False
        assert d.check_tool_call("get_time") is True


class TestReset:
    def test_reset_clears_counters(self):
        d = StuckLoopDetector(max_consecutive=3)
        d.check_content("hi")
        d.check_content("hi")
        d.check_content("hi")
        d.reset()
        assert d.check_content("hi") is False
        assert d.check_content("hi") is False
        assert d.check_content("hi") is True


class TestGetStats:
    def test_get_stats_returns_dict(self):
        d = StuckLoopDetector()
        d.check_content("hi")
        stats = d.get_stats()
        assert "consecutive_count" in stats
        assert "tool_repeat_count" in stats
        assert "elapsed_sec" in stats
        assert stats["consecutive_count"] == 1


class TestValidation:
    def test_max_consecutive_must_be_positive(self):
        with pytest.raises(ValueError):
            StuckLoopDetector(max_consecutive=0)

    def test_max_tool_repeat_must_be_positive(self):
        with pytest.raises(ValueError):
            StuckLoopDetector(max_tool_repeat=0)
