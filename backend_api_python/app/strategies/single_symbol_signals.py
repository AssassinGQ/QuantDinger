"""
单标策略信号提取：纯函数，从 executed_df 列（buy/sell 或 4-way）解析出 pending_signals。
不依赖 Executor，由调用方传入 executed_df 和 trading_config。
"""

import time
from typing import Any, Dict, List

import pandas as pd


def extract_pending_signals_from_df(
    executed_df: pd.DataFrame,
    trading_config: Dict[str, Any],
    last_kline_time: int,
) -> List[Dict[str, Any]]:
    """
    从指标执行后的 DataFrame 提取待触发信号。
    支持 buy/sell 或 open_long/close_long/open_short/close_short 列格式。
    """
    pending_signals: List[Dict[str, Any]] = []

    if executed_df is None or len(executed_df) == 0:
        return pending_signals

    df = executed_df
    if "close" not in df.columns:
        return pending_signals

    if all(col in df.columns for col in ["buy", "sell"]) and not all(
        col in df.columns for col in ["open_long", "close_long", "open_short", "close_short"]
    ):
        td = trading_config.get("trade_direction", trading_config.get("tradeDirection", "both"))
        td = str(td or "both").lower()
        if td not in ["long", "short", "both"]:
            td = "both"

        buy = df["buy"].fillna(False).astype(bool)
        sell = df["sell"].fillna(False).astype(bool)

        df = df.copy()
        if td == "long":
            df["open_long"] = buy
            df["close_long"] = sell
            df["open_short"] = False
            df["close_short"] = False
        elif td == "short":
            df["open_long"] = False
            df["close_long"] = False
            df["open_short"] = sell
            df["close_short"] = buy
        else:
            df["open_long"] = buy
            df["close_short"] = buy
            df["open_short"] = sell
            df["close_long"] = sell

    if not all(col in df.columns for col in ["open_long", "close_long", "open_short", "close_short"]):
        return pending_signals

    signal_mode = trading_config.get("signal_mode", "confirmed")
    exit_signal_mode = trading_config.get("exit_signal_mode", "aggressive")

    entry_check_set: set = set()
    exit_check_set: set = set()

    if len(df) > 1:
        entry_check_set.add(len(df) - 2)
        exit_check_set.add(len(df) - 2)

    if signal_mode == "aggressive" and len(df) > 0:
        entry_check_set.add(len(df) - 1)

    if exit_signal_mode == "aggressive" and len(df) > 0:
        exit_check_set.add(len(df) - 1)

    check_indices = sorted(entry_check_set.union(exit_check_set), reverse=True)

    for idx in check_indices:
        close_price = float(df["close"].iloc[idx])
        if hasattr(df.index[idx], "timestamp"):
            signal_timestamp = int(df.index[idx].timestamp())
        else:
            signal_timestamp = last_kline_time if last_kline_time else int(time.time())

        def _add_signal(sig_type: str, trigger: float, pos_size: float):
            if not any(
                s["type"] == sig_type and s.get("timestamp") == signal_timestamp
                for s in pending_signals
            ):
                pending_signals.append(
                    {"type": sig_type, "trigger_price": trigger, "position_size": pos_size, "timestamp": signal_timestamp}
                )

        if idx in entry_check_set and df["open_long"].iloc[idx]:
            pos_size = 0.08
            if "position_size" in df.columns:
                ps = df["position_size"].iloc[idx]
                if ps > 0:
                    pos_size = float(ps)
            _add_signal("open_long", close_price, pos_size)

        if idx in exit_check_set and df["close_long"].iloc[idx]:
            _add_signal("close_long", close_price, 0)

        if idx in entry_check_set and df["open_short"].iloc[idx]:
            pos_size = 0.08
            if "position_size" in df.columns:
                ps = df["position_size"].iloc[idx]
                if ps > 0:
                    pos_size = float(ps)
            _add_signal("open_short", close_price, pos_size)

        if idx in exit_check_set and df["close_short"].iloc[idx]:
            _add_signal("close_short", close_price, 0)

        if idx in entry_check_set and "add_long" in df.columns and df["add_long"].iloc[idx]:
            pos_size = 0.06
            if "position_size" in df.columns:
                ps = df["position_size"].iloc[idx]
                if ps > 0:
                    pos_size = float(ps)
            _add_signal("add_long", close_price, pos_size)

        if idx in entry_check_set and "add_short" in df.columns and df["add_short"].iloc[idx]:
            pos_size = 0.06
            if "position_size" in df.columns:
                ps = df["position_size"].iloc[idx]
                if ps > 0:
                    pos_size = float(ps)
            _add_signal("add_short", close_price, pos_size)

        if idx in exit_check_set and "reduce_long" in df.columns and df["reduce_long"].iloc[idx]:
            reduce_pct = 0.1
            if "reduce_size" in df.columns:
                try:
                    reduce_pct = float(df["reduce_size"].iloc[idx] or 0)
                except Exception:
                    pass
            elif "position_size" in df.columns:
                try:
                    reduce_pct = float(df["position_size"].iloc[idx] or 0)
                except Exception:
                    pass
            if reduce_pct <= 0:
                reduce_pct = 0.1
            _add_signal("reduce_long", close_price, reduce_pct)

        if idx in exit_check_set and "reduce_short" in df.columns and df["reduce_short"].iloc[idx]:
            reduce_pct = 0.1
            if "reduce_size" in df.columns:
                try:
                    reduce_pct = float(df["reduce_size"].iloc[idx] or 0)
                except Exception:
                    pass
            elif "position_size" in df.columns:
                try:
                    reduce_pct = float(df["position_size"].iloc[idx] or 0)
                except Exception:
                    pass
            if reduce_pct <= 0:
                reduce_pct = 0.1
            _add_signal("reduce_short", close_price, reduce_pct)

    return pending_signals
