#!/usr/bin/env python3
"""
查询数据库中 K 线缓存、宏观缓存、新闻缓存的统计信息，表格化输出。

用法:
  cd backend_api_python
  python scripts/query_cache_stats.py

  # 或指定连接串（.env 中的 DATABASE_URL 优先）
  DATABASE_URL=postgresql://quantdinger:quantdinger123@hgq-nas:35432/quantdinger python scripts/query_cache_stats.py

  # Docker 网络内
  DATABASE_URL=postgresql://quantdinger:quantdinger123@quantdinger-db:5432/quantdinger python scripts/query_cache_stats.py

依赖: psycopg2
"""
import os
import sys
from datetime import datetime

# 支持从项目根目录执行
if __name__ == "__main__":
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)

# 加载 .env
def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# 港股代码 -> 中文名（qd_market_symbols 多为英文，常用标的补充中文）
HSHARE_CN = {
    "00700": "腾讯控股",
    "09988": "阿里巴巴",
    "03690": "美团",
    "01810": "小米集团",
    "02318": "中国平安",
    "01398": "工商银行",
    "00939": "建设银行",
    "01299": "友邦保险",
    "02020": "安踏体育",
    "01024": "快手",
}

# interval_sec -> 周期名
INTERVAL_LABELS = {
    60: "1m",
    300: "5m",
    900: "15m",
    1800: "30m",
    3600: "1H",
    14400: "4H",
    86400: "1D",
    604800: "1W",
}


def _norm_symbol(market, symbol):
    """标准化代码便于匹配：AShare 6 位，HShare 5 位。"""
    s = (symbol or "").strip()
    if not s or not s.isdigit():
        return s
    if market == "AShare":
        return s.zfill(6)
    if market == "HShare":
        return s.zfill(5)
    return s


def _load_symbol_names(conn):
    """从 qd_market_symbols 加载 AShare/HShare 的 代码->中文名 映射。"""
    lookup = {}  # (market, norm_symbol) -> name
    try:
        rows = _run_query(
            conn,
            "SELECT market, symbol, name FROM qd_market_symbols WHERE market IN ('AShare', 'HShare')"
        )
        for r in rows:
            market = (r.get("market") or "").strip()
            symbol = _norm_symbol(market, r.get("symbol"))
            name = (r.get("name") or "").strip()
            if market and symbol:
                # AShare 的 name 通常已是中文；HShare 多为英文，用 HSHARE_CN 覆盖
                if market == "HShare" and symbol in HSHARE_CN:
                    name = HSHARE_CN[symbol]
                if name:
                    lookup[(market, symbol)] = name
    except Exception:
        pass
    return lookup


def _format_category(market, symbol, name_lookup):
    """品类显示：market:symbol 或 market:symbol(中文名)。"""
    norm = _norm_symbol(market, symbol)
    key = (market, norm)
    name = name_lookup.get(key) if name_lookup else None
    base = f"{market}:{symbol}"
    if name:
        return f"{base}({name})"
    return base


def _ts_to_str(ts):
    if ts is None:
        return "-"
    try:
        return datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


def _run_query(conn, sql, params=None):
    cur = conn.cursor()
    try:
        cur.execute(sql, params or ())
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        # RealDictRow 可直接 dict() 复制，保留正确的 key->value
        return [dict(r) for r in rows]
    finally:
        cur.close()


