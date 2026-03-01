"""
Signal deduplicator module to prevent repeated orders.
"""
import time
import threading
from typing import Optional

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
            # For a 1H candle (3600s), TTL will be 7200s
            ttl_sec = max(tf * 2, 120)
            expiry = float(now + ttl_sec)
            
            # The key includes signal_ts. 
            # signal_ts represents the exact timestamp of the candle that triggered the signal.
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
                    except Exception: # pylint: disable=broad-exception-caught
                        pass

                exp = bucket.get(key)
                if exp is not None and float(exp) > now:
                    return True

                bucket[key] = expiry
                return False
        except Exception: # pylint: disable=broad-exception-caught
            return False

    def clear(self):
        """Clear all deduplication records. Useful for testing."""
        with self._signal_dedup_lock:
            self._signal_dedup.clear()

def get_signal_deduplicator() -> SignalDeduplicator:
    """Get the singleton instance of SignalDeduplicator."""
    return SignalDeduplicator()
