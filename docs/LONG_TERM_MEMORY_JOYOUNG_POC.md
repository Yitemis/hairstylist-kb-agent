# 九阳 POC 实战学习笔记

> 来源：
> - C:\\Users\\18414\\Desktop\\阿里-九阳产品智慧大脑POC验证报告.docx
> - C:\\Users\\18414\\Desktop\\九阳产品智慧大脑POC测试报告.docx
> 价值：直接的企业级 RAG + Multi-Agent POC 实战调优经验

---

## 1. 项目概览

九阳产品智慧大脑：基于腾讯云 ADP 平台
- 31 份原始资料
- 12 类业务场景
- 7 个子智能体协同
- Multi-Agent + RAG + 多模态 + 权限隔离
- 模型：hunyuan-hy3 路由 + DeepSeek-V4-Pro 子 Agent
- 33 个 query 全量测试，准确率 100%，0 错误率

---

## 2. 5 层架构（来自 v8.0 报告）

```
接入层
  ↓
路由层（Multi-Agent 调度）
  ↓
能力层（6 个子 Agent + RAG + 工具）
  ↓
知识层（KB-1 ~ KB-4 多库）
  ↓
基础层（LLM Gateway / 向量库 / OSS）
```

---

## 3. 12 类业务场景及应对策略（**实战精华**）

### 4.1 文本类（5 题）
- 挑战：长篇说明书中精准定位关键事实
- 策略：
  - 通用标识符 ## 切分（按标题层级）
  - 800 字符 chunk size + 80 重叠
  - Markdown 表格保留
- 加分：在 MD 中追加 Q&A 速答段（关键事实强冗余编码）
- 实测：TC-01/04/16/20 全部满分
- 案例：TC-04 "800ml 五谷浆 = 29 分钟" 精准命中

### 4.2 表格类（6 题）
- 挑战：多列表格、合并单元格、跨行参数
- 策略：
  - xlsx 转 Markdown 长表（每行 1 切片）
  - 列名规范化（统一大小写、去空格）
- 案例：DJ06X-D525 功能说明书
  - 原 xlsx 含 533 个合并单元格
  - 预处理脚本转 MD 后切片 28 个
  - 全部召回

### 4.3 复杂表格（合并单元格 + 图片，3 题）
- 挑战：xls 老格式、行内图、跨 sheet 关联
- 策略：
  - 脚本逐行扫描
  - 图片单独导出
  - caption 绑定
- 实测：TC-13 "2BJ03004208 用量 = 1" 满分

### 4.4 图文混排（2 题）
- 挑战：PDF 解析后图文分离，召回时只有文字
- 策略：
  - 保留图片 alt 描述
  - 在 MD 中插入 COS 外链
- 实测：TC-26 K7Pro 安装指导图召回成功
- 业务价值：图文混排让客服回答从"等用户脑补"升级为"看图照做"
- 新人培训成本下降 70%

### 4.5 图片内文字（OCR 类，1 题）
- 策略：ADP 自动 OCR + 图片 alt 文本兜底
- 实测：TC-02 K7Pro 功能面板图 5 分

### 4.6 章节定位（1 题）
- 挑战：用户查特定章节时系统未召回完整内容
- 策略：
  - ## 切分保留章节标题
  - 元数据 chapter 标签
- 实测：TC-10 第3节内容 4 分

### 4.7 产品对比（1 题）
- 挑战：跨文档对比
- 策略：JY-Compare Agent 多轮调用 RAG，按维度归纳输出
- 实测：TC-30 Y966 vs Y968 满分，自动产出 9 维度对比表

### 4.8 业务场景（多轮排查，3 题）
- 策略：JY-Aftersales 故障树 Prompt + 上下文记忆
- 实测：TC-19/24 命中故障原因 + 解决步骤 + 客服热线

### 4.9 权限隔离（1 题，加分项）
- 策略：
  - KB-4 文档打 permission_tag（A/B/public）
  - Prompt 拒答模板
- 实测：TC-32 A 角色访问受限文档拒答 5 分

### 4.10 横版说明书（特殊版式，2 题）
- 挑战：横版折页、左右分栏、表格嵌套图片
- 策略：开启 ADP OCR + PDF 旋转预处理
- 实测：TC-25 RH330 横版 PDF 部分场景需补 OCR 3.5 分
- **这是第一轮失分最多的场景（4 个用例）**

### 4.11 型号不明确（反问机制，1 题）
- 策略：JY-Router 识别通用品类时反问型号
- 实测：TC-31 "破壁机不启动了" 自动反问 K7Pro/D525/D650 4 分

