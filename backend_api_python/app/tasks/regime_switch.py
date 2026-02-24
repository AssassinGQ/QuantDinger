"""
regime_switch 插件 — 监控 VIX/Fear&Greed → 自动启停策略。

定时由 APScheduler 调用 run()：
  1. 拉取实时宏观快照（MacroDataService）
  2. 根据 VIX 阈值计算当前 regime
  3. 对比配置中「regime→style→strategy_id」与实际运行状态
  4. 调 StrategyService + TradingExecutor 做启停（两层配合）

P1 扩展：当 multi_strategy.enabled=true 时，通过 PortfolioAllocator
进行加权分配而非二元启停。
"""

import os
import threading
from typing import Any, Dict, List, Optional, Set

from app.utils.logger import get_logger

logger = get_logger(__name__)

JOB_ID = "task_regime_switch"
INTERVAL_MINUTES = 15
# 默认启用；YAML 中 symbol_strategies 为空则 run() 不操作任何策略。需关闭时设 ENABLE_REGIME_SWITCH=false
ENABLED = os.getenv("ENABLE_REGIME_SWITCH", "true").lower() == "true"

_run_lock = threading.Lock()

# ── 配置加载 ────────────────────────────────────────────────────────────

def _load_config() -> Dict[str, Any]:
    """加载配置：regime 策略全局共用，user_id=None。"""
    try:
        from app.services.regime_config_service import get_regime_config_for_runtime
        cfg = get_regime_config_for_runtime() or {}
        logger.debug("[regime_switch] _load_config: enabled=%s",
                     cfg.get("multi_strategy", {}).get("enabled"))
        return cfg
    except Exception as e:
        logger.debug("[regime_switch] DB config not available: %s", e)
        return {}


def reload_config() -> Dict[str, Any]:
    """强制重载配置（保留接口兼容，现已无缓存故直接调用 _load_config）。"""
    return _load_config()


# ── Regime 计算 ─────────────────────────────────────────────────────────

REGIME_PANIC = "panic"
REGIME_HIGH_VOL = "high_vol"
REGIME_LOW_VOL = "low_vol"
REGIME_NORMAL = "normal"


def _resolve_primary_indicator(symbol_strategies: Dict[str, Any], config: Optional[Dict]) -> str:
    """根据配置与品种解析主指标：支持 indicator_per_market 实现港股自动用 VHSI。"""
    cfg = (config or _load_config()).get("regime_rules", {})
    primary = (cfg.get("primary_indicator") or "vix").strip().lower()
    if primary != "auto":
        return primary
    indicator_per_market = cfg.get("indicator_per_market") or {}
    if _has_hshare_symbols(symbol_strategies) and indicator_per_market.get("HShare") == "vhsi":
        return "vhsi"
    if _has_ashare_symbols(symbol_strategies) and indicator_per_market.get("AShare") == "civix":
        return "civix"
    return indicator_per_market.get("default", "vix")


