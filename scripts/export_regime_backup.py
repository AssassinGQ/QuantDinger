#!/usr/bin/env python3
"""
从数据库导出 regime 配置与策略，更新 ai-coder deploy-backup 文件。

用法:
  # 方式1: 在 QuantDinger 容器内（推荐，DB 可访问）
  docker cp scripts/export_regime_backup.py quantdinger-backend:/tmp/
  docker exec quantdinger-backend python3 /tmp/export_regime_backup.py
  docker cp quantdinger-backend:/tmp/deploy-backup-export/. ./ai-coder/.../deploy-backup/

  # 方式2: 宿主机直连 DB（需 postgres 监听 localhost:5432）
  DATABASE_URL=postgresql://quantdinger:quantdinger123@localhost:5432/quantdinger \
    PYTHONPATH=./backend_api_python python3 scripts/export_regime_backup.py

  # 方式3: API 模式（backend 已运行）
  API_BASE=http://localhost:5000 API_AUTH=quantdinger:123456 \
    python3 scripts/export_regime_backup.py --api
"""
import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Set

for p in ["/app", os.path.join(os.path.dirname(__file__), "..", "backend_api_python")]:
    if os.path.exists(p):
        sys.path.insert(0, p)
        break

USE_API = "--api" in sys.argv or os.getenv("EXPORT_VIA_API") == "1"

if not USE_API:
    try:
        from app.utils.db import get_db_connection
    except ImportError as e:
        print(f"[ERROR] 无法导入 app.utils.db: {e}")
        print("请确保在 QuantDinger 容器内运行，或使用 --api 模式")
        sys.exit(1)


def _json_serial(obj):
    if isinstance(obj, datetime):
        return obj.strftime("%a, %d %b %Y %H:%M:%S GMT")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _parse_jsonb(val):
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val) if isinstance(val, str) else {}
    except Exception:
        return {}


def collect_regime_strategy_ids(symbol_strategies: Dict) -> Set[int]:
    ids = set()
    for sym, styles in (symbol_strategies or {}).items():
        for style, sids in (styles or {}).items():
            if isinstance(sids, list):
                for x in sids:
                    if isinstance(x, int):
                        ids.add(x)
                    elif isinstance(x, str) and x.isdigit():
                        ids.add(int(x))
    return ids


