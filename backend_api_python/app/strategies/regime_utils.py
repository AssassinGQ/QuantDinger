"""
Regime 计算工具 — 根据宏观指标阈值判断当前 regime。

从 .env 读取阈值配置，不依赖数据库。
"""
import json
import os
from typing import Any, Dict, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

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
        "fg_extreme_fear": _env_float("REGIME_FG_EXTREME_FEAR", 20),
        "fg_high_fear": _env_float("REGIME_FG_HIGH_FEAR", 35),
        "fg_low_greed": _env_float("REGIME_FG_LOW_GREED", 65),
        "primary_indicator": os.getenv("REGIME_PRIMARY_INDICATOR", "vix"),
    }


def load_regime_to_weights() -> Dict[str, Dict[str, float]]:
    """从 .env 读取 regime→style 权重映射，缺省使用硬编码默认值。"""
    raw = os.getenv("REGIME_TO_WEIGHTS_JSON", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid REGIME_TO_WEIGHTS_JSON, using defaults")
    return dict(_DEFAULT_REGIME_TO_WEIGHTS)


def compute_regime(
    vix: float,
    fear_greed: Optional[float] = None,
    config: Optional[Dict] = None,
    vhsi: Optional[float] = None,
    macro: Optional[Dict[str, float]] = None,
    primary_override: Optional[str] = None,
) -> str:
    """根据主指标（VIX / VHSI / CIVIX / Fear&Greed / Custom）计算当前 regime。

    config 需包含 ``regime_rules`` 键（dict），或直接传 regime_rules 作为顶层 dict。
    """
    cfg = (config or {}).get("regime_rules") or (config if config else {})
    primary = (primary_override or cfg.get("primary_indicator") or "vix").strip().lower()

    if primary == "custom":
        return _compute_regime_custom(vix, fear_greed, config)

    if primary == "vhsi":
        vol_val = vhsi if vhsi is not None else (macro or {}).get("vhsi", vix)
        threshold_panic = cfg.get("vhsi_panic", cfg.get("vix_panic", 30))
        threshold_high = cfg.get("vhsi_high_vol", cfg.get("vix_high_vol", 25))
        threshold_low = cfg.get("vhsi_low_vol", cfg.get("vix_low_vol", 15))
        if vol_val > threshold_panic:
            return REGIME_PANIC
        if vol_val > threshold_high:
            return REGIME_HIGH_VOL
        if vol_val < threshold_low:
            return REGIME_LOW_VOL
        return REGIME_NORMAL

    if primary == "civix":
        vol_val = (macro or {}).get("civix", vix)
        threshold_panic = cfg.get("civix_panic", cfg.get("vix_panic", 30))
        threshold_high = cfg.get("civix_high_vol", cfg.get("vix_high_vol", 25))
        threshold_low = cfg.get("civix_low_vol", cfg.get("vix_low_vol", 15))
        if vol_val > threshold_panic:
            return REGIME_PANIC
        if vol_val > threshold_high:
            return REGIME_HIGH_VOL
        if vol_val < threshold_low:
            return REGIME_LOW_VOL
        return REGIME_NORMAL

    if primary == "fear_greed":
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

    # 默认 VIX
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
    """执行自定义 Python 代码计算 regime。"""
    cfg = (config or {}).get("regime_rules") or (config if config else {})
    custom_code = (cfg.get("custom_code") or "").strip()
    if not custom_code:
        logger.warning("[regime_utils] custom indicator but no custom_code, fallback to normal")
        return REGIME_NORMAL

    from app.services.macro_data_service import MacroDataService
    snapshot = MacroDataService._get_realtime_snapshot()
    macro_env = {
        "vix": float(snapshot.get("vix", 18.0)) if snapshot else vix,
        "vhsi": float(snapshot.get("vhsi", 22.0)) if snapshot else vix,
        "civix": float(snapshot.get("civix", 18.0)) if snapshot else vix,
        "dxy": float(snapshot.get("dxy", 100.0)) if snapshot else 100.0,
        "fear_greed": float(snapshot.get("fear_greed", 50.0)) if snapshot else (fear_greed or 50.0),
    }

    from app.utils.safe_exec import validate_code_safety, safe_exec_code
    is_safe, err = validate_code_safety(custom_code)
    if not is_safe:
        logger.error("[regime_utils] custom code unsafe: %s", err)
        return REGIME_NORMAL

    exec_env = {
        "macro": macro_env,
        **macro_env,
        "regime": None,
        "regime_score": None,
        "math": __import__("math"),
    }
    result = safe_exec_code(code=custom_code, exec_globals=exec_env, timeout=5)
    if not result.get("success"):
        logger.error("[regime_utils] custom code exec failed: %s", result.get("error"))
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

    logger.warning("[regime_utils] custom code must define regime or regime_score")
    return REGIME_NORMAL
