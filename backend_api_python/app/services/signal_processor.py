"""
信号处理：风控叠加、状态过滤、排序、去重、选择。

返回选中的信号，由调用方执行。便于单独测试信号处理逻辑。
"""
import time
from typing import Any, Callable, Dict, List, Optional

from app.services.server_side_risk import (
    check_stop_loss_signal,
    check_take_profit_or_trailing_signal,
)


from app.services.data_handler import DataHandler

def position_state(positions: List[Dict[str, Any]]) -> str:
    """
    Return current position state for a strategy+symbol in local single-position mode.

    Returns: 'flat' | 'long' | 'short'
    """
    try:
        if not positions:
            return "flat"
        side = (positions[0].get("side") or "").strip().lower()
        if side in ("long", "short"):
            return side
    except Exception:
        pass
    return "flat"


def is_signal_allowed(state: str, signal_type: str) -> bool:
    """
    Enforce strict state machine:
    - flat: only open_long/open_short
    - long: only add_long/close_long
    - short: only add_short/close_short
    """
    st = (state or "flat").strip().lower()
    sig = (signal_type or "").strip().lower()
    if st == "flat":
        return sig in ("open_long", "open_short")
    if st == "long":
        return sig in ("add_long", "reduce_long", "close_long")
    if st == "short":
        return sig in ("add_short", "reduce_short", "close_short")
    return False


def signal_priority(signal_type: str) -> int:
    """
    Lower value = higher priority. We always close before (re)opening/adding.
    """
    sig = (signal_type or "").strip().lower()
    if sig.startswith("close_"):
        return 0
    if sig.startswith("reduce_"):
        return 1
    if sig.startswith("open_"):
        return 2
    if sig.startswith("add_"):
        return 3
    return 99


def process_signals(
    strategy_id: int,
    symbol: str,
    triggered_signals: List[Dict[str, Any]],
    current_price: float,
    trade_direction: str,
    leverage: float,
    market_type: str,
    trading_config: Dict[str, Any],
    timeframe_seconds: int,
    *,
    dedup_check: Optional[
        Callable[[int, str, str, int, int], bool]
    ] = None,
    now_ts: Optional[int] = None,
) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    信号处理：叠加风控、过滤、排序、去重，返回选中的一个信号及当前持仓。

    Args:
        dedup_check: 可选，(strategy_id, symbol, signal_type, signal_ts, tf_sec) -> True 表示跳过
        now_ts: 可选，当前时间戳

    Returns:
        (selected_signal, current_positions)。无选中信号时 selected_signal 为 None。
    """
    if not triggered_signals:
        return (None, [])

    data_handler = DataHandler()
    all_signals = list(triggered_signals)
    risk_tp = check_take_profit_or_trailing_signal(
        data_handler,
        strategy_id=strategy_id,
        symbol=symbol,
        current_price=float(current_price),
        market_type=market_type or "swap",
        leverage=float(leverage),
        trading_config=trading_config,
        timeframe_seconds=int(timeframe_seconds or 60),
    )
    if risk_tp:
        all_signals.append(risk_tp)
    risk_sl = check_stop_loss_signal(
        data_handler,
        strategy_id=strategy_id,
        symbol=symbol,
        current_price=float(current_price),
        market_type=market_type or "swap",
        leverage=float(leverage),
        trading_config=trading_config,
        timeframe_seconds=int(timeframe_seconds or 60),
    )
    if risk_sl:
        all_signals.append(risk_sl)

    current_positions = data_handler.get_current_positions(strategy_id, symbol)
    state = position_state(current_positions)
    candidates = [
        s for s in all_signals
        if is_signal_allowed(state, s.get("type"))
    ]
    if state == "flat" and candidates:
        td = (trade_direction or "both").strip().lower()
        if td == "long":
            candidates = [s for s in candidates if s.get("type") == "open_long"]
        elif td == "short":
            candidates = [s for s in candidates if s.get("type") == "open_short"]

    candidates = sorted(
        candidates,
        key=lambda s: (
            signal_priority(s.get("type")),
            int(s.get("timestamp") or 0),
            str(s.get("type") or ""),
        ),
    )

    now_i = int(now_ts or time.time())
    tf = int(timeframe_seconds or 60)

    for s in candidates:
        stype = s.get("type")
        sts = int(s.get("timestamp") or 0)
        if dedup_check is not None and dedup_check(
            strategy_id, symbol, str(stype or ""), sts, tf
        ):
            continue
        return (s, current_positions)

    return (None, current_positions)
