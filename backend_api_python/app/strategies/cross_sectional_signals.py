"""
截面策略信号生成：纯函数，根据 rankings、scores、配置、当前持仓生成 open/close 信号。
不依赖 Executor，current_positions 由调用方传入（通常来自 DataHandler 的 InputContext.positions）。
"""

from typing import Any, Dict, List


def generate_cross_sectional_signals(
    rankings: List[str],
    scores: Dict[str, float],
    trading_config: Dict[str, Any],
    current_positions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    根据排序结果和当前持仓生成截面策略信号。
    current_positions: 持仓列表，每项含 symbol、side 等，由 InputContext.positions 提供。
    """
    portfolio_size = trading_config.get("portfolio_size", 10)
    long_ratio = float(trading_config.get("long_ratio", 0.5))

    long_count = int(portfolio_size * long_ratio)
    short_count = portfolio_size - long_count

    long_symbols = set(rankings[:long_count]) if long_count > 0 else set()
    short_symbols = (
        set(rankings[-short_count:])
        if short_count > 0 and len(rankings) >= short_count
        else set()
    )

    current_long = {p["symbol"] for p in current_positions if p.get("side") == "long"}
    current_short = {p["symbol"] for p in current_positions if p.get("side") == "short"}

    signals: List[Dict[str, Any]] = []

    for symbol in long_symbols:
        if symbol not in current_long:
            if symbol in current_short:
                signals.append(
                    {"symbol": symbol, "type": "close_short", "score": scores.get(symbol, 0)}
                )
            signals.append(
                {"symbol": symbol, "type": "open_long", "score": scores.get(symbol, 0)}
            )

    for symbol in current_long:
        if symbol not in long_symbols:
            signals.append(
                {"symbol": symbol, "type": "close_long", "score": scores.get(symbol, 0)}
            )

    for symbol in short_symbols:
        if symbol not in current_short:
            if symbol in current_long:
                signals.append(
                    {"symbol": symbol, "type": "close_long", "score": scores.get(symbol, 0)}
                )
            signals.append(
                {"symbol": symbol, "type": "open_short", "score": scores.get(symbol, 0)}
            )

    for symbol in current_short:
        if symbol not in short_symbols:
            signals.append(
                {"symbol": symbol, "type": "close_short", "score": scores.get(symbol, 0)}
            )

    return signals
