# Interview Notes (个人面试素材)

> 个人用，不放到项目 README。每个任务完成后会自动追加。
> 包含：选型理由 / 实现细节 / 遇到的坑 / 解决方案 / 面试话术

---

## Task MVP-1: Milvus + Docker 部署 (2026-08-04)

### 🎯 选型理由（为什么选 Milvus）
- ekbs（九阳企业知识库）用的就是 Milvus（借鉴案例）
- 比 Qdrant 更适合生产级（分布式、亿级向量支持）
- 自带 Attu 可视化面板
- 支持 HNSW/IVF/DiskANN 多种索引
- Milvus 2.x 存数据依赖 etcd（metadata）+ MinIO（对象存储）+ Milvus（向量计算）三件套

### 🏗️ 部署架构
- 用 WSL Docker（不是 Docker Desktop，因为没装）
- 三容器编排：
  - `quay.io/coreos/etcd:v3.5.5` - 元数据（集合 schema、节点状态）
  - `minio/minio` - 对象存储（向量二进制 + 索引文件）
  - `milvusdb/milvus:v2.3.3` - 主服务（端口 19530 gRPC + 9091 metrics）
- 数据全部存 E 盘（按要求）：/e/milvus-data, /e/milvus-etcd, /e/milvus-minio
- Docker network: milvus-net（容器间通信用内部域名）

### 🐛 遇到的坑
1. **Docker Hub 连接被拒**（国内网络）：报 `dial tcp 31.13.96.194:443: connection refused`
   - **解决**：加 daemon.json registry-mirrors，配置 `docker.m.daocloud.io` 和 `docker.1panel.live`
2. **daemon.json JSON 格式错**（我之前手写错了）
   - **解决**：用 `printf` 写带引号的 JSON，避免 bash heredoc 嵌套引号问题
3. **Milvus 拉镜像太慢**：~1.5GB（milvus + minio + etcd + attu）
   - **解决**：耐心等（用阿里云 mirror 加速 5-10x）

### 🎤 面试话术
"我们 RAG 系统的向量库选型用了 **Milvus 2.3.3**，为什么不用 Qdrant？"
- Qdrant 用 Rust 写性能好但是单机版，Milvus 是 C++ 写支持分布式（生产亿级向量要扩展）
- 我们参考了九阳企业知识库的真实案例，他们生产就是 Milvus
- Milvus 自带 Attu 可视化（Qdrant 也有但 Attu 功能更强）
- 部署用 Docker Compose 三件套：etcd + minio + milvus，数据全存 E 盘

"为什么用 WSL Docker 而不是 Docker Desktop？"
- 我们环境是 Windows + Git Bash，Docker Desktop 没装
- WSL2 自带 Docker Engine，更轻量
- 缺点：docker 命令不能直接在 Git Bash 用，要 `wsl -d Ubuntu-Docker -- docker ...`

---

## Task MVP-2: Document/ParentChunk 模型 + Milvus 适配器 (2026-08-04)

### 🎯 数据模型选型（为什么父子分块）
- **子块（child chunk, 800 token）**：检索单位，存向量库（Milvus）
  - 字段：vector + parent_id + tenant_id + document_id + filename + category
- **父块（parent chunk, 2000 token）**：context 单位，存业务库（SQLite/PG）
  - 字段：parent_id (PK) + content + token_num + document_id (FK) + position

### 🏗️ 借鉴 ekbs（九阳企业知识库）的设计
- **ekbs 原文**：子块带原始资源引用（URL/HTML），父块只存纯文本
- **优势**：
  - 父块不重复存在向量库 payload（节省存储）
  - 父块可独立更新（不用重新索引全部子块）
  - 检索时只查子块向量，按 parent_id 批量查父块
- **我们改造**：用 parent_id 外键关联（PG/SQLite 都支持）

### 💻 Milvus 适配器（pymilvus 2.x）
- **3 件套部署**（不是单镜像）：
  - `etcd` 存集合 schema + 节点状态
  - `minio` 存向量二进制 + 索引文件
  - `milvus-standalone` 主服务（端口 19530 gRPC + 9091 metrics）