### 4.12 简单 Excel（2 题）
- 挑战：xlsx 解析未识别"省份+城市+价格"三元组
- 策略：预处理为长表 MD（待客户提供完整价格表后处理）
- 实测：TC-11/12 当前 2 分，预处理后预计 5 分

---

## 4. 5 大加分项（实战已落地）

### 4.1 图文混排
- MD 文档中嵌入 markdown 图片语法 + 模型原样输出 + 前端 markdown 渲染
- 实测：TC-15 D525 工作状态图（11s 响应）
- TC-02 K7Pro 紫火版功能面板图（5.2s 响应）

### 4.2 Mermaid 流程图
- 知识库中的流程图以 Mermaid 代码形式保存
- 前端原生渲染为可视化流程图，无需图片资源
- 实现：docx 解析后 Mermaid 代码段保留在切片中 → JY-Policy Prompt 强制 mermaid 代码块包裹 → 前端自动渲染
- 优势 vs 图片：无需 COS 图床、节省存储、代码可编辑维护、矢量缩放清晰

### 4.3 音频混排
- 客服优秀录音以音频外链形式嵌入答案
- 实现：原 HTML 音频链接预处理为 markdown 链接 + HTML5 audio 标签双格式
- 实测：TC-01a 超期退换货话术，答案末尾含 6 个 .wav/.mp3 真实音频 URL
- 业务价值：客服培训听标杆、争议处理引用原话录音、远程支持秒级复制

### 4.4 权限隔离三角色
- 知识库文档标签（permission_tag）+ Agent Prompt 拒答规则
- 生产化路径：体验阶段方括号角色前缀 → 正式上线后 visitor_labels 硬隔离

### 4.5 PDF 说明书生成（DocGen）
- JY-DocGen 自动从知识库检索 → 组装 Markdown → Claw 应用渲染 PDF → 返回下载链接
- 支持风格：用户手册风 / 客服快查风
- 业务价值：把九阳老的扫描版 PDF 说明书（图片型）自动重写为全新 PDF
- 新品上市文档时效缩短 90%

---

## 5. 权限隔离四步实施（可直接复用）

### 第 1 步：创建标签字段
- 路径：ADP 控制台 → KB-4 知识库详情 → 标签管理
- 创建 3 个标签值：
  - permission_tag=A（业务部门）
  - permission_tag=B（信息部 / 管理层）
  - permission_tag=public（公开内容）

### 第 2 步：给文档打标签
- KB-4 文档列表 → 每篇文档右侧"设置" → 文档标签字段选择对应值
- ADP 知识库会在召回阶段对带标签的文档执行硬过滤

### 第 3 步：调用方传 visitor_labels（生产化）
- 正式上线后，调用方从 SSO Token 提取用户角色
- 传入 ADP API 的 visitor_labels 字段
- ADP 后端基于 visitor_labels 与文档 permission_tag 做硬过滤

### 第 4 步：Prompt 拒答兜底
- JY-Policy 提示词加入拒答规则
- 召回为空时不允许编造，必须用标准话术拒答
- 严禁泄露受限文档存在的事实

---

## 6. 多维标签扩展建议（生产化参考）

- 部门：sales / support / it / management / hr
- 敏感度：public / internal / confidential / secret
- 地域：cn-east / cn-south / cn-north（区分销售大区）
- 产品线：beanmilk / blender / water / kettle（按产品线隔离 BOM）

ADP visitor_labels 支持多标签 AND/OR 组合查询
可以做到"华东区 + 售后部门 + internal 级别"三标签组合的精细化权限控制

---

## 7. 性能与可靠性数据

- 单 Agent 直连场景 P50 < 5s
- 路由耗时优化：当前 hunyuan-turbos 1-3s，可切换至 hunyuan-lite 0.5s
- RAG 并行化：JY-Compare/JY-DocGen 多轮可并行，降耗 30%
- 结果缓存：高频查询命中缓存，P50 降至 5s
- 流式输出：首字 < 2s
- 33 个 query 全量测试，0 错误率

---

## 8. 我们项目 vs 九阳 POC 的差距

