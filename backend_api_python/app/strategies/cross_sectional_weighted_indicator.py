"""
执行 Regime 截面策略的指标代码
"""
import math
from typing import Any, Dict

import pandas as pd

from app.strategies.base import RawIndicatorOutput
from app.utils.logger import get_logger

from app.strategies.regime_utils import compute_regime, load_regime_rules, load_regime_to_weights

logger = get_logger(__name__)


def _execute_indicator_code(
    code: str,
    global_env: Dict[str, Any],
    df: pd.DataFrame
) -> int:
    """Execute indicator code and return signal: 1=buy, -1=sell, 0=neutral.

    Reads df['buy']/df['sell'] last row first (standard indicator interface),
    falls back to 'signal' variable for backward compatibility.
    """
    local_env = {"df": df.copy()}
    try:
        exec(code, global_env, local_env) # pylint: disable=exec-used
        executed_df = local_env.get("df", df)

        if "buy" in executed_df.columns or "sell" in executed_df.columns:
            last = executed_df.iloc[-1]
            buy_val = int(last.get("buy", 0) or 0)
            sell_val = int(last.get("sell", 0) or 0)
            logger.debug(
                "Indicator read df[buy]=%s, df[sell]=%s (last row)",
                buy_val, sell_val
            )
            if buy_val:
                return 1
            if sell_val:
                return -1
            return 0

        ind_signal = local_env.get("signal", 0)
        logger.debug("Indicator fallback to signal variable: %s", ind_signal)
        if str(ind_signal).lower() in ("1", "1.0", "long", "buy"):
            return 1
        if str(ind_signal).lower() in ("-1", "-1.0", "short", "sell"):
            return -1
        return 0
    except Exception as e: # pylint: disable=broad-exception-caught
        logger.error("Error executing indicator code: %s", e)
        return 0


def _read_macro_values(
    df: pd.DataFrame,
    macro_indicators: list,
) -> Dict[str, float]:
    """从 df 最后一行读取指定的宏观指标值，nan 回退到默认值。"""
    defaults = {"vix": 18.0, "vhsi": 22.0, "civix": 18.0, "dxy": 100.0, "fear_greed": 50.0}
    last_row = df.iloc[-1]
    result = {}
    for key in macro_indicators:
        val = last_row.get(key, None)
        if val is None or (isinstance(val, float) and math.isnan(val)):
            val = defaults.get(key, 0.0)
        result[key] = float(val)
    return result


def _process_nested_config(
    ind_config: Dict[str, Any],
    df: pd.DataFrame,
    global_env: Dict[str, Any],
    regime_cfg: Dict[str, Any],
    regime_to_weights_map: Dict[str, Any],
    trading_config: Dict[str, Any] = None,
) -> tuple[float, int, Dict[str, Any]]:
    """处理嵌套的 regime style 配置，融合计算最终权重和信号。"""
    # pylint: disable=too-many-locals,too-many-positional-arguments,too-many-arguments
    tc = trading_config or {}
    macro_indicators = tc.get("macro_indicators") or ["vix", "vhsi", "fear_greed"]
    primary_indicator = tc.get("primary_macro_indicator") or "vix"

    macro_values = _read_macro_values(df, macro_indicators)

    vix = macro_values.get("vix", 18.0)
    vhsi = macro_values.get("vhsi", 22.0)
    fear_greed = macro_values.get("fear_greed", 50.0)

    current_regime = compute_regime(
        vix=vix, fear_greed=fear_greed, config=regime_cfg,
        vhsi=vhsi, macro=macro_values,
        primary_override=primary_indicator,
    )
    style_weights = regime_to_weights_map.get(current_regime, {})

    logger.info(
        "Regime Calculation - primary: %s, macro: %s -> Current Regime: %s",
        primary_indicator, macro_values, current_regime
    )

    combined_weight = 0.0
    components = []

    for style, code_or_codes in ind_config.items():
        target_ratio = style_weights.get(style, 0.0)
        if target_ratio <= 0.0:
            continue

        codes = code_or_codes if isinstance(code_or_codes, list) else [code_or_codes]
        if not codes:
            continue

        regime_weight = target_ratio / len(codes)

        for code in codes:
            sig_val = _execute_indicator_code(code, global_env, df)
            combined_weight += sig_val * regime_weight
            direction = {1: "buy", -1: "sell"}.get(sig_val, "neutral")
            logger.info(
                "Regime Component - Style: %s, Direction: %s(%d), RegimeWeight: %.2f",
                style, direction, sig_val, regime_weight
            )
            components.append({
                "style": style,
                "signal": sig_val,
                "regime_weight": round(regime_weight, 4),
                "contribution": round(sig_val * regime_weight, 4)
            })

    final_weight = abs(combined_weight)
    final_signal = 1 if combined_weight > 0 else (-1 if combined_weight < 0 else 0)

    final_dir = {1: "buy", -1: "sell"}.get(final_signal, "neutral")
    logger.info(
        "Regime Result - Combined Weight: %.4f -> Direction: %s(%d), Final Weight: %.4f",
        combined_weight, final_dir, final_signal, final_weight
    )

    rounded_macro = {k: round(v, 2) for k, v in macro_values.items()}
    metadata = {
        "current_regime": current_regime,
        "primary_indicator": primary_indicator,
        **rounded_macro,
        "components": components,
        "combined_weight": round(combined_weight, 4),
        "final_weight": round(final_weight, 4),
        "final_signal": final_signal,
    }

    return final_weight, final_signal, metadata


def run_cross_sectional_weighted_indicator(
    symbol_indicator_codes: Dict[str, Any],
    data: Dict[str, pd.DataFrame],
    trading_config: Dict[str, Any],
) -> RawIndicatorOutput:
    """针对不同 symbol 执行各自的指标代码，并汇总计算 weights 和 signals。"""
    # pylint: disable=too-many-locals
    weights = {}
    signals = {}
    metadata_list = {}

    global_env = {"trading_config": trading_config}

    regime_cfg = {"regime_rules": load_regime_rules()}
    regime_to_weights_map = load_regime_to_weights()

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
            final_weight, final_signal, metadata = _process_nested_config(
                ind_config, df, global_env, regime_cfg, regime_to_weights_map,
                trading_config=trading_config,
            )
            weights[symbol] = final_weight
            signals[symbol] = final_signal
            metadata_list[symbol] = metadata
        else:
            final_signal = _execute_indicator_code(ind_config, global_env, df)
            weights[symbol] = abs(final_signal)
            signals[symbol] = final_signal
            metadata_list[symbol] = {
                "final_weight": abs(final_signal),
                "final_signal": final_signal,
            }

    # Only return metadata for the first symbol if it exists (since regime is single symbol)
    main_metadata = next(iter(metadata_list.values())) if metadata_list else None

    return {"weights": weights, "signals": signals, "metadata": main_metadata}
