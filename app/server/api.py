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
import logging
import time
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.core.agent_factory import get_agent
from app.auth.deps import CurrentUser, get_current_user
from app.db.session import get_session
from app.core.config import (
    chat_config,
    reload_config,
    safety_config,
    embedding_config,
    server_config,
    auth_config,
)
from contextlib import asynccontextmanager

from app.db.session import init_db
from app.db.migration import run_migrations_on_startup, get_current_revision, get_head_revision
from app.domain.safety import safety_filter

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# FastAPI 应用初始化
# ------------------------------------------------------------------

app = FastAPI(
    title="美发智能知识助手 API",
    version="1.0.0",
    description="企业级美发行业知识助手服务",
)




async def _lifespan(app):
    """Lifespan: 启动跑 migration + 安全检查；关闭清理。"""
    # 1. 启动：跑 Alembic 迁移（生产级：先迁移再服务）
    try:
        await run_migrations_on_startup()
    except Exception as e:
        logger.error(f"❌ 数据库迁移失败: {e}")
        raise  # Fast-fail: 启动失败不服务
    # 2. 启动：建表（fallback，新 DB 第一次 create_all 兜底）
    await init_db()
    # 3. JWT 安全检查
    import os
    env = os.environ.get("ENV", "dev").lower()
    if env == "production" and not auth_config.is_secure:
        raise RuntimeError(
            "❌ 生产环境必须设置 JWT_SECRET 环境变量！\n"
            "当前使用默认密钥 'dev-insecure-change-me'，存在严重安全风险。"
        )
    if not auth_config.is_secure:
        logger.warning(
            "⚠️  JWT_SECRET 使用默认值，生产环境务必设置 JWT_SECRET 环境变量"
        )
    # 3.5 启动 metrics gauge updater（定期刷新 memory_facts_total 等）
    from app.core.metrics_updater import start_metrics_updater
    metrics_task = start_metrics_updater()
    # 4. 当前 migration 版本（健康检查用）
    rev_now = get_current_revision()
    rev_head = get_head_revision()
    logger.info(f"DB migration: current={rev_now} head={rev_head}")
    yield
    # 关闭时取消 metrics updater
    if "metrics_task" in locals():
        metrics_task.cancel()
    # 关闭时无清理（连接池在 engine 析构时自动释放）

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
    """生产级健康检查：依次验证 DB / 向量库 / LLM。

    返回 200 = 全部健康
    返回 503 = 任一关键依赖不可用
    """
    from fastapi.responses import JSONResponse
    from sqlalchemy import text
    from app.db.session import async_session_maker

    checks: dict[str, dict] = {}
    overall_healthy = True

    # 1. DB
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "fail", "error": str(e)}
        overall_healthy = False

    # 2. Vector store
    try:
        from app.rag.engine import get_knowledge_stats
        stats = await get_knowledge_stats()
        checks["vector_store"] = {"status": "ok", "total_chunks": stats.get("total_chunks", 0)}
    except Exception as e:
        checks["vector_store"] = {"status": "fail", "error": str(e)}
        # 向量库失败不致命（可以重建）
        # overall_healthy = False

    # 3. LLM 模型
    checks["models"] = {
        "chat": "ok" if chat_config.is_valid else "not_configured",  # type: ignore[name-defined]
        "embedding": "ok" if embedding_config.is_valid else "not_configured",  # type: ignore[name-defined]
    }
    if not chat_config.is_valid:  # type: ignore[name-defined]
        overall_healthy = False

    uptime = int(time.time() - _startup_time)
    safety_stats = safety_filter.get_stats()
    # DB migration 版本（生产可监控）
    try:
        rev_current = get_current_revision()
        rev_head = get_head_revision()
        migration_status = {
            "current": rev_current,
            "head": rev_head,
            "up_to_date": rev_current == rev_head,
        }
    except Exception as e:
        migration_status = {"error": str(e)}
    body = {
        "status": "healthy" if overall_healthy else "degraded",
        "uptime_seconds": uptime,
        "version": app.version,
        "safety": safety_stats,
        "migration": migration_status,
        "checks": checks,
    }
    if overall_healthy:
        return body
    return JSONResponse(content=body, status_code=503)


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


@app.get("/metrics", summary="Prometheus 指标")
async def metrics() -> Response:
    """Prometheus 监控指标（Grafana 接入）。"""
    from fastapi.responses import Response
    from app.core.metrics import render_metrics
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)


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


@app.post('/api/rag/upload')
async def rag_upload_document(
    file: UploadFile,
    document_id: str = '',
    tenant_id: str = 'default',
    category: str = 'general',
) -> dict:
    """文件上传 + 自动解析 + 索引（支持 PDF/Word/Excel/Markdown）。"""
    from app.rag.parsers import get_parser
    from app.rag.parsers.utils import is_safe_url

    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    # 保存到临时文件，调用解析器
    import tempfile, os
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        content_bytes = await file.read()
        tmp.write(content_bytes)
        tmp_path = tmp.name
    try:
        parser = get_parser(tmp_path, file.filename)
        parents = parser.load(
            document_id=document_id or file.filename,
            tenant_id=tenant_id,
            category=category,
        )
        # 把 parent chunks 拼起来索引
        from app.rag.engine import index_document
        total_chunks = 0
        for p in parents:
            for c in p.child_chunks:
                await index_document(
                    document_id=f"{document_id or file.filename}_chunk_{total_chunks}",
                    content=c.content,
                    filename=file.filename,
                    tenant_id=tenant_id,
                    category=category,
                )
                total_chunks += 1
        return {
            "status": "ok",
            "filename": file.filename,
            "document_id": document_id or file.filename,
            "tenant_id": tenant_id,
            "parents": len(parents),
            "child_chunks_indexed": total_chunks,
        }
    finally:
        os.unlink(tmp_path)


@app.get('/api/rag/stats')
async def rag_stats(tenant_id: str | None = None) -> dict:
    """知识库统计接口（监控面板用）。"""
    from app.rag.engine import get_knowledge_stats
    return await get_knowledge_stats(tenant_id)


