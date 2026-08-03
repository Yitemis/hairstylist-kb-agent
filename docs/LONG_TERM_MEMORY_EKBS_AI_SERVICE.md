# ekbs-ai-service 文档解析专项学习笔记

> 来源：D:\\Joyoung\\ekbs-ai-service（九阳企业知识库AI解析服务）
> 学习时间：基于此版本完整学习
> 价值：完整企业级文档解析最佳实践

---

## 1. 项目结构（30+ 文件，~2700 行核心代码）

```
ekbs-ai-service/
+- common/                # 公共模块
|  +- llm/                # 大模型统一接口 (LLMBundle, Chat/CV/Embed/Rerank)
|  +- oss/                # 阿里云 OSS 上传
|  +- mongo/               # MongoDB
|  +- redis/               # Redis
|  +- milvus/              # Milvus 向量库
|  +- utils/               # file_utils, prompt_utils
+- configs/               # 配置（环境变量 + YAML）
+- core/                  # 核心逻辑
|  +- parser/              # 文档解析（重点）
|  |  +- pdf_parser.py      # PDF (MinerU + VLM)
|  |  +- docx_parser.py     # Word (python-docx + lxml)
|  |  +- excel_parser.py    # Excel (openpyxl + pandas)
|  |  +- markdown_parser.py # Markdown (BeautifulSoup)
|  |  +- image_parser.py    # Image (VLM OCR)
|  |  +- audio_parser.py    # Audio (语音转文字)
|  |  +- txt_parser.py      # TXT (编码自动检测)
|  |  +- doc_types.py       # 统一数据模型
|  |  +- utils.py           # SSRF 防护 / 限流下载
|  +- nlp/                 # NLP (tokenizer, codec)
+- service/               # 业务层
|  +- parser/              # 解析调度
|  +- extraction/          # 知识提取
|  +- db/                  # 持久化
|  +- mq_consumer/         # 队列消费
+- api.py                  # 整体 API 入口
```

---

## 2. 核心抽象：统一数据模型 doc_types.py

```python
class ElementTypes:
    TEXT = 'text'
    TABLE = 'table'
    IMAGE = 'image'
    AUDIO = 'audio'

class ChildChunk:
    content: str                # 子块文本（用于 embedding + 检索）
    html_table: str             # HTML 表格（保留结构）
    table_info_list: list       # 表格数据（LLM 拆解后）
    image_url: str              # 图片 OSS URL
    image_info: str             # 图片 VLM 描述
    chunk_type: ElementTypes    # TEXT/TABLE/IMAGE/AUDIO
    token_num: int              # token 数
    is_ignore: bool             # 跳过标记

class ParentChunk:
    content: str                # 父块完整文本
    token_num: int
    child_chunks: list[ChildChunk]  # 子块列表
```

设计精髓：
- 子块携带原始资源（图片 URL、HTML 表格）
- 父块只有纯文本
- 检索用子块（content 编码向量）
- 生成用父块（context 给 LLM）
- 结构不丢（图、表的引用关系通过 child_chunks 保留）

对比我们：
- 我们 ChildChunk 存了 parent_content 在 metadata 里
- 缺点：100 个子块 = 100 份父块拷贝，浪费存储
- 优点：单表存储，查询简单

最佳实践（来自 ekbs）：父块单独存，子块只存 parent_id reference。

---

## 3. 核心架构：6 种解析器 + 4 种 LLM 调用

### 3.1 PDF 解析（~270 行核心逻辑）

Pipeline：
- PDF 文件
-  MinerU 服务（HTTP /file_parse）
-  返回 content_list + images
-  按 type 分流：image/text/table/equation
- 父子分块合并（子 128，父 512）
- 输出 ParentChunk[] 入库

亮点 1：MinerU 服务
- 用 MinerU 专门做 PDF 解析（多栏/表格/公式/OCR）
- HTTP API 调用：POST {MINERU_URL}/file_parse
- 返回 content_list（JSON） + images（base64）

亮点 2：图片 VLM 描述
- 图片 caption + footnote 做 prompt
- 多模态 LLM 生成描述
- 描述作为 child chunk content 入向量库

亮点 3：表格双路处理
- HTML 表格（结构化）+ 原始图片（视觉）
- LLM 拆解成结构化 JSON

亮点 4：父子分块合并
- 子块按类型连续性合并（同类型 token 累加 < 128）
- 父块按 token 累加合并（跨类型仍合并）

### 3.2 DOCX 解析（~595 行）

