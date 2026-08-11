# -*- coding: utf-8 -*-
"""skills 路由 (从 api.py 拆出)。

鉴权 (N12 修复):
- list / get / search 端点: 任意登录用户可读
- reload 端点: 必须 staff (文件 I/O + DOS 防护)
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, get_current_user, require_staff
from app.db.session import get_session

router = APIRouter(prefix="/api", tags=["skills"])


@router.get("/skills", summary="列出所有技能")
async def list_skills(
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict]:
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


@router.get("/skills/{skill_id}", summary="获取技能详情")
async def get_skill(
    skill_id: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
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


@router.post("/skills/search", summary="根据查询找相关技能")
async def search_skills(
    body: dict,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
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


@router.post("/skills/reload", summary="从目录重新加载技能")
async def reload_skills(
    current: Annotated[CurrentUser, Depends(require_staff)],
) -> dict:
    """从 ./data/skills 目录重新加载所有 .md 技能文件 (staff-only, N12)。"""
    from app.core.skill import get_skill_registry
    registry = get_skill_registry()
    n = registry.load_from_dir("./data/skills")
    return {"status": "ok", "loaded": n}


