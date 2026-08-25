---
skill_id: rag-baseline
name: Run RAGAS evaluation baseline
description: Use 15-30 real queries to run RAGAS 4-dim metrics (faithfulness/answer_relevancy/context_precision/context_recall), output baseline report
tags: [rag, eval, baseline, ragas]
version: 1.0
estimated_time: 1-2h
prerequisites:
  - Eval set: app/rag/evaluation/eval_set_en.py (15 EN queries) or eval_set.py (30 ZH queries)
  - Indexed knowledge base (at least 1 doc, 4+ parent chunks)
  - PG + Redis running
---

# Run RAGAS Evaluation Baseline

## Goal
Get quantitative baseline of current RAG quality BEFORE any optimization, so we can measure improvement.

## Steps

1. **Verify data state**:
   ```bash
   python -c "import asyncio; from sqlalchemy.ext.asyncio import create_async_engine; from sqlalchemy import text
   async def check():
       e = create_async_engine('postgresql+asyncpg://hair:hair123@localhost:5432/hairstylist')
       async with e.begin() as c:
           for t in ['documents','parent_chunks','child_chunks']:
               r = await c.execute(text(f'SELECT count(*) FROM {t}'))
               print(f'  {t}: {r.scalar()}')
       await e.dispose()
   asyncio.run(check())"
   ```
   If any count = 0, index a real doc first (use scripts/ingest_mineru_output.py).

2. **Run baseline eval**:
   ```bash
   python scripts/run_rag_evaluation.py en  # 15 EN queries
   # or
   python scripts/run_rag_evaluation.py zh  # 30 ZH queries
   ```

3. **Save report**: copy output to `docs/RAG_EVAL_BASELINE.md`

## Acceptance
- [ ] All eval queries ran without errors
- [ ] 4 metrics printed: recall@5, recall@10, MRR, hit_rate@5, ndcg@5
- [ ] Report saved with numbers

## Reference
- RAGAS doc: https://docs.ragas.io
- Heuristic fallback in `app/rag/evaluation/ragas_runner.py`