- **索引类型**：HNSW（生产推荐，比 IVF 快 30%）
- **过滤**：服务端原生支持 `tenant_id == "xxx" and category in ["a", "b"]`

### 🐛 坑
1. **pymilvus 2.x vs 1.x API 大变**：1.x 用 `connections.connect()` ORM 风格，2.x 用 `MilvusClient` 类
   - 解决：直接用 2.x `MilvusClient`（更新更简单）
2. **多租户过滤**：用 `filter` 表达式字符串（不是 dict）
   - 解决：`f'{TENANT_ID_KEY} == "{tenant_id}"'`
3. **auto_id 必填**：pymilvus 2.x 必须显式 `auto_id=True` 或 `auto_id=False`
   - 解决：建集合时设 `auto_id=True`（避免手动生成 ID）

### 🎤 面试话术
"你们的 RAG 父子分块怎么存的？"
- 子块（800 token，检索单位）进 Milvus 向量库，payload 含 parent_id 引用
- 父块（2000 token，context 单位）进 PostgreSQL 业务库
- 借鉴的是九阳企业知识库 ekbs 的标准设计
- 优势：父块不重复存储（向量库 payload 往往比向量本身还大），更新父块不用重索引子块
- 检索时：Milvus 召回子块 → 按 parent_id 聚合 → 批量查 PG 拿父块 → Rerank

"为什么用 HNSW 不用 IVF？"
- HNSW：图索引，召回率 99%+，查询快（适合实时检索）
- IVF：聚类索引，召回率 95%，训练慢（适合超大数据 + 离线建索引）
- 我们数据量 < 100 万条，HNSW 性能 + 准确率都更好

"多租户怎么做的？"
- 写入时 payload 带 tenant_id
- 检索时用 Milvus 原生 filter 表达式服务端过滤
- 不用应用层做（避免拉全数据再过滤，浪费带宽）
- 业务库也用复合索引 (tenant_id, document_id) 防慢查询

---

## Task MVP-3: PostgreSQL 部署 (2026-08-04)

### 🎯 为什么选 PostgreSQL（不选 SQLite/MySQL）
- **SQLite**：单文件、零配置，**适合开发但不适合生产**
  - 不支持并发写（多 worker 会锁库）
  - 没有网络访问
  - 没有 JSONB / 数组 / 全文搜索等高级类型
- **MySQL**：流行但 JSON 支持弱
  - JSON 类型本质是字符串（不能索引内部字段）
  - 全文搜索要 LIKE %xxx%（性能差）
- **PostgreSQL**：**生产 RAG 首选**
  - JSONB（可索引的二进制 JSON）
  - ARRAY 类型
  - 全文搜索（tsvector + GIN 索引）
  - pgvector 扩展（如果不用 Milvus 也能用 PG 存向量）
  - 多租户 RLS（Row Level Security）

### 🏗️ 部署
- 镜像：`postgres:16-alpine`（117MB 压缩，最小化）
- 数据：E 盘（按要求 `/e/postgres-data`）
- 端口：5432（容器内 → Windows localhost）
- 用户：hair / hair123（生产用 secret 管理）
- 数据库：hairstylist

### 🐛 坑
1. **国内 Docker Hub 拉镜像失败**：报 `connection refused`
   - 解决：daemon.json 加 `docker.m.daocloud.io` 镜像源
   - 教训：先配 mirror 再拉，否则反复失败浪费时间
2. **pg 16-alpine vs pg 16**：alpine 更小（117MB vs 380MB），但 musl libc 偶尔有兼容问题
   - 解决：用 alpine 没问题（生产 90%+ 都在用）

### 🎤 面试话术
"为什么用 PostgreSQL 不用 MySQL？"
- 我们 RAG 场景需要存 JSONB（父块元信息）+ 数组（多标签）+ 全文搜索（BM25）
- MySQL JSON 是字符串，不能索引内部字段
- PostgreSQL JSONB 是二进制，可建 GIN 索引，查询快 100x
- 另外 PostgreSQL 有 pgvector 扩展（如果不用 Milvus 也能存向量）

