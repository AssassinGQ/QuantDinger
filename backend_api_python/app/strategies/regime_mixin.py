"""
Regime 计算与混入类。

合并自 regime_utils.py，新增 DXY 指标支持和 RegimeMixin 混入类。
供 SingleRegimeWeightedStrategy 和 CrossSectionalWeightedStrategy 共用。

从 .env 读取阈值配置，不依赖数据库。
"""
import json
import math
import os
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from app.services.macro_data_service import MacroDataService
from app.utils.logger import get_logger
from app.utils.safe_exec import safe_exec_code, validate_code_safety

logger = get_logger(__name__)

# ── Regime 常量 ─────────────────────────────────────────────────────────────

REGIME_PANIC = "panic"
REGIME_HIGH_VOL = "high_vol"
REGIME_LOW_VOL = "low_vol"
REGIME_NORMAL = "normal"

_DEFAULT_REGIME_TO_WEIGHTS = {
    "panic": {"conservative": 0.8, "balanced": 0.2, "aggressive": 0.0},
    "high_vol": {"conservative": 0.5, "balanced": 0.4, "aggressive": 0.1},
    "normal": {"conservative": 0.2, "balanced": 0.6, "aggressive": 0.2},
    "low_vol": {"conservative": 0.1, "balanced": 0.3, "aggressive": 0.6},
}

_MACRO_DEFAULTS = {
    "vix": 18.0,
    "vhsi": 22.0,
    "civix": 18.0,
    "dxy": 100.0,
    "fear_greed": 50.0,
}


# ── .env 配置加载 ───────────────────────────────────────────────────────────


def load_regime_rules() -> Dict[str, Any]:
    """从 .env 读取 regime 阈值配置，缺省使用硬编码默认值。"""
    def _env_float(key: str, default: float) -> float:
        try:
            return float(os.getenv(key, str(default)))
        except (ValueError, TypeError):
            return default

    return {
        "vix_panic": _env_float("REGIME_VIX_PANIC", 30),
        "vix_high_vol": _env_float("REGIME_VIX_HIGH_VOL", 25),
        "vix_low_vol": _env_float("REGIME_VIX_LOW_VOL", 15),
        "vhsi_panic": _env_float("REGIME_VHSI_PANIC", 30),
        "vhsi_high_vol": _env_float("REGIME_VHSI_HIGH_VOL", 25),
        "vhsi_low_vol": _env_float("REGIME_VHSI_LOW_VOL", 15),
        "civix_panic": _env_float("REGIME_CIVIX_PANIC", 30),
        "civix_high_vol": _env_float("REGIME_CIVIX_HIGH_VOL", 25),
        "civix_low_vol": _env_float("REGIME_CIVIX_LOW_VOL", 15),
        "dxy_panic": _env_float("REGIME_DXY_PANIC", 110),
        "dxy_high_vol": _env_float("REGIME_DXY_HIGH_VOL", 105),
        "dxy_low_vol": _env_float("REGIME_DXY_LOW_VOL", 95),
        "fg_extreme_fear": _env_float("REGIME_FG_EXTREME_FEAR", 20),
        "fg_high_fear": _env_float("REGIME_FG_HIGH_FEAR", 35),
        "fg_low_greed": _env_float("REGIME_FG_LOW_GREED", 65),
        "primary_indicator": os.getenv("REGIME_PRIMARY_INDICATOR", "vix"),
    }


