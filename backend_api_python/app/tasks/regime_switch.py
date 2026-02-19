"""
regime_switch 插件 — 监控 VIX/Fear&Greed → 自动启停策略。

定时由 APScheduler 调用 run()：
  1. 拉取实时宏观快照（MacroDataService）
  2. 根据 VIX 阈值计算当前 regime
  3. 对比配置中「regime→style→strategy_id」与实际运行状态
  4. 调 StrategyService + TradingExecutor 做启停（两层配合）
"""

import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.utils.logger import get_logger

logger = get_logger(__name__)

JOB_ID = "task_regime_switch"
INTERVAL_MINUTES = 15
ENABLED = os.getenv("ENABLE_REGIME_SWITCH", "false").lower() == "true"

_run_lock = threading.Lock()

# ── 配置加载 ────────────────────────────────────────────────────────────

_config_cache: Optional[Dict[str, Any]] = None


def _load_config() -> Dict[str, Any]:
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    config_path = os.getenv(
        "REGIME_SWITCH_CONFIG_PATH",
        str(Path(__file__).resolve().parents[2] / "config" / "regime_switch.yaml"),
    )

    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("[regime_switch] config not found: %s, using defaults", config_path)
        _config_cache = {}
    except Exception as e:
        logger.error("[regime_switch] failed to load config: %s", e)
        _config_cache = {}

    return _config_cache


def reload_config() -> Dict[str, Any]:
    """强制重载配置（用于测试或运行时热更新）。"""
    global _config_cache
    _config_cache = None
    return _load_config()


# ── Regime 计算 ─────────────────────────────────────────────────────────

REGIME_PANIC = "panic"
REGIME_HIGH_VOL = "high_vol"
REGIME_LOW_VOL = "low_vol"
REGIME_NORMAL = "normal"


def compute_regime(vix: float, fear_greed: Optional[float] = None,
                   config: Optional[Dict] = None) -> str:
    """根据 VIX（和可选 F&G）计算当前 regime。"""
    cfg = (config or _load_config()).get("regime_rules", {})
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


# ── 目标策略集合 ────────────────────────────────────────────────────────

def compute_target_strategy_ids(regime: str, config: Optional[Dict] = None) -> Set[int]:
    """根据当前 regime 和配置，计算应该运行的 strategy_id 集合。"""
    cfg = config or _load_config()
    regime_to_style = cfg.get("regime_to_style", {})
    symbol_strategies = cfg.get("symbol_strategies", {})

    active_styles = regime_to_style.get(regime, ["balanced"])
    target_ids: Set[int] = set()

    for _symbol, style_map in (symbol_strategies or {}).items():
        if not isinstance(style_map, dict):
            continue
        for style in active_styles:
            ids = style_map.get(style, [])
            if isinstance(ids, list):
                target_ids.update(int(i) for i in ids)

    return target_ids


# ── 获取宏观数据 ────────────────────────────────────────────────────────

def _fetch_macro_snapshot() -> Dict[str, float]:
    """拉取实时宏观快照（VIX / DXY / Fear&Greed）。"""
    from app.services.macro_data_service import MacroDataService
    snapshot = MacroDataService._get_realtime_snapshot()
    if not snapshot:
        logger.warning("[regime_switch] macro snapshot empty, using defaults")
        return {"vix": 18.0, "dxy": 100.0, "fear_greed": 50.0}
    return {
        "vix": float(snapshot.get("vix", 18.0)),
        "dxy": float(snapshot.get("dxy", 100.0)),
        "fear_greed": float(snapshot.get("fear_greed", 50.0)),
    }


# ── 获取当前运行中的策略 ID ──────────────────────────────────────────────

def _get_currently_running_ids() -> Set[int]:
    """从 TradingExecutor 获取实际运行中的策略 ID 集合。"""
    from app import get_trading_executor
    executor = get_trading_executor()
    with executor.lock:
        return set(executor.running_strategies.keys())


# ── 获取所有已配置的策略 ID ──────────────────────────────────────────────

def _get_all_managed_ids(config: Optional[Dict] = None) -> Set[int]:
    """返回配置中所有品种、所有 style 的 strategy_id 集合（被本模块管理的范围）。"""
    cfg = config or _load_config()
    symbol_strategies = cfg.get("symbol_strategies", {})
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
    """启动策略：先 service 改 DB → 再 executor.start。"""
    if not ids:
        return
    from app import get_trading_executor
    from app.services.strategy import StrategyService

    executor = get_trading_executor()
    service = StrategyService()

    service.batch_start_strategies(ids, user_id=user_id)
    for sid in ids:
        try:
            executor.start_strategy(sid)
        except Exception as e:
            logger.warning("[regime_switch] executor.start_strategy(%d) failed: %s", sid, e)


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


def _run_inner() -> None:
    config = _load_config()
    symbol_strategies = config.get("symbol_strategies") or {}
    if not symbol_strategies:
        logger.debug("[regime_switch] no symbol_strategies configured, noop")
        return

    user_id_raw = config.get("user_id")
    user_id = int(user_id_raw) if user_id_raw is not None else None

    # 1) 拉宏观
    macro = _fetch_macro_snapshot()
    vix = macro["vix"]
    fg = macro["fear_greed"]

    # 2) 算 regime
    regime = compute_regime(vix, fear_greed=fg, config=config)

    # 3) 算目标
    target_ids = compute_target_strategy_ids(regime, config=config)
    managed_ids = _get_all_managed_ids(config)
    running_ids = _get_currently_running_ids()

    # 只操作本模块管理范围内的策略
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

    # 4) 先停后启
    _stop_strategies(ids_to_stop, user_id=user_id)
    _start_strategies(ids_to_start, user_id=user_id)

    logger.info("[regime_switch] done: stopped %d, started %d", len(ids_to_stop), len(ids_to_start))