"为什么用 alpine 镜像？"
- 117MB vs 普通 380MB
- 90% 生产环境在用
- 唯一坑：musl libc（vs glibc）某些 C 扩展编译不过
- 我们的依赖都是纯 Python，没问题

---

## Task MVP-4: MinerU 真实部署 + 解析 30 页 PDF (2026-08-04)

### 🎯 关键决策
- **没 GPU**：走 pipeline 后端（CPU 模式，准确率 86.47%）
- **不用云 API**：本地部署，零网络成本
- **不用 Docker**：pip 装更快（mineru[all] 3.4.4）
- **WSL Docker 拉 MinerU 镜像失败**（daocloud 没这镜像）→ 改用 pip 方案

### 📊 真实性能数据
- 30 页 / 1.2MB PDF
- OCR-det 143 行：31s
- OCR-rec 620 行：33s
- 总耗时约 2 分钟
- 内存峰值 ~1GB（python 进程）
- 输出：6.3MB（md + json + pdf + images）

### 🐛 遇到的 3 个坑
1. **mineru-models-download 默认下到 C 盘** (`C:\Users\18414\.cache\modelscope`, 1GB)
   - 解决：复制到 E 盘 + 改 `C:\Users\18414\mineru.json` 的 `models-dir.pipeline`
2. **配置路径多一层 `models/`**：`E:\mineru-models\pipeline\models` → MinerU 找 `models/models/MFR/...`
   - 解决：改成 `E:\mineru-models\pipeline`（MinerU 自动加 `models/...`）
3. **C 盘 pagefile.sys 22GB 占用**（虚拟内存文件）
   - 解决：减小 pagefile + 禁休眠（powercfg /h off）→ 释放 11GB
   - 终极方案：pagefile 移到 E 盘（脚本在 [scripts/move_pagefile_to_e.ps1](../../scripts/move_pagefile_to_e.ps1)）

### 🎤 面试话术
"你们的 PDF 解析用 MinerU 吗？怎么部署的？"
- 用 MinerU 3.4.4（Apache 2.0 开源）
- pipeline 后端（CPU 模式）因为我们没 GPU
- pip 装 `mineru[all]`（包含 PaddleOCR / layout / table 识别）
- 模型 ~2.5GB 存 E 盘
- 30 页 1.2MB PDF 约 2 分钟

"MinerU 怎么选？"
- 借鉴九阳企业知识库 ekbs 的设计
- 比 PyMuPDF 强在 layout/表格/公式识别
- 比 LlamaParse / Docling 强在 Apache 2.0 完全免费
- 支持 6 种格式（PDF/DOCX/PPTX/XLSX/图片/Web）

"CPU 解析慢不慢？"
- 30 页 ~2 分钟
- 522 页 完整 PDF 预计 30-40 分钟
- 生产建议：有 GPU 用 vlm-engine（95% 准确率，10x 速度）
- 临时方案：分批处理（每 50 页一批）

---

## Task MVP-5: Alembic 自动迁移 (2026-08-04)

### 🎯 为什么需要 Alembic（不只 create_all）
- `Base.metadata.create_all` 只在空表时建表，**已有表 + 新字段不会更新**
- 生产部署：表结构变更必须可追溯、可回滚
- Alembic = 数据库 schema 版本控制（类似 git for DB）

### 🏗️ 实现细节
- 启动时跑 `alembic upgrade head`（自动）
- 失败 Fast-Fail（生产不服务）
- `/health` 端点暴露 migration 状态（监控用）
- 用 `@asynccontextmanager` lifespan（替换旧 `@app.on_event("startup")`）

### 📊 借鉴 12-factor app
- "进程启动 = 配置就绪"
- DB 迁移必须在服务接收流量前完成
- 否则：旧 schema + 新代码 = 数据错乱

### 🐛 踩坑
1. **alembic.ini 路径含冒号** (`e:/hairstylist-kb-agent/...`) → 解析失败
   - 解决：force 设 `script_location` 用 pathlib
