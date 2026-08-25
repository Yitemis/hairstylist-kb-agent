---
skill_id: rag-answer-validator
name: Add Answer Validator (anti-hallucination + citation check)
description: Implement AnswerValidatorPlugin that checks citation count >= 1 + heuristic faithfulness + optional RAGAS real-time evaluation
tags: [rag, validator, anti-hallucination, ragas]
version: 1.0
estimated_time: 1 day
prerequisites:
  - Plugin pipeline in place
  - RAGAS runner in app/rag/evaluation/ragas_runner.py
---

# Add Answer Validator

## Goal
Detect hallucinations + verify citations before returning answer to user.

## Validation Layers

1. **Citation count**: answer must have >= 1 source citation
2. **Heuristic faithfulness** (default): answer keywords must appear in context
3. **RAGAS real-time** (optional, slower): version_tag='ragas_real' triggers full RAGAS eval

## Thresholds

```python
MIN_FAITHFULNESS = 0.30   # 启发式阈值
MIN_CITATION = 1
```

## Steps

1. Create AnswerValidatorPlugin in app/rag/chat_pipeline/plugins/answer_validator.py
2. Use `heuristic_faithfulness` from ragas_runner for fast check
3. If version_tag='ragas_real', call full evaluate_rag() (slower)
4. Set ctx.validator_passed + ctx.validator_reason
5. Optionally fall back to LTM/training knowledge if validation fails

## Acceptance
- [ ] Citation count checked
- [ ] Heuristic faithfulness works
- [ ] Real RAGAS mode works when enabled
- [ ] validator_passed correctly set

## Reference
- Harness v2 sec 6.3
- RAGAS 4-dim metrics
