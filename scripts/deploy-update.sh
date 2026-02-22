#!/usr/bin/env bash
# QuantDinger 更新部署脚本
# 在能访问 192.168.0.118 的机器上执行。前置: git push hgq main
# 用法: bash scripts/deploy-update.sh

set -e
QD_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$QD_ROOT"

echo "=== QuantDinger 更新部署 ==="
echo "项目根: $QD_ROOT"
echo "详细步骤见 scripts/DEPLOY.md"
echo ""

echo "[1/4] SSH 容器拉取代码..."
ssh -p 322 root@192.168.0.118 "cd /home/workspace/ws/QuantDinger && git pull --rebase hgq main 2>/dev/null || git pull --rebase origin main 2>/dev/null || git pull --rebase"

echo "[2/4] SSH 容器编译前端..."
ssh -p 322 root@192.168.0.118 "cd /home/workspace/ws/QuantDinger/quantdinger_vue && npm run build 2>/dev/null || (npm install --legacy-peer-deps && npm run build)"

echo "[3/4] NAS 宿主机更新 backend..."
ssh admin@192.168.0.118 "export PATH=/share/CACHEDEV1_DATA/.qpkg/container-station/bin:\$PATH && cd /share/Data2/ubuntu/ws/QuantDinger && bash scripts/update-backend-in-docker.sh"

echo "[4/4] NAS 宿主机更新 frontend..."
ssh admin@192.168.0.118 "export PATH=/share/CACHEDEV1_DATA/.qpkg/container-station/bin:\$PATH && cd /share/Data2/ubuntu/ws/QuantDinger && bash scripts/update-frontend-in-docker.sh"

echo ""
echo "=== 部署完成 ==="
echo "访问 http://192.168.0.118:8888 验证"
