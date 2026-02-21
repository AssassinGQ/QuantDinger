#!/usr/bin/env python3
"""
从备份 JSON 读取 indicator_group，更新 qd_indicator_codes 表。

宿主机执行（需先在 NAS 上 cd 到 QuantDinger，拉取最新代码）：
  cd /share/Data2/ubuntu/ws
  docker cp ai-coder/cursor/20260217-StrategyOptimizer/top-max/deploy-backup/_backup_indicators.json quantdinger-backend:/tmp/indicators_backup.json
  docker cp QuantDinger/scripts/apply_indicator_groups_from_backup.py quantdinger-backend:/tmp/
  docker exec -e BACKUP_PATH=/tmp/indicators_backup.json quantdinger-backend python3 /tmp/apply_indicator_groups_from_backup.py
"""
import json
import os
import sys

# 优先 /app（容器内），否则用本地 backend
for p in ["/app", os.path.join(os.path.dirname(__file__), "..", "backend_api_python")]:
    if os.path.exists(p):
        sys.path.insert(0, p)
        break

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_PATH = os.environ.get(
    "BACKUP_PATH",
    os.path.join(
        SCRIPT_DIR, "..", "..", "ai-coder", "cursor",
        "20260217-StrategyOptimizer", "top-max", "deploy-backup", "_backup_indicators.json"
    ),
)


def main():
    if not os.path.exists(BACKUP_PATH):
        print(f"备份文件不存在: {BACKUP_PATH}", file=sys.stderr)
        print("可设置 BACKUP_PATH 环境变量或在宿主机 docker cp 备份到容器后指定路径", file=sys.stderr)
        sys.exit(1)

    with open(BACKUP_PATH, "r", encoding="utf-8") as f:
        indicators = json.load(f)

    from app.utils.db import get_db_connection

    updated = 0
    with get_db_connection() as db:
        cur = db.cursor()
        for item in indicators:
            rid = item.get("id")
            group = item.get("indicator_group", "ungrouped")
            user_id = item.get("user_id", 1)
            cur.execute(
                "UPDATE qd_indicator_codes SET indicator_group = %s WHERE id = %s AND user_id = %s",
                (group, rid, user_id),
            )
            if cur.rowcount > 0:
                updated += 1
        db.commit()
        cur.close()

    print(f"数据库已更新 {updated} 条 indicator_group")


if __name__ == "__main__":
    main()