| 维度 | 九阳 POC | 我们 | 差距 |
|------|---------|------|------|
| Multi-Agent 架构 | 6 个子 Agent | 1 个 | -85% |
| ## 标题切分 | 是 | 否 | -100% |
| 800 字符 + 80 重叠 | 是 | 512+128 | 偏小 |
| 表格转 Markdown 长表 | 是 | 否 | -100% |
| 列名规范化 | 是 | 否 | -100% |
| 合并单元格展开 | 是（DJ06X 533个） | 否 | -100% |
| 图文混排 | 是 | 否 | -100% |
| alt 描述 + COS 外链 | 是 | 否 | -100% |
| 横版 PDF 处理 | 是（OCR + 旋转） | 否 | -100% |
| Mermaid 流程图 | 是 | 否 | -100% |
| 音频混排 | 是 | 否 | -100% |
| 权限隔离（4 步） | 是 | 仅 JWT 鉴权 | -60% |
| 文档标签（permission_tag） | 是 | 无 | -100% |
| 多维标签组合 | 是 | 无 | -100% |
| 反问机制 | 是 | 无 | -100% |
| DocGen（PDF 生成） | 是 | 无 | -100% |
| visitor_labels 硬隔离 | 是 | 无 | -100% |
| Q&A 速答段冗余 | 是 | 无 | -100% |
| 模型升级测试流程 | 是 | 无 | -100% |
| 灰度发布 + A/B 测试 | 是 | 无 | -100% |

---

## 9. 我们要立即做的（按价值排序）

### 优先级 P0

1. **按 ## 切分 Markdown 文档**（4.1）
2. **横版 PDF + OCR 兜底**（3.1, 4.10）
3. **合并单元格完整展开**（4.3）
4. **图片 alt 描述 + COS 链接**（4.4）
5. **chunk size 调大到 800+80**（4.1）

### 优先级 P1

6. **xlsx 转 Markdown 长表**（4.2）
7. **Q&A 速答段冗余**（4.1）
8. **章节 chapter 标签**（4.6）
9. **权限文档标签**（4.9）
10. **多模态预处理脚本**

### 优先级 P2

11. **Mermaid 流程图保留**（4.2 加分项）
12. **音频混排**（4.3 加分项）
13. **PDF 生成（DocGen）**（4.5 加分项）
14. **反问机制**（4.11）
15. **多维标签组合**（生产化）

---

## 10. 与之前学习材料的结合

### 与 AgentScope 学习结合
- AgentScope 的 5 层架构（数据/引擎/治理/状态/Harness）→ 与九阳 5 层架构（接入/路由/能力/知识/基础）一一对应
- Harness 6 层（L1-L6）→ 九阳 DOC-1~4 调优阶段映射到 L1（信息边界）+ L6（约束恢复）
- Agent Loop → JY-Router 调度（路由 + 子 Agent + RAG + 重排）

### 与 JavaGuide 学习结合
- JavaGuide 6 环节文档处理 → 九阳 12 类场景的实战化（每类场景对应不同解析策略）
- JavaGuide 评估集 → 九阳 33 个 query 实际评估样本
- JavaGuide 分层记忆 → 九阳 KB-1~KB-4 知识库分层 + permission_tag 隔离

### 与 ekbs 学习结合
- ekbs 的 is_safe_url + 限流下载 → 九阳 KB-4 文档上传实际需要
- ekbs 的 LLMBundle 5 类型 → 九阳 JY-Policy 的 5 类 LLM 调度（chat/cv/rerank/embed）
- ekbs 的 MinerU PDF 解析 → 九阳 PDF 占 4 题失分，需要 vision 兜底
- ekbs 的 ChildChunk/ParentChunk → 九阳章节前缀（chapter 标签）做段落定向召回

---

## 11. 完整学习体系总结

我已学完 4 个学习资料：
1. **AgentScope 2.0** (Python 主项目) - 5 层架构 + 完整工程实现
2. **AgentScope Java** - 同一框架的 Java 版（更完整的 Harness）
3. **JavaGuide AI** - 系统化的 AI 工程化教程（11 篇文档）
4. **ekbs-ai-service** - 真实企业级文档解析实现
5. **九阳 POC** - 真实业务场景的实战调优数据

形成了 4 份长期记忆 + 1 份完整优化 plan：
- docs/LONG_TERM_MEMORY_AI_AGENT.md - AgentScope 学习
- docs/LONG_TERM_MEMORY_JAVAGUIDE_AI.md - JavaGuide 学习
- docs/LONG_TERM_MEMORY_EKBS_AI_SERVICE.md - ekbs 学习
- docs/PROJECT_OPTIMIZATION_PLAN.md - 完整优化路线图

**九阳 POC 经验**要补加到 plan 的 L1 解析模块部分（具体调优方法、参数、多维标签）
**九阳 POC 经验**也要补加到 L2 Agent 模块（## 切分、Q&A 速答段、反问机制）
**九阳 POC 经验**也要补加到 L6 业务模块（权限隔离 4 步、visitor_labels）