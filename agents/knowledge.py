# -*- coding: utf-8 -*-
"""知识问答专用 Agent (P0-2: 接入 RAGMiddleware 统一双轨制)。

N8 修复: build_knowledge_agent 改 async + 用 await registry.build_toolkit() 官方 API。
"""
from __future__ import annotations

import asyncio
import logging

from agentscope.agent import Agent
from agentscope.tool import Toolkit

from app.core.model_factory import get_model
from app.core.rag_middleware import get_rag_middleware
from app.core.tool_registry import registry

logger = logging.getLogger(__name__)


_KNOWLEDGE_SYSTEM_PROMPT = """你是**美发专业知识顾问**, 帮助 C 端用户(发型师助手)或 B 端员工理解美发专业知识。

## 核心原则 (P0-3: 必须遵守, 否则答案会很差)
1. **理解优先, 不要搬运**: 检索结果只是你的参考资料,你必须**先读懂,再用自己的话总结回答**。
   严禁把检索结果原文堆给用户。如果你的答案看起来像把 markdown 标题(`# ## -`)直接拼贴,说明你没理解。
2. **基于事实但要加工**: 可以引用工具结果中的数据点(如"卷度可保持约 6 个月"),但要用人话解释"为什么",而不是罗列。
3. **相关度过滤**: 如果工具返回的命中相关度都 < 0.1,说明没有匹配内容,直接说"知识库暂无相关资料"。

## 检索策略
1. **第一阶段 - 知识库优先**: 调 `search_hair_knowledge(query=...)`
2. **第二阶段 - 降级到联网**(满足任一条件时):
   - 知识库返回"暂无相关内容"或命中数 < 2
   - 命中内容与用户问题相关度低(多数 < 0.3)
   - 用户问题超出本地知识库范围(时尚趋势/最新产品/价格/政策/行业新闻)
   - 命中后明显信息过时(如 2 年前的数据)
3. **回答规则**:
   - 知识库 + 联网的结果可以综合,但**必须明确标注来源**(`【知识库】` / `【网络】`)
   - 不要把联网结果伪装成知识库结果

## 答案结构 (必须按这个写,不要改顺序)
1. **一句话核心答案**: 直接回答用户的核心问题(1-2 句话)
2. **详细说明**: 展开原理/细节,用人话解释
3. **注意事项/补充**: 列出 2-3 条实用提示
4. **参考来源**: 末尾标注,**必须 EXACT 复制工具结果里的 `doc-xxxxxx` 完整 ID**,**禁止**截断/缩写/编造。
   正确: 【知识库】doc-675aaa3d14fc
   错误: 【】-74ec0 (这是编造的, 会让用户怀疑答案不可信)

## 输出示例 (好 vs 差)
❌ 差: "冷烫使用硫代乙醇酸, 热烫加热设备, 数码烫精确控温, ## 烫后护理..."
✅ 好: "**冷烫和热烫的核心区别在于药剂作用方式**。冷烫用硫代乙醇酸在室温下切断头发角蛋白的二硫键再重新连接,效果偏自然柔和,持续约 2-3 个月;热烫通过 100°C 以上高温让蛋白质变性定型,卷度更明显但对头发损伤更大,持续约 6 个月。如果追求持久选热烫,追求柔护发质选冷烫。"

## 你的能力
- 美发产品成分与作用（染膏、烫发水、护发素等）
- 染烫技术原理（染发化学、烫发物理化学等）
- 头皮护理、头发护理知识
- 美发工具使用
- 服务流程与操作规范
- **行业资讯/趋势/最新动态（需联网搜索）**

## 答案结构 (与上面重复,保留)
- 核心答案
- 详细说明
- 参考来源 (Markdown 引用语法: 【知识库】xxx 或 【网络】https://...)"""


async def build_knowledge_agent() -> Agent:
    """构建知识问答专用 Agent (P0-2 + N8 修复 + P0-3 加 web_search).

    工具装载: search_hair_knowledge (本地知识库) + web_search (联网 fallback)
    """
    # P0-3: 2 个工具 (本地 RAG + 联网 fallback)
    selected_tool_names = {"search_hair_knowledge", "web_search"}
    selected_tools = [t for t in registry.get_tools() if t.name in selected_tool_names]

    toolkit = Toolkit()
    for tool in selected_tools:
        await toolkit.add_tool(tool, group_name="basic")

    model = get_model("chat")
    rag_mw = get_rag_middleware()

    agent = Agent(
        name="美发知识顾问",
        system_prompt=_KNOWLEDGE_SYSTEM_PROMPT,
        model=model,
        toolkit=toolkit,
    )
    # 注入 RAGMiddleware (P0-3 调整: 关闭, 避免双重检索 — agent 工具会自己调 search_hair_knowledge)
    if hasattr(agent, "middlewares"):
        agent.middlewares.append(rag_mw)
    else:
        if not hasattr(agent, "_middlewares"):
            agent._middlewares = []
        agent._middlewares.append(rag_mw)

    # P0-3: 知识问答 Agent 走自研 permission.py (只读工具, 无 HITL 需求)
    # 注: AgentScope 的 PermissionMode.BYPASS 是死的, 因自研 PermissionEngine 才生效.
    # 知识 Agent 只装 search_hair_knowledge + web_search, 都是 ToolPermission.READ, 无需拦截.
    logger.info("Knowledge Agent 走自研 permission.py (只读工具, 无 HITL 需求)")

    logger.info(
        "Knowledge Agent 已构建: 工具=%d, middleware=1",
        len(selected_tools),
    )
    return agent


# 全局单例 + 异步锁
_knowledge_agent_instance = None
_init_lock = asyncio.Lock()


async def get_knowledge_agent() -> Agent:
    """获取知识 Agent 单例（异步懒加载 + 双检锁）。"""
    global _knowledge_agent_instance
    if _knowledge_agent_instance is None:
        async with _init_lock:
            if _knowledge_agent_instance is None:
                _knowledge_agent_instance = await build_knowledge_agent()
    return _knowledge_agent_instance


def reload_knowledge_agent() -> None:
    """热重载 Knowledge Agent。"""
    global _knowledge_agent_instance
    _knowledge_agent_instance = None
