---
skill_id: rag-quality-gate
name: Wire 3-layer Quality Gate into main pipeline
description: Implement QualityGatePlugin with HARD_REFUSE / SOFT_REFUSE / NOISE_REFUSE / PROCEED decisions, plus self-RAG retry loop on rewrite_retry
tags: [rag, quality, gate, self-rag]
version: 1.0
estimated_time: 1 day
prerequisites:
  - Plugin pipeline + decision log in place
  - BGE rerank scores measured (usually 0-0.78 range)
---

# Wire Quality Gate

## Goal
Prevent bad retrievals from reaching LLM. 3-layer gate: data quality / retrieval quality / business constraints.

## Thresholds (tuned 2026-08-21 for BGE rerank)

```python
HARD_REFUSE = 0.0001   # 几乎全是噪声, 拒答
SOFT_REFUSE = 0.001    # 低置信度, 警告但放行 (LLM 用训练知识兜底)
TOP1_NOISE = 0.6       # 兼容老阈值
AVG_NOISE = 0.3
```

## Gate Decisions

- `proceed`: top1 正常, 继续
- `proceed_with_warn`: top1 低但有候选, 让 LLM 答, 标 warning
- `refuse`: top1 极低或全噪声, 拒答
- `rewrite_retry`: (旧) 触发 self-RAG 重试

## Self-RAG Retry Loop

PluginRunner 检测 gate=rewrite_retry + enable_self_rag=True 时:
1. 清空 candidate_queries / reranked_hits / context_chunks
2. 跳回 QueryRewritePlugin 重跑
3. 重新过 Recall -> Rerank -> Gate
4. 最多 self_rag_max_retries 次 (默认 2)
5. 超 max_retries 改 proceed_with_warn

## Steps

1. Create QualityGatePlugin in app/rag/chat_pipeline/plugins/gate.py
2. Modify PluginRunner to handle retry loop
3. Add `self_rag_max_retries` field to PipelineContext
4. Test with mock plugins (no real LLM needed)

## Acceptance
- [ ] HARD_REFUSE triggers refuse
- [ ] SOFT_REFUSE triggers proceed_with_warn
- [ ] Self-RAG retry: gate.rewrite_retry -> re-run rewrite -> re-run recall
- [ ] Unit tests for each threshold

## Reference
- Harness v2 sec 4.3 (QualityGateHook)
- JavaGuide quality/validator.py
