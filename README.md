# 美发智能知识助手 (Hairstylist KB Agent)

> 企业级 RAG + 多模态对话系统，借鉴 AWS Bedrock multi-model 路由 + JavaGuide 高可用设计。

## 📊 项目状态

- **测试**: 200+ 通过
- **代码**: 5000+ 行核心代码
- **提交**: 25+ 次
- **Stage**: 1+2 全部完成

## 🏗️ 项目结构

```
hairstylist-kb-agent/
├── app/                              # 主应用代码
│   ├── __init__.py
│   ├── auth/                         # 认证 (JWT, RBAC)
│   ├── core/                         # 核心业务
│   │   ├── config.py                 # 配置 (Lazy 读 env)
│   │   ├── model_factory.py          # LLM/Embedding/Rerank 工厂
│   │   ├── long_term_memory.py       # L1 长期记忆
│   │   ├── archiver.py               # P0-5 数据归档
│   │   ├── cache/                    # LLM 缓存 (LRU)
│   │   ├── concurrency/              # P1 分布式锁
│   │   ├── gateway/                  # P0-3 Model Gateway (熔断+降级)
│   │   ├── tools/                    # Agent 工具集
│   │   └── ... (metrics, middleware, etc.)
│   ├── db/                           # SQLAlchemy 模型 + session
│   ├── embedding/                    # Embedding 适配器
│   │   ├── ark_vision_embedding.py   # 火山方舟多模态
│   │   ├── siliconflow_text_embedding.py  # 硅基流动文本
│   │   └── router.py                 # ModelRouter (5 capability)
│   ├── rag/                          # RAG 引擎
│   │   ├── v2_engine.py              # 父子分块 + 检索
│   │   ├── image_indexer.py          # VLM 图片 RAG
│   │   ├── multimodal_chat.py        # 多模态对话
│   │   ├── context_compression.py    # LLMLingua 借鉴
│   │   ├── hybrid/                   # BM25 + Vector + RRF
│   │   ├── query/                    # 6 策略查询改写
│   │   ├── parsers/                  # PDF/Word/Excel
│   │   ├── chunkers/                 # 父子分块
│   │   └── evaluation/               # 评估集 (30 query)
│   ├── safety/                       # 安全 (敏感词 / HITL)
│   ├── schemas/                      # Pydantic schemas
│   └── server/                       # FastAPI 入口
│       ├── api.py                    # 主路由
│       └── routers/                  # 业务路由
├── tests/                            # 200+ 测试
├── alembic/                          # DB 迁移
├── scripts/                          # 工具脚本
│   ├── ingest_mineru_output.py      # PDF → RAG 入库
│   ├── run_rag_evaluation.py         # 跑评估集
│   ├── init_test_data.py             # 初始化业务数据
│   └── setup_env_paths.sh            # E 盘环境变量
├── docs/                             # 学习文档 (含 RAGAS/JavaGuide/ekbs 借鉴)
├── deploy/                           # 部署配置 (Prometheus)
├── frontend/                         # 前端 (React)
├── data/                             # 业务数据
├── docker-compose.yml                # PG + Milvus + Redis
├── Dockerfile                        # 镜像构建
├── requirements.txt
├── pytest.ini
├── alembic.ini
└── .env.example
```

## 🚀 快速开始

```bash
# 1. 启动依赖
docker-compose up -d

# 2. 安装依赖
pip install -r requirements.txt

# 3. 数据库迁移
alembic upgrade head

# 4. 启动服务
uvicorn app.server.api:app --reload

# 5. 跑测试
pytest tests/ -v
```

## 🛠️ 技术栈

| 类别 | 技术 |
|------|------|
| LLM | 火山方舟 (ark-code-latest) |
| Embedding | 硅基流动 BAAI (text) + 火山方舟 (multimodal) |
| Rerank | 硅基流动 BAAI (免费) |
| 向量库 | Milvus 2.3.3 |
| 关系库 | PostgreSQL 16 |
| 缓存 | PostgreSQL tsvector (BM25) |
| 监控 | Prometheus + Grafana |
| LLM 框架 | AgentScope 2.0 |
| 文档解析 | MinerU 2.x |

## 📚 学习文档

- [docs/MASTER_ROADMAP.md](docs/MASTER_ROADMAP.md) - 完整路线图
- [docs/JAVAGUIDE_LEARNING.md](docs/JAVAGUIDE_LEARNING.md) - JavaGuide 提炼
- [docs/INTERVIEW_NOTES.md](docs/INTERVIEW_NOTES.md) - 面试话术
- [docs/CI_CD.md](docs/CI_CD.md) - CI/CD 流程
- [docs/LONG_TERM_MEMORY_*.md](docs/) - 借鉴 ekbs/九阳/JavaGuide

## 📜 License

Internal Project.
