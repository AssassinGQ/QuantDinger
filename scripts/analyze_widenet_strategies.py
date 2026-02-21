#!/usr/bin/env python3
"""
分析广撒网策略：相同 Indicator 用于不同股票的策略，检查 SL/TP 是否一致。
若一致，可考虑归为截面策略组。

临时脚本，需在 backend 容器或能连 DB 的环境执行。
"""
import json
import os
import re
import sys
from collections import defaultdict

for p in ["/app", os.path.join(os.path.dirname(__file__), "..", "backend_api_python")]:
    if os.path.exists(p):
        sys.path.insert(0, p)
        break


def _parse_widenet_name(name: str) -> tuple:
    """解析 广撒网-市场-symbol-indicator 格式，返回 (market, symbol, indicator)。"""
    # 广撒网-港股-00700-BB(15/2.0)  或  广撒网-美股-JPM-RSI(9,75/25)
    parts = name.split("-")
    if len(parts) >= 4 and "广撒网" in (parts[0] or ""):
        return parts[1].strip(), parts[2].strip(), "-".join(parts[3:]).strip()
    return None, None, None


def _get_risk_params(tc) -> dict:
    """从 trading_config 提取 SL/TP 等风险参数。"""
    if not tc:
        return {}
    if isinstance(tc, str):
        try:
            tc = json.loads(tc)
        except Exception:
            return {}
    return {
        "stop_loss_pct": tc.get("stop_loss_pct"),
        "take_profit_pct": tc.get("take_profit_pct"),
        "trailing_enabled": tc.get("trailing_enabled"),
        "trailing_stop_pct": tc.get("trailing_stop_pct"),
        "trailing_activation_pct": tc.get("trailing_activation_pct"),
    }


def main():
    from app.utils.db import get_db_connection

    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            SELECT id, strategy_name, symbol, market_category, trading_config
            FROM qd_strategies_trading
            WHERE strategy_name LIKE %s
            ORDER BY strategy_name
            """,
            ("%广撒网%",),
        )
        rows = cur.fetchall()
        cur.close()

    if not rows:
        print("未找到含「广撒网」的策略")
        return

    # 按 (market, indicator) 分组
    groups = defaultdict(list)
    for row in rows:
        rid = row["id"] if isinstance(row, dict) else row[0]
        name = (row["strategy_name"] if isinstance(row, dict) else row[1]) or ""
        sym = (row["symbol"] or row.get("symbol") or "").strip()
        market = (row["market_category"] if isinstance(row, dict) else row[3]) or ""
        tc = row["trading_config"] if isinstance(row, dict) else row[4]
        parsed = _parse_widenet_name(name)
        if parsed[0] is None:
            continue
        mkt_from_name, sym_from_name, ind = parsed
        key = (mkt_from_name, ind)
        risk = _get_risk_params(tc)
        groups[key].append({
            "id": rid,
            "name": name,
            "symbol": sym or sym_from_name,
            "market": market,
            "indicator": ind,
            "risk": risk,
        })

    print("=" * 80)
    print("广撒网策略分析：相同 Indicator 用于不同股票，检查 SL/TP 是否一致")
    print("=" * 80)

    for (market, indicator), strategies in sorted(groups.items()):
        risk_vals = set()
        for s in strategies:
            r = s["risk"]
            sl = r.get("stop_loss_pct")
            tp = r.get("take_profit_pct")
            trail = r.get("trailing_enabled")
            # 归一化便于比较（None/0 统一）
            sl_val = float(sl) if sl is not None else 0.0
            tp_val = float(tp) if tp is not None else 0.0
            risk_vals.add((sl_val, tp_val, trail))

        consistent = len(risk_vals) <= 1
        symbol_list = [s["symbol"] for s in strategies]
        sl_tp_sample = strategies[0]["risk"]

        print(f"\n【{market}】{indicator}")
        print(f"  策略数: {len(strategies)}")
        print(f"  标的: {', '.join(sorted(symbol_list))}")
        print(f"  SL/TP 一致: {'是' if consistent else '否'}")
        print(f"  stop_loss_pct: {sl_tp_sample.get('stop_loss_pct')}")
        print(f"  take_profit_pct: {sl_tp_sample.get('take_profit_pct')}")
        print(f"  trailing_enabled: {sl_tp_sample.get('trailing_enabled')}")

        if not consistent:
            print("  各策略 SL/TP 差异:")
            seen = set()
            for s in strategies:
                r = s["risk"]
                k = (r.get("stop_loss_pct"), r.get("take_profit_pct"))
                if k not in seen:
                    seen.add(k)
                    print(f"    - id={s['id']} {s['symbol']}: sl={r.get('stop_loss_pct')} tp={r.get('take_profit_pct')}")

        if consistent and len(strategies) > 1:
            print("  → 可考虑归为「截面策略」组（同一 Indicator + 统一 SL/TP）")


if __name__ == "__main__":
    main()
