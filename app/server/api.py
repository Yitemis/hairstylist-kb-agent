# -*- coding: utf-8 -*-
"""FastAPI 后端：企业级 Agent 服务。

基于 AgentScope 原生能力的企业级服务层：
- 流式对话接口（打字机效果）
- 安全过滤中间件
- 可观测性指标
- 知识库管理接口
- 配置热重载接口

接口列表：
    GET  /            → 前端页面
    GET  /chat        → 对话接口
    GET  /health      → 健康检查
    GET  /metrics     → Prometheus 指标
    POST /reload      → 配置热重载
    POST /reindex     → 知识库重新索引
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.core.agent_factory import get_agent
from app.core.config import (
    chat_config,
    reload_config,
    safety_config,
    embedding_config,
    server_config,
)
from app.domain.safety import safety_filter


# ------------------------------------------------------------------
# FastAPI 应用初始化
# ------------------------------------------------------------------

app = FastAPI(
    title="美发智能知识助手 API",
    version="1.0.0",
    description="企业级美发行业知识助手服务",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=server_config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 前端静态文件
FRONTEND_DIR = Path(__file__).parent / "frontend"
FRONTEND_DIR.mkdir(exist_ok=True)
(FRONTEND_DIR / "static").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")

# 启动时间（服务可用率计算用）
_startup_time = time.time()


# ------------------------------------------------------------------
# 管理接口
# ------------------------------------------------------------------


@app.get("/health")
async def health_check() -> dict:
    """健康检查接口。"""
    uptime = int(time.time() - _startup_time)
    safety_stats = safety_filter.get_stats()

    return {
        "status": "healthy",
        "uptime_seconds": uptime,
        "version": app.version,
        "safety": safety_stats,
        "models": {
            "chat_configured": bool(chat_config.is_valid),  # type: ignore[name-defined]
            "embedding_configured": bool(embedding_config.is_valid),  # type: ignore[name-defined]
        },
    }


@app.post("/reload")
async def reload_configuration() -> dict:
    """热重载配置（无需重启服务）。"""
    reload_config()
    from app.core.agent_factory import reload_agent

    reload_agent()
    return {"status": "ok", "message": "配置已重载，Agent 已刷新"}


# ------------------------------------------------------------------
# 前端页面入口
# ------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """前端页面入口。"""
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🪮 美发智能知识助手</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: system-ui, -apple-system, sans-serif; background: #f9fafb; }
        .container { max-width: 600px; margin: 0 auto; padding: 40px 20px; }
        h1 { color: #1f2937; font-size: 28px; margin-bottom: 24px; display: flex; align-items: center; gap: 10px; }
        .status { background: #DBEAFE; color: #1E40AF; padding: 24px; border-radius: 16px; }
        .status h2 { font-size: 18px; margin-bottom: 12px; }
        .status ul { margin-left: 20px; line-height: 1.8; }
        .code { background: rgba(0,0,0,0.05); padding: 4px 8px; border-radius: 4px; font-family: monospace; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🪮 美发智能知识助手</h1>
        <div class="status">
            <h2>✓ 服务已启动</h2>
            <ul>
                <li>前端页面开发中，稍后上线</li>
                <li>Agent 引擎：<span class="code">ReActAgent (AgentScope)</span></li>
                <li>API 文档：<span class="code">/docs</span></li>
                <li>健康检查：<span class="code">/health</span></li>
            </ul>
        </div>
    </div>
</body>
</html>
        """
    return index_path.read_text(encoding="utf-8")


# ------------------------------------------------------------------
# 核心对话接口
# ------------------------------------------------------------------


@app.get("/chat")


@app.get('/api/rag/search')
async def rag_search(
    query: str,
    tenant_id: str = 'default',
    top_k: int = 5,
    enable_self_rag: bool = True,
) -> dict:
    """RAG 检索接口（支持多租户 + Self-RAG 优化）。"""
    from app.rag.engine import retrieve, self_rag_retrieve

    if enable_self_rag:
        result = await self_rag_retrieve(query, tenant_id=tenant_id, top_k=top_k)
    else:
        result = await retrieve(query, tenant_id=tenant_id, top_k=top_k)

    return {
        'hits': [
            {
                'source': hit.source,
                'content': hit.content,
                'score': hit.score,
            }
            for hit in result.hits
        ],
        'stats': {
            'retrieval_time_ms': result.retrieval_time_ms,
            'child_hits_count': result.child_hits_count,
            'parent_count': result.parent_count,
            'rerank_applied': result.rerank_applied,
        },
        'tenant_id': tenant_id,
    }


@app.post('/api/rag/index')
async def rag_index_document(
    document_id: str,
    content: str,
    filename: str,
    tenant_id: str = 'default',
    category: str = 'general',
) -> dict:
    """API 方式索引单个文档。"""
    from app.rag.engine import index_document
    return await index_document(document_id, content, filename, tenant_id, category)


@app.get('/api/rag/stats')
async def rag_stats(tenant_id: str | None = None) -> dict:
    """知识库统计接口（监控面板用）。"""
    from app.rag.engine import get_knowledge_stats
    return await get_knowledge_stats(tenant_id)
async def chat(message: str, session_id: str | None = None) -> dict:
    """对话接口。

    Args:
        message: 用户问题。
        session_id: 会话 ID（预留多轮对话记忆用）。

    Returns:
        回答结果（含 answer / sources / safety_status）。
    """
    if not message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    # 1. 输入安全过滤
    if safety_config.enable_input_filter:
        ok, reason = safety_filter.filter_input(message)
        if not ok:
            return {
                "answer": reason,
                "safety_triggered": True,
                "sources": [],
            }

    # 2. 领域边界检查
    if safety_config.enable_domain_boundary_check:
        ok, reason = safety_filter.check_domain_boundary(message)
        if not ok:
            return {
                "answer": reason,
                "safety_triggered": True,
                "domain_check": "rejected",
                "sources": [],
            }

    # 3. 调用 Agent
    agent = get_agent()
    from agentscope.message import UserMsg

    msg = UserMsg("用户", message)
    response = await agent(msg) if hasattr(agent, "__call__") else agent(msg)

    answer_text = str(response.content) if hasattr(response, "content") else str(response)

    # 4. 输出安全过滤
    if safety_config.enable_output_filter:
        ok, filtered = safety_filter.filter_output(answer_text)
        if not ok:
            return {
                "answer": filtered,
                "safety_triggered": True,
                "sources": [],
            }
        answer_text = filtered

    return {
        "answer": answer_text,
        "safety_triggered": False,
        "domain_check": "passed",
        "sources": [],  # RAG 接入后填充真实引用来源
    }
