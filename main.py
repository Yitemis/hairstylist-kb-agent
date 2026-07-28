# -*- coding: utf-8 -*-
"""应用入口：命令行流式对话。

运行方式::

    python main.py

演示 :meth:`Agent.reply_stream` 的事件驱动流式输出：该方法是异步生成器，
逐步产生一系列事件，通过监听 ``TEXT_BLOCK_DELTA`` 事件即可实现打字机式的
实时输出，也是后续 Web 界面流式输出的基础。
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
    # reply_stream 返回一个异步事件流，逐个事件处理
    async for event in agent.reply_stream(UserMsg("用户", user_input)):
        # 只处理文本增量事件，拼出打字机效果
        if getattr(event, "type", None) == EventType.TEXT_BLOCK_DELTA:
            print(event.delta, end="", flush=True)
    print()  # 回复结束后换行


async def main() -> None:
    """命令行交互主循环。"""
    # 启动前检查模型配置是否填写完整
    if not is_chat_ready():
        print("=" * 60)
        print("模型尚未配置完整。")
        print("请复制 .env.example 为 .env，并填入火山方舟的：")
        print("  - CHAT_API_KEY（API Key）")
        print("  - CHAT_BASE_URL（火山方舟 OpenAI 兼容端点）")
        print("  - CHAT_MODEL（对话模型型号）")
        print("=" * 60)
        return

    agent = build_agent()
    print("=" * 60)
    print("美发知识助手已启动。")
    print("输入问题开始对话，输入 'exit' 或 'quit' 退出。")
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
