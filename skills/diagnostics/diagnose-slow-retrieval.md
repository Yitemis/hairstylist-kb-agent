---
skill_id: diagnose-slow-retrieval
name: Diagnose slow retrieval (P95 > 2s)
trigger: rag_retrieval_latency_seconds p95 > 2.0
estimated_time: 30min-1h
---

# Diagnose Slow Retrieval

## Symptom
向量检索 P95 > 2s, 用户感觉卡.

## Diagnosis Steps

1. **看 phase_latencies**: 在 decision_log 里查具体哪阶段慢
   - recall > 1s: pgvector 检索慢
   - rerank > 500ms: BGE API 慢
   - generate > 5s: LLM 慢
2. **看 Prometheus rag_phase_latency_seconds histogram**
3. **检查 HNSW 参数**: ef_search 默认 40, 高维向量建议 100
4. **检查 embedding 缓存**: 重复 query 是否有 cache hit
5. **看 Redis**: Redis 缓存命中率
6. **看 pgvector 数据量**: 表多大, 是否需要 partition

## Common Fixes

| 问题 | 修法 |
|---|---|
| pgvector 召回慢 | 调 HNSW ef_search=100 / m=16 |
| BM25 慢 | 加 GIN 索引, 减少 LIMIT |
| Rerank 慢 | 调 rerank_top_n (默认 10) 降为 5 |
| LLM 慢 | 换小模型 (qwen-turbo) / 加 streaming |
| Embedding 重复 | 加 Redis cache (key = query hash) |
| 数据量大 | 按 tenant_id partition |

## Reference
- Harness v2 sec 6.2 (Prometheus)
- pgvector HNSW tuning
