# 美发行业智能知识助手（Hairstylist KB Agent）

基于 [AgentScope](https://github.com/agentscope-ai/agentscope) 框架构建的、面向美发行业 B 端的智能知识助手应用。

发型师、门店员工可以用自然语言提问，助手自主检索企业知识库（产品手册、染烫配方、话术 SOP），结合检索结果给出专业、可溯源的回答。

> **合规声明**：本项目所有代码基于开源框架 AgentScope（Apache-2.0）从零实现，借鉴行业通用的 RAG 工程理念，不包含任何第三方商业项目的源代码或私有实现。测试数据来源于公开资料，仅用于技术演示。

## 特性

- **父子分块（Parent-Child Chunking）**：用小块做向量检索、用大块提供上下文，兼顾检索精度与上下文完整性
- **两阶段检索**：向量检索粗筛 + Rerank 精排，Rerank 组件可选注入、缺省时降级为纯向量检索
- **多格式解析**：支持 Markdown、PDF、Excel 等文档，表格转结构化文本
- **Agentic RAG**：由 Agent 自主判断是否检索，而非被动召回
- **流式输出**：基于事件驱动的实时输出
- **模型可插拔**：通过 OpenAI 兼容接口接入火山方舟等厂商，切换只需修改配置

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

# 3. 配置模型（复制 .env.example 为 .env 并填入 API Key）
copy .env.example .env         # Windows

# 4. 运行
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
