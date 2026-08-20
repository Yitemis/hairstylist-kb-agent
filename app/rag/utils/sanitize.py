# -*- coding: utf-8 -*-
"""base64 image sanitize: remove data:image base64 before embedding/rerank.

借鉴 WeKnora section 9.2 (embeddingImagePayloadPatterns).

Strategy: try 4-multiple lengths from large to small, validate with b64decode.
"""
from __future__ import annotations

import base64
import re
from typing import List, Tuple

_DATA_IMG_START = re.compile(r"data:image/[a-z0-9.+-]+;base64,", re.IGNORECASE)

_MD_DATA_IMG_PATTERN = re.compile('(?is)!\\[[^\\]]*\\]\\(\\s*data:image/[^)]+\\)')

_HTML_DATA_IMG_PATTERN = re.compile('(?is)<img\\b[^>]*\\bsrc=["\']\\s*data:image/[^"\']+["\']')

PLACEHOLDER = "[" + chr(0x56FE) + chr(0x7247) + "]"


def _find_base64_image_spans(text, min_length=200):
    """Find (start, end) positions of base64 images."""
    spans = []
    for m in _DATA_IMG_START.finditer(text):
        content_start = m.end()
        remaining = len(text) - content_start
        for k in range(remaining // 4, 0, -1):
            L = k * 4
            if L < min_length:
                break
            segment = text[content_start:content_start + L]
            try:
                base64.b64decode(segment, validate=True)
                spans.append((m.start(), content_start + L))
                break
            except Exception:
                continue
    return spans


def sanitize_for_embedding(text):
    """Remove base64 images, replace with placeholder."""
    if not text:
        return text
    text = _MD_DATA_IMG_PATTERN.sub(PLACEHOLDER, text)
    text = _HTML_DATA_IMG_PATTERN.sub(PLACEHOLDER, text)
    spans = _find_base64_image_spans(text, min_length=200)
    if not spans:
        return text
    result = []
    prev_end = len(text)
    for start, end in reversed(spans):
        result.append(text[end:prev_end])
        result.append(PLACEHOLDER)
        prev_end = start
    result.append(text[:spans[0][0]])
    return "".join(reversed(result))


def has_base64_image(text):
    """Check for base64 image."""
    if not text:
        return False
    if _find_base64_image_spans(text, min_length=200):
        return True
    if _MD_DATA_IMG_PATTERN.search(text):
        return True
    if _HTML_DATA_IMG_PATTERN.search(text):
        return True
    return False


def estimate_image_token_cost(text):
    """Estimate token cost (4 chars / token)."""
    if not text:
        return 0
    spans = _find_base64_image_spans(text, min_length=200)
    if spans:
        start, end = spans[0]
        return (end - start) // 4
    return 0

__all__ = [
    "PLACEHOLDER", "estimate_image_token_cost",
    "has_base64_image", "sanitize_for_embedding",
]