def compute_regime(vix: float, fear_greed: Optional[float] = None,
                   config: Optional[Dict] = None, vhsi: Optional[float] = None,
                   macro: Optional[Dict[str, float]] = None,
                   primary_override: Optional[str] = None) -> str:
    """根据配置的主指标（VIX / VHSI / Fear&Greed / 自定义 Python）计算当前 regime。"""
    cfg = (config or _load_config()).get("regime_rules", {})
    primary = (primary_override or cfg.get("primary_indicator") or "vix").strip().lower()

    if primary == "custom":
        return _compute_regime_custom(vix, fear_greed, config)

    if primary == "vhsi":
        vol_val = vhsi if vhsi is not None else (macro or {}).get("vhsi", vix)
        vhsi_panic = cfg.get("vhsi_panic", cfg.get("vix_panic", 30))
        vhsi_high_vol = cfg.get("vhsi_high_vol", cfg.get("vix_high_vol", 25))
        vhsi_low_vol = cfg.get("vhsi_low_vol", cfg.get("vix_low_vol", 15))
        if vol_val > vhsi_panic:
            return REGIME_PANIC
        if vol_val > vhsi_high_vol:
            return REGIME_HIGH_VOL
        if vol_val < vhsi_low_vol:
            return REGIME_LOW_VOL
        return REGIME_NORMAL

    if primary == "civix":
        vol_val = (macro or {}).get("civix", vix)
        civix_panic = cfg.get("civix_panic", cfg.get("vix_panic", 30))
        civix_high_vol = cfg.get("civix_high_vol", cfg.get("vix_high_vol", 25))
        civix_low_vol = cfg.get("civix_low_vol", cfg.get("vix_low_vol", 15))
        if vol_val > civix_panic:
            return REGIME_PANIC
        if vol_val > civix_high_vol:
            return REGIME_HIGH_VOL
        if vol_val < civix_low_vol:
            return REGIME_LOW_VOL
        return REGIME_NORMAL

    if primary == "fear_greed":
        # Fear&Greed: 低=恐慌, 高=贪婪。值域 0-100
        fg = fear_greed if fear_greed is not None else 50.0
        fg_extreme_fear = cfg.get("fg_extreme_fear", 20)
        fg_high_fear = cfg.get("fg_high_fear", 35)
        fg_low_greed = cfg.get("fg_low_greed", 65)
        if fg < fg_extreme_fear:
            return REGIME_PANIC
        if fg < fg_high_fear:
            return REGIME_HIGH_VOL
        if fg > fg_low_greed:
            return REGIME_LOW_VOL
        return REGIME_NORMAL
    else:
        # 默认 VIX：高=恐慌, 低=低波动
        vix_panic = cfg.get("vix_panic", 30)
        vix_high_vol = cfg.get("vix_high_vol", 25)
        vix_low_vol = cfg.get("vix_low_vol", 15)
        if vix > vix_panic:
            return REGIME_PANIC
        if vix > vix_high_vol:
            return REGIME_HIGH_VOL
        if vix < vix_low_vol:
            return REGIME_LOW_VOL
        return REGIME_NORMAL


def _compute_regime_custom(
    vix: float, fear_greed: Optional[float], config: Optional[Dict]
) -> str:
    """执行自定义 Python 代码计算 regime。代码可定义 regime（直接）或 regime_score（按阈值映射）。"""
    cfg = (config or _load_config()).get("regime_rules", {})
    custom_code = (cfg.get("custom_code") or "").strip()
    if not custom_code:
        logger.warning("[regime_switch] custom indicator but no custom_code, fallback to normal")
        return REGIME_NORMAL

    from app.services.macro_data_service import MacroDataService
    snapshot = MacroDataService._get_realtime_snapshot()
    macro = {
        "vix": float(snapshot.get("vix", 18.0)) if snapshot else vix,
        "vhsi": float(snapshot.get("vhsi", 22.0)) if snapshot else vix,
        "civix": float(snapshot.get("civix", 18.0)) if snapshot else vix,
        "dxy": float(snapshot.get("dxy", 100.0)) if snapshot else 100.0,
        "fear_greed": float(snapshot.get("fear_greed", 50.0)) if snapshot else (fear_greed or 50.0),
    }

    from app.utils.safe_exec import validate_code_safety, safe_exec_code
    is_safe, err = validate_code_safety(custom_code)
    if not is_safe:
        logger.error("[regime_switch] custom code unsafe: %s", err)
        return REGIME_NORMAL

    exec_env = {
        "macro": macro,
        "vix": macro["vix"],
        "vhsi": macro["vhsi"],
        "civix": macro["civix"],
        "dxy": macro["dxy"],
        "fear_greed": macro["fear_greed"],
        "regime": None,
        "regime_score": None,
        "math": __import__("math"),
    }
    result = safe_exec_code(code=custom_code, exec_globals=exec_env, timeout=5)
    if not result.get("success"):
        logger.error("[regime_switch] custom code exec failed: %s", result.get("error"))
        return REGIME_NORMAL

    regime = exec_env.get("regime")
    if regime in (REGIME_PANIC, REGIME_HIGH_VOL, REGIME_NORMAL, REGIME_LOW_VOL):
        return regime

    score = exec_env.get("regime_score")
    if score is not None:
        try:
            s = float(score)
        except (TypeError, ValueError):
            return REGIME_NORMAL
        ext = cfg.get("custom_score_extreme_fear", 20)
        high = cfg.get("custom_score_high_fear", 35)
        low = cfg.get("custom_score_low_greed", 65)
        if s < ext:
            return REGIME_PANIC
        if s < high:
            return REGIME_HIGH_VOL
        if s > low:
            return REGIME_LOW_VOL
        return REGIME_NORMAL

    logger.warning("[regime_switch] custom code must define regime or regime_score")
    return REGIME_NORMAL


