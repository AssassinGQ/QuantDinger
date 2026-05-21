"""Cross-sectional signal generation and execution intent helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ExecutionIntent:
    """A serializable intent that separates signal and execution dates."""

    symbol: str
    signal_type: str
    signal_date: date
    execution_date: date
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "type": self.signal_type,
            "score": self.score,
            "signal_date": self.signal_date.isoformat(),
            "execution_date": self.execution_date.isoformat(),
        }


def _to_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(float(value)).date()
    raise ValueError(f"Unsupported date value: {value!r}")


def infer_signal_date(context: Dict[str, Any]) -> date:
    """Infer signal date from context with deterministic fallbacks."""
    if "signal_date" in context:
        return _to_date(context["signal_date"])
    if "as_of" in context:
        return _to_date(context["as_of"])
    if "current_time" in context:
        return _to_date(context["current_time"])
    return datetime.utcnow().date()


def infer_execution_date(context: Dict[str, Any], signal_dt: date) -> date:
    """Infer execution date; default to T+1."""
    if "execution_date" in context:
        return _to_date(context["execution_date"])
    return signal_dt + timedelta(days=1)


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


def build_execution_intents(
    signals: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Attach signal/execution ledger fields to raw signals."""
    ctx = context or {}
    signal_dt = infer_signal_date(ctx)
    execution_dt = infer_execution_date(ctx, signal_dt)
    intents: List[Dict[str, Any]] = []
    for signal in signals:
        intent = ExecutionIntent(
            symbol=str(signal.get("symbol", "")),
            signal_type=str(signal.get("type", "")),
            score=float(signal.get("score", 0) or 0),
            signal_date=signal_dt,
            execution_date=execution_dt,
        )
        intents.append({**signal, **intent.to_dict()})
    return intents
