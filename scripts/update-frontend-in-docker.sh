#!/usr/bin/env bash
# 将本地 frontend 代码构建后更新到运行中的 frontend 容器（无需重新 build 镜像）
# 用法：在 QuantDinger 项目根目录执行: bash scripts/update-frontend-in-docker.sh

set -e
CONTAINER="${CONTAINER:-quantdinger-frontend}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Container: $CONTAINER"
echo "Project root: $ROOT"

# 检查容器在运行
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "Error: container '$CONTAINER' is not running."
  exit 1
fi

# 1. 本地构建
VUE_DIR="quantdinger_vue"
DIST_DIR="$VUE_DIR/dist"
if [ ! -d "$VUE_DIR" ]; then
  echo "Error: $VUE_DIR not found."
  exit 1
fi

echo "Building frontend in $VUE_DIR ..."
cd "$VUE_DIR"
npm run build
cd "$ROOT"

if [ ! -d "$DIST_DIR" ] || [ -z "$(ls -A "$DIST_DIR" 2>/dev/null)" ]; then
  echo "Error: build failed or $DIST_DIR is empty."
  exit 1
fi

# 2. 同步 dist 到容器的 nginx 静态目录
DST="/usr/share/nginx/html"
echo "Syncing $DIST_DIR/ -> ${CONTAINER}:${DST}/"
docker cp "$DIST_DIR/." "${CONTAINER}:${DST}/"

# 3. 重载 nginx 以应用新文件（可选，静态文件通常无需重载）
echo "Reloading nginx..."
docker exec "$CONTAINER" nginx -s reload 2>/dev/null || docker restart "$CONTAINER"

echo "Done. Frontend updated."
