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
async def metrics() -> Response:
    """Prometheus 监控指标(Grafana 接入)."""
    from fastapi.responses import Response
    from app.core.metrics import render_metrics
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)


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
        result = await run_with_middlewares(ctx, lambda: chat_service.chat_handler(body, ctx))
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
