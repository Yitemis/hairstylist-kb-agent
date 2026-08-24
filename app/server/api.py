# -*- coding: utf-8 -*-
"""FastAPI 主入口:所有业务路由集中此处."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
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
from app.core.cache.helpers import cache_get, cache_set
from contextlib import asynccontextmanager

from app.db.session import init_db
from app.db.migration import run_migrations_on_startup, get_current_revision, get_head_revision
from app.utils.llm_extract import extract_text
from app.safety.domain_safety import safety_filter
from app.services import booking_service
from app.services import chat_service

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# FastAPI 应用初始化
# ------------------------------------------------------------------

app = FastAPI(
    title="美发智能知识助手 API",
    version="1.0.0",
    description="企业级美发行业知识助手服务",
)


# ------------------------------------------------------------------
# Rate Limiting (P2-13 slowapi 真实接入)
# ------------------------------------------------------------------
# 借鉴 JavaGuide: 高并发场景下必须有限流(防止恶意刷接口 + 保护下游 LLM)
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi.responses import JSONResponse

# 按 IP 限流,默认 100/分钟.生产可调为 60/分钟或更低.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda req, exc: JSONResponse(
    status_code=429,
    content={"detail": "请求过于频繁,请稍后再试", "retry_after": str(exc.detail)},
))
app.add_middleware(SlowAPIMiddleware)



async def _lifespan(app):
    """Lifespan: 启动跑 migration + 安全检查;关闭清理."""
    # 1. 启动:跑 Alembic 迁移(生产级:先迁移再服务)
    try:
        await run_migrations_on_startup()
    except Exception as e:
        logger.error(f"❌ 数据库迁移失败: {e}")
        raise  # Fast-fail: 启动失败不服务
    # 2. 启动:建表(fallback,新 DB 第一次 create_all 兜底)
    await init_db()
    # 3. JWT 安全检查
    import os
    env = os.environ.get("ENV", "dev").lower()
    if env == "production" and not auth_config.is_secure:
        raise RuntimeError(
            "❌ 生产环境必须设置 JWT_SECRET 环境变量!\n"
            "当前使用默认密钥 'dev-insecure-change-me',存在严重安全风险."
        )
    # JWT secret 强校验(fail-fast:dev 也要求 32+ 位 + 2 种字符类)
    try:
        auth_config.validate_for_env(env)
        logger.info("✅ JWT secret 校验通过 (len=%d)", len(auth_config.jwt_secret))
    except RuntimeError as e:
        logger.error(str(e))
        raise  # fail-fast: 启动失败不服务
    # 3.5 启动 metrics gauge updater(定期刷新 memory_facts_total 等)
    from app.core.metrics_updater import start_metrics_updater
    metrics_task = start_metrics_updater()
    # 3.6 启动数据归档后台任务 (每天跑一次)
    from app.core.archiver import start_archiver
    archiver_task = start_archiver()
    # 4. 当前 migration 版本(健康检查用)
    rev_now = get_current_revision()
    rev_head = get_head_revision()
    logger.info(f"DB migration: current={rev_now} head={rev_head}")
    yield
    # 关闭时取消 metrics updater
    if "metrics_task" in locals():
        metrics_task.cancel()
    if "archiver_task" in locals():
        archiver_task.cancel()
    # 关闭时无清理(连接池在 engine 析构时自动释放)

# CORS 配置(P2-15 严格白名单 + 限制方法/头)
app.add_middleware(
    CORSMiddleware,
    allow_origins=server_config.cors_origins,  # 白名单(不要用 ["*"] + credentials)
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],  # 显式列出
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,  # 预检缓存 10 分钟
)


# 前端静态文件
FRONTEND_DIR = Path(__file__).parent / "frontend"
FRONTEND_DIR.mkdir(exist_ok=True)
(FRONTEND_DIR / "static").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")

# 启动时间(服务可用率计算用)
_startup_time = time.time()


# ------------------------------------------------------------------
# 管理接口
# ------------------------------------------------------------------


@app.get("/health")
async def health_check() -> dict:
    """生产级健康检查:依次验证 DB / 向量库 / LLM.

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
        from app.rag.v2_engine import get_knowledge_stats
        stats = await get_knowledge_stats()
        checks["vector_store"] = {"status": "ok", "total_chunks": stats.get("total_chunks", 0)}
    except Exception as e:
        checks["vector_store"] = {"status": "fail", "error": str(e)}
        # 向量库失败不致命(可以重建)
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
    # DB migration 版本(生产可监控)
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
    """热重载配置(无需重启服务)."""
    reload_config()
    from app.core.agent_factory import reload_agent

    reload_agent()
    return {"status": "ok", "message": "配置已重载,Agent 已刷新"}