核心难点：Word 编号系统（1.1 / a. / 1)1）

- 解析 numbering.xml 构建 mapping
- 遍历段落识别 Heading 1/2/3
- 处理编号列表
- 提取图片 ImagePart + PIL + OSS
- 提取表格 _Cell 转 HTML

### 3.3 Excel 解析（~647 行）

核心难点：合并单元格（colspan/rowspan）

- 加载 workbook
- 按 chunk_rows 分块（默认 256 行/块）
- 处理合并单元格（展开 colspan/rowspan）
- 渲染 HTML

亮点：每个工作表按 256 行分块，防止大表 OOM。

### 3.4 Markdown 解析（~350 行）

核心难点：表格/图片的占位符替换

- 先抽离表格（占位符 TABLE_PLACEHOLDER）
- 再抽离图片（占位符 IMAGE_PLACEHOLDER）
- 占位符位置插入 LLM 解析后的内容

亮点：占位符模式 — 把表格/图片从文本中抽离，按位置回插，避免 Markdown 解析时被破坏。

### 3.5 Image 解析（~288 行，长图分割）

核心难点：超长截图（聊天记录长截图）

- 按固定高度（默认 1500 px）分割
- 上下文传给 VLM（前一段末尾 100 字）

亮点：长图分块 + 滚动 context — 避免每段独立看丢连贯性。

### 3.6 TXT 解析（~157 行）

核心：find_codec 自动检测文件编码（chardet/cchardet）

---

## 4. 核心 LLM 抽象：LLMBundle

通过 _FACTORY_NAME 自动注册厂商：

```python
class LLMBundle:
    def __init__(self, llm_type: LLMType, llm_name=None, lang='Chinese'):
        mapping = {
            LLMType.CHAT: ChatModel,
            LLMType.IMAGE2TEXT: CvModel,
            LLMType.EMBEDDING: EmbeddingModel,
            LLMType.RERANK: RerankModel,
            LLMType.SPEECH2TEXT: Seq2txtModel,
        }
        impl_cls = mapping[llm_type][llm_name]
        self.mdl = impl_cls(...)
```

5 种 LLM 类型：
- CHAT：普通对话（用于表格拆解、对话）
- IMAGE2TEXT：图像理解（用于图片 OCR + 描述）
- EMBEDDING：向量嵌入
- RERANK：重排
- SPEECH2TEXT：音频转文字

多厂商支持：Volcengine / OpenAI / Azure / Bedrock / 自定义

优点：
- 业务代码只调 LLMBundle(LLMType.CHAT).chat(...)
- 换厂商只改配置，业务无感

---

## 5. 核心安全：is_safe_url 防 SSRF

```python
def is_safe_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https'): return False
    if parsed.scheme in ('file', 'gopher', 'ftp'): return False
    hostname = parsed.hostname.lower()
    if hostname in ('localhost', '127.0.0.1', '::1'): return False
    ip = ipaddress.ip_address(hostname)
    if ip.is_private or ip.is_loopback or ip.is_link_local: return False
    return True
```

这是我们项目完全没有的！任何 URL 都能 fetch，是 P0 安全漏洞。

---

## 6. 核心运维：限流下载

```python
def download_file(url, max_size=1024):
    response = requests.get(url, stream=True, timeout=10)
    content = b''
    downloaded = 0
    for chunk in response.iter_content(chunk_size=4096):
        content += chunk
        downloaded += len(chunk)
        if downloaded > max_size:
            raise ValueError(f'文件超出大小限制 {url}')
    return content
```

防 OOM：流式读取 + 累加判断，不一次性加载到内存。

---

## 7. 我们项目 vs ekbs-ai-service 的差距

| 维度 | ekbs 标准 | 我们 | 差距 |
|------|---------|------|------|
| PDF 解析 | MinerU + VLM | 0 | -100% |
| Word 解析 | python-docx + lxml | 0 | -100% |
| Excel 解析 | openpyxl + 合并单元格 | 0 | -100% |
| Markdown | BeautifulSoup | 0 | -100% |
| 图片 OCR | VLM | 0 | -100% |
| 多模态 LLM 抽象 | LLMBundle 5 类型 | OpenAIChatModel only | -60% |
| SSRF 防护 | is_safe_url | 0 | -100%（P0 漏洞）|
| 限流下载 | chunk_size 4KB | 0 | -50% |
| 父子分块数据模型 | ChildChunk + ParentChunk | dict in metadata | -50% |
| 占位符替换 | TABLE/IMAGE placeholder | 无 | -80% |
| 编号系统（Word）| 完整解析 | 无 | -100% |
| 合并单元格（Excel）| 完整展开 | 无 | -100% |
| 长图分块 + 滚动 context | 支持 | 无 | -100% |
| MinerU 服务 | 部署 | 无 | -100% |
| OSS 上传 | 集成 | 无 | -100% |
| async 队列消费 | mq_consumer | 无 | -100% |
| json_repair 容错 | 全场景 | 0 | -80% |

