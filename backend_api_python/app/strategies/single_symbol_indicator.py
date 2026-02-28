"""
单标策略指标执行：纯函数，执行指标代码并返回执行后的 DataFrame 和 exec_env。
不依赖 Executor，数据由调用方（DataHandler 构建 InputContext）提供。
"""

import builtins
import traceback
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from app.services.indicator_params import IndicatorParamsParser, IndicatorCaller
from app.services.macro_data_service import MacroDataService
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _to_ratio(v: Any, default: float = 0.0) -> float:
    """Convert percent-like value to ratio in [0, 1]. Accepts 0~1 and 0~100."""
    try:
        x = float(v if v is not None else default)
    except (ValueError, TypeError):
        x = float(default or 0.0)
    if x > 1.0:
        x = x / 100.0
    if x < 0:
        x = 0.0
    if x > 1.0:
        x = 1.0
    return float(x)


def build_cfg_from_trading_config(trading_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a backtest-modal compatible config dict for indicator scripts.
    Frontend stores params as flat keys; backtest expects nested cfg.risk/cfg.scale/cfg.position.
    """
    tc = trading_config or {}
    stop_loss_pct = _to_ratio(tc.get("stop_loss_pct"))
    take_profit_pct = _to_ratio(tc.get("take_profit_pct"))
    trailing_enabled = bool(tc.get("trailing_enabled"))
    trailing_stop_pct = _to_ratio(tc.get("trailing_stop_pct"))
    trailing_activation_pct = _to_ratio(tc.get("trailing_activation_pct"))
    entry_pct = _to_ratio(tc.get("entry_pct"))
    trend_add_enabled = bool(tc.get("trend_add_enabled"))
    trend_add_step_pct = _to_ratio(tc.get("trend_add_step_pct"))
    trend_add_size_pct = _to_ratio(tc.get("trend_add_size_pct"))
    trend_add_max_times = int(tc.get("trend_add_max_times") or 0)
    dca_add_enabled = bool(tc.get("dca_add_enabled"))
    dca_add_step_pct = _to_ratio(tc.get("dca_add_step_pct"))
    dca_add_size_pct = _to_ratio(tc.get("dca_add_size_pct"))
    dca_add_max_times = int(tc.get("dca_add_max_times") or 0)
    trend_reduce_enabled = bool(tc.get("trend_reduce_enabled"))
    trend_reduce_step_pct = _to_ratio(tc.get("trend_reduce_step_pct"))
    trend_reduce_size_pct = _to_ratio(tc.get("trend_reduce_size_pct"))
    trend_reduce_max_times = int(tc.get("trend_reduce_max_times") or 0)
    adverse_reduce_enabled = bool(tc.get("adverse_reduce_enabled"))
    adverse_reduce_step_pct = _to_ratio(tc.get("adverse_reduce_step_pct"))
    adverse_reduce_size_pct = _to_ratio(tc.get("adverse_reduce_size_pct"))
    adverse_reduce_max_times = int(tc.get("adverse_reduce_max_times") or 0)

    return {
        "risk": {
            "stopLossPct": stop_loss_pct,
            "takeProfitPct": take_profit_pct,
            "trailing": {
                "enabled": trailing_enabled,
                "pct": trailing_stop_pct,
                "activationPct": trailing_activation_pct,
            },
        },
        "position": {"entryPct": entry_pct},
        "scale": {
            "trendAdd": {
                "enabled": trend_add_enabled,
                "stepPct": trend_add_step_pct,
                "sizePct": trend_add_size_pct,
                "maxTimes": trend_add_max_times,
            },
            "dcaAdd": {
                "enabled": dca_add_enabled,
                "stepPct": dca_add_step_pct,
                "sizePct": dca_add_size_pct,
                "maxTimes": dca_add_max_times,
            },
            "trendReduce": {
                "enabled": trend_reduce_enabled,
                "stepPct": trend_reduce_step_pct,
                "sizePct": trend_reduce_size_pct,
                "maxTimes": trend_reduce_max_times,
            },
            "adverseReduce": {
                "enabled": adverse_reduce_enabled,
                "stepPct": adverse_reduce_step_pct,
                "sizePct": adverse_reduce_size_pct,
                "maxTimes": adverse_reduce_max_times,
            },
        },
    }


def run_single_indicator(
    indicator_code: str,
    df: pd.DataFrame,
    trading_config: Dict[str, Any],
    initial_highest_price: float = 0.0,
    initial_position: int = 0,
    initial_avg_entry_price: float = 0.0,
    initial_position_count: int = 0,
    initial_last_add_price: float = 0.0,
) -> tuple[Optional[pd.DataFrame], dict]:
    """执行指标代码，返回执行后的 DataFrame 和执行环境。"""
    try:
        df = df.copy()
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
                else:
                    df[col] = df[col].astype("float64")

        ohlcv_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        df = df.dropna(subset=ohlcv_cols)

        if len(df) == 0:
            logger.warning("DataFrame is empty; cannot execute indicator script")
            return None, {}

        signals = pd.Series(0, index=df.index, dtype="float64")
        tc = dict(trading_config or {})
        cfg = build_cfg_from_trading_config(tc)

        user_indicator_params = tc.get("indicator_params", {})
        declared_params = IndicatorParamsParser.parse_params(indicator_code)
        merged_params = IndicatorParamsParser.merge_params(declared_params, user_indicator_params)
        user_id = tc.get("user_id", 1)
        indicator_id = tc.get("indicator_id")
        indicator_caller = IndicatorCaller(user_id, indicator_id)

        local_vars = {
            "df": df,
            "open": df["open"].astype("float64"),
            "high": df["high"].astype("float64"),
            "low": df["low"].astype("float64"),
            "close": df["close"].astype("float64"),
            "volume": df["volume"].astype("float64"),
            "signals": signals,
            "np": np,
            "pd": pd,
            "trading_config": tc,
            "config": tc,
            "cfg": cfg,
            "params": merged_params,
            "call_indicator": indicator_caller.call_indicator,
            "leverage": float(trading_config.get("leverage", 1)),
            "initial_capital": float(trading_config.get("initial_capital", 1000)),
            "commission": 0.001,
            "trade_direction": str(trading_config.get("trade_direction", "long")),
            "initial_highest_price": float(initial_highest_price),
            "initial_position": int(initial_position),
            "initial_avg_entry_price": float(initial_avg_entry_price),
            "initial_position_count": int(initial_position_count),
            "initial_last_add_price": float(initial_last_add_price),
        }
        for macro_col in MacroDataService.MACRO_COLUMNS:
            if macro_col in df.columns:
                local_vars[macro_col] = df[macro_col]

        def safe_import(name, *args, **kwargs):
            allowed = ["numpy", "pandas", "math", "json", "time"]
            if name in allowed or name.split(".")[0] in allowed:
                return builtins.__import__(name, *args, **kwargs)
            raise ImportError(f"不允许导入模块: {name}")

        safe_builtins = {
            k: getattr(builtins, k)
            for k in dir(builtins)
            if not k.startswith("_")
            and k
            not in [
                "eval",
                "exec",
                "compile",
                "open",
                "input",
                "help",
                "exit",
                "quit",
                "__import__",
                "copyright",
                "credits",
                "license",
            ]
        }
        safe_builtins["__import__"] = safe_import
        exec_env = local_vars.copy()
        exec_env["__builtins__"] = safe_builtins

        pre_import_code = "import numpy as np\nimport pandas as pd\n"
        exec(pre_import_code, exec_env)
        exec(indicator_code, exec_env)

        executed_df = exec_env.get("df", df)
        output_obj = exec_env.get("output")
        has_output_signals = (
            isinstance(output_obj, dict)
            and isinstance(output_obj.get("signals"), list)
            and len(output_obj.get("signals", [])) > 0
        )
        if has_output_signals and not all(
            col in executed_df.columns for col in ["buy", "sell"]
        ):
            raise ValueError(
                "Invalid indicator script: output['signals'] is provided, but df['buy'] and df['sell'] are missing."
            )

        return executed_df, exec_env
    except Exception as e:
        logger.error("Failed to execute indicator script: %s", e)
        logger.error(traceback.format_exc())
        return None, {}
