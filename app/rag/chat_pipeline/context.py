# -*- coding: utf-8 -*-
"""PipelineContext: 一次 RAG 调用的完整上下文 (Pipeline 链上传递).

字段按 8 阶段组织: intake / plan / prefilter / rewrite / recall /
rerank / gate / compress / generate / validator / observability.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    """Pipeline 共享上下文: 一次 chat/query 调用的所有状态."""

    # ============== 基础 ==============
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    # ============== 用户输入 ==============
    user_id: int = 0
    session_id: str = ""
    message: str = ""
    role: str = "user"
    history: str = ""
    # 业务租户 ID (与 user_id 解耦, 默认 = str(user_id), 可被 chat_handler 覆盖)
    tenant_id: str = ""

    # ============== Intake 阶段产出 ==============
    intent: str = "knowledge"
    intake_route: str = "rag"
    intake_confidence: float = 1.0
    rewrite_strategies: List[str] = field(default_factory=list)
    top_k: int = 5
    confidence_threshold: float = 0.4

    # ============== Plan 阶段产出 ==============
    recall_top_k: int = 30
    rerank_top_n: int = 10
    context_top_n: int = 5
    enable_bm25: bool = True
    enable_rerank: bool = True
    enable_compress: bool = False
    enable_self_rag: bool = False
    self_rag_max_retries: int = 2  # gate=rewrite_retry 时最大重试次数
    enable_answer_validator: bool = True

    # ============== Prefilter 阶段产出 ==============
    category_filter: Optional[List[str]] = None
    audience_filter: Optional[List[str]] = None
    include_unpublished: bool = False

    # ============== Rewrite 阶段产出 ==============
    candidate_queries: List[str] = field(default_factory=list)
    rewrite_candidates_meta: List[Dict[str, Any]] = field(default_factory=list)

    # ============== Recall 阶段产出 ==============
    vector_candidates: List[Dict[str, Any]] = field(default_factory=list)
    bm25_candidates: List[Dict[str, Any]] = field(default_factory=list)
    fused_candidates: List[Dict[str, Any]] = field(default_factory=list)
    child_hits_count: int = 0

    # ============== Rerank 阶段产出 ==============
    reranked_hits: List[Any] = field(default_factory=list)
    rerank_applied: bool = False

    # ============== Gate 阶段产出 ==============
    gate_decision: str = "proceed"
    gate_reason: str = ""
    top1_score: float = 0.0
    avg_score: float = 0.0

    # ============== Compress 阶段产出 ==============
    context_chunks: List[Dict[str, Any]] = field(default_factory=list)
    context_tokens: int = 0
    context_utilization: float = 0.0
    context_zone: str = "smart"

    # ============== Generate 阶段产出 ==============
    answer: str = ""
    answer_tokens: int = 0
    answer_latency_ms: int = 0
    sources: List[Dict[str, Any]] = field(default_factory=list)

    # ============== Answer Validator 阶段产出 ==============
    validator_passed: bool = True
    validator_reason: str = ""
    citation_count: int = 0

    # ============== Observability / Trace 阶段产出 ==============
    phase_latencies: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None
    version_tag: str = "v1"

    # ============== 注入区 (Context Assembler 7 步) ==============
    system_constraints: str = ""
    facts_injection: str = ""
    skill_injection: str = ""

    def to_response(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": self.sources,
            "mode": self.intent,
            "trace_id": self.trace_id,
            "self_rag": {
                "enabled": self.enable_self_rag,
                "gate_decision": self.gate_decision,
                "gate_reason": self.gate_reason,
                "top1_score": round(self.top1_score, 3),
            },
            "latency_ms": int(time.time() * 1000) - self.started_at_ms,
        }

    def record_phase(self, phase: str, latency_ms: int) -> None:
        self.phase_latencies[phase] = latency_ms

    def is_failed(self) -> bool:
        return self.error is not None or self.gate_decision == "refuse"


__all__ = ["PipelineContext"]