def fetch_regime_config() -> Dict[str, Any]:
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute("""
            SELECT symbol_strategies, regime_to_weights, regime_rules,
                   regime_to_style, multi_strategy
            FROM qd_regime_config
            ORDER BY updated_at DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        cur.close()

    if not row:
        return {}

    ss = _parse_jsonb(row.get("symbol_strategies"))
    rtw = _parse_jsonb(row.get("regime_to_weights"))
    rr = _parse_jsonb(row.get("regime_rules"))
    rts = _parse_jsonb(row.get("regime_to_style"))
    ms = _parse_jsonb(row.get("multi_strategy"))

    if rtw and ms.get("regime_to_weights") != rtw:
        ms = dict(ms) if ms else {}
        ms["regime_to_weights"] = rtw
    if "enabled" not in ms and rtw:
        ms = dict(ms) if ms else {}
        ms["enabled"] = True

    return {
        "regime_rules": rr,
        "regime_to_style": rts,
        "multi_strategy": ms,
        "symbol_strategies": ss,
        "user_id": None,
        "interval_minutes": 15,
    }


def fetch_strategies(strategy_ids: Set[int]) -> List[Dict]:
    if not strategy_ids:
        return []

    placeholders = ",".join(["%s"] * len(strategy_ids))
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(f"""
            SELECT id, strategy_name, strategy_type, market_category, symbol, timeframe,
                   initial_capital, leverage, status, execution_mode,
                   indicator_config, trading_config, notification_config,
                   exchange_config, ai_model_config,
                   strategy_group_id, group_base_name, display_group,
                   decide_interval, created_at, updated_at
            FROM qd_strategies_trading
            WHERE id IN ({placeholders})
        """, tuple(strategy_ids))
        rows = cur.fetchall()
        cur.close()

    result = []
    for r in rows:
        row = dict(r) if hasattr(r, "keys") else {}
        if not row:
            continue
        for field in ("indicator_config", "trading_config", "notification_config",
                     "exchange_config", "ai_model_config"):
            row[field] = _parse_jsonb(row.get(field))
        for dt in ("created_at", "updated_at"):
            if row.get(dt):
                row[dt] = row[dt].strftime("%a, %d %b %Y %H:%M:%S GMT") if hasattr(row[dt], "strftime") else str(row[dt])
        row["initial_capital"] = str(row.get("initial_capital", 10000))
        result.append(row)

    result.sort(key=lambda x: -x.get("id", 0))
    return result


def collect_indicator_ids_from_strategies(strategies: List[Dict]) -> Set[int]:
    ids = set()
    for s in strategies:
        ind_cfg = s.get("indicator_config") or {}
        iid = ind_cfg.get("indicator_id")
        if iid:
            ids.add(int(iid))
    return ids


def fetch_indicators_db(indicator_ids: Set[int]) -> List[Dict]:
    if not indicator_ids:
        return []
    placeholders = ",".join(["%s"] * len(indicator_ids))
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(f"""
            SELECT id, user_id, is_buy, end_time, name, code, description,
                   publish_to_community, pricing_type, price, is_encrypted, preview_image,
                   createtime, updatetime, indicator_group
            FROM qd_indicator_codes
            WHERE id IN ({placeholders})
        """, tuple(indicator_ids))
        rows = cur.fetchall()
        cur.close()

    result = []
    for r in rows:
        row = dict(r) if hasattr(r, "keys") else {}
        if not row:
            continue
        row["price"] = str(row.get("price", 0))
        row["indicator_group"] = row.get("indicator_group") or "ungrouped"
        result.append(row)
    result.sort(key=lambda x: -x.get("id", 0))
    return result


def build_regime_yaml(cfg: Dict[str, Any]) -> str:
    try:
        import yaml
        return yaml.dump(cfg, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        return json.dumps(cfg, ensure_ascii=False, indent=2)


def fetch_via_api() -> tuple:
    """通过 HTTP API 获取 regime 配置和策略（需 backend 运行且登录）"""
    import requests
    api_base = os.getenv("API_BASE", "http://localhost:5000").rstrip("/")
    auth = os.getenv("API_AUTH", "quantdinger:123456")
    user, pw = auth.split(":") if ":" in auth else (auth, "")

    session = requests.Session()
    login = session.post(f"{api_base}/api/auth/login", json={"username": user, "password": pw}, timeout=10)
    if login.status_code != 200 or not login.json().get("data", {}).get("token"):
        raise RuntimeError("API 登录失败")
    token = login.json()["data"]["token"]
    session.headers["Authorization"] = f"Bearer {token}"

    cfg_resp = session.get(f"{api_base}/api/multi-strategy/config", timeout=10)
    if cfg_resp.status_code != 200 or cfg_resp.json().get("code") != 1:
        raise RuntimeError("获取 regime 配置失败")
    data = cfg_resp.json().get("data") or {}
    ss = data.get("symbol_strategies", {})
    ids = collect_regime_strategy_ids(ss)

    strat_resp = session.get(f"{api_base}/api/strategies", timeout=15)
    if strat_resp.status_code != 200 or strat_resp.json().get("code") != 1:
        raise RuntimeError("获取策略列表失败")
    all_strats = strat_resp.json().get("data", {}).get("strategies", [])
    strategies = [s for s in all_strats if s.get("id") in ids]
    strategies.sort(key=lambda x: -x.get("id", 0))

    cfg = {
        "regime_rules": data.get("regime_rules", {}),
        "regime_to_style": {},
        "multi_strategy": data.get("multi_strategy", {}),
        "symbol_strategies": ss,
        "user_id": None,
        "interval_minutes": 15,
    }
    rt_style = cfg["multi_strategy"].get("regime_to_style")
    if rt_style:
        cfg["regime_to_style"] = rt_style
    else:
        cfg["regime_to_style"] = {
            "panic": ["conservative"], "high_vol": ["conservative", "balanced"],
            "normal": ["balanced"], "low_vol": ["balanced", "aggressive"],
        }

    ind_ids = collect_indicator_ids_from_strategies(strategies)
    ind_resp = session.get(f"{api_base}/api/indicator/getIndicators", timeout=15)
    indicators = []
    if ind_resp.status_code == 200 and ind_resp.json().get("code") == 1:
        all_inds = ind_resp.json().get("data") or []
        indicators = [i for i in all_inds if i.get("id") in ind_ids]
        indicators.sort(key=lambda x: -x.get("id", 0))
    return cfg, strategies, indicators


def main():
    parser = argparse.ArgumentParser(description="从数据库导出 regime 备份")
    default_out = os.path.join(
        os.path.dirname(__file__), "..", "..", "ai-coder", "cursor",
        "20260217-StrategyOptimizer", "top-max", "deploy-backup"
    )
    if not os.path.exists(default_out):
        default_out = "/tmp/deploy-backup-export"
    parser.add_argument("--output", "-o", default=default_out, help="输出目录")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    parser.add_argument("--api", action="store_true", help="通过 HTTP API 获取（需 backend 运行）")
    args = parser.parse_args()

    indicators: List[Dict] = []
    if args.api or USE_API:
        print("正在通过 API 获取 regime 配置...")
        try:
            cfg, strategies, indicators = fetch_via_api()
        except Exception as e:
            print(f"[ERROR] API 模式失败: {e}")
            sys.exit(1)
        print(f"  获取 {len(strategies)} 条策略, {len(indicators)} 个指标")
    else:
        print("正在从数据库读取 regime 配置...")
        cfg = fetch_regime_config()
        if not cfg.get("symbol_strategies"):
            print("[WARN] qd_regime_config 为空或 symbol_strategies 为空")
            cfg = cfg or {}
            cfg.setdefault("regime_rules", {})
            cfg.setdefault("regime_to_style", {})
            cfg.setdefault("multi_strategy", {})
            cfg.setdefault("symbol_strategies", {})

        ids = collect_regime_strategy_ids(cfg.get("symbol_strategies"))
        print(f"  找到 {len(ids)} 个 regime 策略 ID")

        print("正在读取策略详情...")
        strategies = fetch_strategies(ids)
        print(f"  读取 {len(strategies)} 条策略")

        ind_ids = collect_indicator_ids_from_strategies(strategies)
        print("正在读取指标详情...")
        indicators = fetch_indicators_db(ind_ids)
        print(f"  读取 {len(indicators)} 个指标")

    yaml_path = os.path.join(args.output, "_backup_regime_switch.yaml")
    json_path = os.path.join(args.output, "_backup_strategies.json")

    ind_path = os.path.join(args.output, "_backup_indicators.json")
    if args.dry_run:
        print(f"\n[DRY-RUN] 将写入:")
        print(f"  {yaml_path}")
        print(f"  {json_path}")
        print(f"  {ind_path}")
        print(f"  symbol_strategies keys: {list(cfg.get('symbol_strategies', {}).keys())}")
        return

    os.makedirs(args.output, exist_ok=True)

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(build_regime_yaml(cfg))
    print(f"  已写入: {yaml_path}")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(strategies, f, ensure_ascii=False, indent=2, default=_json_serial)
    print(f"  已写入: {json_path}")

    with open(ind_path, "w", encoding="utf-8") as f:
        json.dump(indicators, f, ensure_ascii=False, indent=2, default=_json_serial)
    print(f"  已写入: {ind_path}")

    print("完成")


if __name__ == "__main__":
    main()
