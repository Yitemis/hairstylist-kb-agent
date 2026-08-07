#!/bin/bash
echo "=== 1. 启动 Docker daemon ==="
rm -f /var/run/docker.pid
nohup dockerd > /var/log/dockerd.log 2>&1 &
sleep 10

echo "=== 2. 验证 Docker ==="
if docker info > /dev/null 2>&1; then
    echo "✓ Docker daemon OK"
else
    echo "✗ Docker daemon failed, retrying..."
    sleep 5
fi

echo "=== 3. 启动 Milvus ==="
cd /mnt/e/hairstylist-kb-agent
docker compose -f ops/docker-compose.yml up -d

echo "=== 4. 容器状态 ==="
sleep 5
docker compose -f ops/docker-compose.yml ps
