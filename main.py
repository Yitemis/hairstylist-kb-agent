# -*- coding: utf-8 -*-
"""应用入口 —— M0 阶段：Hello World Agent（命令行流式对话）。

运行方式：
    python main.py

【本文件演示的框架核心原理】
1. Agent.reply_stream()：异步生成器，实时“吐出”一连串事件（Event）。
2. 事件驱动：通过监听 TEXT_BLOCK_DELTA 等事件实现打字机式输出。
3. 这正是后续 Web 界面流式输出的底层基础。
"""
import asyncio
import sys

# Windows 终端默认 GBK 编码，打印 emoji / 部分字符会报 UnicodeEncodeError。
# 强制标准输出/错误使用 UTF-8，保证跨平台一致的显示效果。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from agentscope.event import EventType
from agentscope.message import UserMsg

from app.agent_factory import build_agent
from app.config import is_chat_ready


async def chat_once(agent, user_input: str) -> None:
    """向 Agent 发送一句话，并以打字机方式流式打印回复。

    Args:
        agent: 已组装好的 Agent 实例。
        user_input: 用户输入的文本。
    """
    # reply_stream 返回一个异步事件流；我们逐个事件处理
    async for event in agent.reply_stream(UserMsg("用户", user_input)):
        # 只处理“文本增量”事件，拼出打字机效果
        if getattr(event, "type", None) == EventType.TEXT_BLOCK_DELTA:
            print(event.delta, end="", flush=True)
    print()  # 回复结束后换行


async def main() -> None:
    """命令行交互主循环。"""
    # 启动前先检查模型配置是否填好，给出友好提示
    if not is_chat_ready():
        print("=" * 60)
        print("⚠️  模型尚未配置完整！")
        print("请复制 .env.example 为 .env，并填入火山方舟的：")
        print("  - CHAT_API_KEY（你的 API Key）")
        print("  - CHAT_BASE_URL（火山方舟 OpenAI 兼容端点）")
        print("  - CHAT_MODEL（对话模型型号，如 doubao-pro-32k）")
        print("=" * 60)
        return

    agent = build_agent()
    print("=" * 60)
    print("💇 美发知识助手已启动（M0 最简版）")
    print("输入你的问题，输入 'exit' 或 'quit' 退出。")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if user_input.lower() in ("exit", "quit", "退出"):
            print("再见！")
            break
        if not user_input:
            continue

        print("助手：", end="", flush=True)
        await chat_once(agent, user_input)


if __name__ == "__main__":
    asyncio.run(main())
