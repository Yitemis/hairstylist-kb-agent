# -*- coding: utf-8 -*-
"""Agent 工厂：基于 AgentScope 2.0 原生 Agent 构建业务专用 Agent。

100% 复用框架能力，不重造轮子：
- Agent (ReAct loop): 思考-行动循环
- Toolkit: 工具注册（知识库检索 + 后续订单工具）
- ChatModel (OpenAI 兼容): 对话模型
"""
from __future__ import annotations

import logging

from agentscope.agent import Agent

from app.core.model_factory import get_model
from app.core.tool_registry import registry

logger = logging.getLogger(__name__)


_HAIR_SYSTEM_PROMPT = """你是**美发智能助手**，同时支持「专业知识库问答」和「对话式预约下单」两种能力：

## 📖 如果你被问到专业问题（如产品成分、染烫技术、操作流程）
1. **必须先调用 `search_hair_knowledge` 工具检索知识库**，再基于检索结果回答，绝对不可以编造；
2. 用专业、准确、易懂的语言回答，结构清晰，必要时分点说明；
3. 保持专业、友好、有耐心的语气。

## 📅 如果用户想预约理发/染发/烫发等服务（对话式下单）
请严格按照以下流程**逐步引导用户**，不要跳过任何一步：
1. **第一步必须调用 `create_draft_order(user_id)` 创建草稿订单**；
2. **第二步调用 `list_branches(user_id, ...)`** 列出所有分店，如果用户提供位置，带上用户经纬度按距离排序；让用户选择分店；
3. 用户选了分店 → **立即调用 `update_order_fields` 更新分店ID到订单**；
4. 用户选完分店 → 调用 `list_stylists(user_id, branch_id)` 列出该分店所有发型师，让用户选择；
5. 用户选了发型师 → **立即调用 `update_order_fields` 更新发型师ID**；
6. 用户不知道选什么项目 → 调用 `recommend_services(user_id, 用户需求描述)` 列出推荐服务；用户选完项目，自动会填充时长和价格；
7. 用户选完项目 → 询问预约哪一天哪个时间段，用户给了之后更新进去，自动计算结束时间；
8. 最后询问用户联系电话和姓名，更新进去；
9. **所有必填信息（分店、项目、发型师、日期时间、电话）齐全后**，提示用户确认，确认后调用 `confirm_order` 提交订单；
10. confirm_order 会自动检查冲突，如果报错，把错误信息告诉用户，让用户重新选择；
11. 用户随时可以让你展示当前订单信息，你直接整理出来即可，不需要调用工具。

## 📌 工具调用规则
- 每次最多调用一个工具，调用完等待返回结果再继续；
- 所有工具调用都**必须带上 `user_id` 参数**（当前登录用户的 ID），不要遗漏；
- 用户可以直接说所有信息（比如"我明天10点去人民广场店找托尼剪发"），你要解析出来分步骤调用工具更新；
- 前端也支持点选，不管用户是说的还是点选的，你都要调用工具保存到订单；
- 只回答美发和预约相关内容，不回答无关话题；
- 对于不确定的内容如实说明，不要编造。
"""


def build_agent(
    name: str = "美发顾问",
    system_prompt: str | None = None,
    enable_tools: bool = True,
) -> Agent:
    """构建美发知识助手 Agent（基于 AgentScope 2.0 Agent）。

    Args:
        name: Agent 名称。
        system_prompt: 自定义系统提示词（默认使用美发领域专用）。
        enable_tools: 是否启用知识库检索工具。

    Returns:
        配置好的 Agent 实例，支持工具调用 + 多轮对话。
    """
    # 1. 获取对话模型（从模型工厂）
    model = get_model("chat")

    # 2. 构建 Agent
    agent = Agent(
        name=name,
        system_prompt=system_prompt or _HAIR_SYSTEM_PROMPT,
        model=model,
        toolkit=registry.build_toolkit() if enable_tools else None,
    )

    logger.info("Agent 已构建: %s, 模型=%s, 工具数=%d", name, model.model, len(registry.get_tools()))
    return agent


# 全局单例（服务运行时共享）
_agent_instance: Agent | None = None


def get_agent() -> Agent:
    """获取全局 Agent 单例（懒加载，首次调用时初始化）。"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = build_agent()
    return _agent_instance


def reload_agent() -> None:
    """热重载 Agent（配置变更后调用，无需重启服务）。"""
    global _agent_instance
    _agent_instance = None
