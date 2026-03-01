"""
Tests for app.services.signal_deduplicator module.
"""
import time
from app.services.signal_processor import get_signal_deduplicator

class TestSignalDeduplicator:
    """Test suite for SignalDeduplicator singleton."""

    def test_singleton_instance(self):
        """Test that get_signal_deduplicator returns a singleton."""
        instance1 = get_signal_deduplicator()
        instance2 = get_signal_deduplicator()
        assert instance1 is instance2

    def test_dedup_key_generation(self):
        """Test _dedup_key generates correct format."""
        deduplicator = get_signal_deduplicator()
        # pylint: disable=protected-access
        key = deduplicator._dedup_key(1, "BTC/USDT:USDT", "OPEN_LONG", 1000)
        assert key == "1|BTC/USDT|open_long|1000"

    def test_should_skip_signal(self):
        """Test basic deduplication logic."""
        deduplicator = get_signal_deduplicator()
        deduplicator.clear()
        
        now = int(time.time())
        # First time should not skip
        assert not deduplicator.should_skip_signal_once_per_candle(
            strategy_id=1,
            symbol="BTC/USDT",
            signal_type="open_long",
            signal_ts=1000,
            timeframe_seconds=60,
            now_ts=now
        )
        
        # Second time within candle should skip
        assert deduplicator.should_skip_signal_once_per_candle(
            strategy_id=1,
            symbol="BTC/USDT",
            signal_type="open_long",
            signal_ts=1000,
            timeframe_seconds=60,
            now_ts=now + 10
        )

    def test_expiry_logic(self):
        """Test that keys expire correctly."""
        deduplicator = get_signal_deduplicator()
        deduplicator.clear()
        
        now = int(time.time())
        # Add signal
        assert not deduplicator.should_skip_signal_once_per_candle(
            strategy_id=1,
            symbol="BTC/USDT",
            signal_type="open_long",
            signal_ts=1000,
            timeframe_seconds=60,
            now_ts=now
        )
        
        # After expiry (TTL is max(tf*2, 120) = 120s for 60s timeframe)
        assert not deduplicator.should_skip_signal_once_per_candle(
            strategy_id=1,
            symbol="BTC/USDT",
            signal_type="open_long",
            signal_ts=1000,
            timeframe_seconds=60,
            now_ts=now + 121
        )
