# -*- coding: utf-8 -*-
"""项目启动脚本。

用法：
    1. 启动向量库：python start.py --db
    2. 启动 Web 服务：python start.py
    3. 索引知识文档：python start.py --index
    4. 全部一起启动：python start.py --all
"""
import argparse
import subprocess
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def start_db():
    """启动 Milvus + Attu 向量库栈（Docker Compose）。"""
    print('=' * 60)
    print('启动 Milvus 向量库 + Attu 可视化面板...')
    print('=' * 60)
    try:
        subprocess.run(
            ['docker-compose', '-f', 'ops/docker-compose.yml', 'up', '-d'],
            cwd=PROJECT_ROOT,
            check=True,
        )
        print('')
        print('✓ Milvus 启动中，请等待 30-60 秒...')
        print('')
        print('📊 Attu 面板: http://localhost:3001')
        print('🔌 Milvus 端口: localhost:19530')
        print('')
    except FileNotFoundError:
        print('❌ 未找到 docker-compose 命令，请先安装 Docker Desktop')
        print('   下载地址: https://www.docker.com/get-started')
        sys.exit(1)
    except subprocess.CalledProcessError:
        print('⚠️  Docker 启动命令执行失败，请检查 Docker 是否在运行')
        sys.exit(1)


def index_docs():
    """索引知识库文档。"""
    print('=' * 60)
    print('开始索引知识库文档...')
    print('=' * 60)
    subprocess.run(
        [sys.executable, '-m', 'app.rag.index'],
        cwd=PROJECT_ROOT,
        check=True,
    )


def start_server():
    """启动 Web 服务。"""
    print('=' * 60)
    print('启动美发知识助手 API 服务...')
    print('=' * 60)
    print('')
    print('🌐 API 地址: http://localhost:7860')
    print('📖 API 文档: http://localhost:7860/docs')
    print('')
    subprocess.run(
        [sys.executable, '-m', 'uvicorn', 'app.server.api:app', '--reload'],
        cwd=PROJECT_ROOT,
    )


def start_all():
    """一键启动全部：DB + 索引 + Web 服务。"""
    start_db()
    print('等待 Milvus 初始化 20 秒...')
    import time
    time.sleep(20)
    index_docs()
    start_server()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='美发知识助手启动脚本')
    parser.add_argument('--db', action='store_true', help='只启动向量库（Milvus + Attu）')
    parser.add_argument('--index', action='store_true', help='只索引知识库文档')
    parser.add_argument('--server', action='store_true', help='只启动 Web 服务')
    parser.add_argument('--all', action='store_true', help='一键启动全部（DB + 索引 + 服务）')

    args = parser.parse_args()

    if len(sys.argv) == 1:
        # 无参数：默认启动服务
        start_server()
    elif args.all:
        start_all()
    elif args.db:
        start_db()
    elif args.index:
        index_docs()
    elif args.server:
        start_server()