#!/usr/bin/env python3
"""
将名称含 aggressive/balanced/conservative 的策略按股票分组，设置 display_group。
港股代码映射为中文名(代码)，如 腾讯(00700)；其他市场用原 symbol。

临时脚本，scp 部署，不上库。

用法（宿主机）:
  export PATH=/share/CACHEDEV1_DATA/.qpkg/container-station/bin:$PATH
  cd /share/Data2/ubuntu/ws/QuantDinger
  docker cp scripts/group_regime_strategies_by_symbol.py quantdinger-backend:/tmp/
  docker exec quantdinger-backend python3 /tmp/group_regime_strategies_by_symbol.py [--dry-run]
"""
import argparse
import json
import os
import re
import sys

for p in ["/app", os.path.join(os.path.dirname(__file__), "..", "backend_api_python")]:
    if os.path.exists(p):
        sys.path.insert(0, p)
        break

# 港股代码 -> 中文名（5 位格式，如 00700）
HK_SYMBOL_TO_NAME = {
    "00700": "腾讯",
    "09988": "阿里",
    "03690": "美团",
    "01810": "小米",
    "09618": "京东",
    "01211": "比亚迪",
    "02015": "理想汽车",
    "09866": "蔚来",
    "09868": "小鹏",
    "00388": "港交所",
    "02318": "中国平安",
    "00005": "汇丰",
    "02269": "药明生物",
    "02020": "安踏",
    "01398": "工商银行",
    "00939": "建设银行",
    "01299": "友邦保险",
    "01024": "快手",
}


def _normalize_hk_symbol(s: str) -> str:
    """港股代码补足为 5 位，如 700 -> 00700。"""
    if not s or not s.isdigit():
        return s
    return s.zfill(5)


def _get_symbol(row) -> str:
    """从 strategy 行提取 symbol。"""
    sym = (row.get("symbol") or "").strip()
    if sym:
        return sym
    tc = row.get("trading_config")
    if isinstance(tc, dict):
        return (tc.get("symbol") or "").strip()
    if isinstance(tc, str):
        try:
            d = json.loads(tc)
            return (d.get("symbol") or "").strip()
        except Exception:
            pass
    # 从 strategy_name 解析，如 "09988 MAX-aggressive xxx" 或 "TSLA MAX-balanced xxx"
    name = (row.get("strategy_name") or "").strip()
    parts = name.split()
    if parts:
        first = parts[0].strip()
        if re.match(r"^\d{4,5}$", first):  # 港股 4-5 位
            return first.zfill(5)
        if re.match(r"^[A-Za-z]+(?:\/[\w]+)?$", first):  # TSLA, XAUUSD, BTC/USDT
            return first
    return ""


def _display_group(symbol: str, market_category: str) -> str:
    """根据 symbol 和 market 生成 display_group，格式为 股票名-regime。"""
    if not symbol:
        return "ungrouped"
    m = (market_category or "").strip()
    base = symbol
    if m == "HShare":
        hk = _normalize_hk_symbol(symbol)
        if hk in HK_SYMBOL_TO_NAME:
            base = f"{HK_SYMBOL_TO_NAME[hk]}({hk})"
    return f"{base}-regime"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="仅预览")
    parser.add_argument("--symbol", type=str, help="仅处理指定 symbol（如 03690）")
    parser.add_argument("--exclude", type=str, help="排除指定 symbol，多个用逗号分隔（如 03690）")
    args = parser.parse_args()

    from app.utils.db import get_db_connection

    updated = 0

    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute("""
            SELECT id, strategy_name, symbol, market_category, trading_config
            FROM qd_strategies_trading
            WHERE strategy_name ILIKE %s OR strategy_name ILIKE %s OR strategy_name ILIKE %s
        """, ("%aggressive%", "%balanced%", "%conservative%"))
        rows = cur.fetchall()

        symbol_filter = None
        if args.symbol:
            symbol_filter = _normalize_hk_symbol(args.symbol.strip()) or args.symbol.strip()

        exclude_set = set()
        if args.exclude:
            for x in args.exclude.split(","):
                s = (x or "").strip()
                if s:
                    exclude_set.add(_normalize_hk_symbol(s) or s)

        for row in rows:
            rid = row["id"] if isinstance(row, dict) else row[0]
            name = (row["strategy_name"] if isinstance(row, dict) else row[1]) or ""
            sym = _get_symbol(row)
            if sym in exclude_set:
                continue
            if symbol_filter and sym != symbol_filter:
                continue
            market = (row["market_category"] if isinstance(row, dict) else row[3]) or ""
            dg = _display_group(sym, market)
            if not dg or dg == "ungrouped":
                continue
            if args.dry_run:
                print(f"  [dry-run] id={rid} {name[:50]}... | sym={sym} → {dg}")
                updated += 1
            else:
                cur.execute(
                    "UPDATE qd_strategies_trading SET display_group = %s WHERE id = %s",
                    (dg, rid),
                )
                if cur.rowcount > 0:
                    updated += 1
                    print(f"  → id={rid} {name[:45]}... | {dg}")

        if not args.dry_run:
            db.commit()
        cur.close()

    print(f"{'[dry-run] 将' if args.dry_run else '已将'} {updated} 个策略按股票分组")


if __name__ == "__main__":
    main()
