# -*- coding: utf-8 -*-
"""Context Compression tests."""
import pytest
from app.rag.context_compression import (
    CompressionMethod, CompressedContext,
    estimate_tokens, split_sentences, keyword_score,
    sentence_bm25_compress, bm25_rerank_compress, compress_context,
)


def test_estimate_tokens_chinese():
    text = "染发" * 50
    assert 25 < estimate_tokens(text) < 90


def test_estimate_tokens_english():
    text = "haircut " * 20
    assert 10 < estimate_tokens(text) < 45


def test_estimate_tokens_mixed():
    text = "染发 haircut" * 10
    assert estimate_tokens(text) > 0


def test_split_sentences_chinese():
    text = "染发前要测试。过敏要避免。烫发分冷热。"
    sents = split_sentences(text)
    assert len(sents) >= 3
    assert "染发前" in sents[0]


def test_split_sentences_english():
    text = "First sentence. Second sentence. Third."
    sents = split_sentences(text)
    assert len(sents) >= 2
    assert "First" in sents[0]


def test_keyword_score_match():
    s = "染发前要做皮肤测试"
    assert keyword_score(s, ["染发", "皮肤"]) == 2


def test_keyword_score_no_match():
    s = "其他内容"
    assert keyword_score(s, ["染发", "皮肤"]) == 0


def test_keyword_score_case_insensitive():
    s = "Haircut for Round Face"
    assert keyword_score(s, ["haircut", "round"]) == 2


def test_sentence_bm25_compress_basic():
    text = "染发前需要做皮肤过敏测试。染发的化学原理包括氧化反应。烫发需要先软化。圆脸适合短发。其他无关内容比如天气。"
    compressed = sentence_bm25_compress(text, "染发前要做什么测试", top_k=2, max_chars=1000)
    assert "染发" in compressed
    assert len(compressed) < len(text)


def test_sentence_bm25_compress_no_keywords():
    text = "abc. def. ghi."
    compressed = sentence_bm25_compress(text, "xyz", top_k=3)
    assert len(compressed) > 0


def test_sentence_bm25_compress_max_chars():
    text = "。".join([f"句子{i}" for i in range(100)])
    compressed = sentence_bm25_compress(text, "句子", top_k=50, max_chars=100)
    assert len(compressed) <= 100


class FakeHit:
    def __init__(self, content):
        self.content = content


def test_bm25_rerank_compress_orders_by_keywords():
    hits = [FakeHit("其他无关"), FakeHit("染发前要测试皮肤"), FakeHit("理发基础"), FakeHit("染发后护理")]
    reranked = bm25_rerank_compress(hits, "染发前要测试什么", top_k=2)
    assert "染发" in reranked[0].content
    assert len(reranked) == 2


def test_bm25_rerank_compress_top_k_limit():
    hits = [FakeHit(f"doc {i}") for i in range(10)]
    reranked = bm25_rerank_compress(hits, "anything", top_k=3)
    assert len(reranked) == 3


def test_bm25_rerank_compress_no_keywords():
    hits = [FakeHit("a"), FakeHit("b")]
    reranked = bm25_rerank_compress(hits, "", top_k=2)
    assert len(reranked) == 2


@pytest.mark.asyncio
async def test_compress_context_none():
    hits = [FakeHit("abc"), FakeHit("def")]
    cc = await compress_context(hits, "q", method=CompressionMethod.NONE)
    assert cc.method == CompressionMethod.NONE
    assert cc.compression_ratio == 1.0
    assert "abc" in cc.text


@pytest.mark.asyncio
async def test_compress_context_bm25():
    hits = [FakeHit("染发需要测试皮肤"), FakeHit("理发基础"), FakeHit("染发后如何护理")]
    cc = await compress_context(hits, "染发", method=CompressionMethod.BM25_RERANK, top_k=2)
    assert cc.method == CompressionMethod.BM25_RERANK
    assert cc.hit_count == 3
    assert "染发" in cc.text


@pytest.mark.asyncio
async def test_compress_context_sentence():
    text = "第一句关于染发。第二句关于烫发。第三句无关。"
    hits = [FakeHit(text)]
    cc = await compress_context(hits, "染发", method=CompressionMethod.SENTENCE_TOPK, top_k=1)
    assert cc.method == CompressionMethod.SENTENCE_TOPK
    assert "染发" in cc.text


@pytest.mark.asyncio
async def test_compress_context_empty():
    cc = await compress_context([], "q")
    assert cc.text == ""
    assert cc.compression_ratio == 0.0


@pytest.mark.asyncio
async def test_compress_context_reduces_size():
    long_text = "。".join([f"句子{i}关于染发" for i in range(50)])
    hits = [FakeHit(long_text)]
    cc = await compress_context(hits, "染发", method=CompressionMethod.SENTENCE_TOPK, top_k=5)
    assert cc.compressed_length < cc.original_length
