# -*- coding: utf-8 -*-
"""AgentStateStore 接口 + JsonFile 实现。

借鉴 AgentScope 2.0 的 AgentStateStore 设计：
- 接口：save / get / getList / exists / delete / listSessionIds
- 三元组定位：(userId, sessionId, key) → State
- safe(filename) 防路径遍历
- 多后端切换只改一行初始化代码
"""
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
    """获取全局状态存储单例。"""
    global _state_store
    if _state_store is None:
        from app.core.config import agent_state_config
        if agent_state_config.backend == "memory":
            _state_store = InMemoryAgentStateStore()
        else:
            _state_store = JsonFileAgentStateStore(agent_state_config.root_path)
    return _state_store