# ── 目标策略集合 ────────────────────────────────────────────────────────

def _get_symbol_strategies_from_db(user_id: Optional[int] = 1) -> Dict[str, Dict[str, List[int]]]:
    """从数据库策略的 trading_config.regime_style 与 symbol 构建 symbol_strategies 结构。
    仅包含 regime_style 为 conservative/balanced/aggressive 且 symbol 存在的策略。
    """
    from app.services.strategy import StrategyService
    service = StrategyService()
    strategies = service.list_strategies(user_id=user_id)
    result: Dict[str, Dict[str, List[int]]] = {}
    valid_styles = {"conservative", "balanced", "aggressive"}
    for s in strategies:
        tc = (s.get("trading_config") or {}) if isinstance(s.get("trading_config"), dict) else {}
        symbol = tc.get("symbol")
        style = (tc.get("regime_style") or "").strip().lower()
        if not symbol or style not in valid_styles:
            continue
        sid = s.get("id")
        if sid is None:
            continue
        if symbol not in result:
            result[symbol] = {}
        if style not in result[symbol]:
            result[symbol][style] = []
        result[symbol][style].append(int(sid))
    return result


def compute_target_strategy_ids(regime: str, config: Optional[Dict] = None,
                                symbol_strategies_override: Optional[Dict] = None,
                                regime_per_symbol: Optional[Dict[str, str]] = None) -> Set[int]:
    """根据 regime 和配置，计算应该运行的 strategy_id 集合（P0 二元模式）。
    当 regime_per_symbol 非空时，每个 symbol 使用其自身的 regime。"""
    cfg = config or _load_config()
    regime_to_style = cfg.get("regime_to_style", {})
    symbol_strategies = symbol_strategies_override if symbol_strategies_override is not None else cfg.get("symbol_strategies", {})

    target_ids: Set[int] = set()
    for symbol, style_map in (symbol_strategies or {}).items():
        if not isinstance(style_map, dict):
            continue
        sym_regime = (regime_per_symbol or {}).get(symbol) or regime
        active_styles = regime_to_style.get(sym_regime, ["balanced"])
        for style in active_styles:
            ids = style_map.get(style, [])
            if isinstance(ids, list):
                target_ids.update(int(i) for i in ids)

    return target_ids


# ── 获取宏观数据 ────────────────────────────────────────────────────────

def _fetch_macro_snapshot() -> Dict[str, float]:
    """拉取实时宏观快照（VIX / VHSI / CIVIX / DXY / Fear&Greed）。"""
    from app.services.macro_data_service import MacroDataService
    snapshot = MacroDataService._get_realtime_snapshot()
    if not snapshot:
        logger.warning("[regime_switch] macro snapshot empty, using defaults")
        return {"vix": 18.0, "vhsi": 22.0, "civix": 18.0, "dxy": 100.0, "fear_greed": 50.0}
    vix_def = float(snapshot.get("vix", 18.0))
    return {
        "vix": vix_def,
        "vhsi": float(snapshot.get("vhsi", snapshot.get("vix", 22.0))),
        "civix": float(snapshot.get("civix", vix_def)),
        "dxy": float(snapshot.get("dxy", 100.0)),
        "fear_greed": float(snapshot.get("fear_greed", 50.0)),
    }


