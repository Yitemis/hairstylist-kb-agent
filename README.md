# 美发行业智能知识助手（Hairstylist KB Agent）

基于 [AgentScope](https://github.com/agentscope-ai/agentscope) 框架构建的、面向美发行业 B 端的智能知识助手应用。

发型师、门店员工可以用自然语言提问，助手自主检索企业知识库（产品手册、染烫配方、话术 SOP），结合检索结果给出专业、可溯源的回答。

> **合规声明**：本项目所有代码基于开源框架 AgentScope（Apache-2.0）从零实现，借鉴行业通用的 RAG 工程理念，不包含任何第三方商业项目的源代码或私有实现。测试数据来源于公开资料，仅用于技术演示。

## 核心技术亮点

- **父子分块（Parent-Child Chunking）**：小块保证检索精度，大块保证回答完整性
- **两阶段检索**：向量粗筛 + Rerank 精排，显著提升准确率
- **多格式 & 表格深加工**：解决表格类文档检索难题
- **Agentic RAG**：Agent 自主决策何时检索，而非被动召回
- **流式事件驱动**：Web 界面打字机式实时输出
- **模型可插拔**：火山方舟 / 通义等厂商可自由切换

## 项目结构

```
hairstylist-kb-agent/
├── docs/               # 文档（PRD 等）
├── app/                # 应用层（配置、Agent 组装）
├── rag/                # RAG 核心（父子分块、Rerank、知识库）
├── scripts/            # 脚本（离线索引等）
├── tests/              # 测试
└── main.py             # 应用入口
```

## 环境要求

- Python 3.11+

## 快速开始

```bash
# 1. 创建并激活虚拟环境
python -m venv .venv
.venv\Scripts\activate        # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置模型（复制 .env.example 为 .env 并填入你的 key）
copy .env.example .env         # Windows

# 4. 运行 Hello World Agent
python main.py
```

## 开发进度

- [x] M0 环境搭建（项目骨架 + Hello World Agent）
- [ ] M1 RAG 打通
- [ ] M2 父子分块
- [ ] M3 Rerank 精排
- [ ] M4 多格式解析
- [ ] M5 Agent 集成
- [ ] M6 Web 界面
- [ ] M7 进阶扩展

详见 [docs/PRD.md](docs/PRD.md)
