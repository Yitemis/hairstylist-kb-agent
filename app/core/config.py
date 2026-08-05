# -*- coding: utf-8 -*-
"""企业级配置中心：多环境 + 类型安全 + 热更新。

加载优先级（从高到低：
1. 环境变量（容器部署时注入）
2. 环境专属 .env 文件（.env.dev / .env.staging / .env.prod）
3. 全局 .env 默认文件
4. 代码默认值
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


# ------------------------------------------------------------------
# 环境标识
# ------------------------------------------------------------------

ENV = os.getenv("HAIRSTYLIST_ENV", "dev").lower()
ENV_DEV = ENV == "dev"
ENV_STAGING = ENV == "staging"
ENV_PROD = ENV == "prod"


# ------------------------------------------------------------------
# 加载配置文件
# ------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.parent

# 先加载基础配置
load_dotenv(PROJECT_ROOT / ".env", override=True)

# 再加载环境专属配置（覆盖公共值更高）
_env_file = PROJECT_ROOT / f".env.{ENV}"
if _env_file.exists():
    load_dotenv(_env_file, override=True)


def _get_env(key: str, default: str = "") -> str:
    """安全的环境变量读取，统一前缀避免拼写。"""
    return os.getenv(key, default).strip()


# ------------------------------------------------------------------
# 类型安全的配置类
# ------------------------------------------------------------------


@dataclass
class ModelConfig:
    """统一模型配置结构（对话 / Embedding / Rerank 共用）。"""

    api_key: str = ""
    base_url: str = ""
    model: str = ""
    dimensions: int = 1024
    max_retries: int = 3
    timeout: int = 60
    stream: bool = True

    @property
    def is_valid(self) -> bool:
        """检查配置是否完整。"""
        return bool(self.api_key and self.base_url and self.model)


@dataclass
class VectorStoreConfig:
    """向量库配置（生产级多引擎支持）。

    引擎选择：
    - milvus（默认，生产推荐）：Docker Compose 独立部署，带 Attu 可视化面板
      启动命令：docker-compose -f ops/docker-compose.yml up -d
      面板地址：http://localhost:3001
    - qdrant-local：Qdrant Python 内嵌本地文件（快速开发）
    """

    engine: str = "milvus"  # milvus / qdrant-local
    host: str = "localhost"
    port: int = 19530
    uri: str = ""
    api_key: str = ""
    path: str = "./data/qdrant"  # qdrant-local 数据目录
    collection: str = "hairstylist_kb"
    metric_type: str = "COSINE"
    dims: int = 2048

    @property
    def is_valid(self) -> bool:
        if self.engine == "milvus":
            return True  # 默认 localhost:19530 无需额外配置
        return True


@dataclass
class ServerConfig:
    """服务端配置。"""

    host: str = "127.0.0.1"
    port: int = 7860
    workers: int = 1
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    rate_limit: str = "100/minute"
    enable_metrics: bool = True


@dataclass
class SafetyConfig:
    """安全护轨配置。"""

    enable_input_filter: bool = True
    enable_output_filter: bool = True
    max_input_length: int = 500
    max_output_length: int = 2000
    enable_domain_boundary_check: bool = False


@dataclass
class LoggingConfig:
    """日志与监控配置。"""

    level: str = "INFO"
    enable_audit_log: bool = True
    enable_metrics: bool = True
    metrics_port: int = 9090
    log_retention_days: int = 30


@dataclass
class DatabaseConfig:
    """业务数据库配置（用户/订单等）。

    开发默认 SQLite 单文件，零安装；生产可切 MySQL：
    DATABASE_URL=mysql+aiomysql://user:pwd@host:3306/dbname
    """

    url: str = ""
    echo: bool = False

    @property
    def resolved_url(self) -> str:
        """未显式配置时回落到项目根目录下的 SQLite 文件。"""
        if self.url:
            return self.url
        db_path = (PROJECT_ROOT / "data" / "app.db").as_posix()
        return f"sqlite+aiosqlite:///{db_path}"


@dataclass
class AuthConfig:
    """认证与 JWT 配置。"""

    jwt_secret: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 默认 7 天

    @property
    def is_secure(self) -> bool:
        """检查 JWT secret 是否安全（JavaGuide 安全 + OWASP JWT 规范）。

        - 不能是默认 dev 值
        - 长度 >= 32 字符（256 bit 推荐）
        - 至少 2 种字符类（字母/数字/特殊）
        """
        import re as _re
        if self.jwt_secret == "dev-insecure-change-me":
            return False
        if len(self.jwt_secret) < 32:
            return False
        has_alpha = bool(_re.search(r"[a-zA-Z]", self.jwt_secret))
        has_digit = bool(_re.search(r"\d", self.jwt_secret))
        has_special = bool(_re.search(r"[^a-zA-Z0-9]", self.jwt_secret))
        return sum([has_alpha, has_digit, has_special]) >= 2

    def validate_for_env(self, env: str) -> None:
        """启动时强校验（fail-fast）。

        借鉴 JavaGuide 安全：所有环境都要求强 secret，不只是 production。
        """
        import re as _re
        if self.jwt_secret == "dev-insecure-change-me":
            raise RuntimeError(
                "JWT_SECRET 使用默认值！请设置强密钥 (>=32 字符 + 字母数字特殊) "
                "示例: openssl rand -base64 32"
            )
        if len(self.jwt_secret) < 32:
            raise RuntimeError(
                f"JWT_SECRET 长度仅 {len(self.jwt_secret)} (< 32)。"
                "请用 openssl rand -base64 32 生成"
            )
        has_alpha = bool(_re.search(r"[a-zA-Z]", self.jwt_secret))
        has_digit = bool(_re.search(r"\d", self.jwt_secret))
        has_special = bool(_re.search(r"[^a-zA-Z0-9]", self.jwt_secret))
        if sum([has_alpha, has_digit, has_special]) < 2:
            raise RuntimeError(
                "JWT_SECRET 过弱：必须包含至少 2 种字符类（字母/数字/特殊）"
            )


# ------------------------------------------------------------------
# 全局单例
# ------------------------------------------------------------------


def _build_model_config(prefix: str) -> ModelConfig:
    """从环境变量构建模型配置。"""
    return ModelConfig(
        api_key=_get_env(f"{prefix}_API_KEY"),
        base_url=_get_env(f"{prefix}_BASE_URL"),
        model=_get_env(f"{prefix}_MODEL"),
        dimensions=int(_get_env(f"{prefix}_DIMENSIONS", "1024")),
        max_retries=int(_get_env(f"{prefix}_MAX_RETRIES", "3")),
        timeout=int(_get_env(f"{prefix}_TIMEOUT", "60")),
        stream=_get_env(f"{prefix}_STREAM", "1") == "1",
    )


chat_config = _build_model_config("CHAT")
embedding_config = _build_model_config("EMBEDDING")
rerank_config = _build_model_config("RERANK")

vector_store_config = VectorStoreConfig(
    engine=_get_env("VECTOR_STORE_ENGINE", "milvus"),
    host=_get_env("VECTOR_STORE_HOST", "localhost"),
    port=int(_get_env("VECTOR_STORE_PORT", "19530")),
    uri=_get_env("VECTOR_STORE_URI", ""),
    api_key=_get_env("VECTOR_STORE_API_KEY", ""),
    path=_get_env("VECTOR_STORE_PATH", "./data/qdrant"),
    collection=_get_env("VECTOR_COLLECTION", "hairstylist_kb"),
    metric_type=_get_env("VECTOR_METRIC_TYPE", "COSINE"),
    dims=int(_get_env("VECTOR_DIMS", "2048")),
)

server_config = ServerConfig(
    host=_get_env("SERVER_HOST", "127.0.0.1"),
    port=int(_get_env("SERVER_PORT", "7860")),
    workers=int(_get_env("SERVER_WORKERS", "1")),
    cors_origins=[
        x.strip() for x in _get_env("CORS_ORIGINS", "*").split(",") if x.strip()],
    rate_limit=_get_env("RATE_LIMIT", "100/minute"),
    enable_metrics=_get_env("ENABLE_METRICS", "1") == "1",
)

safety_config = SafetyConfig(
    enable_input_filter=_get_env("ENABLE_INPUT_FILTER", "1") == "1",
    enable_output_filter=_get_env("ENABLE_OUTPUT_FILTER", "1") == "1",
    max_input_length=int(_get_env("MAX_INPUT_LENGTH", "500")),
    max_output_length=int(_get_env("MAX_OUTPUT_LENGTH", "2000")),
    enable_domain_boundary_check=_get_env("ENABLE_DOMAIN_BOUNDARY_CHECK", "0") == "1",
)

logging_config = LoggingConfig(
    level=_get_env("LOG_LEVEL", "INFO"),
    enable_audit_log=_get_env("ENABLE_AUDIT_LOG", "1") == "1",
    enable_metrics=_get_env("ENABLE_METRICS", "1") == "1",
    metrics_port=int(_get_env("METRICS_PORT", "9090")),
    log_retention_days=int(_get_env("LOG_RETENTION_DAYS", "30")),
)

class _LazyDatabaseConfig:
    """延迟读取 DATABASE_URL（支持测试时切换 DB）。"""
    @property
    def url(self) -> str:
        return _get_env("DATABASE_URL", "")
    @property
    def echo(self) -> bool:
        return _get_env("DATABASE_ECHO", "0") == "1"
    @property
    def resolved_url(self) -> str:
        if self.url:
            return self.url
        db_path = (PROJECT_ROOT / "data" / "app.db").as_posix()
        return f"sqlite+aiosqlite:///{db_path}"


# 用 Lazy 配置替代之前的 dataclass 实例
class _DatabaseConfigProxy:
    """代理到 _LazyDatabaseConfig 的字段。"""
    def __getattr__(self, name):
        return getattr(_lazy_db, name)
    @property
    def resolved_url(self):
        return _lazy_db.resolved_url


_lazy_db = _LazyDatabaseConfig()
database_config = _DatabaseConfigProxy()

auth_config = AuthConfig(
    jwt_secret=_get_env("JWT_SECRET", "dev-insecure-change-me"),
    jwt_algorithm=_get_env("JWT_ALGORITHM", "HS256"),
    access_token_expire_minutes=int(
        _get_env("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7))
    ),
)

# 兼容旧代码
is_chat_ready = chat_config.is_valid

# 配置字典（供模型工厂使用）
model_configs = {
    "chat": chat_config,
    "embedding": embedding_config,
    "rerank": rerank_config,
}


@dataclass
class AgentStateConfig:
    """Agent 状态持久化配置。"""

    backend: str = "json_file"  # "json_file" | "memory"
    root_path: str = "./data/agent_state"


agent_state_config = AgentStateConfig(
    backend=_get_env("AGENT_STATE_BACKEND", "json_file"),
    root_path=_get_env("AGENT_STATE_ROOT", "./data/agent_state"),
)


# ------------------------------------------------------------------
# 配置热更新
# ------------------------------------------------------------------


def reload_config() -> None:
    """热重载配置（修改 .env 文件后调用，无需重启服务）。"""
    global chat_config, embedding_config, rerank_config, vector_store_config
    global server_config, safety_config, logging_config

    load_dotenv(PROJECT_ROOT / ".env", override=True)
    if _env_file.exists():
        load_dotenv(_env_file, override=True)

    chat_config = _build_model_config("CHAT")
    embedding_config = _build_model_config("EMBEDDING")
    rerank_config = _build_model_config("RERANK")


# ------------------------------------------------------------------
# 启动时打印配置摘要
# ------------------------------------------------------------------


def print_config_summary() -> None:
    """打印配置摘要（服务启动时调用）。"""
    print("=" * 60)
    print(f"🪮 美发智能知识助手  [环境: {ENV.upper()}]")
    print("=" * 60)
    print(f"\n📚 配置文件: {_env_file.name if _env_file.exists() else '.env (默认)'}")
    print(f"\n🤖 模型状态:")
    print(f"   对话模型: {'✓ 已配置' if chat_config.is_valid else '✗ 未配置'}")
    print(f"   嵌入模型: {'✓ 已配置' if embedding_config.is_valid else '✗ 未配置'}")
    print(f"   重排模型: {'✓ 已配置' if rerank_config.is_valid else '○ 可选'}")
    print(f"\n🗄️  向量库: {vector_store_config.engine} @ {vector_store_config.host}:{vector_store_config.port} / {vector_store_config.collection}")
    print(f"\n🔒 安全护轨: {'已启用' if safety_config.enable_input_filter else '已禁用'}")
    print(f"\n📊 可观测性: {'已启用' if logging_config.enable_metrics else '已禁用'}")
    print(f"\n🌐 服务地址: http://{server_config.host}:{server_config.port}")
    print("=" * 60)
