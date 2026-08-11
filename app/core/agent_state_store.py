# -*- coding: utf-8 -*-
"""Agent 状态持久化。"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 安全的文件名字符（只允许字母数字下划线点和短横线）
_SAFE_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-.=]+$")
_SAFE_DIR_PATTERN = re.compile(r"^[a-zA-Z0-9_\-.=]+$")


def _safe_dirname(name: str) -> str:
    """把不安全的 userId / sessionId 编码成安全目录名。

    如果包含危险字符（路径遍历），用 base64 编码；否则直接返回。
    """
    if _SAFE_DIR_PATTERN.match(name):
        return name
    import base64
    return "b64_" + base64.urlsafe_b64encode(name.encode("utf-8")).decode("ascii").rstrip("=")


class AgentStateStore(ABC):
    """Agent 状态持久化抽象接口。

    借鉴 AgentScope 2.0：
        void save(String userId, String sessionId, String key, State value);
        <T extends State> Optional<T> get(...);
        boolean exists(...);
        void delete(...);
        Set<String> listSessionIds(userId);
    """

    @abstractmethod
    def save(self, user_id: str, session_id: str, key: str, value: Any) -> None: ...

    @abstractmethod
    def get(self, user_id: str, session_id: str, key: str) -> Any | None: ...

    @abstractmethod
    def exists(self, user_id: str, session_id: str) -> bool: ...

    @abstractmethod
    def delete(self, user_id: str, session_id: str) -> None: ...

    @abstractmethod
    def list_session_ids(self, user_id: str) -> list[str]: ...


class JsonFileAgentStateStore(AgentStateStore):
    """本地 JSON 文件实现。

    目录结构：
        <root>/
          <safe(userId)>/
            <safe(sessionId)>/
              agent_state.json
              memory_messages.jsonl
    """

    def __init__(self, root: str = "./data/agent_state") -> None:
        # 转绝对路径，避免 cwd 不同导致找不到
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        logger.info("JsonFileAgentStateStore 初始化: %s", self.root)

    def _dir_for(self, user_id: str, session_id: str) -> Path:
        return self.root / _safe_dirname(user_id) / _safe_dirname(session_id)

    def _path_for(self, user_id: str, session_id: str, key: str) -> Path:
        if not _SAFE_FILENAME_PATTERN.match(key):
            raise ValueError(f"非法的 key: {key}")
        return self._dir_for(user_id, session_id) / f"{key}.json"

    def save(self, user_id: str, session_id: str, key: str, value: Any) -> None:
        path = self._path_for(user_id, session_id, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(value, "model_dump"):
            data = value.model_dump()
        elif isinstance(value, dict):
            data = value
        else:
            data = value.__dict__ if hasattr(value, "__dict__") else value
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug("save: %s/%s/%s", user_id, session_id, key)

    def get(self, user_id: str, session_id: str, key: str) -> Any | None:
        try:
            path = self._path_for(user_id, session_id, key)
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("get 失败: %s", e)
            return None

    def exists(self, user_id: str, session_id: str) -> bool:
        return self._dir_for(user_id, session_id).exists()

    def delete(self, user_id: str, session_id: str) -> None:
        import shutil
        d = self._dir_for(user_id, session_id)
        if d.exists():
            shutil.rmtree(d)
            logger.info("delete session: %s/%s", user_id, session_id)

    def list_session_ids(self, user_id: str) -> list[str]:
        d = self.root / _safe_dirname(user_id)
        if not d.exists():
            logger.warning("user dir not exist: %s (cwd=%s, root=%s)", d, Path.cwd(), self.root)
            return []
        result = sorted([p.name for p in d.iterdir() if p.is_dir()])
        logger.debug("list_session_ids: user=%s -> %s", user_id, result)
        return result


class InMemoryAgentStateStore(AgentStateStore):
    """内存实现（测试用）。"""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str, str], Any] = {}

    def save(self, user_id, session_id, key, value) -> None:
        self._data[(user_id, session_id, key)] = value

    def get(self, user_id, session_id, key):
        return self._data.get((user_id, session_id, key))

    def exists(self, user_id, session_id) -> bool:
        return any(s == session_id for u, s, _ in self._data if u == user_id)

    def delete(self, user_id, session_id) -> None:
        for k in list(self._data.keys()):
            if k[0] == user_id and k[1] == session_id:
                del self._data[k]

    def list_session_ids(self, user_id) -> list[str]:
        return sorted({s for u, s, _ in self._data if u == user_id})


# 全局单例
_state_store: AgentStateStore | None = None


def get_state_store() -> AgentStateStore:
    """获取全局状态存储单例。

    后端选择：
    - memory: InMemoryAgentStateStore（测试用）
    - redis: RedisAgentStateStore（生产用，多副本安全，P0-5 真实接入）
    - file: JsonFileAgentStateStore（开发用，单副本）
    """
    global _state_store
    if _state_store is None:
        from app.core.config import agent_state_config
        backend = agent_state_config.backend
        if backend == "memory":
            _state_store = InMemoryAgentStateStore()
        elif backend == "redis":
            _state_store = RedisAgentStateStore.from_env()
        else:
            _state_store = JsonFileAgentStateStore(agent_state_config.root_path)
    return _state_store


class RedisAgentStateStore(AgentStateStore):
    """P0-5: Redis 实现（生产级，多 worker 安全，跨进程共享）。

    Key 设计:
        {prefix}:{user_id}:{session_id}:{key} → JSON
        {prefix}:sessions:{user_id} → set[session_id]
    """

    PREFIX = "agent_state"

    def __init__(self, redis_client) -> None:
        self.r = redis_client

    @classmethod
    def from_env(cls) -> "RedisAgentStateStore":
        """从 REDIS_URL 构造（带降级：连不上走 file）。"""
        import os
        import redis
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        try:
            client = redis.from_url(url, decode_responses=True, socket_timeout=2)
            client.ping()
            logger.info("RedisAgentStateStore 连接成功: %s", url)
            return cls(client)
        except Exception as e:
            # N1 修复: 降级到 JsonFile（开发可用，单进程），不再用 InMemory（生产丢数据）
            logger.warning("Redis 连不上 (%s)，降级到 JsonFile", e)
            from app.core.config import agent_state_config
            return JsonFileAgentStateStore(agent_state_config.root_path)

    def _k(self, user_id: str, session_id: str, key: str) -> str:
        return f"{self.PREFIX}:{user_id}:{session_id}:{key}"

    def _sk(self, user_id: str) -> str:
        return f"{self.PREFIX}:sessions:{user_id}"

    def save(self, user_id, session_id, key, value) -> None:
        if hasattr(value, "model_dump"):
            data = value.model_dump()
        elif isinstance(value, dict):
            data = value
        else:
            data = value.__dict__ if hasattr(value, "__dict__") else value
        import json
        self.r.set(self._k(user_id, session_id, key), json.dumps(data, ensure_ascii=False))
        self.r.sadd(self._sk(user_id), session_id)

    def get(self, user_id, session_id, key):
        import json
        raw = self.r.get(self._k(user_id, session_id, key))
        return json.loads(raw) if raw else None

    def exists(self, user_id, session_id) -> bool:
        return self.r.sismember(self._sk(user_id), session_id)

    def delete(self, user_id, session_id) -> None:
        # 删所有属于该 session 的 key（用 SCAN 避免 KEYS 阻塞）
        for k in self.r.scan_iter(f"{self.PREFIX}:{user_id}:{session_id}:*"):
            self.r.delete(k)
        self.r.srem(self._sk(user_id), session_id)

    def list_session_ids(self, user_id) -> list[str]:
        return sorted(self.r.smembers(self._sk(user_id)) or set())
