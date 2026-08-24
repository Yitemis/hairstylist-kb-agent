# -*- coding: utf-8 -*-
"""Prometheus 指标：借鉴 SRE 最佳实践。

暴露 5 个核心指标：
- chat_requests_total: chat 调用总数（标签 mode/result）
- chat_request_duration_seconds: chat 处理耗时直方图
- llm_tokens_total: LLM token 消耗（标签 model/role）
- tool_calls_total: 工具调用总数（标签 tool）
- active_sessions: 当前活跃 session 数
"""
from __future__ import annotations

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)


# 计数器
chat_requests_total = Counter(
    "chat_requests_total",
    "Total chat requests",
    ["mode", "result"],  # mode: booking/knowledge/casual, result: success/error
)

tool_calls_total = Counter(
    "tool_calls_total",
    "Total tool invocations",
    ["tool_name", "result"],  # tool_name: list_branches/etc, result: ok/error
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens consumed",
    ["model", "role"],  # role: prompt/completion
)

llm_cache_total = Counter(
    "llm_cache_total",
    "LLM cache hits/misses",
    ["result"],  # hit/miss
)

idempotency_hits_total = Counter(
    "idempotency_hits_total",
    "Idempotency cache hits (duplicate requests avoided)",
)


rag_retrievals_total = Counter(
    "rag_retrievals_total",
    "Total RAG retrievals",
    ["tenant_id", "result"],
)

# Harness v2 §6.2: 分阶段指标
rag_phase_latency_seconds = Histogram(
    "rag_phase_latency_seconds",
    "RAG 每个阶段耗时 (秒)",
    ["phase", "tenant_id"],
    buckets=(0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0),
)

rag_gate_decisions_total = Counter(
    "rag_gate_decisions_total",
    "Quality Gate 决策计数 (proceed/refuse/rewrite_retry)",
    ["decision", "tenant_id"],
)

rag_recall_quality_hist = Histogram(
    "rag_recall_top1_score",
    "粗召回 top1 分数分布",
    ["tenant_id"],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

rag_validator_total = Counter(
    "rag_validator_total",
    "Answer Validator 决策 (pass/fail)",
    ["result", "tenant_id"],
)

rag_pipeline_errors_total = Counter(
    "rag_pipeline_errors_total",
    "Pipeline 错误计数 (按 plugin 名)",
    ["plugin", "tenant_id"],
)

# 直方图
chat_request_duration_seconds = Histogram(
    "chat_request_duration_seconds",
    "Chat request processing time",
    ["mode"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM API call duration",
    ["model", "operation"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

# 仪表
active_sessions = Gauge(
    "active_sessions",
    "Number of active chat sessions (last 5 min)",
)

memory_facts_total = Gauge(
    "memory_facts_total",
    "Total long-term memory facts stored",
    ["user_id"],
)


def render_metrics() -> tuple[bytes, str]:
    """渲染 Prometheus 格式 metrics。"""
    return generate_latest(), CONTENT_TYPE_LATEST
