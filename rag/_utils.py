# -*- coding: utf-8 -*-
"""RAG 模块通用工具。"""
import uuid


def generate_id() -> str:
    """生成一个唯一 ID（用于父块标识等）。

    使用 uuid4 的 hex 形式，短小且无碰撞风险。
    """
    return uuid.uuid4().hex
