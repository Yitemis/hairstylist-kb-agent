# -*- coding: utf-8 -*-
"""Memory: 长期记忆 (LTM) + 中间件 (extract / load / 注入).

按职责拆分:
  - ltm: 跨会话事实提取 + 注入 (核心 API)
  - ltm_v2: LTM 增强版 (去重 + 失效 + 语义合并, 借鉴 Mem0/Letta)
  - middleware: LTM 接入 LangGraph / chat handler 的中间件 (extract_and_save / load_user_facts)

旧路径 app.core.long_term_memory / app.rag.middleware.long_term_memory 已迁到这里.
"""
from memory.ltm import (
    extract_facts_with_llm,
    save_facts,
    get_user_facts,
    build_facts_injection,
    extract_and_save_facts,
)
from memory.ltm_v2 import (
    delete_user_fact,
    get_recent_facts,
    fact_count_per_user,
    merge_similar_facts,
    extract_and_save_facts_v2,
)