# ------------------------------------------------------------------
# 前端页面入口
# ------------------------------------------------------------------



@app.get("/metrics", summary="Prometheus 指标")
async def metrics():
    """Prometheus 监控指标(Grafana 接入)."""
    from fastapi.responses import Response
    from app.core.metrics import render_metrics
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)


# ------------------------------------------------------------------
# Harness v2 §6.1: RAG 决策日志查询端点 (Harness Level 2+)
# ------------------------------------------------------------------

@app.post("/api/chat/stream", summary="对话接口 (SSE 流式输出)")
async def chat_stream(
    request: Request,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    body: dict = None,
):
    """SSE 流式对话. 边生成边返回, 改善 UX.

    Event 格式:
      event: meta    data: {"trace_id": "...", "intent": "knowledge", "gate": "proceed"}
      event: chunk   data: {"text": "..."}
      event: sources data: [{"document_id": "...", "content": "..."}]
      event: done    data: {"latency_ms": 1234, "answer_tokens": 100}
      event: error   data: {"message": "..."}
    """
    from fastapi.responses import StreamingResponse
    import json as _json

    message = (body.get("message") or "").strip()
    if not current:
        raise HTTPException(status_code=401, detail="缺少身份认证")
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    user_id = current.id
    session_id = body.get("session_id") or "default"

    async def event_stream():
        try:
            from app.rag.chat_pipeline import (
                PipelineContext, get_default_runner,
            )
            from app.db.session import async_session_maker
            from app.db.models import ChatMessage
            from app.rag.middleware.long_term_memory import (
                extract_and_save_after_chat,
            )

            # 1. 加载历史
            history = ""
            async with async_session_maker() as session:
                from sqlalchemy import select
                stmt = select(ChatMessage).where(
                    ChatMessage.user_id == user_id,
                    ChatMessage.session_id == session_id,
                ).order_by(ChatMessage.id.desc()).limit(20)
                rows = (await session.scalars(stmt)).all()
                for m in reversed(rows):
                    prefix = "user: " if m.role == "user" else "assistant: "
                    history += prefix + m.content + "\n"
                # 持久化用户消息
                session.add(ChatMessage(
                    user_id=user_id, role="user", content=message,
                    session_id=session_id,
                ))
                await session.commit()

            # 2. 跑 Pipeline (非流式, 全量答案)
            import os
            default_tenant = os.environ.get("DEFAULT_TENANT_ID") or str(user_id)
            ctx = PipelineContext(
                user_id=user_id, session_id=session_id,
                message=message, history=history,
                role=getattr(current, "role", "user"),
                tenant_id=default_tenant,
            )
            runner = get_default_runner()
            ctx = await runner.run(ctx)

            # SSE helper: 避免 f-string 多行问题
            def sse(event, data):
                return "event: " + event + "\ndata: " + _json.dumps(data) + "\n\n"

            # 3. 事件 1: meta
            yield sse("meta", {
                "trace_id": ctx.trace_id,
                "intent": ctx.intent,
                "gate_decision": ctx.gate_decision,
                "gate_reason": ctx.gate_reason,
                "top1_score": round(ctx.top1_score, 3),
                "latency_ms_total": int(sum(ctx.phase_latencies.values())),
            })

            # 4. 事件 2: 答案分块 (按字符 chunk_size 切)
            answer = ctx.answer or ""
            chunk_size = 20
            for i in range(0, len(answer), chunk_size):
                yield sse("chunk", {"text": answer[i:i+chunk_size]})

            # 5. 事件 3: sources
            if ctx.sources:
                yield sse("sources", ctx.sources)

            # 6. 事件 4: done
            yield sse("done", {
                "latency_ms": ctx.answer_latency_ms,
                "phase_latencies": ctx.phase_latencies,
                "validator_passed": ctx.validator_passed,
            })

            # 7. 持久化 AI 回复 (后台)
            async with async_session_maker() as session:
                session.add(ChatMessage(
                    user_id=user_id, role="assistant",
                    content=answer, mode=ctx.intent,
                ))
                await session.commit()

            # 8. LTM 提取 (后台, 失败不影响响应)
            try:
                await extract_and_save_after_chat(user_id, message, answer)
            except Exception:
                pass

        except Exception as e:
            logger.exception("chat_stream failed: %s", e)
            yield sse("error", {"message": str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx 不缓冲
        },
    )