@app.get('/api/rag/chunks', summary='列出已索引的 chunks')
async def rag_list_chunks(
    document_id: str | None = None,
    tenant_id: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> dict:
    """查看向量库里的 chunks（用于调试切分效果）。

    - document_id: 按文档 ID 过滤（可选）
    - tenant_id: 按租户过滤（可选）
    - limit: 返回前 N 条（默认 10）
    - offset: 跳过前 N 条（用于分页）

    返回每个 chunk 的完整 payload（含 content）和元数据。
    """
    from app.rag.engine import _get_qdrant_client
    from app.core.config import vector_store_config
    from qdrant_client import models as qdrant_models

    if vector_store_config.engine != "qdrant-local":
        raise HTTPException(status_code=400, detail="仅 qdrant-local 模式支持此端点")

    client = await _get_qdrant_client()
    must_conditions = []
    if document_id is not None:
        must_conditions.append(
            qdrant_models.FieldCondition(
                key="document_id", match=qdrant_models.MatchValue(value=document_id)
            )
        )
    if tenant_id is not None:
        must_conditions.append(
            qdrant_models.FieldCondition(
                key="tenant_id", match=qdrant_models.MatchValue(value=tenant_id)
            )
        )
    query_filter = qdrant_models.Filter(must=must_conditions) if must_conditions else None

    results = client.scroll(
        collection_name=vector_store_config.collection,
        limit=limit,
        offset=offset,
        with_payload=True,
        with_vectors=False,
        scroll_filter=query_filter,
    )
    points = results[0]

    return {
        "total": len(points),
        "offset": offset,
        "limit": limit,
        "chunks": [
            {
                "id": p.id,
                "filename": (p.payload or {}).get("filename"),
                "document_id": (p.payload or {}).get("document_id"),
                "tenant_id": (p.payload or {}).get("tenant_id"),
                "category": (p.payload or {}).get("category"),
                "content": (p.payload or {}).get("content", ""),
                "content_length": len((p.payload or {}).get("content", "")),
            }
            for p in points
        ],
    }


@app.get('/api/rag/test-recall', summary='测试召回命中（按相关度排序）')
async def rag_test_recall(
    query: str,
    top_k: int = 10,
    filename: str | None = None,
    tenant_id: str | None = None,
) -> dict:
    """测试召回命中：问一个问题，返回按相关度排序的切片。

    借鉴 ekbs-ai-service 的 `/txt/test` 端点思路：
    - 用户问问题
    - 走完整 RAG 流程（embed + 向量召回 + 多租户 filter）
    - 返回按 score 排序的切片

    Args:
        query: 用户问题
        top_k: 返回前 N 条（默认 10）
        filename: 按文件名过滤（可选）
        tenant_id: 按租户过滤（可选）

    Returns:
        {
          "query": "...",
          "elapsed_ms": 123,
          "hits": [{ "rank": 1, "score": 0.95, "content": "...", "filename": "...", "document_id": "..." }, ...]
        }
    """
    from app.rag.engine import retrieve, self_rag_retrieve
    from app.core.config import vector_store_config

    if not query.strip():
        raise HTTPException(status_code=400, detail="query 必填")

    # 选择 self_rag_retrieve（带反思） 或 retrieve
    if filename or tenant_id:
        # 带过滤条件用 retrieve
        result = await retrieve(
            query=query,
            tenant_id=tenant_id or "default",
            top_k=top_k,
            enable_rerank=False,  # 简化：直接返回向量分数
        )
    else:
        result = await retrieve(
            query=query,
            tenant_id="default",
            top_k=top_k,
            enable_rerank=False,
        )

    # 按 score 排序
    sorted_hits = sorted(result.hits, key=lambda h: h.score, reverse=True)[:top_k]

    # 如果指定 filename 过滤
    if filename:
        sorted_hits = [h for h in sorted_hits if filename in (h.source or "")]

    return {
        "query": query,
        "elapsed_ms": result.retrieval_time_ms,
        "child_hits_count": result.child_hits_count,
        "total_candidates": len(result.hits),
        "hits": [
            {
                "rank": i + 1,
                "score": round(hit.score, 4),
                "content": hit.content,
                "filename": hit.source,
                "tenant_id": hit.tenant_id,
                "parent_id": hit.parent_id,
            }
            for i, hit in enumerate(sorted_hits)
        ],
    }


@app.get('/api/rag/documents', summary='列出已索引的文档')
async def rag_list_documents(tenant_id: str | None = None) -> dict:
    """列出所有已索引的文档（按 document_id 分组，含 chunk 数）。"""
    from app.rag.engine import _get_qdrant_client
    from app.core.config import vector_store_config
    from qdrant_client import models as qdrant_models

    if vector_store_config.engine != "qdrant-local":
        raise HTTPException(status_code=400, detail="仅 qdrant-local 模式支持此端点")

    client = await _get_qdrant_client()
    must_conditions = []
    if tenant_id is not None:
        must_conditions.append(
            qdrant_models.FieldCondition(
                key="tenant_id", match=qdrant_models.MatchValue(value=tenant_id)
            )
        )
    query_filter = qdrant_models.Filter(must=must_conditions) if must_conditions else None

    # 拉所有 chunk（不取向量）
    results = client.scroll(
        collection_name=vector_store_config.collection,
        limit=10000,
        with_payload=True,
        with_vectors=False,
        scroll_filter=query_filter,
    )
    points = results[0]

    # 按 document_id 聚合
    doc_map: dict[str, dict] = {}
    for p in points:
        payload = p.payload or {}
        doc_id = payload.get("document_id") or f"orphan_{p.id}"
        if doc_id not in doc_map:
            doc_map[doc_id] = {
                "document_id": doc_id,
                "filename": payload.get("filename"),
                "category": payload.get("category"),
                "tenant_id": payload.get("tenant_id"),
                "chunk_count": 0,
                "first_indexed_at": None,
            }
        doc_map[doc_id]["chunk_count"] += 1

    return {
        "total": len(doc_map),
        "documents": list(doc_map.values()),
    }


@app.post("/api/chat", summary="对话接口")
async def chat(body: dict) -> dict:
    """对话接口（前后端都用这个）。

    Body: { "message": str, "user_id": int, "session_id": str | None }

    实现策略：
    - 中间件链（洋葱模式）：日志、限流
    - 业务逻辑：意图识别 → booking/knowledge/casual 分流
    - 状态持久化：每次调用自动 saveStateToSession
    """
    message = (body.get("message") or "").strip()
    user_id = body.get("user_id")
    session_id = body.get("session_id") or "default"
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id 必填")

    # 走中间件链
    from app.core.middleware import MiddlewareContext, run_with_middlewares
    from app.core.structured_logging import set_trace_id, set_user_id, set_session_id
    from app.core.metrics import chat_requests_total, chat_request_duration_seconds
    import time as _t

    ctx = MiddlewareContext(user_id=user_id, session_id=session_id)
    # 设置 trace_id 上下文（贯穿整个请求）
    set_trace_id(ctx.trace_id)
    set_user_id(user_id)
    set_session_id(session_id)

    t0 = _t.time()
    try:
        # 多模态支持
        image_paths = body.get("image_paths") or []
        image_b64s = body.get("image_b64s") or []
        if image_paths or image_b64s:
            from app.rag.multimodal_chat import multimodal_chat
            from app.auth.deps import get_current_user_from_request
            # 尝试拿当前 user role
            is_staff = False
            try:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    from app.auth.security import decode_token
                    payload = decode_token(auth_header[7:])
                    if payload and payload.get("role") in ("staff", "admin"):
                        is_staff = True
            except Exception:
                pass
            user_id_val = body.get("user_id") or 0
            mm_result = await multimodal_chat(
                text=message, image_paths=image_paths, image_b64s=image_b64s,
                is_staff=is_staff, tenant_id=str(user_id_val) or "default",
            )
            chat_requests_total.labels(mode="multimodal", result="success").inc()
            return {
                "mode": "multimodal",
                "answer": mm_result["answer"],
                "audience": mm_result["audience"],
                "sources_count": mm_result["sources_count"],
                "images_count": mm_result["images_count"],
            }
        result = await run_with_middlewares(ctx, lambda: _chat_handler(body, ctx))
        chat_requests_total.labels(
            mode=result.get("mode", "unknown"), result="success"
        ).inc()
        chat_request_duration_seconds.labels(
            mode=result.get("mode", "unknown")
        ).observe(_t.time() - t0)
        return result
    except Exception as e:
        chat_requests_total.labels(mode="unknown", result="error").inc()
        logger.exception("chat failed: %s", e)
        raise


async def _chat_handler(body: dict, ctx) -> dict:
    """chat 业务处理逻辑（被中间件链调用）。"""
    message = (body.get("message") or "").strip()
    user_id = body.get("user_id")
    session_id = body.get("session_id") or "default"
    from app.core.model_factory import get_model
    from app.core.agent_factory import get_agent
    from app.db.models import ChatMessage
    from app.db.session import async_session_maker
    from agentscope.message import TextBlock, UserMsg, SystemMsg

    # 0. 加载该用户最近 20 条历史消息，构建上下文（用于 LLM 多轮对话）
    history_text = ""
    async with async_session_maker() as session:
        from sqlalchemy import select
        hist_stmt = (
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(20)
        )
        hist_rows = list((await session.execute(hist_stmt)).scalars().all())
        hist_rows.reverse()  # 按时间正序
        if hist_rows:
            history_lines = []
            for m in hist_rows:
                role_label = "用户" if m.role == "user" else "助手"
                history_lines.append(f"{role_label}：{m.content[:200]}")
            history_text = "\n".join(history_lines[-10:])  # 取最近10条

    # 0.5 状态恢复：检查 session 状态（借鉴 AgentScope 的 AgentStateStore）
    session_state = _load_session_state(user_id, session_id or "default")

    # 1. 保存用户消息
    async with async_session_maker() as session:
        user_msg_row = ChatMessage(user_id=user_id, role="user", content=message)
        session.add(user_msg_row)
        await session.commit()

    # 2. 输入安全过滤
    if safety_config.enable_input_filter:
        ok, reason = safety_filter.filter_input(message)
        if not ok:
            await _save_ai_message(user_id, reason, mode="safety")
            return {"answer": reason, "safety_triggered": True, "sources": []}

    # 3. 意图识别（用 LLM）
    intent = await _detect_intent_with_llm(message)
    logger.info(f"意图识别: {intent}")

    # 4. 业务调度
    if intent == "booking":
        result = await _handle_booking_flow(message, user_id, session_id or "default")
        if isinstance(result, tuple):
            answer, options = result
        else:
            answer, options = result, None
        await _save_ai_message(user_id, answer, mode="booking")
        await _save_session_state(
            user_id, session_id or "default", "booking", "booking",
            options=options, pending_order_id=None,
            extra={"last_answer_len": len(answer)},
        )
        return {
            "answer": answer,
            "safety_triggered": False,
            "domain_check": "passed",
            "sources": [],
            "mode": "booking",
            "options": options,
        }

    # 5. 知识问答：用 ReAct Agent 自主调用 RAG 工具
    if intent == "knowledge":
        try:
            from app.core.knowledge_agent_factory import get_knowledge_agent
            agent = get_knowledge_agent()
            from agentscope.message import TextBlock, UserMsg, SystemMsg

            sys = "你是美发行业专业顾问。必须先调用工具检索知识库，**严格基于检索结果**回答，不要编造。如果知识库没结果请如实说明。"
            if history_text:
                sys += f"\n\n【历史对话】\n{history_text}"
            sys_msg = SystemMsg(name="system", role="system", content=[TextBlock(text=sys)])
            user_msg = UserMsg(name="user", role="user", content=[TextBlock(text=message)])

            resp = await agent.reply([sys_msg, user_msg])
            text = ""
            sources = []
            if hasattr(resp, "content") and resp.content:
                for block in resp.content:
                    if hasattr(block, "text") and block.text:
                        text += block.text
            # 从 metadata 里取 tool calls（如果有）
            if hasattr(resp, "metadata") and resp.metadata:
                for k, v in resp.metadata.items():
                    if "source" in k.lower():
                        sources.append(v)

            if not text:
                text = "（Agent 返回空）"
            await _save_ai_message(user_id, text, mode="knowledge")
            await _save_session_state(
                user_id, session_id or "default", "knowledge", "knowledge",
                options=None, extra={"last_answer_len": len(text)},
            )
            return {
                "answer": text,
                "safety_triggered": False,
                "domain_check": "passed",
                "sources": sources,
                "mode": "knowledge",
            }
        except Exception as e:
            logger.warning("ReAct Agent 调用失败，使用 LLM 兜底: %s", e)

    # 6. 闲聊 / 知识问答兜底：直接调 LLM
    from app.core.model_factory import get_model
    from agentscope.message import TextBlock, UserMsg
    try:
        model = get_model("chat")
        system = "你是美发行业专业顾问，简洁、专业地回答用户问题。"

        # 【RAG 中间件】自动检索知识库注入（借鉴 AgentScope RAGMiddleware）
        from app.rag.engine import retrieve as rag_retrieve
        try:
            t0 = time.time()
            rag_result = await rag_retrieve(query=message, top_k=3)
            rag_elapsed = int((time.time() - t0) * 1000)
            if rag_result.hits:
                hint_lines = [f"\n\n【RAG 检索 {len(rag_result.hits)} 条相关知识（{rag_elapsed}ms）】"]
                for i, hit in enumerate(rag_result.hits[:3], 1):
                    hint_lines.append(f"\n[{i}] {hit.source}（分数 {hit.score:.2f}）\n{hit.content[:300]}")
                system += "\n".join(hint_lines)
                logger.debug("RAG 自动注入: %d 条", len(rag_result.hits))
        except Exception as e:
            logger.debug("RAG 检索失败，不影响流程: %s", e)

        # 【HarnessAgent 招牌】注入相关技能（从 message 自动匹配）
        from app.core.skill import build_skill_injection
        skill_inject = build_skill_injection(message)
        if skill_inject:
            system += f"\n\n{skill_inject}"

        # 【长期记忆】注入用户已知偏好
        from app.core.long_term_memory import get_user_facts, build_facts_injection
        facts = await get_user_facts(user_id)
        if facts:
            system += f"\n\n{build_facts_injection(facts)}"

        if history_text:
            system += f"\n\n【历史对话】\n{history_text}"
        sys_msg = UserMsg(name="system", content=[TextBlock(text=system)])
        user_msg = UserMsg(name="user", content=[TextBlock(text=message)])

        # 【高可用】LLM 调用加重试 + 指标 + 流式
        from app.core.retry import async_retry
        from app.core.metrics import llm_request_duration_seconds, llm_tokens_total
        import time as _t

        @async_retry(max_attempts=3, base_delay=1.0, max_delay=8.0)
        async def call_llm():
            return await model([sys_msg, user_msg], stream=True)

        try:
            t0 = _t.time()
            resp = await call_llm()
            llm_request_duration_seconds.labels(
                model=getattr(model, "model", "unknown"), operation="chat"
            ).observe(_t.time() - t0)
        except Exception as e:
            logger.error("LLM 调用失败（已重试 3 次）: %s", e)
            err_text = f"抱歉，AI 暂时无法回答，请稍后再试。"
            mode_label = "knowledge" if intent == "knowledge" else "casual"
            await _save_ai_message(user_id, err_text, mode=mode_label)
            return {
                "answer": err_text,
                "safety_triggered": False,
                "domain_check": "passed",
                "sources": [],
                "mode": mode_label,
            }

        text = ""
        async for chunk in resp:
            if hasattr(chunk, "content") and chunk.content:
                for block in chunk.content:
                    if hasattr(block, "text") and block.text:
                        text += block.text
        if not text:
            text = "（LLM 返回空）"
        mode_label = "knowledge" if intent == "knowledge" else "casual"
        await _save_ai_message(user_id, text, mode=mode_label)

        # 【长期记忆】自动从本轮对话中提取事实
        from app.core.long_term_memory import extract_and_save_facts
        try:
            await extract_and_save_facts(user_id, message, text)
        except Exception as e:
            logger.warning("事实提取失败: %s", e)

        await _save_session_state(
            user_id, session_id or "default", intent, mode_label,
            options=None, extra={"last_answer_len": len(text)},
        )
        return {
            "answer": text,
            "safety_triggered": False,
            "domain_check": "passed",
            "sources": [],
            "mode": mode_label,
        }
    except Exception as e:
        logger.warning("LLM 调用失败: %s", e)
        err_text = f"抱歉，AI 暂时无法回答：{type(e).__name__}: {e}"
        await _save_ai_message(user_id, err_text, mode="error")
        return {
            "answer": err_text,
            "safety_triggered": False,
            "domain_check": "passed",
            "sources": [],
        }


async def _save_ai_message(user_id: int, content: str, mode: str = "knowledge") -> None:
    """保存 AI 回复到 chat_messages 表。"""
    from app.db.models import ChatMessage
    from app.db.session import async_session_maker
    async with async_session_maker() as session:
        ai_msg = ChatMessage(user_id=user_id, role="ai", content=content, mode=mode)
        session.add(ai_msg)
        await session.commit()


def _load_session_state(user_id: int, session_id: str) -> dict:
    """从 AgentStateStore 加载会话状态（借鉴 AgentScope 2.0）。"""
    from app.core.agent_state_store import get_state_store
    store = get_state_store()
    state = store.get(str(user_id), session_id, "agent_state") or {}
    if state:
        logger.debug("恢复 session state: %s/%s", user_id, session_id)
    return state


async def _save_session_state(
    user_id: int,
    session_id: str,
    intent: str,
    mode: str,
    options: list[dict] | None = None,
    pending_order_id: int | None = None,
    extra: dict | None = None,
) -> None:
    """保存会话状态到 AgentStateStore（每次 chat 调用结束自动触发）。

    借鉴 AgentScope 的 saveStateToSession 模式：
    - 每次 call() 结束自动保存 AgentState
    - 服务器重启时能从持久化恢复
    """
    from app.core.agent_state_store import get_state_store
    from datetime import datetime

    state = {
        "intent": intent,
        "mode": mode,
        "options": options or [],
        "pending_order_id": pending_order_id,
        "extra": extra or {},
        "last_call_at": datetime.now().isoformat(),
    }
    store = get_state_store()
    store.save(str(user_id), session_id, "agent_state", state)
    logger.debug("保存 session state: %s/%s", user_id, session_id)

    # 同时同步更新 chat_sessions 表（用于跨副本恢复时的元数据查询）
    from app.db.models import ChatSession
    from app.db.session import async_session_maker
    from sqlalchemy import select
    async with async_session_maker() as db_session:
        stmt = select(ChatSession).where(ChatSession.session_id == session_id)
        row = (await db_session.execute(stmt)).scalar_one_or_none()
        if row is None:
            # 新建会话记录
            new_session = ChatSession(
                session_id=session_id,
                user_id=user_id,
                title=state["extra"].get("title"),
                state_json=str(state),
                pending_order_id=pending_order_id,
                last_iter=1,
            )
            db_session.add(new_session)
        else:
            row.state_json = str(state)
            row.pending_order_id = pending_order_id or row.pending_order_id
            row.last_iter += 1
        await db_session.commit()


async def _detect_intent_with_llm(message: str) -> str:
    """用 LLM 做意图识别，返回 booking / knowledge / casual。"""
    from app.core.model_factory import get_model
    from agentscope.message import TextBlock, UserMsg

    system = """你是意图分类器。根据用户消息判断意图，只返回三类之一：

- booking: 任何与预约、下单、选门店/发型师/服务、改时间、查自己订单、继续编辑订单、取消订单、推荐服务等操作类请求。
- knowledge: 问美发专业知识（烫发原理、产品成分、染发技术、护理建议、头皮问题等）。
- casual: 闲聊、问候、问无关话题（"你好""今天天气"等）。

只返回一个英文单词：booking 或 knowledge 或 casual，不要其他内容。"""

    try:
        model = get_model("chat")
        user_msg = UserMsg(name="user", content=[TextBlock(text=message)])
        sys_msg = UserMsg(name="system", content=[TextBlock(text=system)])
        resp = await model([sys_msg, user_msg])
        text = ""
        if hasattr(resp, "__aiter__"):
            async for item in resp:
                if hasattr(item, "content") and item.content:
                    for block in item.content:
                        if hasattr(block, "text") and block.text:
                            text += block.text
        elif hasattr(resp, "content") and resp.content:
            for block in resp.content:
                if hasattr(block, "text") and block.text:
                    text += block.text
        text = text.strip().lower()
        if "booking" in text:
            return "booking"
        if "knowledge" in text:
            return "knowledge"
        return "casual"
    except Exception as e:
        logger.warning("LLM 意图识别失败，用关键词兜底: %s", e)
        # 兜底：关键词检测
        booking_kw = ["预约", "下单", "分店", "门店", "发型师", "继续", "改", "换", "重选", "取消", "订单", "我选", "我要"]
        if any(k in message for k in booking_kw):
            return "booking"
        return "casual"


@app.get("/api/chat/history", summary="获取用户对话历史")
async def get_chat_history(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 50,
) -> dict:
    """获取当前登录用户最近的对话历史。"""
    from app.db.models import ChatMessage
    from sqlalchemy import select

    user_id = current.id
    if current.is_staff:
        # 员工查 history 时还是查自己的 ID（员工账号）
        pass

    stmt = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    messages = list(result.scalars().all())
    messages.reverse()  # 返回正序

    return {
        "messages": [
            {
                "id": m.id,
                "user_id": m.user_id,
                "role": m.role,
                "content": m.content,
                "order_id": m.order_id,
                "mode": m.mode,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "total": len(messages),
    }


@app.delete("/api/chat/history", summary="清空用户对话历史")
async def clear_chat_history(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """清空当前登录用户的所有对话历史。"""
    from app.db.models import ChatMessage
    from sqlalchemy import delete

    stmt = delete(ChatMessage).where(ChatMessage.user_id == current.id)
    await session.execute(stmt)
    await session.commit()
    return {"status": "ok", "message": "对话已清空"}


@app.get("/api/chat/sessions", summary="列出用户的所有会话")
async def list_chat_sessions(
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """列出用户所有会话（从 AgentStateStore + chat_sessions 表合并）。"""
    from app.core.agent_state_store import get_state_store
    from app.db.models import ChatSession
    from app.db.session import async_session_maker
    from sqlalchemy import select

    # 从 state_store 列 session_ids
    store = get_state_store()
    file_session_ids = store.list_session_ids(str(current.id))

    # 从 chat_sessions 表查
    async with async_session_maker() as db_session:
        stmt = select(ChatSession).where(ChatSession.user_id == current.id).order_by(ChatSession.updated_at.desc())
        rows = (await db_session.execute(stmt)).scalars().all()
        db_sessions = [
            {
                "id": r.id,
                "session_id": r.session_id,
                "title": r.title,
                "pending_order_id": r.pending_order_id,
                "interrupted": r.interrupted,
                "last_iter": r.last_iter,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ]

    return {
        "file_sessions": file_session_ids,
        "db_sessions": db_sessions,
    }


@app.get("/api/chat/sessions/{session_id}/state", summary="获取会话状态")
async def get_session_state(
    session_id: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """从 AgentStateStore 恢复会话状态（用于断点续传）。"""
    from app.core.agent_state_store import get_state_store
    store = get_state_store()
    state = store.get(str(current.id), session_id, "agent_state")
    if state is None:
        raise HTTPException(status_code=404, detail="会话状态不存在")
    return state


@app.post("/api/chat/sessions", summary="创建/保存会话状态")
async def save_session(
    body: dict,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """手动保存会话状态（一般由 chat 端点自动调用，这里暴露给高级用户）。"""
    from app.core.agent_state_store import get_state_store
    store = get_state_store()
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id 必填")
    state = body.get("state", {})
    store.save(str(current.id), session_id, "agent_state", state)
    return {"status": "ok", "message": f"会话 {session_id} 已保存"}


@app.delete("/api/chat/sessions/{session_id}", summary="删除会话")
async def delete_session(
    session_id: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """删除会话（包括 state + messages + db 记录）。"""
    from app.core.agent_state_store import get_state_store
    from app.db.models import ChatMessage, ChatSession
    from app.db.session import async_session_maker
    from sqlalchemy import delete, select

    # 1. 删 state_store
    store = get_state_store()
    store.delete(str(current.id), session_id)

    # 2. 删 messages + sessions
    async with async_session_maker() as db_session:
        await db_session.execute(delete(ChatMessage).where(ChatMessage.user_id == current.id))
        await db_session.execute(delete(ChatSession).where(
            ChatSession.user_id == current.id,
            ChatSession.session_id == session_id,
        ))
        await db_session.commit()

    return {"status": "ok", "message": f"会话 {session_id} 已删除"}


# ============================================================
# HITL（人在回路）权限 API
# ============================================================

@app.post("/api/permission/evaluate", summary="评估工具调用权限")
async def evaluate_permission(
    body: dict,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """评估一个工具调用是否需要用户确认（借鉴 AgentScope PermissionEngine）。

    Body: { "tool_name": str, "tool_args": dict, "context": dict }
    Returns: { "decision": "allowed"|"asking"|"denied", "ask_id": str, "ask_message": str, ... }
    """
    from app.core.permission import (
        PermissionRequest, get_permission_engine,
    )
    request = PermissionRequest(
        user_id=current.id,
        tool_name=body.get("tool_name", ""),
        tool_args=body.get("tool_args") or {},
        context=body.get("context") or {},
    )
    engine = get_permission_engine()
    result = engine.evaluate(request)

    response = {
        "decision": result.decision.value,
        "reason": result.reason,
        "ask_message": result.ask_message,
        "deny_message": result.deny_message,
    }

    if result.decision.value == "asking":
        ask_id = engine.create_pending_ask(request, result)
        response["ask_id"] = ask_id

    return response


@app.post("/api/permission/resolve", summary="确认/拒绝 pending 询问")
async def resolve_permission(
    body: dict,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """用户在前端点击"确认"或"拒绝"后，调用此端点。

    Body: { "ask_id": str, "approved": bool }
    """
    from app.core.permission import get_permission_engine
    engine = get_permission_engine()
    ask_id = body.get("ask_id")
    approved = bool(body.get("approved"))
    if not ask_id:
        raise HTTPException(status_code=400, detail="ask_id 必填")
    result = engine.resolve_ask(ask_id, approved)
    if result is None:
        raise HTTPException(status_code=404, detail="ask_id 不存在或已过期")
    request, perm_result = result
    return {
        "decision": perm_result.decision.value,
        "tool_name": request.tool_name,
        "tool_args": request.tool_args,
        "approved": approved,
    }


# ============================================================
# 技能库 API（HarnessAgent 招牌能力）
# ============================================================

@app.get("/api/skills", summary="列出所有技能")
async def list_skills() -> list[dict]:
    """列出所有注册的技能。"""
    from app.core.skill import get_skill_registry
    registry = get_skill_registry()
    return [
        {
            "skill_id": s.skill_id,
            "name": s.name,
            "description": s.description,
            "tags": s.tags,
            "version": s.version,
            "content_preview": s.content[:200],
        }
        for s in registry.list_all()
    ]


@app.get("/api/skills/{skill_id}", summary="获取技能详情")
async def get_skill(skill_id: str) -> dict:
    from app.core.skill import get_skill_registry
    registry = get_skill_registry()
    skill = registry.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"技能 {skill_id} 不存在")
    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "description": skill.description,
        "content": skill.content,
        "tags": skill.tags,
        "version": skill.version,
    }


@app.post("/api/skills/search", summary="根据查询找相关技能")
async def search_skills(body: dict) -> dict:
    """根据 query 搜索最相关的技能（用于调试 / 预览）。"""
    from app.core.skill import find_skills_for
    query = body.get("query", "")
    top_k = body.get("top_k", 3)
    skills = find_skills_for(query, top_k=top_k)
    return {
        "query": query,
        "matched": [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "description": s.description,
                "content_preview": s.content[:200],
            }
            for s in skills
        ],
    }


@app.post("/api/skills/reload", summary="从目录重新加载技能")
async def reload_skills() -> dict:
    """从 ./data/skills 目录重新加载所有 .md 技能文件。"""
    from app.core.skill import get_skill_registry
    registry = get_skill_registry()
    n = registry.load_from_dir("./data/skills")
    return {"status": "ok", "loaded": n}


# ============================================================
# 长期记忆（用户偏好事实）API
# ============================================================

@app.get("/api/user/facts", summary="获取当前用户所有长期事实")
async def get_user_facts(
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict]:
    """获取当前用户所有已知偏好（如：常用发型师、过敏产品、常去分店）。"""
    from app.core.long_term_memory import get_user_facts
    return await get_user_facts(current.id)


@app.delete("/api/user/facts/{fact_key}", summary="删除一条用户事实")
async def delete_user_fact(
    fact_key: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """删除一条用户事实（如用户改主意了要忘记某个偏好）。"""
    from app.db.models import UserProfile
    from app.db.session import async_session_maker
    from sqlalchemy import delete
    async with async_session_maker() as session:
        await session.execute(delete(UserProfile).where(
            UserProfile.user_id == current.id,
            UserProfile.fact_key == fact_key,
        ))
        await session.commit()
    return {"status": "ok", "message": f"已删除 {fact_key}"}


@app.post("/api/user/facts/extract", summary="从一段对话中提取事实")
async def extract_facts_endpoint(
    body: dict,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """手动触发事实提取（一般由 chat 端点自动调用，这里暴露给测试）。"""
    from app.core.long_term_memory import extract_facts_with_llm, save_facts
    user_message = body.get("user_message", "")
    ai_message = body.get("ai_message", "")
    facts = await extract_facts_with_llm(current.id, user_message, ai_message)
    saved = await save_facts(current.id, facts) if facts else 0
    return {"extracted": len(facts), "saved": saved, "facts": facts}


async def _handle_booking_flow(message: str, user_id: int, session_id: str):
    """根据用户消息和当前订单状态，调度工具返回文案。"""
    from app.agent_tools.order_tools import (
        confirm_order, create_draft_order, list_branches,
        list_stylists, recommend_services, update_order_fields,
    )
    from app.db.session import async_session_maker
    from sqlalchemy import select
    from app.db.models import Order

    msg = message.lower()

    # 取当前订单
    async with async_session_maker() as session:
        current_order = None
        stmt = (
            select(Order)
            .where(Order.user_id == user_id)
            .where(Order.status.in_(["draft", "pending"]))
            .order_by(Order.updated_at.desc())
        )
        r = await session.execute(stmt)
        current_order = r.scalar_one_or_none()
        order_id = current_order.id if current_order else None

        # 1. 用户开始预约（无订单 或 说"我想预约"等）
        if (not current_order) and any(k in msg for k in ["预约", "想约", "想烫", "想染", "想剪", "想做一个", "下单", "我想做"]):
            # 创建草稿
            draft_result = await create_draft_order(user_id=user_id)
            order_id = await _get_latest_draft_id(user_id)
            # 列出分店 + 选项
            branches_result = await list_branches(user_id=user_id)
            options = await _get_branch_options()
            return (f"{draft_result}\n\n{branches_result}", options)

        # 2. 有订单，提取信息
        if current_order:
            updated_fields = {}

            # 选分店
            for branch in await _get_branches_dict():
                if branch["name"] in message and current_order.branch_id != branch["id"]:
                    updated_fields["branch_id"] = branch["id"]
                    break

            # 选发型师
            for s in await _get_stylists_dict():
                if s["name"] in message and current_order.stylist_id != s["id"]:
                    updated_fields["stylist_id"] = s["id"]
                    break

            # 选服务（只在用户消息明确包含完整服务名时才匹配，否则不填）
            service_matched = False
            for sv in await _get_services_dict():
                if sv["name"] in message and current_order.service_id != sv["id"]:
                    updated_fields["service_id"] = sv["id"]
                    service_matched = True
                    break
            # 如果用户消息包含烫/染/剪等大类别关键词，但没匹配上服务名 → 返回服务选项
            if not service_matched:
                service_intent_keywords = ["做", "想要", "想", "烫", "染", "剪", "护理", "造型"]
                if any(k in message for k in service_intent_keywords) and not current_order.service_id:
                    services_text = (
                        f"暂时没有找到「{message}」这个具体服务项目。请从以下服务项目中选择："
                    )
                    options = await _get_service_options()
                    return (services_text, options)

            # 询问服务（用户说了一个未知服务名）
            if not updated_fields.get("service_id") and current_order.branch_id and current_order.stylist_id and not current_order.service_id:
                # 看是不是说"想做烫发/染发"这类大类别
                service_keywords = ["做", "想要", "烫", "染", "剪", "护理", "造型", "项目", "服务"]
                if any(k in message for k in service_keywords):
                    services_text = await recommend_services(user_id=user_id, user_description=message)
                    options = await _get_service_options()
                    return (services_text, options)

            # 提取日期/时间
            import re
            from datetime import date, timedelta
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})|(\d{1,2}月\d{1,2}日)|(今天|明天|后天|今晚|明晚)|([下本]?周[一二三四五六日末])|(周[一二三四五六日末])', message)
            if date_match:
                date_str = date_match.group(0)
                today_d = date.today()
                if "今天" in date_str:
                    iso_date = today_d.isoformat()
                elif "明天" in date_str:
                    iso_date = (today_d + timedelta(days=1)).isoformat()
                elif "后天" in date_str:
                    iso_date = (today_d + timedelta(days=2)).isoformat()
                elif re.match(r'周[一二三四五六日]', date_str):
                    # 找下/本周几
                    weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "末": 6}
                    target = weekday_map[date_str[-1]]
                    days_ahead = (target - today_d.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7  # 本周日=下周日
                    iso_date = (today_d + timedelta(days=days_ahead)).isoformat()
                else:
                    iso_date = date_str
                updated_fields["appointment_date"] = iso_date

            time_match = re.search(r'(\d{1,2}):(\d{2})|(\d{1,2}点)|(上午\d{1,2}点?)|(下午\d{1,2}点?)', message)
            if time_match:
                t = time_match.group(0)
                if ":" in t:
                    time_str = t
                elif "下午" in t:
                    hour = re.search(r'\d+', t).group()
                    h = int(hour)
                    if h == 12:
                        h = 12
                    elif h < 12:
                        h += 12
                    time_str = f"{h:02d}:00"
                elif "上午" in t:
                    hour = re.search(r'\d+', t).group()
                    h = int(hour)
                    if h == 12:
                        h = 0
                    time_str = f"{h:02d}:00"
                else:
                    hour = t.replace("点", "")
                    time_str = f"{int(hour):02d}:00"
                updated_fields["appointment_time"] = time_str

            # 提取电话
            phone_match = re.search(r'1[3-9]\d{9}', message)
            if phone_match:
                updated_fields["customer_phone"] = phone_match.group(0)

            # 提取姓名（"我叫xxx"）
            name_match = re.search(r'我叫(.{1,5})', message) or re.search(r'我是(.{1,5})', message)
            if name_match:
                updated_fields["customer_name"] = name_match.group(1).strip()

            if updated_fields:
                # service_type 字段必须由 service_id 自动填，不允许直接覆盖
                if "service_id" in updated_fields:
                    # 通过 service_id 自动获取服务名
                    services_dict = await _get_services_dict()
                    for sv in services_dict:
                        if sv["id"] == updated_fields["service_id"]:
                            updated_fields["service_type"] = sv["name"]
                            break
                result = await update_order_fields(
                    user_id=user_id,
                    order_id=current_order.id,
                    **updated_fields,
                )
                return result

            # 没有任何字段匹配：引导用户
            # 还没选分店
            if not current_order.branch_id:
                branches_text = await list_branches(user_id=user_id)
                options = await _get_branch_options()
                return (branches_text, options)
            # 还没选发型师
            if not current_order.stylist_id:
                stylists_text = await list_stylists(user_id=user_id, branch_id=current_order.branch_id)
                options = await _get_stylist_options(current_order.branch_id)
                return (stylists_text, options)
            # 还没选服务
            if not current_order.service_id:
                services_text = await recommend_services(user_id=user_id, user_description=message)
                options = await _get_service_options()
                return (services_text, options)
            # 还没选日期
            if not current_order.appointment_date:
                return '请告诉我您希望哪天到店？可以说"明天"、"下周六"、"8月10日"等。'
            # 还没选时间
            if not current_order.appointment_time:
                return '请告诉我您希望几点到店？比如"下午2点"、"10:00"等。'
            # 还没留电话
            if not current_order.customer_phone:
                return '请留下您的联系电话（11位手机号），店家会联系您确认。'

            # 询问分店
            if "分店" in message or "门店" in message or "店" in message and not current_order.branch_id:
                branches_text = await list_branches(user_id=user_id)
                options = await _get_branch_options()
                return (branches_text, options)

            # 询问发型师
            if ("发型师" in message or "师傅" in message or "谁" in message) and current_order.branch_id and not current_order.stylist_id:
                stylists_text = await list_stylists(user_id=user_id, branch_id=current_order.branch_id)
                options = await _get_stylist_options(current_order.branch_id)
                return (stylists_text, options)

            # 询问服务
            if ("服务" in message or "项目" in message or "做什么" in message) and not current_order.service_id:
                services_text = await recommend_services(user_id=user_id, user_description=message)
                options = await _get_service_options()
                return (services_text, options)

            # 确认
            if "确认" in message or ("好的" in message and current_order.branch_id and current_order.stylist_id) or "可以" in message or "就这样" in message:
                if current_order.status == "draft":
                    return await confirm_order(user_id=user_id, order_id=current_order.id)
                elif current_order.status == "pending":
                    return "订单已提交，等待店家确认，无需重复操作。"
                else:
                    return f"订单当前状态：{current_order.status}，无法再次确认。"

            # 查看当前订单 / 继续编辑
            if any(k in msg for k in ["我的订单", "现在", "状态", "信息", "看看", "继续编辑", "继续", "接着", "帮我继续"]):
                # 继续编辑：智能列出还缺什么
                if any(k in msg for k in ["继续", "接着", "继续编辑", "帮我继续", "帮我"]):
                    return await _continue_editing(current_order)
                return await _show_current_order(current_order)

        # 走到这里：booking intent 但没匹配上具体规则
        # 自动创建草稿订单（如果还没有），并引导选分店
        if not current_order:
            draft_result = await create_draft_order(user_id=user_id)
            order_id = await _get_latest_draft_id(user_id)
            branches_text = await list_branches(user_id=user_id)
            options = await _get_branch_options()
            return (f"{draft_result}\n\n{branches_text}", options)

        # 走到这里：booking intent，没匹配上任何更新规则，但有 current_order
        # 智能引导：列出还缺什么
        return await _continue_editing(current_order)


async def _get_latest_draft_id(user_id: int) -> int | None:
    from app.db.session import async_session_maker
    from sqlalchemy import select
    from app.db.models import Order
    async with async_session_maker() as session:
        stmt = select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(1)
        r = await session.execute(stmt)
        o = r.scalar_one_or_none()
        return o.id if o else None


async def _get_branch_options() -> list[dict]:
    """获取分店的可点击选项列表。"""
    from app.db.session import async_session_maker
    from sqlalchemy import select
    from app.db.models import Branch
    async with async_session_maker() as session:
        stmt = select(Branch).where(Branch.is_active == True).order_by(Branch.id)
        rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "type": "branch",
                "id": b.id,
                "title": b.name,
                "subtitle": b.address,
                "badge": f"每日最多 {b.max_daily_appointments} 单" if b.max_daily_appointments else None,
            }
            for b in rows
        ]


async def _get_stylist_options(branch_id: int) -> list[dict]:
    """获取指定分店的发型师可点击选项。"""
    from app.db.session import async_session_maker
    from sqlalchemy import select
    from app.db.models import Stylist
    async with async_session_maker() as session:
        stmt = (
            select(Stylist)
            .where(Stylist.is_active == True)
            .where(Stylist.branch_id == branch_id)
            .order_by(Stylist.id)
        )
        rows = (await session.execute(stmt)).scalars().all()
        result = []
        for s in rows:
            specialties = []
            try:
                specialties = json.loads(s.specialties) if s.specialties else []
            except Exception:
                specialties = []
            result.append({
                "type": "stylist",
                "id": s.id,
                "title": s.name,
                "subtitle": " · ".join(specialties) if specialties else s.description or "发型师",
                "badge": f"{s.max_daily_hours}h/天",
            })
        return result


async def _get_service_options() -> list[dict]:
    """获取服务项目可点击选项。"""
    from app.db.session import async_session_maker
    from sqlalchemy import select
    from app.db.models import Service
    async with async_session_maker() as session:
        stmt = select(Service).where(Service.is_active == True).order_by(Service.category, Service.id)
        rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "type": "service",
                "id": sv.id,
                "title": sv.name,
                "subtitle": f"{sv.category} · {sv.duration_minutes}分钟 · ¥{sv.price}",
                "badge": sv.category,
            }
            for sv in rows
        ]


async def _get_branches_dict() -> list[dict]:
    from app.db.session import async_session_maker
    from sqlalchemy import select
    from app.db.models import Branch
    async with async_session_maker() as session:
        stmt = select(Branch).where(Branch.is_active == True)
        r = await session.execute(stmt)
        return [{"id": b.id, "name": b.name} for b in r.scalars().all()]


async def _get_stylists_dict() -> list[dict]:
    from app.db.session import async_session_maker
    from sqlalchemy import select
    from app.db.models import Stylist
    async with async_session_maker() as session:
        stmt = select(Stylist).where(Stylist.is_active == True)
        r = await session.execute(stmt)
        return [{"id": s.id, "name": s.name, "branch_id": s.branch_id} for s in r.scalars().all()]


async def _get_services_dict() -> list[dict]:
    from app.db.session import async_session_maker
    from sqlalchemy import select
    from app.db.models import Service
    async with async_session_maker() as session:
        stmt = select(Service).where(Service.is_active == True)
        r = await session.execute(stmt)
        return [{"id": s.id, "name": s.name, "category": s.category, "duration_minutes": s.duration_minutes, "price": float(s.price) if s.price else 0} for s in r.scalars().all()]


async def _show_current_order(order) -> str:
    from app.db.session import async_session_maker
    async with async_session_maker() as session:
        order = await session.get(order.__class__, order.id)
        # 加载关联
        if order.branch_id:
            await session.refresh(order, ["branch"])
        if order.stylist_id:
            await session.refresh(order, ["stylist"])
        lines = ["📋 你当前订单："]
        lines.append(f"- 编号：{order.order_no}")
        if order.branch and hasattr(order, 'branch') and order.branch:
            lines.append(f"- 分店：{order.branch.name}")
        if order.stylist and hasattr(order, 'stylist') and order.stylist:
            lines.append(f"- 发型师：{order.stylist.name}")
        if order.service_type:
            lines.append(f"- 项目：{order.service_type}")
        if order.appointment_date:
            t = order.appointment_time.strftime('%H:%M') if order.appointment_time else ''
            e = order.end_time.strftime('%H:%M') if order.end_time else ''
            lines.append(f"- 时间：{order.appointment_date} {t} - {e}")
        if order.total_price:
            lines.append(f"- 总价：¥{order.total_price}")
        if order.customer_phone:
            lines.append(f"- 电话：{order.customer_phone}")
        lines.append(f"- 状态：{order.status}")
        return "\n".join(lines)


async def _continue_editing(current_order) -> tuple[str, list[dict] | None]:
    """继续编辑：智能列出当前草稿还缺什么字段，并返回对应选项。"""
    from app.db.session import async_session_maker
    from app.db.models import Order
    from app.agent_tools.order_tools import list_branches, list_stylists, recommend_services

    if current_order is None:
        return ('你没有进行中的订单。请先说"我要预约"或"想烫头发"等开始下单。', None)

    # 重新加载以保证是最新
    async with async_session_maker() as session:
        fresh = await session.get(Order, current_order.id)
        if fresh:
            if fresh.branch_id:
                await session.refresh(fresh, ["branch"])
            if fresh.stylist_id:
                await session.refresh(fresh, ["stylist"])
            current_order = fresh

    lines = [f"📋 帮你继续编辑订单 {current_order.order_no}："]
    if current_order.branch and hasattr(current_order, 'branch') and current_order.branch:
        lines.append(f"✅ 分店：{current_order.branch.name}")
    else:
        lines.append("❌ 分店：未选择")
    if current_order.stylist and hasattr(current_order, 'stylist') and current_order.stylist:
        lines.append(f"✅ 发型师：{current_order.stylist.name}")
    else:
        lines.append("❌ 发型师：未选择")
    if current_order.service_type:
        lines.append(f"✅ 项目：{current_order.service_type}")
    else:
        lines.append("❌ 项目：未选择")
    if current_order.appointment_date:
        t = current_order.appointment_time.strftime('%H:%M') if current_order.appointment_time else ''
        e = current_order.end_time.strftime('%H:%M') if current_order.end_time else ''
        lines.append(f"✅ 时间：{current_order.appointment_date} {t} - {e}")
    else:
        lines.append("❌ 时间：未选择")
    if current_order.customer_phone:
        lines.append(f"✅ 电话：{current_order.customer_phone}")
    else:
        lines.append("❌ 电话：未填写")

    # 决定下一步要给出什么选项
    options: list[dict] | None = None
    text = "\n".join(lines)
    if not current_order.branch_id:
        text += "\n\n请选择分店："
        options = await _get_branch_options()
    elif not current_order.stylist_id:
        text += f"\n\n{current_order.branch.name}有以下发型师："
        options = await _get_stylist_options(current_order.branch_id)
    elif not current_order.service_id:
        text += "\n\n请选择服务项目："
        options = await _get_service_options()
    elif not current_order.appointment_date or not current_order.appointment_time:
        text += '\n\n请告诉我您希望哪天几点到店？可以说"明天10点"、"下周六14:00"等。'
    elif not current_order.customer_phone:
        text += '\n\n请留下您的联系电话（11位手机号），店家会联系您确认。'
    else:
        text += '\n\n所有信息都齐了，回复"确认"提交订单。'

    return (text, options)


# ------------------------------------------------------------------
# 认证接口（用户/店家注册登录）
# ------------------------------------------------------------------

from app.server.routers import auth as auth_router
from app.server.routers import branches as branches_router
from app.server.routers import stylists as stylists_router
from app.server.routers import services as services_router
from app.server.routers import orders as orders_router
from app.server.routers import chat_stream

app.include_router(auth_router.router)
app.include_router(branches_router.router)
app.include_router(stylists_router.router)
app.include_router(services_router.router)
app.include_router(orders_router.router)
app.include_router(chat_stream.router)
