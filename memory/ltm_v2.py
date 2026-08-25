"""长期记忆增强版：去重 + 失效 + 语义相似合并。

借鉴 Mem0 / Letta 的"记忆生命周期"理念：
- 短期：每轮对话产生的 fact
- 长期：user_profiles 表（已有）
- 失效：同 key 新 value 覆盖旧（已有）
- 去重：新 fact 与已有做 embedding 相似度合并

高级特性：
1. delete_user_fact(user_id, fact_key) - 用户主动删除
2. merge_similar_facts(user_id, threshold=0.92) - 相似 fact 合并
3. get_recent_facts(user_id, days=30) - 时间窗口过滤
4. fact_count_per_user - 统计
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def delete_user_fact(user_id: int, fact_key: str) -> bool:
    """删除用户某条事实。

    用途：用户撤回（"我不要记住这个"）/ 隐私合规（GDPR）。
    """
    from app.db.models import UserProfile
    from app.db.session import async_session_maker
    from sqlalchemy import delete as sa_delete

    async with async_session_maker() as session:
        stmt = sa_delete(UserProfile).where(
            UserProfile.user_id == user_id,
            UserProfile.fact_key == fact_key,
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0


async def get_recent_facts(user_id: int, days: int = 30) -> list[dict[str, Any]]:
    """获取用户最近 N 天的事实（按时间窗口）。"""
    from app.db.models import UserProfile
    from app.db.session import async_session_maker
    from sqlalchemy import select
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now() - timedelta(days=days)  # naive datetime, match PG TIMESTAMP WITHOUT TIMEZONE
    async with async_session_maker() as session:
        stmt = (
            select(UserProfile)
            .where(
                UserProfile.user_id == user_id,
                UserProfile.updated_at >= cutoff,
            )
            .order_by(UserProfile.confidence.desc(), UserProfile.updated_at.desc())
        )
        rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "key": r.fact_key,
            "value": r.fact_value,
            "confidence": r.confidence,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


async def fact_count_per_user() -> dict[int, int]:
    """统计每用户事实数（用于监控 + 限流）。"""
    from app.db.models import UserProfile
    from app.db.session import async_session_maker
    from sqlalchemy import select, func

    async with async_session_maker() as session:
        stmt = (
            select(UserProfile.user_id, func.count(UserProfile.id))
            .group_by(UserProfile.user_id)
        )
        rows = (await session.execute(stmt)).all()
    return {user_id: count for user_id, count in rows}


async def merge_similar_facts(user_id: int, similarity_threshold: float = 0.92) -> int:
    """用 embedding 相似度合并同 key 的相似 fact。

    场景：用户 3 个月说"我不喜欢短刘海"，3 天后说"短刘海显脸大"
    → 两条 fact 语义相似，合并为 "我不喜欢短刘海（显脸大）"

    Returns: 合并的数量
    """
    from app.db.models import UserProfile
    from app.db.session import async_session_maker
    from sqlalchemy import select
    from app.rag.v2_engine import _get_embedding
    import numpy as np

    async with async_session_maker() as session:
        stmt = (
            select(UserProfile)
            .where(UserProfile.user_id == user_id)
            .order_by(UserProfile.updated_at.desc())
        )
        facts = list((await session.execute(stmt)).scalars().all())
        if len(facts) < 2:
            return 0

        # Embedding 全部 fact
        texts = [f"{f.fact_key}: {f.fact_value}" for f in facts]
        try:
            vecs = await _get_embedding(texts)
        except Exception as e:
            logger.warning("Embedding for fact merge failed: %s", e)
            return 0
        if not vecs:
            return 0

        # 找相似对 (cosine > threshold)
        merged_count = 0
        vec_arr = np.array(vecs, dtype=np.float32)
        # Normalize
        norms = np.linalg.norm(vec_arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vec_norm = vec_arr / norms

        # 简单 O(n^2) - 假设每用户 fact 不会超过 100
        n = len(facts)
        to_delete = set()
        for i in range(n):
            if i in to_delete:
                continue
            for j in range(i + 1, n):
                if j in to_delete:
                    continue
                sim = float(vec_norm[i] @ vec_norm[j])
                if sim > similarity_threshold:
                    # 合并 i+j → i（保留最新的 + 高 confidence）
                    if facts[i].confidence < facts[j].confidence:
                        facts[i].fact_value = facts[j].fact_value
                        facts[i].confidence = facts[j].confidence
                    to_delete.add(j)
                    merged_count += 1

        for j in to_delete:
            await session.delete(facts[j])
        await session.commit()
    logger.info("Merged %d similar facts (user=%d)", merged_count, user_id)
    return merged_count


async def extract_and_save_facts_v2(
    user_id: int,
    user_message: str,
    ai_message: str,
    auto_merge: bool = True,
) -> int:
    """高级版：提取 + 保存 + 自动合并。"""
    from app.core.long_term_memory import extract_facts_with_llm, save_facts
    facts = await extract_facts_with_llm(user_id, user_message, ai_message)
    saved = await save_facts(user_id, facts)
    if auto_merge and saved > 0:
        try:
            await merge_similar_facts(user_id)
        except Exception as e:
            logger.debug("Auto-merge failed: %s", e)
    return saved
