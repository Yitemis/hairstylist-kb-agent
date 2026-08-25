# -*- coding: utf-8 -*-
"""Agents: 业务 Agent 定义 + 意图分类.

按职责拆分:
  - base: 通用 Agent 工厂 (AgentScope 2.0 wrapper)
  - knowledge: 知识问答 Agent (RAG + 联网搜索)
  - booking: 预约 Agent (8 个 booking 工具)
  - business: 业务管理 Agent (订单/分店/员工/用户/统计)
  - intent_classifier: 顶层意图路由 (knowledge / booking)

旧路径 app.core.*_agent_factory 已迁到这里, app.core 有 shim 兼容旧 import.
"""
from agents.base import get_agent
from agents.knowledge import get_knowledge_agent
from agents.booking import get_booking_agent
from agents.business import get_business_agent
from agents.intent_classifier import classify_top_intent, classify_booking_sub
