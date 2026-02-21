"""
Multi-Strategy Dynamic Combination API routes.

提供组合总览、权重查询/修改、regime 状态、持仓聚合、
熔断器状态、配置查看、regime 切换历史等接口。
"""

from flask import Blueprint, request, jsonify, g
from datetime import datetime

from app.utils.logger import get_logger
from app.utils.auth import login_required

logger = get_logger(__name__)

multi_strategy_bp = Blueprint("multi_strategy", __name__)


# ── helpers ──────────────────────────────────────────────────────────────

def _get_allocator():
    from app.services.portfolio_allocator import get_portfolio_allocator
    return get_portfolio_allocator()


def _get_breaker():
    from app.services.circuit_breaker import get_circuit_breaker
    return get_circuit_breaker()


def _get_config():
    from app.tasks.regime_switch import _load_config
    return _load_config()


def _is_enabled(config=None):
    cfg = config or _get_config()
    return cfg.get("multi_strategy", {}).get("enabled", False)


# ── Regime history (DB persistence) ──────────────────────────────────────

def _record_regime_event(event: dict) -> None:
    """将 regime 切换事件写入 qd_regime_history 表。"""
    try:
        from app.utils.db import get_db_connection
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute("""
                INSERT INTO qd_regime_history
                    (from_regime, to_regime, vix, dxy, fear_greed,
                     weights_before, weights_after,
                     strategies_started, strategies_stopped, strategies_weight_changed,
                     trigger_source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                event.get("from_regime"),
                event.get("to_regime"),
                event.get("vix"),
                event.get("dxy"),
                event.get("fear_greed"),
                _to_json(event.get("weights_before")),
                _to_json(event.get("weights_after")),
                event.get("strategies_started", []),
                event.get("strategies_stopped", []),
                event.get("strategies_weight_changed", []),
                event.get("trigger_source", "auto"),
            ))
            db.commit()
            cur.close()
    except Exception as e:
        logger.error("[multi_strategy] failed to record regime event: %s", e)


def _fetch_regime_history(limit: int = 50, offset: int = 0) -> list:
    """从 qd_regime_history 表查询历史记录。"""
    try:
        from app.utils.db import get_db_connection
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute("""
                SELECT id, from_regime, to_regime, vix, dxy, fear_greed,
                       weights_before, weights_after,
                       strategies_started, strategies_stopped, strategies_weight_changed,
                       trigger_source, created_at
                FROM qd_regime_history
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            rows = cur.fetchall()
            cur.close()
            return [dict(r) for r in rows] if rows else []
    except Exception as e:
        logger.error("[multi_strategy] failed to fetch regime history: %s", e)
        return []


def _to_json(obj):
    if obj is None:
        return None
    import json
    return json.dumps(obj, ensure_ascii=False) if isinstance(obj, dict) else str(obj)


# ── API routes ───────────────────────────────────────────────────────────

@multi_strategy_bp.route("/summary", methods=["GET"])
@login_required
def get_summary():
    """组合总览：regime、权重、各品种分配与持仓。"""
    try:
        config = _get_config()
        if not _is_enabled(config):
            return jsonify({"code": 1, "msg": "multi-strategy not enabled", "data": None})

        allocator = _get_allocator()
        breaker = _get_breaker()

        from app.tasks.regime_switch import _fetch_macro_snapshot
        macro = _fetch_macro_snapshot()

        summary = allocator.get_portfolio_summary()
        cb_status = breaker.get_status(config)

        regime_per_symbol = allocator.regime_per_symbol
        weights_per_symbol = allocator.effective_weights_per_symbol
        use_per_symbol = bool(regime_per_symbol)

        data = {
            "regime": allocator.current_regime,
            "regime_per_symbol": regime_per_symbol if use_per_symbol else None,
            "weights_per_symbol": weights_per_symbol if use_per_symbol else None,
            "macro": macro,
            "weights": {
                "target": allocator.target_weights,
                "effective": allocator.effective_weights,
            },
            "circuit_breaker": cb_status,
            "allocation": summary.get("allocation", {}),
            "positions": summary.get("positions", {}),
            "total_equity": summary.get("total_equity", 0),
            "total_unrealized_pnl": summary.get("total_unrealized_pnl", 0),
        }
        return jsonify({"code": 1, "msg": "success", "data": data})
    except Exception as e:
        logger.exception("[multi_strategy] summary error: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@multi_strategy_bp.route("/weights", methods=["GET"])
@login_required
def get_weights():
    """当前各 style 的目标权重与生效权重。"""
    try:
        allocator = _get_allocator()
        data = {
            "target": allocator.target_weights,
            "effective": allocator.effective_weights,
            "regime": allocator.current_regime,
        }
        return jsonify({"code": 1, "msg": "success", "data": data})
    except Exception as e:
        logger.exception("[multi_strategy] weights error: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@multi_strategy_bp.route("/weights", methods=["PUT"])
@login_required
def put_weights():
    """手动覆盖权重（临时干预）。"""
    try:
        body = request.get_json(force=True, silent=True) or {}
        weights = body.get("weights")
        if not isinstance(weights, dict):
            return jsonify({"code": 0, "msg": "weights dict required"}), 400

        allocator = _get_allocator()
        from app.services.portfolio_allocator import _normalize_weights
        normalized = _normalize_weights({k: float(v) for k, v in weights.items()})
        allocator._effective_weights = normalized
        allocator._target_weights = normalized

        return jsonify({"code": 1, "msg": "weights updated", "data": normalized})
    except Exception as e:
        logger.exception("[multi_strategy] put weights error: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@multi_strategy_bp.route("/regime", methods=["GET"])
@login_required
def get_regime():
    """当前 regime 状态。"""
    try:
        allocator = _get_allocator()
        from app.tasks.regime_switch import _fetch_macro_snapshot
        macro = _fetch_macro_snapshot()
        data = {
            "regime": allocator.current_regime,
            "vix": macro["vix"],
            "vhsi": macro.get("vhsi", macro["vix"]),
            "dxy": macro["dxy"],
            "fear_greed": macro["fear_greed"],
        }
        return jsonify({"code": 1, "msg": "success", "data": data})
    except Exception as e:
        logger.exception("[multi_strategy] regime error: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@multi_strategy_bp.route("/allocation", methods=["GET"])
@login_required
def get_allocation():
    """每个策略的分配资金明细。"""
    try:
        allocator = _get_allocator()
        data = {
            "allocation": allocator.strategy_allocation,
            "frozen": allocator.frozen_strategies,
        }
        return jsonify({"code": 1, "msg": "success", "data": data})
    except Exception as e:
        logger.exception("[multi_strategy] allocation error: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@multi_strategy_bp.route("/positions", methods=["GET"])
@login_required
def get_positions():
    """组合持仓视图。可选 ?symbol=XAUUSD 过滤。"""
    try:
        allocator = _get_allocator()
        positions = allocator.get_combined_positions()
        symbol = request.args.get("symbol")
        if symbol:
            positions = {k: v for k, v in positions.items() if k == symbol.upper()}
        return jsonify({"code": 1, "msg": "success", "data": positions})
    except Exception as e:
        logger.exception("[multi_strategy] positions error: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@multi_strategy_bp.route("/circuit-breaker", methods=["GET"])
@login_required
def get_circuit_breaker_status():
    """熔断器状态。"""
    try:
        config = _get_config()
        breaker = _get_breaker()
        return jsonify({"code": 1, "msg": "success", "data": breaker.get_status(config)})
    except Exception as e:
        logger.exception("[multi_strategy] circuit-breaker error: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@multi_strategy_bp.route("/circuit-breaker/reset", methods=["POST"])
@login_required
def reset_circuit_breaker():
    """手动解除熔断。"""
    try:
        breaker = _get_breaker()
        breaker.reset()
        return jsonify({"code": 1, "msg": "circuit breaker reset"})
    except Exception as e:
        logger.exception("[multi_strategy] circuit-breaker reset error: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@multi_strategy_bp.route("/config", methods=["GET"])
@login_required
def get_config():
    """返回当前多策略配置（脱敏）。仅从 DB 读取。"""
    try:
        config = _get_config()
        safe = {
            "symbol_strategies": config.get("symbol_strategies", {}),
            "multi_strategy": config.get("multi_strategy", {}),
            "regime_rules": config.get("regime_rules", {}),
        }
        return jsonify({"code": 1, "msg": "success", "data": safe})
    except Exception as e:
        logger.exception("[multi_strategy] config error: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@multi_strategy_bp.route("/config", methods=["PUT"])
@login_required
def put_config():
    """保存 regime 配置到 DB。"""
    try:
        body = request.get_json(force=True, silent=True) or {}
        symbol_strategies = body.get("symbol_strategies")
        regime_to_weights = body.get("regime_to_weights")
        regime_rules = body.get("regime_rules")
        multi_strategy = body.get("multi_strategy")

        if symbol_strategies is None or regime_to_weights is None:
            return jsonify({"code": 0, "msg": "symbol_strategies and regime_to_weights required"}), 400

        from app.services.regime_config_service import save_regime_config
        from app.tasks.regime_switch import reload_config
        ok = save_regime_config(
            symbol_strategies=symbol_strategies,
            regime_to_weights=regime_to_weights,
            regime_rules=regime_rules,
            multi_strategy=multi_strategy,
        )
        if not ok:
            logger.warning("[multi_strategy] put_config: save_regime_config failed")
            return jsonify({"code": 0, "msg": "save failed", "data": None}), 500
        reload_config()
        return jsonify({"code": 1, "msg": "saved", "data": None})
    except Exception as e:
        logger.exception("[multi_strategy] put config error: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@multi_strategy_bp.route("/config/parse-yaml", methods=["POST"])
@login_required
def parse_yaml_config():
    """解析上传的 YAML 文件，返回结构化数据，不写 DB。"""
    try:
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"code": 0, "msg": "file required"}), 400
        import yaml
        content = f.stream.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        data = yaml.safe_load(content) or {}
        result = {
            "symbol_strategies": data.get("symbol_strategies", {}),
            "regime_to_weights": (
                data.get("multi_strategy", {}).get("regime_to_weights")
                or data.get("regime_to_weights", {})
            ),
            "regime_rules": data.get("regime_rules", {}),
            "multi_strategy": data.get("multi_strategy", {}),
        }
        return jsonify({"code": 1, "msg": "success", "data": result})
    except yaml.YAMLError as e:
        logger.warning("[multi_strategy] parse-yaml error: %s", e)
        return jsonify({"code": 0, "msg": f"YAML parse error: {e}", "data": None}), 400
    except Exception as e:
        logger.exception("[multi_strategy] parse-yaml error: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@multi_strategy_bp.route("/history", methods=["GET"])
@login_required
def get_history():
    """Regime 切换历史记录。?limit=50&offset=0"""
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = int(request.args.get("offset", 0))
        events = _fetch_regime_history(limit, offset)
        return jsonify({"code": 1, "msg": "success", "data": {"events": events}})
    except Exception as e:
        logger.exception("[multi_strategy] history error: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500