最关键差距：
1. P0 安全漏洞：没有 is_safe_url
2. P0 功能缺失：0 种文档解析（我们只接 str）
3. P1 能力缺失：没有 LLMBundle 多模态抽象

---

## 8. 我们的 L1 解析模块改进路线（细化）

### 阶段 1（必须有）：
1. 新建 app/rag/parsers/ 子模块
2. PDFParser（先 PyMuPDF 简单版，后期 MinerU）
3. DocxParser（python-docx）
4. ExcelParser（openpyxl）
5. MarkdownParser（markdown + BeautifulSoup）
6. TxtParser（自动检测编码）
7. 统一数据模型（借鉴 ekbs 的 ChildChunk/ParentChunk）
8. is_safe_url 防 SSRF（P0）

### 阶段 2（生产强化）：
9. VLM 解析图片（多模态 LLM）
10. LLM 拆解表格（结构化 JSON）
11. MinerU 服务集成（识别率提升 30%+）
12. OSS 上传图片
13. 长图分块 + 滚动 context

### 阶段 3（高级）：
14. 占位符替换
15. Word 编号系统
16. Excel 合并单元格完整展开
17. JSON 解析容错（用 json_repair）
18. 异步队列消费（mq_consumer）

---

## 9. 关键启示

### 9.1 文档解析是 RAG 的上半段

> RAG 的瓶颈通常不在检索层，而在文档进入索引之前的那段管线。

### 9.2 多模态 LLM 是图片/表格的关键

> CLIP 对截图/图表理解差。要用 GPT-4V、Qwen-VL 等多模态 LLM 生成图片描述。

### 9.3 父子分块的标准数据模型

```python
class ChildChunk:  # 检索单位
    content: str           # 纯文本（用于 embedding）
    chunk_type: TEXT/TABLE/IMAGE
    image_url/html_table  # 原始资源引用
    token_num: int

class ParentChunk:  # context 单位
    content: str
    child_chunks: list     # 包含哪些子块
```

核心：子块带原始资源引用（URL/HTML），父块只存纯文本。

### 9.4 安全第一

> is_safe_url 防 SSRF + 限流下载 防 OOM。这两个是基础中的基础。

### 9.5 占位符模式

> Markdown/HTML 解析时，先抽离表格/图片，用占位符替代，回插。这避免结构被破坏。

---

## 10. 我们项目应该立即做的事（按价值排序）

### 优先级 P0（必须）

1. 新建 app/rag/parsers/ 模块（参考 ekbs 完整设计）
2. 6 种文件类型：PDF/Word/Excel/Markdown/TXT/Image
3. 统一 ChildChunk/ParentChunk 数据模型
4. is_safe_url 防 SSRF
5. download_file 限流下载
6. 3 道校验（格式/解析/Chunking 质量）

### 优先级 P1（应该）

7. PDF 用 MinerU + VLM（解析率 +30%）
8. Word 用 python-docx
9. Excel 用 openpyxl
10. LLMBundle 抽象（5 种 LLM 类型）
11. JSON 解析容错（用 json_repair）

### 优先级 P2（完善）

12. OSS 上传图片
13. 占位符替换
14. Word 编号系统
15. 长图分块 + 滚动 context
16. 异步队列消费（mq_consumer）
17. MinerU 服务

---

## 11. 与之前规划的关系

docs/PROJECT_OPTIMIZATION_PLAN.md 已包含所有 RAG 模块优化任务。

这次 ekbs 学习的重要补充：

- 之前规划 L1-P0-01 文档自动解析
- ekbs 补充：6 种解析器 + 统一数据模型 + SSRF + 限流
- 之前规划 L1-P1-05 评估集
- ekbs 补充：50 条按经验分配（高频/失败/精确/拒答/多跳）
- 之前规划 L2-P0-01 Booking 用 ReAct
- ekbs 补充：保留硬编码 fallback
- 之前规划 L3-P1-02 结构化输出
- ekbs 补充：借鉴 LLMBundle 抽象