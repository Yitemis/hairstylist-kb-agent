# RAG 文档解析 - MinerU 部署指南

> 借鉴思路来自九阳 POC（实际部署 MinerU 处理多栏 PDF）

## 当前 PDF 解析架构（双引擎 + 降级）

```
PDF 文件
  ↓
1️⃣ 优先尝试 MinerU 服务（识别率最高）
  ↓ 连不上 / 失败
2️⃣ 降级到 PyMuPDF（标准文本提取，Apache 2.0 免费）
  ↓ 文字不够
3️⃣ OCR 兜底（pytesseract，可选）
```

## 部署 MinerU（5 分钟，Apache 2.0 完全免费）

### 方式 1：Docker（推荐生产）

```bash
# 拉取镜像（OpenDataLab 上海 AI Lab 出品）
docker pull opendatalab/mineru

# 启动服务
docker run -d \
  --name mineru \
  -p 8888:8888 \
  -v /path/to/models:/models \
  opendatalab/mineru

# 验证
curl http://localhost:8888/health
```

### 方式 2：pip（推荐开发）

```bash
pip install magic-pdf[full]
python -m magic_pdf.serve
# 默认监听 8888
```

### 方式 3：从源码（自定义）

```bash
git clone https://github.com/opendatalab/MinerU.git
cd MinerU
pip install -e .
python -m magic_pdf.serve
```

## 环境变量

```bash
# .env 或启动时
MINERU_URL=http://localhost:8888
```

## 验证集成

```bash
# 上传 PDF 文件测试
curl -X POST "http://localhost:8000/api/rag/upload?document_id=test" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/test.pdf"

# 后端日志应输出
# - "MinerU 不可用或失败，降级到 PyMuPDF"（MinerU 没启动）
# - 或成功解析（如果 MinerU 在跑）
```

## 当前支持的文件格式

| 格式 | 解析器 | 开源 | 状态 |
|------|--------|------|------|
| PDF | PyMuPDF + MinerU + OCR | ✅ | ✅ |
| Word | python-docx | ✅ | ✅ |
| Excel | openpyxl | ✅ | ✅ |
| Markdown | 正则 + 标准库 | ✅ | ✅ |

## MinerU 优势（vs PyMuPDF）

| 文档类型 | PyMuPDF | MinerU | 谁用 |
|----------|---------|---------|------|
| 标准文本 | 100% | 100% | 都行 |
| 多栏排版 | 乱序 | **SOTA layout 分析** | MinerU |
| 表格+文字 | 部分丢 | **表格识别** | MinerU |
| 公式 | ❌ | **公式识别** | MinerU |
| 扫描件 OCR | ❌ | 强 | MinerU |
| 速度（30MB）| 1.9s | 5s | PyMuPDF 快 |

## 推荐路径

1. **开发环境**：只装 PyMuPDF（够用，1.9s）
2. **测试环境**：部署 MinerU Docker（5 分钟搞定）
3. **生产环境**：MinerU + 模型预热池 + 健康检查

## 集成代码位置

- `app/rag/parsers/pdf_parser.py` - 双引擎 + 降级
- `app/core/config.py` - 读取 `MINERU_URL` 环境变量
- `app/server/api.py` - `POST /api/rag/upload` 端点

## 借鉴来源（仅借鉴思路，无代码复制）

- **MinerU** (opendatalab/MinerU, Apache 2.0)：https://github.com/opendatalab/MinerU
- **九阳 POC 实战**：横版 PDF 失分最多 → 引入 MinerU
- **ekbs-ai-service**：6 种解析器统一调度 + SSRF 防护

## 下一步

P1 改进：图片 VLM 描述（VLM 选 open source LLaVA 或 GPT-4V）
P2 改进：MinerU 表格抽取结果作为独立 metadata


## PDF_PARSER 环境变量

3 种模式（借鉴九阳 POC + AgentScope 设计）：

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| **auto** (默认) | MinerU 优先，失败自动降级 PyMuPDF | 开发 + 测试 |
| **mineru** | 强制 MinerU，失败报错 | 生产（保证识别率） |
| **fast** / **pymupdf** | 只用 PyMuPDF（0 依赖）| 纯文本快速场景 |

```bash
# 默认（auto）
unset PDF_PARSER

# 生产（强制 MinerU）
export PDF_PARSER=mineru

# 纯文本快速（只用 PyMuPDF）
export PDF_PARSER=fast
```

按九阳 POC 实战，所有 PDF（标准/横版/扫描）都用 MinerU 路径最稳：
- MinerU 不可用 → auto 模式自动降级 PyMuPDF
- MinerU 不可用但设了 mineru 模式 → 报错（说明 MinerU 服务挂了）

借鉴来源：仅借鉴九阳 POC 的 MinerU 选型 + ekbs 的降级模式思路。
