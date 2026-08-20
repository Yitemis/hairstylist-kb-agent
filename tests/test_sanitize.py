# -*- coding: utf-8 -*-
"""base64 sanitize unit tests."""
import pytest

from app.rag.utils.sanitize import (
    PLACEHOLDER,
    estimate_image_token_cost,
    has_base64_image,
    sanitize_for_embedding,
)


# 200-byte raw -> 268-char base64 (>200 threshold)
SAMPLE_B64 = "eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHg="


class TestSanitizeForEmbedding:
    def test_data_url_in_text(self):
        text = "PREFIX" + "data:image/png;base64," + SAMPLE_B64 + "SUFFIX"
        out = sanitize_for_embedding(text)
        assert PLACEHOLDER in out
        assert SAMPLE_B64 not in out
        assert "PREFIX" in out
        assert "SUFFIX" in out

    def test_markdown_image_data_url(self):
        text = "![product](data:image/png;base64," + SAMPLE_B64 + ")"
        out = sanitize_for_embedding(text)
        assert PLACEHOLDER in out
        assert SAMPLE_B64 not in out

    def test_html_img_data_url(self):
        text = '<img src="data:image/png;base64,' + SAMPLE_B64 + '" alt="x">'
        out = sanitize_for_embedding(text)
        assert PLACEHOLDER in out
        assert SAMPLE_B64 not in out

    def test_no_image_passthrough(self):
        text = "plain text without image"
        out = sanitize_for_embedding(text)
        assert out == text

    def test_empty_string(self):
        assert sanitize_for_embedding("") == ""
        assert sanitize_for_embedding(None) is None

    def test_short_base64_not_matched(self):
        text = "data:image/png;base64,iVBORw0KGgo"
        out = sanitize_for_embedding(text)
        assert "data:image" in out

    def test_multiple_images_replaced(self):
        text = (
            "A" + "data:image/png;base64," + SAMPLE_B64 + "B"
            + "data:image/jpeg;base64," + SAMPLE_B64 + "C"
        )
        out = sanitize_for_embedding(text)
        assert "A" in out and "B" in out and "C" in out
        assert out.count(PLACEHOLDER) == 2


class TestHasBase64Image:
    def test_detects_image(self):
        text = "prefix data:image/png;base64," + SAMPLE_B64 + " suffix"
        assert has_base64_image(text) is True

    def test_no_image(self):
        assert has_base64_image("plain text") is False

    def test_empty(self):
        assert has_base64_image("") is False
        assert has_base64_image(None) is False


class TestEstimateTokenCost:
    def test_with_image(self):
        text = "data:image/png;base64," + SAMPLE_B64
        cost = estimate_image_token_cost(text)
        assert cost > 0
        # cost = len(match) // 4, match contains prefix "data:image/png;base64," (~22 chars)
        # so cost = (268 + 22) // 4 = 72
        assert 50 <= cost <= 100  # reasonable range

    def test_without_image(self):
        assert estimate_image_token_cost("plain text") == 0
