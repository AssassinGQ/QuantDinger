"""
信号处理：风控叠加、状态过滤、排序、去重、选择。

返回选中的信号，由调用方执行。便于单独测试信号处理逻辑。
"""
import time
from typing import Any, Dict, List, Optional, Tuple
import threading

from app.data_sources.base import TIMEFRAME_SECONDS
from app.services.server_side_risk import (
    check_stop_loss_signal,
    check_take_profit_or_trailing_signal,
)
from app.services.data_handler import DataHandler


class SignalDeduplicator:
    """
    In-memory signal de-dup cache to prevent repeated orders on the same candle signal.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SignalDeduplicator, cls).__new__(cls)
                cls._instance._signal_dedup = {}
                cls._instance._signal_dedup_lock = threading.Lock()
            return cls._instance

    def __init__(self):
        # Pylint needs these definitions
        if not hasattr(self, '_signal_dedup'):
            self._signal_dedup = {}
            self._signal_dedup_lock = threading.Lock()

    def _dedup_key(self, strategy_id: int, symbol: str, signal_type: str, signal_ts: int) -> str:
        sym = (symbol or "").strip().upper()
        if ":" in sym:
            sym = sym.split(":", 1)[0]
        return f"{int(strategy_id)}|{sym}|{(signal_type or '').strip().lower()}|{int(signal_ts or 0)}"

    def should_skip_signal_once_per_candle(
        self,
        strategy_id: int,
        symbol: str,
        signal_type: str,
        signal_ts: int,
        timeframe_seconds: int,
        now_ts: Optional[int] = None,
    ) -> bool:
        """Check if a signal should be skipped to avoid duplication within the same candle."""
        try:
            now = int(now_ts or time.time())
            tf = int(timeframe_seconds or 0)
            if tf <= 0:
                tf = 60
            # Keep keys long enough to cover at least the next candle.
            ttl_sec = max(tf * 2, 120)
            expiry = float(now + ttl_sec)
            key = self._dedup_key(strategy_id, symbol, signal_type, int(signal_ts or 0))

            with self._signal_dedup_lock:
                bucket = self._signal_dedup.get(int(strategy_id))
                if bucket is None:
                    bucket = {}
                    self._signal_dedup[int(strategy_id)] = bucket

                # Opportunistic cleanup
                stale = [k for k, exp in bucket.items() if float(exp) <= now]
                for k in stale[:512]:
                    try:
                        del bucket[k]
                    except (KeyError, TypeError):
                        pass

                exp = bucket.get(key)
                if exp is not None and float(exp) > now:
                    return True

                bucket[key] = expiry
                return False
        except (ValueError, TypeError, KeyError):
            return False

    def remove_key(self, strategy_id: int, symbol: str, signal_type: str, signal_ts: int):
        """Remove a specific dedup key so the same signal can be retried."""
        try:
            key = self._dedup_key(strategy_id, symbol, signal_type, int(signal_ts or 0))
            with self._signal_dedup_lock:
                bucket = self._signal_dedup.get(int(strategy_id))
                if bucket and key in bucket:
                    del bucket[key]
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def clear(self):
        """Clear all deduplication records. Useful for testing."""
        with self._signal_dedup_lock:
            self._signal_dedup.clear()

def get_signal_deduplicator() -> SignalDeduplicator:
    """Get the singleton instance of SignalDeduplicator."""
    return SignalDeduplicator()


def position_state(positions: List[Dict[str, Any]]) -> str:
    """
    Return current position state for a strategy+symbol in local single-position mode.

    Returns: 'flat' | 'long' | 'short'
    """
    try:
        if not positions:
            return "flat"
        pos = positions[0]
        size = float(pos.get("size") or 0)
        if size <= 0:
            return "flat"
        side = (pos.get("side") or "").strip().lower()
        if side in ("long", "short"):
            return side
    except (KeyError, TypeError, AttributeError, ValueError):
        pass
    return "flat"

def is_signal_allowed(state: str, signal_type: str) -> bool:
    """
    Enforce strict state machine:
    - flat: only open_long/open_short
    - long: only add_long/reduce_long/close_long
    - short: only add_short/reduce_short/close_short
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
    strategy_ctx: Dict[str, Any],
    symbol: str,
    triggered_signals: List[Dict[str, Any]],
    current_price: float,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    信号处理：叠加风控、过滤、排序、去重，返回选中的一个信号及当前持仓。

    Args:
        strategy_ctx: 策略上下文(包含 ID, config 等)
        symbol: 交易对
        triggered_signals: 指标产生的原始信号列表
        current_price: 当前价格
        now_ts: 可选，当前时间戳

    Returns:
        (selected_signal, current_positions)。无选中信号时 selected_signal 为 None。
    """
    if not triggered_signals:
        return (None, [])

    strategy_id = int(strategy_ctx.get("id") or 0)
    leverage = float(strategy_ctx.get("_leverage", 1.0))
    market_type = strategy_ctx.get("_market_type", "swap")
    trading_config = strategy_ctx.get("trading_config") or {}

    # Extract trade direction and timeframe from config
    trade_direction = "long" if market_type == "spot" else trading_config.get("trade_direction", "long")

    # Calculate timeframe seconds based on strategy configuration
    tf_str = str(trading_config.get("timeframe", "1H")).strip()
    if tf_str not in TIMEFRAME_SECONDS:
        tf_str = tf_str.upper() if tf_str.islower() else tf_str.lower()
    timeframe_seconds = int(TIMEFRAME_SECONDS.get(tf_str, 3600))

    data_handler = DataHandler()
    deduplicator = get_signal_deduplicator()
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

    for s in candidates:
        stype = s.get("type")
        sts = int(s.get("timestamp") or 0)
        # timeframe_seconds defines the candle period for dedup TTL
        if deduplicator.should_skip_signal_once_per_candle(
            strategy_id, symbol, str(stype or ""), sts, timeframe_seconds
        ):
            continue
        return (s, current_positions)

    return (None, current_positions)
