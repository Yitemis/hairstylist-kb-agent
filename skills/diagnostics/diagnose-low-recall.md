---
skill_id: diagnose-low-recall
name: Diagnose low recall@5
trigger: context_recall < 0.6 OR recall@5 < 0.5 in eval
estimated_time: 1-2h
---

# Diagnose Low Recall

## Symptom
eval 跑出来 recall@5 < 0.5, 召回率不达标.

## Diagnosis Steps

1. **看 failed queries**: query 是哪类? (English/Chinese? short/long? specific/general?)
2. **查 recall_top_k**: 默认 30 是否够? 试试 50/100
3. **看 embedding 分布**: 用 bge-large-zh 对英文 doc, 多语言支持差
4. **检查 query rewrite**: 中文 query 改写后变成英文?
5. **看 BM25 召回**: 如果 BM25 召回 0, 可能是 jieba 分词没启用
6. **看 pgvector 索引**: HNSW ef_search 参数是否合理

## Common Fixes

| 问题 | 修法 |
|---|---|
| 英文 doc + 中文 embedding | 换 bge-m3 multilingual |
| 短 query 召回差 | 启用 query rewrite multiquery |
| 长 query 召回差 | 启用 subquery / stepback |
| 中文 query 被改写成英文 | 改 QueryRewritePlugin 加语言检测 |
| BM25 0 hits | 检查 jieba 装没装 |
| pgvector 召回慢/少 | 调 HNSW ef_search=100 |

## Reference
- Harness v2 sec 7 (knowledge update)
- JavaGuide rag-optimization sec 2.5
