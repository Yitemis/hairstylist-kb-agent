# CI/CD 流程 (GitHub Actions)

> 借鉴 GitHub Actions + 12-factor app 部署理念

## 📊 Pipeline 概览

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  unit-tests │ ──> │ integration-tests│ ──> │  deploy (optional)│
│  (≤30s)     │     │  (5-10 min)      │     │                   │
└─────────────┘     └──────────────────┘     └──────────────────┘
```

## Job 1: unit-tests (快速, 无服务)

**触发**: 每次 push / PR

**步骤**:
1. 装依赖 (pip install -r requirements.txt)
2. 跑**纯单元测试** (无 PG / Milvus 依赖):
   - `test_audience_isolation_unit.py` - RBAC 隔离
   - `test_idempotency.py` - LLM 缓存
   - `test_jwt_security.py` - JWT 强校验
   - `test_metrics.py` - Prometheus 指标
   - `test_milvus_store.py` - Milvus 适配器
   - `test_mineru_backends.py` - MinerU 多后端
   - `test_model_gateway.py` - Model Gateway
   - `test_model_router.py` - ModelRouter
3. Python 语法检查 (compileall)

**为什么快**: 无数据库启动, 30 秒内

## Job 2: integration-tests (完整集成, 5-10 分钟)

**触发**: 依赖 unit-tests 通过

**服务容器**:
- `postgres:16-alpine` (port 5432)
- Milvus standalone (port 19530) - 用 `standalone_embed.sh` 或 docker compose

**步骤**:
1. 装依赖
2. 启动 Milvus stack (etcd + minio + milvus)
3. 等服务 ready (pg_isready + curl milvus health)
4. `alembic upgrade head` (建表)
5. 跑**全部测试** (除了慢的 RAG pipeline)

**为什么慢**: Milvus 启动 + 真实 embedding API

## 🚀 本地运行 (开发用)

```bash
# 跑全部测试
pytest tests/ -v

# 跑纯单测 (30 秒)
pytest tests/test_idempotency.py tests/test_jwt_security.py tests/test_metrics.py \
       tests/test_model_gateway.py tests/test_model_router.py -v

# 跑单测 + 集成
DATABASE_URL="postgresql+asyncpg://hair:hair123@localhost:5432/hairstylist" \
  pytest tests/ -v --ignore=tests/test_rag_pipeline.py
```

## 📊 当前测试统计

| 类型 | 文件数 | 测试数 |
|------|--------|--------|
| 纯单元 | 8+ | ~80 |
| 集成 (需 PG) | 10+ | ~120 |
| 慢 (RAG pipeline) | 1 | 5 |
| **总计** | **20+** | **~200** |

## 🎯 借鉴 vs 改进

| 业界 CI 实践 | 我们做法 |
|--------------|---------|
| 1 个 unit + 1 个 integration job | ✅ 2 个 job (快速 + 完整) |
| Cache pip dependencies | ✅ `cache: pip` |
| Service containers (PG/Redis) | ✅ PG via service |
| Milvus in CI | ⚠️ 复杂 (需 etcd+minio)，用 docker fallback |
| Test parallelization | ⚠️ 暂未 (单线程 pytest) |
| Coverage report | ⚠️ 暂未 (后续加) |
| Auto deploy on main | ⏳ 后续 (K8s 时加) |

## 🔮 未来改进

1. **Coverage report** (codecov.io) - 跟踪代码覆盖率
2. **Performance benchmark** (locust) - 性能回归测试
3. **Lint job** (ruff + black) - 代码风格
4. **Security scan** (bandit + safety) - 安全漏洞
5. **Auto deploy to staging** (PR merge 后) - 持续部署
6. **Release workflow** (semantic-versioning) - 自动发版
