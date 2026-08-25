---
skill_id: diagnose-high-hallucination
name: Diagnose high hallucination (low faithfulness)
trigger: faithfulness < 0.7 in RAGAS eval OR user 反馈答案不准
estimated_time: 1-2h
---

# Diagnose Hallucination

## Symptom
RAGAS faithfulness < 0.7, 答案与 KB 内容不符.

## Diagnosis Steps

1. **看 RAGAS detail**: 哪些 query faithfulness 低? 是不是召回不相关的 context?
2. **检查 Answer Validator**: 是否跑过 faithfulness 校验?
3. **看 system prompt**: 有没有"不编造 KB 外信息"的约束?
4. **看 Rerank**: 有没有用 BGE rerank? 没用的话可能召回了不相关但 score 高的 chunk
5. **看 LLM temperature**: 是否设了 0 让回答更稳定?
6. **看 prompt 长度**: 太长可能让 LLM 走神

## Common Fixes

| 问题 | 修法 |
|---|---|
| 没 Rerank | 启用 BGE Rerank, 质量提升 30%+ |
| 没 Citation 约束 | prompt 加"必须用 [1][2] 引用" |
| LLM 温度太高 | temperature=0 (deterministic) |
| 系统 prompt 弱 | 加"只基于 [KB] 回答"硬约束 |
| 没 Answer Validator | 加 faithfulness 检查, fail 时降级 |
| Retrieval 召回了不相关 | 调 Quality Gate, top1<阈值拒答 |

## Reference
- Harness v2 sec 6.3 (RAGAS)
- quality/validator.py
