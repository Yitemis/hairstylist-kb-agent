---
skill_id: rag-decision-log
name: Add RAG decision log table + observability plugin
description: Create rag_decision_log table (29 fields) + ObservabilityPlugin that writes every RAG call (8 phases, gate decision, top1 score, validator pass/fail, version_tag)
tags: [rag, observability, audit, migration]
version: 1.0
estimated_time: 1 day
prerequisites:
  - Plugin pipeline in place
  - Alembic migration setup
---

# Add RAG Decision Log

## Goal
Make RAG system "black box" -> traceable. Every chat call writes a row capturing all 8 phase states for replay/A-B/root-cause.

## Table Schema (29 fields)

```python
class RagDecisionLog(Base):
    __tablename__ = "rag_decision_log"
    id, trace_id, user_id, tenant_id, query, created_at
    intent, intake_route
    rewrite_strategies, rewrite_candidates
    vector_count, bm25_count, recall_count
    rerank_top_n, rerank_applied
    gate_decision, gate_reason, top1_score
    context_count, context_tokens
    answer, answer_tokens, answer_latency_ms
    validator_passed, validator_reason, citation_count
    version_tag, phase_latencies, error
```

## Steps

1. Create alembic migration 0014_rag_decision_log.py
2. Add SQLAlchemy model RagDecisionLog in app/db/models.py
3. Implement ObservabilityPlugin in app/rag/chat_pipeline/plugins/observability.py
   - Write to DB async (loop.create_task, non-blocking)
   - Emit Prometheus metrics (rag_phase_latency_seconds, rag_gate_decisions_total)
4. Add /api/rag/decision_log query endpoint

## Acceptance
- [ ] alembic upgrade head runs without error
- [ ] rag_decision_log table has 29 columns
- [ ] Every chat writes 1 row
- [ ] /api/rag/decision_log?user_id=X returns history
- [ ] /api/rag/decision_log/stats returns aggregations

## Reference
- Harness v2 sec 6.1 (decision log) + sec 6.2 (Prometheus)
