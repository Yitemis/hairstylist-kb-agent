# ============================================================
# 美发智能知识助手 - Docker 生产镜像
# ============================================================

FROM python:3.11-slim

LABEL maintainer="hairstylist-kb-agent"
LABEL description="企业级美发行业知识助手"

WORKDIR /app

# 安装系统依赖（curl, ca-certificates 用于 HTTPS 调用）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 先安装 Python 依赖（利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 数据目录挂载点（持久化向量库数据）
VOLUME /app/data

# 暴露端口
# - 7860: API 服务
# - 9090: Prometheus 指标
EXPOSE 7860 9090

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# 启动命令
CMD ["python", "main.py"]
