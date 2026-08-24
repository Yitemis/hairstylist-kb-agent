# -*- coding: utf-8 -*-
"""Chat Pipeline (Harness v2) 单测.

覆盖:
  1. Plugin 基类: name / priority / on_event
  2. PluginRunner: 串联 / 排序 / 异常中断
  3. PipelineContext: 字段完整 / to_response / record_phase
  4. QualityGatePlugin: 3 层 Gate 决策 (纯函数测试, 不依赖 LLM)
  5. IntakePlugin: 路由决策
"""
import pytest

from app.rag.chat_pipeline.context import PipelineContext
from app.rag.chat_pipeline.plugin import Plugin
from app.rag.chat_pipeline.runner import PluginRunner


class TestPipelineContext:
    def test_default_fields(self):
        ctx = PipelineContext()
        assert ctx.intent == "knowledge"
        assert ctx.gate_decision == "proceed"
        assert ctx.rerank_applied is False
        assert ctx.phase_latencies == {}
        assert ctx.trace_id

    def test_to_response(self):
        ctx = PipelineContext(user_id=1, message="test", answer="ans", intent="knowledge")
        resp = ctx.to_response()
        assert resp["answer"] == "ans"
        assert resp["mode"] == "knowledge"
        assert "trace_id" in resp
        assert "latency_ms" in resp
        assert resp["latency_ms"] >= 0

    def test_record_phase(self):
        ctx = PipelineContext()
        ctx.record_phase("intake", 50)
        ctx.record_phase("rewrite", 200)
        assert ctx.phase_latencies == {"intake": 50, "rewrite": 200}

    def test_is_failed(self):
        ctx = PipelineContext()
        assert not ctx.is_failed()
        ctx.error = "boom"
        assert ctx.is_failed()
        ctx.error = None
        ctx.gate_decision = "refuse"
        assert ctx.is_failed()


class DummyPlugin(Plugin):
    name = "dummy"
    priority = 50

    def __init__(self, return_value=None, raise_exc=False):
        super().__init__()
        self.called = False
        self.return_value = return_value
        self.raise_exc = raise_exc

    async def on_event(self, ctx):
        self.called = True
        if self.raise_exc:
            raise RuntimeError("dummy failed")
        return self.return_value or ctx


class TestPluginBase:
    def test_plugin_repr(self):
        p = DummyPlugin()
        assert "dummy" in repr(p)
        assert "priority=50" in repr(p)

    def test_plugin_disabled(self):
        p = DummyPlugin()
        p.enabled = False
        assert p.enabled is False


class TestPluginRunner:
    @pytest.mark.asyncio
    async def test_empty_runner(self):
        runner = PluginRunner()
        ctx = await runner.run(PipelineContext(message="x"))
        assert ctx.phase_latencies == {}

    @pytest.mark.asyncio
    async def test_sequential_execution(self):
        p1 = DummyPlugin()
        p2 = DummyPlugin()
        runner = PluginRunner([p1, p2])
        ctx = await runner.run(PipelineContext(message="x"))
        assert p1.called and p2.called

    @pytest.mark.asyncio
    async def test_priority_sorting(self):
        p1 = DummyPlugin(); p1.priority = 100; p1.name = "later"
        p2 = DummyPlugin(); p2.priority = 10; p2.name = "earlier"
        runner = PluginRunner()
        runner.add(p1).add(p2)
        priorities = [p.priority for p in runner.plugins]
        assert priorities == [10, 100]

    @pytest.mark.asyncio
    async def test_disabled_plugin_skipped(self):
        p1 = DummyPlugin(); p1.enabled = False
        runner = PluginRunner([p1])
        ctx = await runner.run(PipelineContext())
        assert not p1.called
        assert "dummy" not in ctx.phase_latencies

    @pytest.mark.asyncio
    async def test_exception_interrupts_pipeline(self):
        p_ok = DummyPlugin(); p_ok.name = "ok"; p_ok.priority = 10
        p_fail = DummyPlugin(raise_exc=True); p_fail.name = "fail"; p_fail.priority = 20
        p_after = DummyPlugin(); p_after.name = "after"; p_after.priority = 30
        runner = PluginRunner([p_ok, p_fail, p_after])
        ctx = await runner.run(PipelineContext())
        assert p_ok.called
        assert p_fail.called
        assert not p_after.called
        assert "fail" in ctx.error

    @pytest.mark.asyncio
    async def test_phase_latencies_recorded(self):
        p = DummyPlugin()
        runner = PluginRunner([p])
        ctx = await runner.run(PipelineContext())
        assert "dummy" in ctx.phase_latencies
        assert ctx.phase_latencies["dummy"] >= 0