def _has_hshare_symbols(symbol_strategies: Dict[str, Any]) -> bool:
    """检测 symbol_strategies 中是否包含港股标的。"""
    if not symbol_strategies:
        return False
    symbols = [str(k).replace(".HK", "").strip() for k in symbol_strategies.keys()]
    if not symbols:
        return False
    try:
        from app.utils.db import get_db_connection
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                "SELECT 1 FROM qd_market_symbols WHERE market = 'HShare' AND symbol = ANY(%s) LIMIT 1",
                (symbols,)
            )
            row = cur.fetchone()
            cur.close()
            return row is not None
    except Exception:
        return any(len(s) == 5 and s.isdigit() for s in symbols)


def _has_ashare_symbols(symbol_strategies: Dict[str, Any]) -> bool:
    """检测 symbol_strategies 中是否包含 A 股标的。"""
    if not symbol_strategies:
        return False
    symbols = [str(k).strip() for k in symbol_strategies.keys()]
    if not symbols:
        return False
    try:
        from app.utils.db import get_db_connection
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                "SELECT 1 FROM qd_market_symbols WHERE market = 'AShare' AND symbol = ANY(%s) LIMIT 1",
                (symbols,)
            )
            row = cur.fetchone()
            cur.close()
            return row is not None
    except Exception:
        return any(len(s) == 6 and s.isdigit() for s in symbols)


def _get_symbol_to_market(symbol_strategies: Dict[str, Any]) -> Dict[str, str]:
    """symbol → market 映射。用于多套 regime（港股 VHSI、美股 VIX 等）。"""
    if not symbol_strategies:
        return {}
    symbols = [str(k).replace(".HK", "").strip() for k in symbol_strategies.keys()]
    result: Dict[str, str] = {}
    try:
        from app.utils.db import get_db_connection
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                "SELECT symbol, market FROM qd_market_symbols WHERE symbol = ANY(%s)",
                (symbols,)
            )
            for row in cur.fetchall():
                sym = str(row.get("symbol", "")).strip()
                market = str(row.get("market", "")).strip() or "default"
                result[sym] = market
                if sym + ".HK" in symbol_strategies:
                    result[sym + ".HK"] = market
            cur.close()
    except Exception:
        pass
    for sym in symbol_strategies.keys():
        s = str(sym).replace(".HK", "").strip()
        if s not in result:
            result[s] = "HShare" if (len(s) == 5 and s.isdigit()) else "default"
    return result


def _use_per_market_regime(config: Optional[Dict]) -> bool:
    """是否启用 per-market 多套 regime。"""
    cfg = (config or _load_config()).get("regime_rules", {})
    indicator_per_market = cfg.get("indicator_per_market") or {}
    return bool(indicator_per_market) and cfg.get("primary_indicator", "vix").strip().lower() == "auto"


def compute_regime_per_symbol(
    symbol_strategies: Dict[str, Any],
    macro: Dict[str, float],
    config: Optional[Dict],
) -> Dict[str, str]:
    """为每个 symbol 计算 regime，支持港股 VHSI、美股 VIX 等 per-market 差异化。"""
    if not _use_per_market_regime(config):
        single_regime = compute_regime(
            macro["vix"], fear_greed=macro.get("fear_greed"),
            config=config, vhsi=macro.get("vhsi"), macro=macro,
            primary_override=_resolve_primary_indicator(symbol_strategies, config)
        )
        return {sym: single_regime for sym in symbol_strategies.keys()}

    symbol_to_market = _get_symbol_to_market(symbol_strategies)
    cfg = (config or _load_config()).get("regime_rules", {})
    indicator_per_market = cfg.get("indicator_per_market") or {}
    vix = macro["vix"]
    vhsi = macro.get("vhsi", vix)
    fg = macro.get("fear_greed", 50.0)

    result: Dict[str, str] = {}
    for sym in symbol_strategies.keys():
        s_plain = str(sym).replace(".HK", "").strip()
        market = symbol_to_market.get(s_plain) or symbol_to_market.get(sym) or "default"
        indicator = indicator_per_market.get(market) or indicator_per_market.get("default", "vix")
        primary = str(indicator).strip().lower() if indicator else "vix"
        regime = compute_regime(vix, fear_greed=fg, config=config, vhsi=vhsi, macro=macro, primary_override=primary)
        result[sym] = regime
    return result


