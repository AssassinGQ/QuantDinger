#!/usr/bin/env python3
"""
K 线历史回填：将 5m/15m/30m/1H 等分钟级数据向历史方向拉取并写入 qd_kline_points。

用法:
  cd backend_api_python
  python scripts/backfill_kline_history.py --market HShare --days 90
  python scripts/backfill_kline_history.py --market HShare --symbols 00700,00939 --timeframes 5m,1H --days 180
  python scripts/backfill_kline_history.py --market AShare --symbols 000001,600519 --days 60

  # 从 qd_market_symbols 读取标的
  python scripts/backfill_kline_history.py --market HShare --from-db --days 90

依赖: psycopg2, DATABASE_URL
"""
import os
import sys
import time
import argparse
from datetime import datetime

if __name__ == "__main__":
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)


def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# 周期秒数
TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1H": 3600, "4H": 14400, "1D": 86400, "1W": 604800}


def main():
    _load_env()
    parser = argparse.ArgumentParser(description="K 线历史回填（5m/15m/30m/1H）")
    parser.add_argument("--market", required=True, help="市场: HShare, AShare, USStock 等")
    parser.add_argument("--symbols", type=str, default="", help="逗号分隔标的，如 00700,00939")
    parser.add_argument("--from-db", action="store_true", help="从 qd_market_symbols 读取该市场标的")
    parser.add_argument("--timeframes", type=str, default="5m,15m,30m,1H", help="逗号分隔周期，默认 5m,15m,30m,1H")
    parser.add_argument("--days", type=int, default=90, help="回填天数，默认 90")
    parser.add_argument("--chunk", type=int, default=800, help="每请求条数，默认 800（防限流）")
    parser.add_argument("--delay", type=float, default=1.5, help="请求间隔秒数")
    parser.add_argument("--dry-run", action="store_true", help="仅打印将要执行的标的/周期，不实际拉取")
    args = parser.parse_args()

    # 解析标的
    if args.from_db:
        try:
            from app.utils.db import get_db_connection
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT DISTINCT symbol FROM qd_market_symbols WHERE market = %s AND is_active = 1 ORDER BY symbol",
                    (args.market,),
                )
                rows = cur.fetchall()
                symbols = [r["symbol"] if isinstance(r, dict) else r[0] for r in rows if r]
                cur.close()
            if not symbols:
                print("qd_market_symbols 中无该市场标的", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print("从 DB 读取标的失败:", e, file=sys.stderr)
            sys.exit(1)
    else:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        if not symbols:
            print("请指定 --symbols 或 --from-db", file=sys.stderr)
            sys.exit(1)

    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    if not timeframes:
        timeframes = ["5m", "15m", "30m", "1H"]

    print(f"回填: market={args.market} symbols={len(symbols)} timeframes={timeframes} days={args.days}")
    if args.dry_run:
        for s in symbols:
            print(f"  {args.market}:{s} -> {timeframes}")
        print("(dry-run, 未执行)")
        return

    from app.services.kline_fetcher import get_kline

    now_sec = int(time.time())
    total_fetched = 0
    total_skipped = 0

    for si, symbol in enumerate(symbols):
        for ti, tf in enumerate(timeframes):
            interval_sec = TF_SECONDS.get(tf, 300)
            # 目标：回填 days 天的数据（按交易日估算，约 days * 0.7 根/天）
            bars_needed = max(100, int(args.days * 0.75 * (86400 / interval_sec)))
            fetched_this = 0
            next_before = now_sec + interval_sec

            while fetched_this < bars_needed:
                try:
                    klines = get_kline(args.market, symbol, tf, limit=args.chunk, before_time=next_before)
                except Exception as e:
                    print(f"  [ERR] {args.market}:{symbol} {tf}: {e}")
                    break

                if not klines:
                    break

                min_ts = min(b["time"] for b in klines)
                fetched_this += len(klines)
                total_fetched += len(klines)
                next_before = min_ts

                oldest = datetime.utcfromtimestamp(min_ts).strftime("%Y-%m-%d")
                print(f"  {args.market}:{symbol} {tf} +{len(klines)} 条, 最早 {oldest}, 累计 {fetched_this}")

                if len(klines) < args.chunk // 2:
                    break

                time.sleep(args.delay)

            if fetched_this == 0:
                total_skipped += 1

        if si < len(symbols) - 1:
            time.sleep(args.delay * 2)

    print(f"\nDone. 总拉取 {total_fetched} 条, 空结果 {total_skipped} 次")


if __name__ == "__main__":
    main()