2. **删旧 migration 后 alembic 找不到基线**
   - 解决：手动 `UPDATE alembic_version SET version_num='0001_base_schema'`
3. **pymilvus create_collection + 手动 create_index 冲突**
   - 解决：只 create_collection（自动建默认索引），不再手动 create_index
4. **auto_id=False 必须自己提供 id**
   - 解决：UUID 转 int64 注入

### 🎤 面试话术
"你们的数据库 schema 怎么管理？"
- 用 **Alembic**（SQLAlchemy 官方迁移工具）
- 启动时自动 `alembic upgrade head`（生产 Fast-Fail）
- `/health` 暴露 migration 状态（current/head/up_to_date）
- 借鉴 12-factor app："进程启动 = 配置就绪"
- 失败不服务，避免旧 schema 读错数据

"Alembic 和 create_all 区别？"
- create_all 只在空表建表，加字段不会改
- Alembic = 数据库版本控制（类似 git）
- 每次 schema 变更：`alembic revision --autogenerate -m "add xxx"`
- 部署：`alembic upgrade head`（可回滚 `alembic downgrade -1`）

---

## Task MVP-6: 混合检索 (Vector + BM25 + RRF) (2026-08-04)

### 🎯 为什么混合检索
- **向量检索的痛点**（借鉴 ekbs）：对错误码、SKU、专业术语召回差
- **BM25 痛点**：无语义理解（"空调" vs "冷气"）
- **双路融合**：取长补短，显著提升 context recall

### 🏗️ 实现细节
**借鉴 ekbs（九阳企业知识库）双路检索设计**

1. **Vector 召回**（Milvus HNSW）
   - 1024/2048 dim
   - top_k=20 children
   - 服务端 filter（tenant_id + category）

2. **BM25 召回**（PG tsvector + ts_rank_cd）
   - 客户端 jieba 分词 → 空格分隔 → `to_tsvector('simple', content)`
   - GIN 索引（毫秒级）
   - ts_rank_cd 是 PG 内置 BM25 风格排序函数
   - 多租户 + category filter

3. **RRF 融合**（Reciprocal Rank Fusion）
   - 公式: `score(d) = sum(weight_i / (k + rank_i))`
   - k=60（原 RRF 论文）
   - vector_weight=0.7, bm25_weight=0.3
   - 不需要训练，无额外参数

### 📊 真实数据
- 30 页 PDF（理发书）→ 4 父块 / 52 子块
- 索引时间: 20 秒
- 检索时间: 2.5 秒
- 查询: "basic barber services" → 3 hits
  - Hit1: "STANDARD BARBERING... basic barber services" 完美匹配

### 🐛 4 个关键坑
1. **SQLite 不支持 tsvector** → 切 PostgreSQL
2. **Windows + asyncpg 跨 event loop** → NullPool + SelectorEventLoop
3. **中文分词不匹配 tsvector** → 客户端 jieba 分好后存
4. **业务测试空数据** → seed fixture
5. **config dataclass 不重读 env** → Lazy proxy

### 🎤 面试话术
"你们的 RAG 检索怎么做的？为什么不用纯向量？"
- **双路混合**：向量（Milvus HNSW）+ BM25（PG tsvector）
- **RRF 融合**（k=60）：公式简单无需训练
- 借鉴九阳企业知识库 ekbs 的设计
- 纯向量的痛点：错误码、SKU、专业术语召回差
- BM25 补足：对**精确字符串匹配**更强

"中文全文搜索怎么做的？"
- 客户端 jieba 分词 → 空格分隔 → PG `to_tsvector('simple', content)`
- GIN 索引（毫秒级）
- 查询时 jieba 分词 → `to_tsquery('simple', '词1 & 词2')` 匹配
- **必须客户端分词**（PG 内置 simple 配置对中文不友好）

"为什么用 PG 不上 ES？"
- 数据量 < 100 万条，PG 够用
- 减少组件（一个 DB 干所有事）
- 多租户用 RLS 就能搞定
- ES 要单独集群，运维成本高

---
