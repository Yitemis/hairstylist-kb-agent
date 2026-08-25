---
skill_id: rag-plugin-pipeline
name: Refactor chat_service to Plugin Pipeline
description: Refactor monolithic 130-line if-else chat_service.py into 10 independent Plugins (Intake/Rewrite/Prefilter/Recall/Rerank/Gate/Compress/Generate/Validator/Observe) with priority-based PluginRunner
tags: [rag, refactor, plugin, harness]
version: 1.0
estimated_time: 1-2 days
prerequisites:
  - chat_service.py working (130 lines if-else)
  - Harness v2 design doc (5+1 layer + 10 plugins)
---

# Refactor chat_service to Plugin Pipeline

## Goal
Replace monolithic chat logic with modular, testable Plugin architecture. Each Plugin has priority, runs in order, can be enabled/disabled for A/B testing.

## Architecture

10 Plugins with priorities:
- 10: IntakePlugin (intent classify + route)
- 20: QueryRewritePlugin (6 strategies)
- 30: PrefilterPlugin (tenant/audience)
- 40: RecallPlugin (vector + BM25)
- 50: RerankPlugin (BGE + enriched passage)
- 60: QualityGatePlugin (3-layer gate)
- 70: CompressPlugin (token budget)
- 80: GeneratePlugin (LLM call)
- 90: AnswerValidatorPlugin (anti-hallucination)
- 100: ObservabilityPlugin (decision_log + metrics)

## Steps

1. **PipelineContext**: 53-field dataclass, passed through all plugins
2. **Plugin base class**: `name`, `priority`, `enabled`, `on_event(ctx) -> ctx`
3. **PluginRunner**: sort by priority, run sequentially, exception interrupts, record phase latencies
4. **Refactor chat_service**: reduce to 50 lines (just build ctx + run runner + persist)

## Acceptance
- [ ] All 10 plugins implemented
- [ ] PluginRunner sorts by priority
- [ ] chat_service.py <= 50 lines for chat_handler
- [ ] Each plugin has unit test (>= 2 cases)
- [ ] End-to-end chat still returns 200

## Reference
- Harness v2 sec 5.1-5.3 (Plugin design)
- WeKnora chat_pipeline/runner.go
