# -*- coding: utf-8 -*-
"""Chat Pipeline: 插件式 RAG + 答案生成管道.

入口:
    from app.rag.chat_pipeline import get_default_runner
    runner = get_default_runner()
    ctx = await runner.run(PipelineContext(message=..., user_id=..., ...))
    response = ctx.to_response()
"""
from app.rag.chat_pipeline.context import PipelineContext
from app.rag.chat_pipeline.plugin import Plugin
from app.rag.chat_pipeline.plugins import (
    AnswerValidatorPlugin,
    CompressPlugin,
    GeneratePlugin,
    IntakePlugin,
    ObservabilityPlugin,
    PrefilterPlugin,
    QualityGatePlugin,
    QueryRewritePlugin,
    RecallPlugin,
    RerankPlugin,
)
from app.rag.chat_pipeline.runner import (
    PluginRunner,
    get_default_runner,
    reset_default_runner,
)

__all__ = [
    "AnswerValidatorPlugin",
    "CompressPlugin",
    "GeneratePlugin",
    "IntakePlugin",
    "ObservabilityPlugin",
    "PipelineContext",
    "Plugin",
    "PluginRunner",
    "PrefilterPlugin",
    "QualityGatePlugin",
    "QueryRewritePlugin",
    "RecallPlugin",
    "RerankPlugin",
    "get_default_runner",
    "reset_default_runner",
]