@app.get("/api/rag/decision_log", summary="查询 RAG 决策日志")
async def query_decision_log(
    trace_id: str | None = None,
    user_id: int | None = None,
    intent: str | None = None,
    gate_decision: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """查询 RAG 决策日志 (Harness v2 §6.1).

    Args:
        trace_id: 按 trace 查 (精准)
        user_id: 按用户查
        intent: knowledge/booking/casual
        gate_decision: proceed/proceed_with_warn/refuse
        limit: 默认 50, 最大 500
        offset: 分页

    Returns:
        list of decision_log rows + total count
    """
    from sqlalchemy import select, func
    from app.db.session import async_session_maker
    from app.db.models import RagDecisionLog

    limit = min(limit, 500)
    conditions = []
    if trace_id:
        conditions.append(RagDecisionLog.trace_id == trace_id)
    if user_id is not None:
        conditions.append(RagDecisionLog.user_id == user_id)
    if intent:
        conditions.append(RagDecisionLog.intent == intent)
    if gate_decision:
        conditions.append(RagDecisionLog.gate_decision == gate_decision)

    async with async_session_maker() as session:
        # total
        cnt_stmt = select(func.count()).select_from(RagDecisionLog)
        if conditions:
            cnt_stmt = cnt_stmt.where(*conditions)
        total = (await session.execute(cnt_stmt)).scalar() or 0

        # rows
        stmt = select(RagDecisionLog)
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(RagDecisionLog.created_at.desc()).limit(limit).offset(offset)
        rows = (await session.execute(stmt)).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "trace_id": r.trace_id,
                "user_id": r.user_id,
                "intent": r.intent,
                "intake_route": r.intake_route,
                "gate_decision": r.gate_decision,
                "gate_reason": r.gate_reason,
                "top1_score": round(r.top1_score, 4),
                "context_count": r.context_count,
                "citation_count": r.citation_count,
                "validator_passed": r.validator_passed,
                "validator_reason": r.validator_reason,
                "version_tag": r.version_tag,
                "phase_latencies_ms": r.phase_latencies,
                "answer_latency_ms": r.answer_latency_ms,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "query": (r.query or "")[:200],
                "answer_preview": (r.answer or "")[:200],
            }
            for r in rows
        ],
    }


@app.get("/api/rag/decision_log/stats", summary="决策日志统计 (按 gate / intent / version)")
async def decision_log_stats(days: int = 7):
    """按 gate_decision / intent / version_tag 聚合统计 (RePlayHook 用)."""
    from datetime import datetime, timedelta
    from sqlalchemy import select, func
    from app.db.session import async_session_maker
    from app.db.models import RagDecisionLog

    since = datetime.now() - timedelta(days=days)
    async with async_session_maker() as session:
        # by gate
        gate_rows = (await session.execute(
            select(
                RagDecisionLog.gate_decision,
                func.count().label("count"),
                func.avg(RagDecisionLog.top1_score).label("avg_top1"),
                func.avg(RagDecisionLog.answer_latency_ms).label("avg_latency_ms"),
            )
            .where(RagDecisionLog.created_at >= since)
            .group_by(RagDecisionLog.gate_decision)
        )).all()

        # by intent
        intent_rows = (await session.execute(
            select(
                RagDecisionLog.intent,
                func.count().label("count"),
            )
            .where(RagDecisionLog.created_at >= since)
            .group_by(RagDecisionLog.intent)
        )).all()

        # by version
        version_rows = (await session.execute(
            select(
                RagDecisionLog.version_tag,
                func.count().label("count"),
                func.sum(func.cast(RagDecisionLog.validator_passed, sa_text_int())).label("passed"),
            )
            .where(RagDecisionLog.created_at >= since)
            .group_by(RagDecisionLog.version_tag)
        )).all() if False else []  # skip if sa_text_int not available

        # total
        total = (await session.execute(
            select(func.count()).select_from(RagDecisionLog).where(RagDecisionLog.created_at >= since)
        )).scalar() or 0

    return {
        "window_days": days,
        "since": since.isoformat(),
        "total": total,
        "by_gate_decision": [
            {
                "gate_decision": r.gate_decision,
                "count": r.count,
                "avg_top1_score": round(float(r.avg_top1 or 0), 4),
                "avg_latency_ms": round(float(r.avg_latency_ms or 0), 1),
            }
            for r in gate_rows
        ],
        "by_intent": [
            {"intent": r.intent, "count": r.count} for r in intent_rows
        ],
    }


