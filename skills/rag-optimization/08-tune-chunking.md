---
skill_id: rag-chunking-tune
name: Tune chunking strategy (4 strategies comparison)
description: Run benchmark_chunking.py comparing 4 chunking strategies (fixed-size, sentence-aware, semantic, hierarchical). Output best strategy based on recall@5 + NDCG@5
tags: [rag, chunking, benchmark, optimization]
version: 1.0
estimated_time: 1-2 days
prerequisites:
  - Have eval set + indexed doc
  - smart_chunker module exists
---

# Tune Chunking Strategy

## Goal
Find the best chunking strategy for your domain. Currently default is parent=2000 / child=800, but optimal varies.

## 4 Strategies to Compare

1. **Fixed-size**: parent=2000/child=800, overlap=80 (current default)
2. **Small chunks**: parent=1000/child=400, overlap=40 (more granular)
3. **Large chunks**: parent=3000/child=1200, overlap=120 (more context)
4. **Semantic**: split by heading/topic, not by size

## Steps

1. Create scripts/benchmark_chunking.py:
   - For each strategy, re-index the same doc
   - Run eval set
   - Compare recall@5, MRR, ndcg@5
2. Run benchmark on real data
3. Pick best strategy based on metrics
4. Update default in index_document

## Acceptance
- [ ] benchmark_chunking.py runs all 4 strategies
- [ ] Comparison report generated
- [ ] Best strategy documented in code

## Reference
- Harness v2 sec 3 tier chunking
- smart_chunker.py in app/rag/chunkers/
