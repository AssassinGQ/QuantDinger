#!/usr/bin/env bash
# 将本地 backend 代码更新到运行中的 backend 容器（无需重新 build 镜像）
# 用法：在 QuantDinger 项目根目录执行: bash scripts/update-backend-in-docker.sh

set -e
CONTAINER="${CONTAINER:-quantdinger-backend}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Container: $CONTAINER"
echo "Project root: $ROOT"

# 检查容器在运行
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "Error: container '$CONTAINER' is not running."
  exit 1
fi

# 同步整个 app 目录到容器（不依赖 git，所有变更都会进容器）
SRC="backend_api_python/app"
DST="/app/app"
if [ ! -d "$SRC" ]; then
  echo "Error: $SRC not found."
  exit 1
fi
echo "Syncing $SRC/ -> ${CONTAINER}:${DST}/"
docker cp "$SRC/." "${CONTAINER}:${DST}/"

echo "Restarting backend to load new code..."
docker restart "$CONTAINER"
echo "Done. Wait a few seconds for health check."
