# -*- coding: utf-8 -*-
"""Admin 运维端点 (从 api.py 抽出)。

权限：只允许 admin 角色访问。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import CurrentUser, get_current_user

router = APIRouter(prefix="/api/admin", tags=["Admin 运维"])


@router.post("/archive", summary="手动触发数据归档")
async def admin_archive(
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """手动触发数据归档（运维用）。"""
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="需要 admin 权限")
    from app.core.archiver import archive_old_data
    result = await archive_old_data()
    return {"status": "ok", "archived": result}
