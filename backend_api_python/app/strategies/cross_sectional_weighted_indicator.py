"""
执行 Regime 截面策略的指标代码
"""
from typing import Any, Dict

import pandas as pd

from app.strategies.base import RawIndicatorOutput
from app.utils.logger import get_logger

# Import regime logic
from app.tasks.regime_switch import _load_config, compute_regime

logger = get_logger(__name__)


def _execute_indicator_code(
    code: str,
    global_env: Dict[str, Any],
    df: pd.DataFrame
) -> tuple[float, int]:
    """Execute indicator code and return (weight, signal_val)."""
    local_env = {"df": df.copy()}
    try:
        exec(code, global_env, local_env) # pylint: disable=exec-used
        ind_weight = float(local_env.get("weight", 0.0))
        ind_signal = local_env.get("signal", 0)

        sig_val = 0
        if str(ind_signal).lower() in ("1", "1.0", "long", "buy"):
            sig_val = 1
        elif str(ind_signal).lower() in ("-1", "-1.0", "short", "sell"):
            sig_val = -1

        return ind_weight, sig_val
    except Exception as e: # pylint: disable=broad-exception-caught
        logger.error("Error executing indicator code: %s", e)
        return 0.0, 0


def _process_nested_config(
    ind_config: Dict[str, str],
    df: pd.DataFrame,
    global_env: Dict[str, Any],
    regime_cfg: Dict[str, Any],
    regime_to_weights_map: Dict[str, Any]
) -> tuple[float, int]:
    """处理嵌套的 regime style 配置，融合计算最终权重和信号。"""
    # pylint: disable=too-many-locals
    last_row = df.iloc[-1]
    vix = float(last_row.get("vix", 18.0))
    vhsi = float(last_row.get("vhsi", 22.0))
    fear_greed = float(last_row.get("fear_greed", 50.0))
    macro_data = {"vix": vix, "vhsi": vhsi, "civix": vix, "fear_greed": fear_greed}

    current_regime = compute_regime(
        vix=vix, fear_greed=fear_greed, config=regime_cfg, vhsi=vhsi, macro=macro_data
    )
    style_weights = regime_to_weights_map.get(current_regime, {})

    combined_weight = 0.0

    for style, code in ind_config.items():
        target_ratio = style_weights.get(style, 0.0)
        if target_ratio <= 0.0:
            continue

        ind_weight, sig_val = _execute_indicator_code(code, global_env, df)
        combined_weight += sig_val * ind_weight * target_ratio

    final_weight = abs(combined_weight)
    final_signal = 1 if combined_weight > 0 else (-1 if combined_weight < 0 else 0)

    return final_weight, final_signal


def run_cross_sectional_weighted_indicator(
    symbol_indicator_codes: Dict[str, Any],
    data: Dict[str, pd.DataFrame],
    trading_config: Dict[str, Any],
) -> RawIndicatorOutput:
    """
    针对不同 symbol 执行各自的指标代码，并汇总计算 weights 和 signals。
    """
    weights = {}
    signals = {}

    global_env = {"trading_config": trading_config}

    regime_cfg = _load_config()

    regime_to_weights_map = regime_cfg.get("regime_to_weights") or \
                            regime_cfg.get("multi_strategy", {}).get("regime_to_weights") or {
        "panic": {"conservative": 0.8, "balanced": 0.2, "aggressive": 0.0},
        "high_vol": {"conservative": 0.5, "balanced": 0.4, "aggressive": 0.1},
        "normal": {"conservative": 0.2, "balanced": 0.6, "aggressive": 0.2},
        "low_vol": {"conservative": 0.1, "balanced": 0.3, "aggressive": 0.6},
    }

    for symbol, df in data.items():
        if df is None or len(df) == 0:
            continue

        ind_config = symbol_indicator_codes.get(symbol)
        if not ind_config:
            logger.warning(
                "No indicator code found for symbol %s in cross_sectional_weighted", symbol
            )
            continue

        if isinstance(ind_config, dict):
            final_weight, final_signal = _process_nested_config(
                ind_config, df, global_env, regime_cfg, regime_to_weights_map
            )
            weights[symbol] = final_weight
            signals[symbol] = final_signal
        else:
            final_weight, final_signal = _execute_indicator_code(ind_config, global_env, df)
            weights[symbol] = final_weight
            signals[symbol] = final_signal

    return {"weights": weights, "signals": signals}
