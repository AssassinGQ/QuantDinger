#!/usr/bin/env python3
"""
将名称含「广撒网」的策略按市场分组：广撒网港股、广撒网美股、广撒网外汇。

临时脚本，scp 部署，不上库。

用法（宿主机）:
  export PATH=/share/CACHEDEV1_DATA/.qpkg/container-station/bin:$PATH
  cd /share/Data2/ubuntu/ws/QuantDinger
  docker cp scripts/group_widenet_strategies.py quantdinger-backend:/tmp/
  docker exec quantdinger-backend python3 /tmp/group_widenet_strategies.py [--dry-run]
"""
import argparse
import os
import sys

for p in ["/app", os.path.join(os.path.dirname(__file__), "..", "backend_api_python")]:
    if os.path.exists(p):
        sys.path.insert(0, p)
        break

# 广撒网-市场-symbol-indicator -> display_group
MARKET_TO_GROUP = {
    "港股": "广撒网港股",
    "美股": "广撒网美股",
    "外汇": "广撒网外汇",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="仅预览")
    args = parser.parse_args()

    from app.utils.db import get_db_connection

    updated = 0

    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            SELECT id, strategy_name
            FROM qd_strategies_trading
            WHERE strategy_name LIKE %s
            """,
            ("%广撒网%",),
        )
        rows = cur.fetchall()

        for row in rows:
            rid = row["id"] if isinstance(row, dict) else row[0]
            name = (row["strategy_name"] if isinstance(row, dict) else row[1]) or ""
            parts = name.split("-")
            if len(parts) < 2 or "广撒网" not in (parts[0] or ""):
                continue
            market = (parts[1] or "").strip()
            group_name = MARKET_TO_GROUP.get(market)
            if not group_name:
                continue
            if args.dry_run:
                print(f"  [dry-run] id={rid} {name[:55]}... → {group_name}")
                updated += 1
            else:
                cur.execute(
                    "UPDATE qd_strategies_trading SET display_group = %s WHERE id = %s",
                    (group_name, rid),
                )
                if cur.rowcount > 0:
                    updated += 1
                    print(f"  → id={rid} {name[:50]}... → {group_name}")

        if not args.dry_run:
            db.commit()
        cur.close()

    print(f"{'[dry-run] 将' if args.dry_run else '已将'} {updated} 个广撒网策略分组")


if __name__ == "__main__":
    main()