def _print_table(title, headers, rows, col_widths=None):
    """rows: list of dicts with keys matching headers, or list of tuples in header order."""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print("=" * 80)
    if not rows:
        print("  (无数据)")
        return
    # rows 为 dict 时按 headers 取值；为 tuple/list 时直接按序
    def _row_vals(r):
        if isinstance(r, (list, tuple)):
            return [str(x) for x in r]
        return [str(r.get(h, "")) for h in headers]
    sample_vals = _row_vals(rows[0])
    if col_widths is None:
        col_widths = [max(len(str(h)), len(sv)) for h, sv in zip(headers, sample_vals)]
        for r in rows[1:]:
            for i, v in enumerate(_row_vals(r)):
                col_widths[i] = max(col_widths[i], len(str(v)))
    col_widths = [max(c, len(h)) for c, h in zip(col_widths, headers)]
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(fmt.format(*headers))
    print("  " + "-" * (sum(col_widths) + 2 * (len(headers) - 1)))
    for r in rows:
        vals = _row_vals(r)
        vals = [v[:col_widths[i]] for i, v in enumerate(vals)]
        print(fmt.format(*vals))
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="查询 K线/宏观/新闻 缓存统计")
    parser.add_argument("--limit", type=int, default=50, help="K线表格最多显示行数，0=不限制")
    args = parser.parse_args()

    _load_env()
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        print("需要 psycopg2: pip install psycopg2-binary", file=sys.stderr)
        sys.exit(1)

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        print("请设置 DATABASE_URL 或确保 .env 中有配置", file=sys.stderr)
        sys.exit(1)

    try:
        conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    except Exception as e:
        print(f"数据库连接失败: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        # AShare/HShare 名称映射（用于品类列显示中文名）
        name_lookup = _load_symbol_names(conn)

        # ---------- 1. K 线缓存 ----------
        # 优先用 qd_kline_points（主存储），fallback 到 qd_kline_cache
        kline_rows = []
        try:
            rows = _run_query(
                conn,
                """
                SELECT market, symbol, interval_sec,
                       COUNT(*) AS cnt,
                       MIN(time_sec) AS min_ts,
                       MAX(time_sec) AS max_ts
                FROM qd_kline_points
                GROUP BY market, symbol, interval_sec
                ORDER BY market, symbol, interval_sec
                """
            )
            display_rows = rows[: args.limit] if args.limit > 0 else rows
            for r in display_rows:
                interval_sec = int(r.get("interval_sec") or 60)
                market = r.get("market") or ""
                symbol = r.get("symbol") or ""
                kline_rows.append({
                    "品类": _format_category(market, symbol, name_lookup),
                    "周期": INTERVAL_LABELS.get(interval_sec, f"{interval_sec}s"),
                    "数据点总数": r.get("cnt", 0),
                    "覆盖范围": f"{_ts_to_str(r.get('min_ts'))} ~ {_ts_to_str(r.get('max_ts'))}",
                })
            if args.limit > 0 and len(rows) > args.limit:
                kline_rows.append({"品类": f"... 共 {len(rows)} 条，仅显示前 {args.limit} 条", "周期": "-", "数据点总数": "-", "覆盖范围": "-"})
        except Exception as e:
            print(f"  qd_kline_points 查询失败: {e}")

        if not kline_rows:
            try:
                rows = _run_query(
                    conn,
                    """
                    SELECT market, symbol, timeframe,
                           COUNT(*) AS cnt,
                           MIN(time_sec) AS min_ts,
                           MAX(time_sec) AS max_ts
                    FROM qd_kline_cache
                    GROUP BY market, symbol, timeframe
                    ORDER BY market, symbol, timeframe
                    """
                )
                for r in rows:
                    market = r.get("market") or ""
                    symbol = r.get("symbol") or ""
                    kline_rows.append({
                        "品类": _format_category(market, symbol, name_lookup),
                        "周期": r.get("timeframe", "-"),
                        "数据点总数": r["cnt"],
                        "覆盖范围": f"{_ts_to_str(r['min_ts'])} ~ {_ts_to_str(r['max_ts'])}",
                    })
            except Exception as e:
                print(f"  qd_kline_cache 查询失败: {e}")

        _print_table("1. K 线缓存 (qd_kline_points / qd_kline_cache)", ["品类", "周期", "数据点总数", "覆盖范围"], kline_rows)

        # ---------- 2. 宏观缓存 ----------
        macro_rows = []
        try:
            rows = _run_query(
                conn,
                """
                SELECT indicator,
                       COUNT(*) AS cnt,
                       MIN(date_val)::text AS min_d,
                       MAX(date_val)::text AS max_d
                FROM qd_macro_data
                GROUP BY indicator
                ORDER BY indicator
                """
            )
            for r in rows:
                macro_rows.append({
                    "品类": r["indicator"],
                    "数据点总数": r["cnt"],
                    "覆盖范围": f"{r['min_d']} ~ {r['max_d']}",
                })
        except Exception as e:
            print(f"  qd_macro_data 查询失败: {e}")

        _print_table("2. 宏观缓存 (qd_macro_data)", ["品类", "数据点总数", "覆盖范围"], macro_rows)

        # ---------- 3. 新闻/同步缓存 ----------
        sync_rows = []
        try:
            rows = _run_query(
                conn,
                """
                SELECT cache_key, value_json, updated_at
                FROM qd_sync_cache
                ORDER BY cache_key
                """
            )
            import json
            for r in rows:
                cnt = "-"
                if r.get("value_json"):
                    try:
                        j = json.loads(r["value_json"])
                        if isinstance(j, dict):
                            if "cn" in j and "en" in j:
                                cnt = f"cn:{len(j.get('cn',[]))} en:{len(j.get('en',[]))}"
                            else:
                                cnt = str(len(j))
                        elif isinstance(j, list):
                            cnt = str(len(j))
                        else:
                            cnt = f"{len(str(j))} chars"
                    except Exception:
                        cnt = f"{len(r['value_json'])} chars"
                up = r.get("updated_at")
                up_str = up.strftime("%Y-%m-%d %H:%M") if hasattr(up, "strftime") else str(up or "-")[:19]
                sync_rows.append({
                    "品类": r["cache_key"],
                    "数据点总数": cnt,
                    "更新时间": up_str,
                })
        except Exception as e:
            print(f"  qd_sync_cache 查询失败: {e}")

        _print_table("3. 新闻/同步缓存 (qd_sync_cache)", ["品类", "数据点总数", "更新时间"], sync_rows)

    finally:
        conn.close()

    print("Done.\n")


if __name__ == "__main__":
    main()
