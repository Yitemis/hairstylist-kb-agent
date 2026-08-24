# -*- coding: utf-8 -*-
"""10 个 Plugin: 串联成 Pipeline (priority 决定顺序)./"""
from app.rag.chat_pipeline.plugins.answer_validator import (
    AnswerValidatorPlugin,
)
from app.rag.chat_pipeline.plugins.compress import CompressPlugin
from app.rag.chat_pipeline.plugins.generate import GeneratePlugin
from app.rag.chat_pipeline.plugins.gate import QualityGatePlugin
from app.rag.chat_pipeline.plugins.intake import IntakePlugin
from app.rag.chat_pipeline.plugins.observability import ObservabilityPlugin
from app.rag.chat_pipeline.plugins.prefilter import PrefilterPlugin
from app.rag.chat_pipeline.plugins.recall import RecallPlugin
from app.rag.chat_pipeline.plugins.rewrite import QueryRewritePlugin
from app.rag.chat_pipeline.plugins.rerank import RerankPlugin

__all__ = [
    "AnswerValidatorPlugin",
    "CompressPlugin",
    "GeneratePlugin",
    "IntakePlugin",
    "ObservabilityPlugin",
    "PrefilterPlugin",
    "QualityGatePlugin",
    "QueryRewritePlugin",
    "RecallPlugin",
    "RerankPlugin",
]