class TestQualityGatePlugin:
    @pytest.mark.asyncio
    async def test_no_candidates_refuse(self):
        from app.rag.chat_pipeline.plugins.gate import QualityGatePlugin
        gate = QualityGatePlugin()
        ctx = PipelineContext(message="test", reranked_hits=[])
        ctx = await gate.on_event(ctx)
        assert ctx.gate_decision == "refuse"
        assert ctx.gate_reason == "no_candidates"

    @pytest.mark.asyncio
    async def test_very_low_top1_hard_refuse(self):
        # top1 < HARD_REFUSE (0.0001) -> 拒答
        from app.rag.chat_pipeline.plugins.gate import QualityGatePlugin
        gate = QualityGatePlugin()
        ctx = PipelineContext(message="test", reranked_hits=[{"rerank_score": 0.00001, "score": 0.00001}])
        ctx = await gate.on_event(ctx)
        assert ctx.gate_decision == "refuse"
        assert "hard_refuse" in ctx.gate_reason

    @pytest.mark.asyncio
    async def test_soft_top1_proceed_with_warn(self):
        # 0.0001 < top1 < 0.001 -> 警告但放行
        from app.rag.chat_pipeline.plugins.gate import QualityGatePlugin
        gate = QualityGatePlugin()
        ctx = PipelineContext(message="test", reranked_hits=[{"rerank_score": 0.0005, "score": 0.0005}])
        ctx = await gate.on_event(ctx)
        assert ctx.gate_decision in ("proceed", "proceed_with_warn")  # 0.5 -> proceed
        assert "low_confidence" in ctx.gate_reason

    @pytest.mark.asyncio
    async def test_mid_top1_proceed(self):
        # 0.01 < top1 < 0.6 + avg >= 0.3 -> proceed
        from app.rag.chat_pipeline.plugins.gate import QualityGatePlugin
        gate = QualityGatePlugin()
        ctx = PipelineContext(message="test", reranked_hits=[{"rerank_score": 0.3, "score": 0.3}])
        ctx = await gate.on_event(ctx)
        assert ctx.gate_decision == "proceed"

    @pytest.mark.asyncio
    async def test_high_score_proceed(self):
        from app.rag.chat_pipeline.plugins.gate import QualityGatePlugin
        gate = QualityGatePlugin()
        ctx = PipelineContext(
            message="test",
            reranked_hits=[
                {"rerank_score": 0.85, "score": 0.85},
                {"rerank_score": 0.75, "score": 0.75},
            ],
        )
        ctx = await gate.on_event(ctx)
        assert ctx.gate_decision == "proceed"
        assert ctx.top1_score == 0.85


