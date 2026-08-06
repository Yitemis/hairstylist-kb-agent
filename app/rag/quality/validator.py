# -*- coding: utf-8 -*-
"""RAG 3 layer quality validation (P1, inspired by ekbs + JavaGuide).
- Layer 1: document (pre-upload) - format/size/type
- Layer 2: chunk (post-embedding) - abnormal content
- Layer 3: answer (post-retrieval) - relevance/anti-hallucination
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    passed: bool
    layer: str
    reason: str = ""
    suggestions: List[str] = None

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


MAX_FILE_SIZE_MB = 100
MIN_FILE_SIZE_BYTES = 100
MIN_CHUNK_CHARS = 20
MAX_CHUNK_CHARS = 5000
MAX_DUPLICATE_RATIO = 0.5
MIN_AVG_SIMILARITY = 0.3
MIN_TOP1_SIMILARITY = 0.4


def validate_document_level(filename, file_size_bytes, content_type=""):
    """Layer 1: document-level - filename/size/type."""
    from app.rag.parsers import is_supported
    if not filename:
        return ValidationResult(False, "document", "filename cannot be empty", ["provide filename"])
    if file_size_bytes <= 0:
        return ValidationResult(False, "document", "file is empty", ["check uploaded file"])
    if file_size_bytes < MIN_FILE_SIZE_BYTES:
        return ValidationResult(False, "document",
            f"file too small ({file_size_bytes} bytes), may be empty", ["check file content"])
    size_mb = file_size_bytes / 1024 / 1024
    if size_mb > MAX_FILE_SIZE_MB:
        return ValidationResult(False, "document",
            f"file too large ({size_mb:.1f}MB > {MAX_FILE_SIZE_MB}MB)", [f"compress to {MAX_FILE_SIZE_MB}MB"])
    if not is_supported(filename):
        return ValidationResult(False, "document",
            f"unsupported format: {filename}",
            ["supported: PDF/Word/Excel/Markdown/Image/Audio/TXT"])
    return ValidationResult(True, "document", "document format validated")


def validate_chunk_level(chunk_content, embedding=None):
    """Layer 2: chunk-level - text quality + embedding sanity."""
    if not chunk_content or not chunk_content.strip():
        return ValidationResult(False, "chunk", "chunk empty", ["skip empty chunk"])
    content = chunk_content.strip()
    if len(content) < MIN_CHUNK_CHARS:
        return ValidationResult(False, "chunk",
            f"chunk too short ({len(content)} chars < {MIN_CHUNK_CHARS})", ["merge adjacent chunks"])
    if len(content) > MAX_CHUNK_CHARS:
        return ValidationResult(False, "chunk",
            f"chunk too long ({len(content)} chars > {MAX_CHUNK_CHARS})", ["re-split"])
    lines = [l for l in content.split(chr(10)) if l.strip()]
    if len(lines) > 5:
        unique_lines = set(lines)
        dup_ratio = 1 - len(unique_lines) / len(lines)
        if dup_ratio > MAX_DUPLICATE_RATIO:
            return ValidationResult(False, "chunk",
                f"duplicate rate too high ({dup_ratio:.0%}), may be abnormal", ["check source"])
    if embedding is not None:
        if len(embedding) == 0:
            return ValidationResult(False, "chunk", "embedding empty")
        if any(not (-10 < x < 10) for x in embedding):
            return ValidationResult(False, "chunk", "embedding abnormal (NaN/Inf)")
    return ValidationResult(True, "chunk", "chunk validated")


def validate_chunks_batch(chunks):
    return [validate_chunk_level(c, e) for c, e in chunks]


def validate_answer_level(hits, llm_answer=""):
    """Layer 3: answer-level - retrieval relevance + anti-hallucination."""
    if not hits:
        return ValidationResult(False, "answer",
            "no retrieval results, LLM may hallucinate",
            ["optimize query", "check knowledge base coverage"])
    similarities = [getattr(h, "score", None) for h in hits]
    similarities = [s for s in similarities if s is not None]
    if not similarities:
        return ValidationResult(False, "answer", "cannot get similarity", ["check Milvus"])
    avg_sim = sum(similarities) / len(similarities)
    top1_sim = max(similarities)
    if avg_sim < MIN_AVG_SIMILARITY:
        return ValidationResult(False, "answer",
            f"avg similarity too low ({avg_sim:.2f} < {MIN_AVG_SIMILARITY})",
            ["try different embedding or query rewrite"])
    if top1_sim < MIN_TOP1_SIMILARITY:
        return ValidationResult(False, "answer",
            f"top-1 similarity too low ({top1_sim:.2f} < {MIN_TOP1_SIMILARITY})",
            ["best match quality is poor"])
    if llm_answer and len(llm_answer.strip()) < 5:
        return ValidationResult(False, "answer",
            "LLM answer too short, may be incomplete", ["retry LLM call"])
    return ValidationResult(True, "answer",
        f"answer validated (avg_sim={avg_sim:.2f}, top1_sim={top1_sim:.2f})")