def load_regime_to_weights() -> Dict[str, Dict[str, float]]:
    """从 .env 读取 regime->style 权重映射，缺省使用硬编码默认值。"""
    raw = os.getenv("REGIME_TO_WEIGHTS_JSON", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid REGIME_TO_WEIGHTS_JSON, using defaults")
    return dict(_DEFAULT_REGIME_TO_WEIGHTS)


# ── Regime 计算 ─────────────────────────────────────────────────────────────


def _classify_by_thresholds(
    value: float, threshold_panic: float, threshold_high: float, threshold_low: float,
) -> str:
    """通用阈值分类：值越高越 panic（适用于 VIX/VHSI/CIVIX/DXY 等正向指标）。"""
    if value > threshold_panic:
        return REGIME_PANIC
    if value > threshold_high:
        return REGIME_HIGH_VOL
    if value < threshold_low:
        return REGIME_LOW_VOL
    return REGIME_NORMAL


def compute_regime(
    vix: float,
    fear_greed: Optional[float] = None,
    config: Optional[Dict] = None,
    **kwargs,
) -> str:
    """根据主指标（VIX / VHSI / CIVIX / DXY / Fear&Greed / Custom）计算当前 regime。

    config 需包含 ``regime_rules`` 键（dict），或直接传 regime_rules 作为顶层 dict。

    Keyword Args:
        vhsi: VHSI 指标值
        dxy: DXY 指标值
        macro: 宏观指标 dict，可包含 vhsi/civix/dxy/fear_greed
        primary_override: 强制指定主指标类型
    """
    cfg = (config or {}).get("regime_rules") or (config if config else {})
    primary_override = kwargs.get("primary_override")
    primary = (primary_override or cfg.get("primary_indicator") or "vix").strip().lower()

    if primary == "custom":
        return _compute_regime_custom(vix, fear_greed, config)

    resolved = _resolve_indicator_value(primary, vix, fear_greed, kwargs)
    return _classify_primary(primary, resolved, cfg)


def _resolve_indicator_value(
    primary: str,
    vix: float,
    fear_greed: Optional[float],
    kwargs: Dict[str, Any],
) -> float:
    """从显式参数或 macro dict 中解析主指标值。"""
    macro = kwargs.get("macro") or {}
    if primary == "vhsi":
        vhsi = kwargs.get("vhsi")
        return vhsi if vhsi is not None else macro.get("vhsi", vix)
    if primary == "civix":
        return macro.get("civix", vix)
    if primary == "dxy":
        dxy = kwargs.get("dxy")
        return dxy if dxy is not None else macro.get("dxy", 100.0)
    if primary == "fear_greed":
        return fear_greed if fear_greed is not None else 50.0
    return vix


def _classify_primary(primary: str, value: float, cfg: Dict) -> str:
    """根据主指标类型和值判断 regime。"""
    if primary == "fear_greed":
        return _classify_fear_greed(value, cfg)

    thresholds = _THRESHOLD_KEYS.get(primary, _THRESHOLD_KEYS["vix"])
    return _classify_by_thresholds(
        value,
        cfg.get(thresholds[0], thresholds[3]),
        cfg.get(thresholds[1], thresholds[4]),
        cfg.get(thresholds[2], thresholds[5]),
    )


_THRESHOLD_KEYS = {
    "vix":   ("vix_panic",   "vix_high_vol",   "vix_low_vol",   30, 25, 15),
    "vhsi":  ("vhsi_panic",  "vhsi_high_vol",  "vhsi_low_vol",  30, 25, 15),
    "civix": ("civix_panic", "civix_high_vol", "civix_low_vol", 30, 25, 15),
    "dxy":   ("dxy_panic",   "dxy_high_vol",   "dxy_low_vol",   110, 105, 95),
}


def _classify_fear_greed(fg: float, cfg: Dict) -> str:
    """Fear & Greed 指标是反向的：值越低越 panic。"""
    if fg < cfg.get("fg_extreme_fear", 20):
        return REGIME_PANIC
    if fg < cfg.get("fg_high_fear", 35):
        return REGIME_HIGH_VOL
    if fg > cfg.get("fg_low_greed", 65):
        return REGIME_LOW_VOL
    return REGIME_NORMAL


def _compute_regime_custom(
    vix: float, fear_greed: Optional[float], config: Optional[Dict]
) -> str:
    """执行自定义 Python 代码计算 regime。"""
    cfg = (config or {}).get("regime_rules") or (config if config else {})
    custom_code = (cfg.get("custom_code") or "").strip()
    if not custom_code:
        logger.warning("[regime_mixin] custom indicator but no custom_code, fallback to normal")
        return REGIME_NORMAL

    macro_env = _build_custom_macro_env(vix, fear_greed)
    exec_env = _run_custom_code(custom_code, macro_env)
    if exec_env is None:
        return REGIME_NORMAL
    return _interpret_custom_result(exec_env, cfg)


def _build_custom_macro_env(vix: float, fear_greed: Optional[float]) -> Dict[str, float]:
    """构建 custom code 的宏观数据环境。"""
    snapshot = MacroDataService.get_realtime_snapshot()
    if snapshot:
        return {
            "vix": float(snapshot.get("vix", 18.0)),
            "vhsi": float(snapshot.get("vhsi", 22.0)),
            "civix": float(snapshot.get("civix", 18.0)),
            "dxy": float(snapshot.get("dxy", 100.0)),
            "fear_greed": float(snapshot.get("fear_greed", 50.0)),
        }
    return {
        "vix": vix, "vhsi": vix, "civix": vix,
        "dxy": 100.0, "fear_greed": fear_greed or 50.0,
    }


def _run_custom_code(custom_code: str, macro_env: Dict) -> Optional[Dict]:
    """验证并执行自定义代码，返回执行环境或 None。"""
    is_safe, err = validate_code_safety(custom_code)
    if not is_safe:
        logger.error("[regime_mixin] custom code unsafe: %s", err)
        return None

    exec_env = {
        "macro": macro_env, **macro_env,
        "regime": None, "regime_score": None,
        "math": __import__("math"),
    }
    result = safe_exec_code(code=custom_code, exec_globals=exec_env, timeout=5)
    if not result.get("success"):
        logger.error("[regime_mixin] custom code exec failed: %s", result.get("error"))
        return None
    return exec_env


def _interpret_custom_result(exec_env: Dict, cfg: Dict) -> str:
    """从 custom code 执行结果中解析 regime。"""
    valid_regimes = (REGIME_PANIC, REGIME_HIGH_VOL, REGIME_NORMAL, REGIME_LOW_VOL)
    regime = exec_env.get("regime")
    if regime in valid_regimes:
        return regime

    score = exec_env.get("regime_score")
    if score is not None:
        try:
            return _classify_fear_greed(float(score), {
                "fg_extreme_fear": cfg.get("custom_score_extreme_fear", 20),
                "fg_high_fear": cfg.get("custom_score_high_fear", 35),
                "fg_low_greed": cfg.get("custom_score_low_greed", 65),
            })
        except (TypeError, ValueError):
            return REGIME_NORMAL

    logger.warning("[regime_mixin] custom code must define regime or regime_score")
    return REGIME_NORMAL


# ── 辅助函数 ────────────────────────────────────────────────────────────────

_REBALANCE_FREQ_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}