# ── 获取当前运行中的策略 ID ──────────────────────────────────────────────

def _get_currently_running_ids() -> Set[int]:
    """从 TradingExecutor 获取实际运行中的策略 ID 集合。"""
    from app import get_trading_executor
    executor = get_trading_executor()
    with executor.lock:
        return set(executor.running_strategies.keys())


# ── 获取所有已配置的策略 ID ──────────────────────────────────────────────

def _get_all_managed_ids(config: Optional[Dict] = None,
                         symbol_strategies_override: Optional[Dict] = None) -> Set[int]:
    """返回配置中所有品种、所有 style 的 strategy_id 集合（被本模块管理的范围）。"""
    cfg = config or _load_config()
    symbol_strategies = (symbol_strategies_override if symbol_strategies_override is not None
                         else cfg.get("symbol_strategies", {}))
    all_ids: Set[int] = set()
    for _symbol, style_map in (symbol_strategies or {}).items():
        if not isinstance(style_map, dict):
            continue
        for ids in style_map.values():
            if isinstance(ids, list):
                all_ids.update(int(i) for i in ids)
    return all_ids


# ── 启停操作 ────────────────────────────────────────────────────────────

def _stop_strategies(ids: List[int], user_id: Optional[int] = None) -> None:
    """停止策略：先 executor.stop → 再 service 改 DB。"""
    if not ids:
        return
    from app import get_trading_executor
    from app.services.strategy import StrategyService

    executor = get_trading_executor()
    service = StrategyService()

    for sid in ids:
        try:
            executor.stop_strategy(sid)
        except Exception as e:
            logger.warning("[regime_switch] executor.stop_strategy(%d) failed: %s", sid, e)

    service.batch_stop_strategies(ids, user_id=user_id)


def _start_strategies(ids: List[int], user_id: Optional[int] = None) -> None:
    """启动策略：先 service 改 DB → 再 executor.start。executor 失败时回滚 DB 并记日志。"""
    if not ids:
        return
    from app import get_trading_executor
    from app.services.strategy import StrategyService

    executor = get_trading_executor()
    service = StrategyService()

    service.batch_start_strategies(ids, user_id=user_id)
    failed_ids = []
    for sid in ids:
        try:
            ok = executor.start_strategy(sid)
            if not ok:
                failed_ids.append(sid)
                logger.warning(
                    "[regime_switch] executor.start_strategy(%d) returned False (likely thread limit), revert DB",
                    sid,
                )
        except Exception as e:
            failed_ids.append(sid)
            logger.warning("[regime_switch] executor.start_strategy(%d) failed: %s", sid, e)
    if failed_ids:
        service.batch_stop_strategies(failed_ids, user_id=user_id)
        logger.warning(
            "[regime_switch] reverted DB status for %d strategies that failed to start: %s",
            len(failed_ids), failed_ids[:20] if len(failed_ids) > 20 else failed_ids,
        )


# ── 主入口 ──────────────────────────────────────────────────────────────

def run() -> None:
    """由 APScheduler 定时调用的入口。"""
    if not _run_lock.acquire(blocking=False):
        logger.info("[regime_switch] already running, skip this tick")
        return
    try:
        _run_inner()
    finally:
        _run_lock.release()


def _is_multi_strategy_enabled(config: Dict) -> bool:
    """检查是否启用 P1 多策略权重分配模式。"""
    return bool(config.get("multi_strategy", {}).get("enabled", False))