# ------------------------------------------------------------------
# Harness v2 §7.3: IndexAlias 蓝绿切换 API
# ------------------------------------------------------------------

@app.get("/api/rag/index_alias", summary="当前索引别名状态")
async def get_index_alias():
    """查看 IndexAlias 状态 (历史 + 默认 alias)."""
    from app.rag.index_alias import get_index_alias
    alias = get_index_alias()
    return {
        "default_alias": alias.DEFAULT_ALIAS,
        "rollback_window_days": alias.ROLLBACK_WINDOW_DAYS,
        "history": alias.get_history(),
    }


@app.post("/api/rag/index_alias/create", summary="建新索引别名")
async def create_index_alias(payload: dict):
    """建新索引 (空), 不影响 prod.

    Body: {"new_index": "index_v2_bge_m3", "embedding_model": "BAAI/bge-m3"}
    """
    from app.rag.index_alias import get_index_alias
    new_index = payload.get("new_index")
    if not new_index:
        raise HTTPException(400, "new_index required")
    embedding_model = payload.get("embedding_model")
    alias = get_index_alias()
    result = await alias.create_new(new_index, embedding_model=embedding_model)
    return {
        "action": result.action,
        "new_index": result.to_alias,
        "switched_count": result.switched_count,
        "error": result.error,
    }


@app.post("/api/rag/index_alias/switch", summary="切索引别名 (支持 dry_run)")
async def switch_index_alias(payload: dict):
    """切 alias: 老 -> 新. 默认 dry_run=True 不实际切.

    Body: {"new_index": "index_v2", "old_index": "index_v1", "dry_run": true}
    """
    from app.rag.index_alias import get_index_alias
    new_index = payload.get("new_index")
    old_index = payload.get("old_index")
    dry_run = payload.get("dry_run", True)
    if not new_index or not old_index:
        raise HTTPException(400, "new_index and old_index required")
    alias = get_index_alias()
    result = await alias.switch(new_index, old_index, dry_run=dry_run)
    return {
        "action": result.action,
        "from_alias": result.from_alias,
        "to_alias": result.to_alias,
        "switched_count": result.switched_count,
        "dry_run": result.dry_run,
        "error": result.error,
    }


@app.post("/api/rag/index_alias/rollback", summary="回滚到上一个 alias")
async def rollback_index_alias():
    """回滚到 history 里的上一个 alias."""
    from app.rag.index_alias import get_index_alias
    alias = get_index_alias()
    result = await alias.rollback()
    return {
        "action": result.action,
        "from_alias": result.from_alias,
        "to_alias": result.to_alias,
        "switched_count": result.switched_count,
        "error": result.error,
    }


@app.post("/api/rag/knowledge/update", summary="增量更新文档")
async def update_document(payload: dict):
    """触发 KnowledgeUpdater.on_document_changed.

    Body: {
      "document_id": "doc1",
      "content": "...",
      "filename": "x.md",
      "tenant_id": "demo",
      "category": "haircare" (optional),
      "audience": "all" (optional)
    }
    """
    from app.rag.knowledge_updater import (
        ChangeEvent, get_knowledge_updater,
    )
    event = ChangeEvent(
        document_id=payload.get("document_id"),
        content=payload.get("content", ""),
        filename=payload.get("filename", ""),
        tenant_id=payload.get("tenant_id", "default"),
        audience=payload.get("audience", "all"),
        category=payload.get("category", "general"),
        chunk_size=payload.get("chunk_size", 800),
        chunk_overlap=payload.get("chunk_overlap", 80),
    )
    if not event.document_id or not event.content:
        raise HTTPException(400, "document_id and content required")
    updater = get_knowledge_updater()
    result = await updater.on_document_changed(event)
    return {
        "action": result.action,
        "document_id": result.document_id,
        "version_id": result.version_id,
        "content_hash": result.content_hash,
        "reason": result.reason,
        "parents": result.parents,
        "children": result.children,
        "latency_ms": result.latency_ms,
        "error": result.error,
    }


@app.post("/api/rag/knowledge/soft_delete", summary="软删文档")
async def soft_delete_document(payload: dict):
    """软删文档 (不真删, RAG 自动过滤)."""
    from app.rag.knowledge_updater import get_knowledge_updater
    document_id = payload.get("document_id")
    tenant_id = payload.get("tenant_id", "default")
    if not document_id:
        raise HTTPException(400, "document_id required")
    updater = get_knowledge_updater()
    result = await updater.soft_delete(document_id, tenant_id)
    return {
        "action": result.action,
        "document_id": result.document_id,
        "reason": result.reason,
        "error": result.error,
    }


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """前端页面入口."""
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
                <li>前端页面开发中,稍后上线</li>
                <li>Agent 引擎:<span class="code">ReActAgent (AgentScope)</span></li>
                <li>API 文档:<span class="code">/docs</span></li>
                <li>健康检查:<span class="code">/health</span></li>
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

