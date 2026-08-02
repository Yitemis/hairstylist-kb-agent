# -*- coding: utf-8 -*-
"""结构化日志：JSON 格式 + 自动 trace_id + 上下文注入。

生产环境推荐用 JSON 日志，方便 Loki/ELK 索引。
开发环境用普通文本日志，方便人眼读。
"""
from __future__ import annotations

import json
import logging
import sys
import time
from contextvars import ContextVar
from typing import Any

# 上下文变量：贯穿整个请求生命周期
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")
user_id_var: ContextVar[int] = ContextVar("user_id", default=0)
session_id_var: ContextVar[str] = ContextVar("session_id", default="-")


def set_trace_id(trace_id: str) -> None:
    trace_id_var.set(trace_id)


def set_user_id(user_id: int) -> None:
    user_id_var.set(user_id)


def set_session_id(session_id: str) -> None:
    session_id_var.set(session_id)


class JSONFormatter(logging.Formatter):
    """JSON 格式化器：每条日志一行 JSON。"""

    def __init__(self, service: str = "hairstylist-api") -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        # 默认字段
        log_entry: dict[str, Any] = {
            "ts": time.time(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "service": self.service,
        }
        # 上下文（如果有）
        try:
            log_entry["trace_id"] = trace_id_var.get()
            log_entry["user_id"] = user_id_var.get()
            log_entry["session_id"] = session_id_var.get()
        except LookupError:
            pass
        # 异常信息
        if record.exc_info:
            log_entry["exc_info"] = self.formatException(record.exc_info)
        # 额外字段（通过 extra={"foo": "bar"} 传入）
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "message", "asctime",
            ):
                log_entry[key] = value
        return json.dumps(log_entry, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    """初始化日志（启动时调用一次）。"""
    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # 抑制 agentscope 过于啰嗦的日志
    logging.getLogger("agentscope").setLevel("WARNING")
    logging.getLogger("httpx").setLevel("WARNING")