def check_rebalance_due(
    rebalance_frequency: str, last_rebalance: Optional[datetime],
) -> bool:
    """判断是否到了再平衡周期，供 Runner 和 Strategy 共用。"""
    if last_rebalance is None:
        return True
    delta = datetime.now() - last_rebalance
    return delta.days >= _REBALANCE_FREQ_DAYS.get(rebalance_frequency, 1)


def read_macro_values(
    df: pd.DataFrame,
    macro_indicators: list,
) -> Dict[str, float]:
    """从 df 最后一行读取指定的宏观指标值，nan 回退到默认值。"""
    last_row = df.iloc[-1]
    result = {}
    for key in macro_indicators:
        val = last_row.get(key, None)
        if val is None or (isinstance(val, float) and math.isnan(val)):
            val = _MACRO_DEFAULTS.get(key, 0.0)
        result[key] = float(val)
    return result


# ── RegimeMixin ─────────────────────────────────────────────────────────────


class RegimeMixin:
    """Regime 计算混入类，供 SingleRegimeWeightedStrategy 和 CrossSectionalWeightedStrategy 共用。"""

    def compute_regime_from_context(
        self,
        macro: Dict[str, float],
        config: Dict[str, Any],
    ) -> str:
        """根据宏观数据计算当前 regime。"""
        primary = config.get("primary_macro_indicator", "vix")
        regime_cfg = {"regime_rules": load_regime_rules()}

        return compute_regime(
            vix=macro.get("vix", 18.0),
            vhsi=macro.get("vhsi"),
            fear_greed=macro.get("fear_greed"),
            dxy=macro.get("dxy"),
            macro=macro,
            config=regime_cfg,
            primary_override=primary,
        )

    def get_capital_ratio(
        self,
        regime: str,
        strategy_type: str,
    ) -> float:
        """根据 regime 和策略类型获取可用资金比例。"""
        weights = load_regime_to_weights()
        return weights.get(regime, {}).get(strategy_type, 1.0)