class TestIntakePlugin:
    @pytest.mark.asyncio
    async def test_empty_message_refuse(self):
        from app.rag.chat_pipeline.plugins.intake import IntakePlugin
        intake = IntakePlugin()
        ctx = PipelineContext(user_id=1, message="")
        ctx = await intake.on_event(ctx)
        assert ctx.intent == "casual"
        assert ctx.gate_decision == "refuse"

    @pytest.mark.asyncio
    async def test_booking_refused(self):
        from app.rag.chat_pipeline.plugins.intake import IntakePlugin
        intake = IntakePlugin()
        ctx = PipelineContext(user_id=1, message="我要预约明天下午 3 点")
        ctx = await intake.on_event(ctx)
        assert ctx.gate_decision == "refuse"
        assert "booking" in ctx.gate_reason

    @pytest.mark.asyncio
    async def test_knowledge_uses_strategies(self):
        from app.rag.chat_pipeline.plugins.intake import IntakePlugin
        intake = IntakePlugin()
        ctx = PipelineContext(user_id=1, message="染发前要做什么测试")
        ctx = await intake.on_event(ctx)
        assert ctx.intake_route == "rag"
        assert len(ctx.rewrite_strategies) > 0
        assert ctx.top_k == 5


class TestSelfRagRetry:
    """Self-RAG retry loop 测试 (Harness v2 §4.5)."""

    @pytest.mark.asyncio
    async def test_no_retry_when_disabled(self):
        from app.rag.chat_pipeline.runner import PluginRunner
        from app.rag.chat_pipeline.plugins.gate import QualityGatePlugin

        # 1) 没 retry: gate=rewrite_retry 也不重试
        gate = QualityGatePlugin()
        runner = PluginRunner([gate])
        ctx = PipelineContext(
            message="test",
            reranked_hits=[{"rerank_score": 0.5, "score": 0.5}],
            enable_self_rag=False,
        )
        ctx = await runner.run(ctx)
        # gate=proceed_with_warn (top1=0.005 in soft range)
        assert ctx.gate_decision in ("proceed", "proceed_with_warn")  # 0.5 -> proceed
        # 只有 1 个 phase (gate), 没 retry
        assert len(ctx.phase_latencies) == 1  # self_rag=False, no retry

    @pytest.mark.asyncio
    async def test_retry_loop_count(self):
        from app.rag.chat_pipeline.runner import PluginRunner
        from app.rag.chat_pipeline.plugins.gate import QualityGatePlugin

        # 2) mock plugin: 第一次 gate=rewrite_retry, 第二次 gate=proceed
        class MockRewritePlugin(Plugin):
            name = "query_rewrite"
            priority = 20
            def __init__(self):
                super().__init__()
                self.call_count = 0
            async def on_event(self, ctx):
                self.call_count += 1
                ctx.candidate_queries = [f"rewrite_v{self.call_count}"]
                return ctx

        class MockRerankPlugin(Plugin):
            name = "rerank"
            priority = 50
            async def on_event(self, ctx):
                ctx.reranked_hits = [{"rerank_score": 0.5, "score": 0.5}]
                return ctx

        class ToggleGatePlugin(Plugin):
            """第一次 rewrite_retry, 第二次 proceed."""
            name = "quality_gate"
            priority = 60
            def __init__(self):
                super().__init__()
                self.call_count = 0
            async def on_event(self, ctx):
                self.call_count += 1
                if self.call_count == 1:
                    ctx.gate_decision = "rewrite_retry"
                    ctx.gate_reason = "first attempt low"
                else:
                    ctx.gate_decision = "proceed"
                    ctx.gate_reason = "retry success"
                    ctx.top1_score = 0.5
                return ctx

        rewrite = MockRewritePlugin()
        gate = ToggleGatePlugin()
        runner = PluginRunner([rewrite, MockRerankPlugin(), gate])

        ctx = PipelineContext(
            message="test",
            enable_self_rag=True,
            self_rag_max_retries=2,
        )
        ctx = await runner.run(ctx)

        # rewrite 被调了 2 次 (第 1 次 + retry)
        assert rewrite.call_count == 2
        assert gate.call_count == 2
        # 最终 gate=proceed (retry 成功)
        assert ctx.gate_decision == "proceed"
        # phase_latencies 应该有 retry 后缀
        phase_keys = list(ctx.phase_latencies.keys())
        has_retry = any("_retry" in k for k in phase_keys)
        assert has_retry, f"expected retry phase, got {phase_keys}"