def _run_inner() -> None:
    config = _load_config()
    symbol_strategies = config.get("symbol_strategies") or {}
    # 策略启停使用默认主用户（regime 配置全局，策略仍按用户）
    user_id = 1

    if not symbol_strategies:
        symbol_strategies = _get_symbol_strategies_from_db(user_id=user_id)
    if not symbol_strategies:
        logger.debug("[regime_switch] no symbol_strategies (config or DB with regime_style), noop")
        return

    macro = _fetch_macro_snapshot()
    regime_per_symbol = compute_regime_per_symbol(symbol_strategies, macro, config)
    regime_default = next(iter(regime_per_symbol.values()), "normal") if regime_per_symbol else "normal"

    if _is_multi_strategy_enabled(config):
        _run_multi_strategy(regime_default, config, symbol_strategies, macro, user_id,
                           regime_per_symbol=regime_per_symbol)
    else:
        _run_legacy(regime_default, config, symbol_strategies, macro, user_id,
                    regime_per_symbol=regime_per_symbol)


def _run_multi_strategy(
    regime: str, config: Dict, symbol_strategies: Dict,
    macro: Dict[str, float], user_id: Optional[int],
    regime_per_symbol: Optional[Dict[str, str]] = None,
) -> None:
    """P1 多策略权重分配模式。支持 per-symbol regime（港股 VHSI、美股 VIX 等）。"""
    from app.services.portfolio_allocator import get_portfolio_allocator

    allocator = get_portfolio_allocator()
    result = allocator.update_regime(regime, config, symbol_strategies,
                                    regime_per_symbol=regime_per_symbol)

    ids_to_stop = result.get("stopped", [])
    ids_to_start = result.get("started", [])
    weight_changed = result.get("weight_changed", [])
    running_count = result.get("running_count", 0)
    target_count = result.get("target_count", 0)
    symbols_with_pool = result.get("symbols_with_pool", 0)
    symbols_total = result.get("symbols_total", 0)

    if ids_to_stop:
        _stop_strategies(ids_to_stop, user_id=user_id)
    if ids_to_start:
        _start_strategies(ids_to_start, user_id=user_id)

    logger.info(
        "[regime_switch] MULTI regime=%s (VIX=%.1f F&G=%.0f) | symbols_pool=%d/%d running=%d target=%d | weights=%s | stop=%s start=%s weight_changed=%s",
        regime, macro["vix"], macro["fear_greed"],
        symbols_with_pool, symbols_total,
        running_count, target_count,
        allocator.effective_weights,
        ids_to_stop, ids_to_start, weight_changed,
    )


def _run_legacy(
    regime: str, config: Dict, symbol_strategies: Dict,
    macro: Dict[str, float], user_id: Optional[int],
    regime_per_symbol: Optional[Dict[str, str]] = None,
) -> None:
    """P0 二元启停模式（向后兼容）。支持 per-symbol regime。"""
    vix = macro["vix"]
    fg = macro["fear_greed"]

    target_ids = compute_target_strategy_ids(regime, config=config,
                                            symbol_strategies_override=symbol_strategies,
                                            regime_per_symbol=regime_per_symbol)
    managed_ids = _get_all_managed_ids(config, symbol_strategies_override=symbol_strategies)
    running_ids = _get_currently_running_ids()

    managed_running = running_ids & managed_ids

    ids_to_start = sorted(target_ids - managed_running)
    ids_to_stop = sorted(managed_running - target_ids)

    if not ids_to_start and not ids_to_stop:
        logger.info(
            "[regime_switch] regime=%s (VIX=%.1f F&G=%.0f) | no change needed | running=%s",
            regime, vix, fg, sorted(managed_running),
        )
        return

    logger.info(
        "[regime_switch] regime=%s (VIX=%.1f F&G=%.0f) | stop=%s start=%s",
        regime, vix, fg, ids_to_stop, ids_to_start,
    )

    _stop_strategies(ids_to_stop, user_id=user_id)
    _start_strategies(ids_to_start, user_id=user_id)

    logger.info("[regime_switch] done: stopped %d, started %d", len(ids_to_stop), len(ids_to_start))
