"""
Regime 配置服务 — 从 DB 读写 regime 配置。

用于前端配置页与 regime_switch 运行时读取。
YAML 仅用于创建时的导入，运行与 YAML 无关。
"""

from typing import Any, Dict, Optional

from app.utils.logger import get_logger
from app.utils.db import get_db_connection

logger = get_logger(__name__)


def get_regime_config_for_runtime(user_id: Optional[int] = None) -> Dict[str, Any]:
    """供 regime_switch 运行时读取的完整配置（YAML 结构兼容）。"""
    row = get_regime_config(user_id)
    if not row:
        return {}
    ms = dict(row.get("multi_strategy") or {})
    if row.get("regime_to_weights"):
        ms["regime_to_weights"] = row["regime_to_weights"]
    if "enabled" not in ms and row.get("regime_to_weights"):
        ms["enabled"] = True
    return {
        "symbol_strategies": row.get("symbol_strategies") or {},
        "regime_rules": row.get("regime_rules") or {},
        "regime_to_style": row.get("regime_to_style") or {},
        "multi_strategy": ms,
    }


def get_regime_config(user_id: Optional[int] = None) -> Dict[str, Any]:
    """从 DB 读取 regime 配置。user_id 为 None 时取最新一条。"""
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            if user_id is not None:
                cur.execute("""
                    SELECT symbol_strategies, regime_to_weights, regime_rules,
                           regime_to_style, multi_strategy, updated_at
                    FROM qd_regime_config
                    WHERE user_id = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                """, (user_id,))
            else:
                cur.execute("""
                    SELECT symbol_strategies, regime_to_weights, regime_rules,
                           regime_to_style, multi_strategy, updated_at
                    FROM qd_regime_config
                    ORDER BY (CASE WHEN symbol_strategies = '{}'::jsonb THEN 1 ELSE 0 END),
                             updated_at DESC
                    LIMIT 1
                """)
            row = cur.fetchone()
            cur.close()

        if not row:
            return {}

        def _parse_jsonb(val):
            if val is None:
                return {}
            if isinstance(val, dict):
                return val
            import json
            return json.loads(val) if isinstance(val, str) else {}

        result = {
            "symbol_strategies": _parse_jsonb(row.get("symbol_strategies")),
            "regime_to_weights": _parse_jsonb(row.get("regime_to_weights")),
            "regime_rules": _parse_jsonb(row.get("regime_rules")),
            "regime_to_style": _parse_jsonb(row.get("regime_to_style")),
            "multi_strategy": _parse_jsonb(row.get("multi_strategy")),
            "user_id": user_id,
        }
        return result
    except Exception as e:
        logger.error("[regime_config] get_regime_config failed: %s", e)
        return {}


def _ensure_multi_strategy_structure(ms: Dict) -> Dict:
    """确保 multi_strategy 包含 regime_to_weights 等。"""
    if not ms:
        ms = {}
    if "regime_to_weights" not in ms or not ms["regime_to_weights"]:
        ms = dict(ms)
        ms["regime_to_weights"] = {
            "panic": {"conservative": 0.8, "balanced": 0.2, "aggressive": 0.0},
            "high_vol": {"conservative": 0.5, "balanced": 0.4, "aggressive": 0.1},
            "normal": {"conservative": 0.2, "balanced": 0.6, "aggressive": 0.2},
            "low_vol": {"conservative": 0.1, "balanced": 0.3, "aggressive": 0.6},
        }
    return ms


def save_regime_config(
    user_id: Optional[int],
    symbol_strategies: Dict[str, Any],
    regime_to_weights: Dict[str, Any],
    regime_rules: Optional[Dict] = None,
    regime_to_style: Optional[Dict] = None,
    multi_strategy: Optional[Dict] = None,
) -> bool:
    """保存 regime 配置到 DB。"""
    import json
    try:
        regime_rules = regime_rules or {}
        regime_to_style = regime_to_style or {}
        multi_strategy = multi_strategy or {}
        multi_strategy = _ensure_multi_strategy_structure(multi_strategy)
        if regime_to_weights:
            multi_strategy["regime_to_weights"] = regime_to_weights

        ss_json = json.dumps(symbol_strategies, ensure_ascii=False)
        rtw_json = json.dumps(regime_to_weights, ensure_ascii=False)
        rr_json = json.dumps(regime_rules, ensure_ascii=False)
        rts_json = json.dumps(regime_to_style, ensure_ascii=False)
        ms_json = json.dumps(multi_strategy, ensure_ascii=False)

        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute("""
                SELECT id FROM qd_regime_config WHERE user_id IS NOT DISTINCT FROM %s
                ORDER BY updated_at DESC LIMIT 1
            """, (user_id,))
            existing = cur.fetchone()
            if existing:
                cur.execute("""
                    UPDATE qd_regime_config
                    SET symbol_strategies = %s::jsonb, regime_to_weights = %s::jsonb,
                        regime_rules = %s::jsonb, regime_to_style = %s::jsonb,
                        multi_strategy = %s::jsonb, updated_at = NOW()
                    WHERE id = %s
                """, (ss_json, rtw_json, rr_json, rts_json, ms_json, existing["id"]))
            else:
                cur.execute("""
                    INSERT INTO qd_regime_config
                        (user_id, symbol_strategies, regime_to_weights, regime_rules, regime_to_style, multi_strategy)
                    VALUES (%s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                """, (user_id, ss_json, rtw_json, rr_json, rts_json, ms_json))
            db.commit()
            cur.close()
        return True
    except Exception as e:
        logger.error("[regime_config] save_regime_config failed: %s", e)
        return False
