#!/usr/bin/env bash
# QuantDinger 后端更新部署脚本
# 在能解析 hgq-nas 的机器上执行。前置: git push hgq main
# 只更新后端，不编译前端

set -e
QD_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$QD_ROOT"

echo "=== QuantDinger 后端更新部署 ==="
echo "项目根: $QD_ROOT"
echo ""

echo "[1/2] SSH 容器拉取代码..."
ssh -p 322 root@hgq-nas "cd /home/workspace/ws/QuantDinger && git pull --rebase hgq main 2>/dev/null || git pull --rebase origin main 2>/dev/null || git pull --rebase"

echo "[2/2] NAS 宿主机更新 backend..."
ssh admin@hgq-nas "export PATH=/share/CACHEDEV1_DATA/.qpkg/container-station/bin:\$PATH && cd /share/Data2/ubuntu/ws/QuantDinger && bash scripts/update-backend-in-docker.sh"

echo ""
echo "=== 部署完成 ==="
echo "访问 http://hgq-nas:8888 验证"
