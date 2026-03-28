#!/usr/bin/env bash
# 将本地 frontend 构建结果更新到运行中的 frontend 容器（无需重新 build 镜像）
# 用法：在 QuantDinger 项目根目录执行: bash scripts/update-frontend-in-docker.sh

set -e
CONTAINER="${CONTAINER:-quantdinger-frontend}"
UBUNTU_CONTAINER="${UBUNTU_CONTAINER:-ubuntu-1}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VUE_DIR="$ROOT/quantdinger_vue"
cd "$ROOT"

echo "Container: $CONTAINER"
echo "Ubuntu Container: $UBUNTU_CONTAINER"
echo "Project root: $ROOT"

# 检查 ubuntu-1 容器在运行
if ! docker ps --format '{{.Names}}' | grep -q "^${UBUNTU_CONTAINER}$"; then
  echo "Error: container '$UBUNTU_CONTAINER' is not running."
  exit 1
fi

# 在 ubuntu-1 容器中拉取最新代码并构建
echo "Pulling latest code in $UBUNTU_CONTAINER..."
docker exec "$UBUNTU_CONTAINER" bash -c "cd /home/workspace/ws/QuantDinger/ && git pull --rebase"
echo "Building frontend in $UBUNTU_CONTAINER..."
docker exec "$UBUNTU_CONTAINER" bash -c "cd /home/workspace/ws/QuantDinger/quantdinger_vue && npm run build"

# 检查 frontend 容器在运行
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "Error: container '$CONTAINER' is not running."
  exit 1
fi

# 前端应在 SSH 容器内完成编译（见 infrastructure.md），此处仅拷贝 dist
if [ ! -d "$VUE_DIR" ]; then
  echo "Error: $VUE_DIR not found."
  exit 1
fi

SRC="$VUE_DIR/dist"
if [ ! -d "$SRC" ]; then
  echo "Error: $SRC not found. Build frontend first in SSH container: cd quantdinger_vue && npm run build"
  exit 1
fi

# 同步 dist 到容器
DST="/usr/share/nginx/html"
echo "Syncing $SRC/ -> ${CONTAINER}:${DST}/"
#docker cp -r "${CONTAINER}:${DST}/" "${CONTAINER}:${DST}-bakk/"
docker cp "$SRC/." "${CONTAINER}:${DST}/"

echo "Done. Frontend updated. Wait a few seconds for nginx to serve new files."
