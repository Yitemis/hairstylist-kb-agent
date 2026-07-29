# -*- coding: utf-8 -*-
"""美发智能知识助手 - 企业级主入口。

运行模式：
    # 1. Web 服务模式（默认，推荐）
    python main.py

    # 2. 命令行对话模式（调试用）
    python main.py --cli

环境配置：
    复制 .env.example 为 .env，填入火山方舟 API Key。
    不同环境可使用 .env.dev / .env.staging / .env.prod。
"""
import asyncio
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# 加载配置（必须在导入 app 模块之前）
load_dotenv(PROJECT_ROOT / ".env", override=True)


from app.core.config import ENV, print_config_summary, chat_config  # noqa: E402
from app.core.agent_factory import build_agent  # noqa: E402


def run_cli_mode() -> None:
    """命令行对话模式（调试用）。"""
    from agentscope.message import UserMsg

    agent = build_agent()

    print("=" * 60)
    print("🪮 美发知识助手（命令行模式）")
    print(f"环境: {ENV.upper()} | 输入 'exit' 退出")
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

        # 使用 AgentScope 原生流式输出
        msg = UserMsg("用户", user_input)
        response = agent(msg)
        print(response.content)


def run_server_mode() -> None:
    """Web 服务模式（企业级生产模式）。"""
    from app.server.api import app
    from app.core.config import server_config

    print_config_summary()

    uvicorn.run(
        app,
        host=server_config.host,
        port=server_config.port,
        workers=server_config.workers,
        log_level=logging_config.level.lower(),  # type: ignore[name-defined] # noqa: F821
    )


if __name__ == "__main__":
    # 命令行参数解析
    if "--cli" in sys.argv:
        # 命令行调试模式
        if not chat_config.is_valid:
            print("=" * 60)
            print("⚠️  模型尚未配置完整。")
            print("请复制 .env.example 为 .env，并填入火山方舟 API 配置。")
            print("=" * 60)
            sys.exit(1)
        run_cli_mode()
    else:
        # 默认：Web 服务模式
        run_server_mode()
