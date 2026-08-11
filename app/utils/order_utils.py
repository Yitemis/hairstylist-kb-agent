# -*- coding: utf-8 -*-
"""订单相关公共工具（P2-1 去重）。

借鉴 JavaGuide: 公共逻辑下沉到工具类，禁止重复实现。
"""
from __future__ import annotations

import random
import secrets
from datetime import datetime


def generate_order_no() -> str:
    """生成订单号：YYMMDD + 8位随机（4 hex 高熵，避免碰撞）。

    之前在 orders.py:28 和 order_tools.py:46 各有一份，现统一。
    """
    prefix = datetime.now().strftime("%y%m%d")
    suffix = secrets.token_hex(4).upper()
    return f"{prefix}{suffix}"
