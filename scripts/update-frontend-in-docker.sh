#!/usr/bin/env bash
# 将本地 frontend 构建结果更新到运行中的 frontend 容器（无需重新 build 镜像）
# 用法：在 QuantDinger 项目根目录执行: bash scripts/update-frontend-in-docker.sh

set -e
CONTAINER="${CONTAINER:-quantdinger-frontend}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VUE_DIR="$ROOT/quantdinger_vue"
cd "$ROOT"

echo "Container: $CONTAINER"
echo "Project root: $ROOT"

# 检查容器在运行
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "Error: container '$CONTAINER' is not running."
  exit 1
fi

# 本地构建
if [ ! -d "$VUE_DIR" ]; then
  echo "Error: $VUE_DIR not found."
  exit 1
fi

echo "Installing dependencies (if needed)..."
cd "$VUE_DIR"
npm install --legacy-peer-deps

echo "Building frontend..."
npm run build

# 同步 dist 到容器
SRC="$VUE_DIR/dist"
DST="/usr/share/nginx/html"
echo "Syncing $SRC/ -> ${CONTAINER}:${DST}/"
docker cp "$SRC/." "${CONTAINER}:${DST}/"

echo "Done. Frontend updated. Wait a few seconds for nginx to serve new files."