@app.post("/api/chat", summary="对话接口(支持多模态 + role 隔离 + 幂等)")
async def chat(
    request: Request,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    body: dict = None,
) -> dict:
    """对话接口.

    幂等机制:
    - 前端传 idempotency_key(client UUID)
    - 24h 内同样 key 直接返回上次结果
    - 兜底:用 user_id + message hash

    安全 (P1-1): 强制 JWT 鉴权,user_id 从 token 取,绝不从 body 取.
    """
    message = (body.get("message") or "").strip()
    # P1-1 修复:user_id 强制从 JWT 取,不再接受 body 里的 user_id
    if current is None:
        raise HTTPException(status_code=401, detail="缺少身份认证")
    user_id = current.id
    session_id = body.get("session_id") or "default"
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    # 幂等检查(避免重复扣费 + 重复处理)
    from app.core.cache.llm_cache import get_idempotency_cache, generate_idempotency_key
    from app.core.cache.helpers import cache_get, cache_set
    from app.core.metrics import idempotency_hits_total
    idem_key = body.get("idempotency_key") or generate_idempotency_key(
        user_id=user_id, message=message, session_id=session_id
    )
    idem_cache = get_idempotency_cache()
    cached_result = await cache_get(idem_cache, idem_key)
    if cached_result is not None:
        idempotency_hits_total.inc()
        logger.info("Idempotency hit (key=%s) for user=%d", idem_key, user_id)
        return cached_result

    # 走中间件链
    from app.core.middleware import MiddlewareContext, run_with_middlewares
    from app.core.structured_logging import set_trace_id, set_user_id, set_session_id
    from app.core.metrics import chat_requests_total, chat_request_duration_seconds
    import time as _t

    ctx = MiddlewareContext(user_id=user_id, session_id=session_id)
    # 设置 trace_id 上下文(贯穿整个请求)
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
            # N15 修复: 直接用 current.role, 不重新解码 JWT (避免重复解析)
            is_staff = current.role in ("staff", "admin")
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
        result = await run_with_middlewares(ctx, lambda: chat_service.chat_handler(body, ctx, enable_self_rag=body.get("enable_self_rag", False)))
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
    finally:
        # 成功才缓存(避免缓存错误结果)
        if "result" in dir() and result is not None:
            try:
                await cache_set(idem_cache, idem_key, result)
            except Exception:
                pass


def _load_session_state(user_id: int, session_id: str) -> dict:
    """从 AgentStateStore 加载会话状态(借鉴 AgentScope 2.0)."""
    from app.core.agent_state_store import get_state_store
    store = get_state_store()
    state = store.get(str(user_id), session_id, "agent_state") or {}
    if state:
        logger.debug("恢复 session state: %s/%s", user_id, session_id)
    return state


# 6 个 chat 子端点 (history / sessions) 已搬到 routers/chat.py (N14)


# ============================================================
# HITL(人在回路)权限 API
# ============================================================












# ==================================================================
# Router 注册
# ==================================================================
# P0-1 修复: FastAPI 0.141 include_router 有 bug (路由不生效)
# 用手动 routes.extend 代替
from app.server.routers import (
    auth as auth_router,
    branches as branches_router,
    stylists as stylists_router,
    services as services_router,
    orders as orders_router,
    chat_stream,
    chat as chat_router,
    rag as rag_router,
    admin as admin_router,
    skills as skills_router,
    user_facts as user_facts_router,
    permission as permission_router,
)

for r in (
    auth_router.router, branches_router.router, stylists_router.router,
    services_router.router, orders_router.router, chat_stream.router,
    chat_router.router,
    rag_router.router, admin_router.router,
    skills_router.router, user_facts_router.router, permission_router.router,
):
    # P0-1 修复: FastAPI 0.141 include_router 有 bug (路由不生效)
    # 用手动 routes.extend 代替; 0.142+ 已修, 走正常 include_router 避免重复注册
    import fastapi as _fastapi
    if _fastapi.__version__ < "0.142":
        app.router.routes.extend(r.routes)
    else:
        app.include_router(r)
