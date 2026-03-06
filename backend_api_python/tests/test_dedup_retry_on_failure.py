"""
Tests for dedup-retry-on-failure behavior across three layers:

1. SignalDeduplicator (in-memory, signal_processor.py) — remove_key unblocks retry
2. SignalDeduplicator (in-memory, signal_deduplicator.py) — remove_key unblocks retry
3. PendingOrderEnqueuer (DB-level) — failed status bypasses candle dedup
4. PendingOrderWorker._mark_failed — clears both in-memory dedup caches
5. Normal dedup still works — successful/pending/processing orders are still deduped
"""
import json
import time
from unittest.mock import MagicMock, patch, call

import pytest

from app.services.signal_processor import (
    SignalDeduplicator as SPDeduplicator,
    get_signal_deduplicator as sp_get_dedup,
)
from app.services.signal_deduplicator import (
    SignalDeduplicator as SDDeduplicator,
    get_signal_deduplicator as sd_get_dedup,
)
from app.services.pending_order_enqueuer import PendingOrderEnqueuer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sp_dedup():
    d = sp_get_dedup()
    d.clear()
    return d


@pytest.fixture
def sd_dedup():
    d = sd_get_dedup()
    d.clear()
    return d


@pytest.fixture
def mock_dh():
    return MagicMock()


@pytest.fixture
def enqueuer(mock_dh):
    enq = PendingOrderEnqueuer()
    enq.data_handler = mock_dh
    return enq


# ===========================================================================
# Layer 1: SignalDeduplicator (signal_processor.py) — remove_key
# ===========================================================================

class TestSignalProcessorDedupRemoveKey:
    """Verify remove_key allows the same candle signal to be retried."""

    def test_remove_key_allows_retry(self, sp_dedup):
        now = int(time.time())
        kw = dict(strategy_id=10, symbol="AAPL", signal_type="open_long",
                  signal_ts=170000, timeframe_seconds=86400)

        assert not sp_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now)
        assert sp_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now + 1)

        sp_dedup.remove_key(10, "AAPL", "open_long", 170000)

        assert not sp_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now + 2)

    def test_remove_key_only_affects_target(self, sp_dedup):
        now = int(time.time())
        kw_a = dict(strategy_id=10, symbol="AAPL", signal_type="open_long",
                    signal_ts=170000, timeframe_seconds=86400)
        kw_b = dict(strategy_id=10, symbol="GOOGL", signal_type="open_long",
                    signal_ts=170000, timeframe_seconds=86400)

        assert not sp_dedup.should_skip_signal_once_per_candle(**kw_a, now_ts=now)
        assert not sp_dedup.should_skip_signal_once_per_candle(**kw_b, now_ts=now)

        sp_dedup.remove_key(10, "AAPL", "open_long", 170000)

        assert not sp_dedup.should_skip_signal_once_per_candle(**kw_a, now_ts=now + 1)
        assert sp_dedup.should_skip_signal_once_per_candle(**kw_b, now_ts=now + 1)

    def test_remove_key_nonexistent_is_noop(self, sp_dedup):
        sp_dedup.remove_key(999, "XYZ", "close_long", 0)

    def test_remove_key_different_signal_ts(self, sp_dedup):
        now = int(time.time())
        kw = dict(strategy_id=10, symbol="AAPL", signal_type="open_long",
                  signal_ts=170000, timeframe_seconds=86400)
        assert not sp_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now)

        sp_dedup.remove_key(10, "AAPL", "open_long", 999999)

        assert sp_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now + 1)


# ===========================================================================
# Layer 2: SignalDeduplicator (signal_deduplicator.py) — remove_key
# ===========================================================================

class TestSignalDeduplicatorRemoveKey:
    """Same tests for the signal_deduplicator.py copy."""

    def test_remove_key_allows_retry(self, sd_dedup):
        now = int(time.time())
        kw = dict(strategy_id=20, symbol="5", signal_type="open_long",
                  signal_ts=180000, timeframe_seconds=86400)

        assert not sd_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now)
        assert sd_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now + 1)

        sd_dedup.remove_key(20, "5", "open_long", 180000)

        assert not sd_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now + 2)

    def test_remove_key_only_affects_target(self, sd_dedup):
        now = int(time.time())
        kw_a = dict(strategy_id=20, symbol="5", signal_type="open_long",
                    signal_ts=180000, timeframe_seconds=86400)
        kw_b = dict(strategy_id=20, symbol="9618", signal_type="open_long",
                    signal_ts=180000, timeframe_seconds=86400)

        assert not sd_dedup.should_skip_signal_once_per_candle(**kw_a, now_ts=now)
        assert not sd_dedup.should_skip_signal_once_per_candle(**kw_b, now_ts=now)

        sd_dedup.remove_key(20, "5", "open_long", 180000)

        assert not sd_dedup.should_skip_signal_once_per_candle(**kw_a, now_ts=now + 1)
        assert sd_dedup.should_skip_signal_once_per_candle(**kw_b, now_ts=now + 1)


# ===========================================================================
# Layer 3: PendingOrderEnqueuer — DB-level candle dedup with failed bypass
# ===========================================================================

class TestEnqueuerCandleDedupFailedBypass:
    """
    When the last pending_order for the same candle is 'failed',
    the enqueuer should NOT skip — it should allow a new order.
    """

    def test_same_candle_sent_blocks(self, enqueuer):
        """Normal case: status=sent blocks new order for same candle."""
        ts = int(time.time())
        enqueuer.data_handler.find_recent_pending_order.return_value = {
            "id": 100, "status": "sent", "created_at": ts
        }
        result = enqueuer.enqueue_pending_order(
            strategy_id=1, symbol="AAPL", signal_type="open_long",
            amount=10, price=150.0, signal_ts=ts,
            market_type="spot", leverage=1.0, execution_mode="live",
        )
        assert result is None
        enqueuer.data_handler.insert_pending_order.assert_not_called()

    def test_same_candle_pending_blocks(self, enqueuer):
        """Normal case: status=pending blocks new order."""
        ts = int(time.time())
        enqueuer.data_handler.find_recent_pending_order.return_value = {
            "id": 101, "status": "pending", "created_at": ts
        }
        result = enqueuer.enqueue_pending_order(
            strategy_id=1, symbol="AAPL", signal_type="open_long",
            amount=10, price=150.0, signal_ts=ts,
            market_type="spot", leverage=1.0, execution_mode="live",
        )
        assert result is None
        enqueuer.data_handler.insert_pending_order.assert_not_called()

    def test_same_candle_processing_blocks(self, enqueuer):
        """Normal case: status=processing blocks new order."""
        ts = int(time.time())
        enqueuer.data_handler.find_recent_pending_order.return_value = {
            "id": 102, "status": "processing", "created_at": ts
        }
        result = enqueuer.enqueue_pending_order(
            strategy_id=1, symbol="AAPL", signal_type="open_long",
            amount=10, price=150.0, signal_ts=ts,
            market_type="spot", leverage=1.0, execution_mode="live",
        )
        assert result is None
        enqueuer.data_handler.insert_pending_order.assert_not_called()

    def test_same_candle_failed_allows_retry(self, enqueuer):
        """Key fix: status=failed should NOT block — allows new order."""
        ts = int(time.time())
        enqueuer.data_handler.find_recent_pending_order.return_value = {
            "id": 103, "status": "failed", "created_at": ts - 60
        }
        enqueuer.data_handler.get_user_id.return_value = 1
        enqueuer.data_handler.insert_pending_order.return_value = 200

        result = enqueuer.enqueue_pending_order(
            strategy_id=1, symbol="AAPL", signal_type="open_long",
            amount=10, price=150.0, signal_ts=ts,
            market_type="spot", leverage=1.0, execution_mode="live",
        )
        assert result == 200
        enqueuer.data_handler.insert_pending_order.assert_called_once()

    def test_same_candle_failed_within_cooldown_blocks(self, enqueuer):
        """Failed but within 30s cooldown should still be blocked by cooldown."""
        ts = int(time.time())
        enqueuer.data_handler.find_recent_pending_order.return_value = {
            "id": 104, "status": "failed", "created_at": ts - 5
        }
        result = enqueuer.enqueue_pending_order(
            strategy_id=1, symbol="AAPL", signal_type="open_long",
            amount=10, price=150.0, signal_ts=ts,
            market_type="spot", leverage=1.0, execution_mode="live",
        )
        assert result is None
        enqueuer.data_handler.insert_pending_order.assert_not_called()

    def test_no_signal_ts_uses_generic_dedup(self, enqueuer):
        """Without signal_ts, strict_candle_dedup is off; uses inflight/cooldown instead."""
        enqueuer.data_handler.find_recent_pending_order.return_value = {
            "id": 105, "status": "failed", "created_at": int(time.time()) - 5
        }
        result = enqueuer.enqueue_pending_order(
            strategy_id=1, symbol="BTC/USDT", signal_type="open_long",
            amount=0.1, price=50000.0, signal_ts=0,
            market_type="swap", leverage=1.0, execution_mode="live",
        )
        # signal_ts=0 → strict_candle_dedup=False → skips candle check
        # status=failed → not in (pending, processing) → goes to cooldown check
        # created_at is 5s ago < 30s cooldown → blocked
        assert result is None

    def test_no_signal_ts_failed_past_cooldown_allows(self, enqueuer):
        """Without signal_ts, failed order past cooldown allows new order."""
        enqueuer.data_handler.find_recent_pending_order.return_value = {
            "id": 106, "status": "failed", "created_at": int(time.time()) - 60
        }
        enqueuer.data_handler.get_user_id.return_value = 1
        enqueuer.data_handler.insert_pending_order.return_value = 300

        result = enqueuer.enqueue_pending_order(
            strategy_id=1, symbol="BTC/USDT", signal_type="open_long",
            amount=0.1, price=50000.0, signal_ts=0,
            market_type="swap", leverage=1.0, execution_mode="live",
        )
        assert result == 300


# ===========================================================================
# Layer 4: PendingOrderWorker._mark_failed — clears dedup caches
# ===========================================================================

class TestMarkFailedClearsDedupCache:
    """
    _mark_failed with signal info should clear both in-memory dedup singletons.
    """

    def test_mark_failed_clears_both_dedup_caches(self, sp_dedup, sd_dedup):
        now = int(time.time())
        kw = dict(strategy_id=10, symbol="AAPL", signal_type="open_long", signal_ts=170000)

        sp_dedup.should_skip_signal_once_per_candle(
            **kw, timeframe_seconds=86400, now_ts=now)
        sd_dedup.should_skip_signal_once_per_candle(
            **kw, timeframe_seconds=86400, now_ts=now)

        assert sp_dedup.should_skip_signal_once_per_candle(
            **kw, timeframe_seconds=86400, now_ts=now + 1)
        assert sd_dedup.should_skip_signal_once_per_candle(
            **kw, timeframe_seconds=86400, now_ts=now + 1)

        from app.services.live_trading import records

        with patch("app.services.live_trading.records.get_db_connection") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            records.mark_order_failed(
                order_id=999,
                error="ibkr_order_failed:test",
                strategy_id=10,
                symbol="AAPL",
                signal_type="open_long",
                signal_ts=170000,
            )

        assert not sp_dedup.should_skip_signal_once_per_candle(
            **kw, timeframe_seconds=86400, now_ts=now + 2)
        assert not sd_dedup.should_skip_signal_once_per_candle(
            **kw, timeframe_seconds=86400, now_ts=now + 2)

    def test_mark_failed_without_signal_info_no_clear(self, sp_dedup):
        now = int(time.time())
        kw = dict(strategy_id=10, symbol="AAPL", signal_type="open_long", signal_ts=170000)

        sp_dedup.should_skip_signal_once_per_candle(
            **kw, timeframe_seconds=86400, now_ts=now)

        from app.services.live_trading import records

        with patch("app.services.live_trading.records.get_db_connection") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            records.mark_order_failed(order_id=999, error="some_error")

        assert sp_dedup.should_skip_signal_once_per_candle(
            **kw, timeframe_seconds=86400, now_ts=now + 1)

    def test_mark_failed_updates_db_status(self):
        from app.services.live_trading import records

        with patch("app.services.live_trading.records.get_db_connection") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            records.mark_order_failed(order_id=42, error="test_error")

            mock_cursor.execute.assert_called_once()
            sql_call = mock_cursor.execute.call_args
            assert "status = 'failed'" in sql_call[0][0]
            assert sql_call[0][1] == ("test_error", 42)
            mock_conn.commit.assert_called_once()


# ===========================================================================
# Layer 5: Normal dedup — verify existing behavior is preserved
# ===========================================================================

class TestNormalDedupPreserved:
    """Ensure normal dedup behavior is not broken by the changes."""

    def test_same_candle_dedup_works(self, sp_dedup):
        now = int(time.time())
        kw = dict(strategy_id=1, symbol="BTC/USDT", signal_type="open_long",
                  signal_ts=160000, timeframe_seconds=3600)
        assert not sp_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now)
        assert sp_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now + 10)
        assert sp_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now + 100)

    def test_different_symbol_not_deduped(self, sp_dedup):
        now = int(time.time())
        kw_a = dict(strategy_id=1, symbol="BTC/USDT", signal_type="open_long",
                    signal_ts=160000, timeframe_seconds=3600)
        kw_b = dict(strategy_id=1, symbol="ETH/USDT", signal_type="open_long",
                    signal_ts=160000, timeframe_seconds=3600)
        assert not sp_dedup.should_skip_signal_once_per_candle(**kw_a, now_ts=now)
        assert not sp_dedup.should_skip_signal_once_per_candle(**kw_b, now_ts=now)

    def test_different_signal_type_not_deduped(self, sp_dedup):
        now = int(time.time())
        kw_a = dict(strategy_id=1, symbol="BTC/USDT", signal_type="open_long",
                    signal_ts=160000, timeframe_seconds=3600)
        kw_b = dict(strategy_id=1, symbol="BTC/USDT", signal_type="close_long",
                    signal_ts=160000, timeframe_seconds=3600)
        assert not sp_dedup.should_skip_signal_once_per_candle(**kw_a, now_ts=now)
        assert not sp_dedup.should_skip_signal_once_per_candle(**kw_b, now_ts=now)

    def test_different_candle_ts_not_deduped(self, sp_dedup):
        now = int(time.time())
        kw_a = dict(strategy_id=1, symbol="BTC/USDT", signal_type="open_long",
                    signal_ts=160000, timeframe_seconds=3600)
        kw_b = dict(strategy_id=1, symbol="BTC/USDT", signal_type="open_long",
                    signal_ts=163600, timeframe_seconds=3600)
        assert not sp_dedup.should_skip_signal_once_per_candle(**kw_a, now_ts=now)
        assert not sp_dedup.should_skip_signal_once_per_candle(**kw_b, now_ts=now)

    def test_different_strategy_not_deduped(self, sp_dedup):
        now = int(time.time())
        kw_a = dict(strategy_id=1, symbol="AAPL", signal_type="open_long",
                    signal_ts=160000, timeframe_seconds=86400)
        kw_b = dict(strategy_id=2, symbol="AAPL", signal_type="open_long",
                    signal_ts=160000, timeframe_seconds=86400)
        assert not sp_dedup.should_skip_signal_once_per_candle(**kw_a, now_ts=now)
        assert not sp_dedup.should_skip_signal_once_per_candle(**kw_b, now_ts=now)

    def test_ttl_expiry_allows_reentry(self, sp_dedup):
        now = int(time.time())
        kw = dict(strategy_id=1, symbol="BTC/USDT", signal_type="open_long",
                  signal_ts=160000, timeframe_seconds=3600)
        assert not sp_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now)
        assert sp_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now + 100)
        # TTL = max(3600*2, 120) = 7200s
        assert not sp_dedup.should_skip_signal_once_per_candle(**kw, now_ts=now + 7201)

    def test_clear_removes_all(self, sp_dedup):
        now = int(time.time())
        sp_dedup.should_skip_signal_once_per_candle(
            strategy_id=1, symbol="A", signal_type="open_long",
            signal_ts=1000, timeframe_seconds=60, now_ts=now)
        sp_dedup.should_skip_signal_once_per_candle(
            strategy_id=2, symbol="B", signal_type="close_long",
            signal_ts=2000, timeframe_seconds=60, now_ts=now)
        sp_dedup.clear()
        assert not sp_dedup.should_skip_signal_once_per_candle(
            strategy_id=1, symbol="A", signal_type="open_long",
            signal_ts=1000, timeframe_seconds=60, now_ts=now + 1)
        assert not sp_dedup.should_skip_signal_once_per_candle(
            strategy_id=2, symbol="B", signal_type="close_long",
            signal_ts=2000, timeframe_seconds=60, now_ts=now + 1)


# ===========================================================================
# Layer 6: End-to-end scenario — IBKR order fails then retries
# ===========================================================================

class TestEndToEndIBKRFailRetry:
    """
    Simulate: signal -> dedup registered -> order placed -> IBKR rejects ->
    _mark_failed clears dedup -> same signal re-enters -> new order allowed.
    """

    def test_ibkr_reject_then_retry_full_flow(self, sp_dedup, sd_dedup, enqueuer):
        now = int(time.time())
        signal_ts = 170000
        sid = 501
        symbol = "5"

        # Step 1: signal passes in-memory dedup
        assert not sp_dedup.should_skip_signal_once_per_candle(
            strategy_id=sid, symbol=symbol, signal_type="open_long",
            signal_ts=signal_ts, timeframe_seconds=86400, now_ts=now)

        # Step 2: signal enters enqueuer, no prior DB record
        enqueuer.data_handler.find_recent_pending_order.return_value = None
        enqueuer.data_handler.get_user_id.return_value = 1
        enqueuer.data_handler.insert_pending_order.return_value = 500
        pid = enqueuer.enqueue_pending_order(
            strategy_id=sid, symbol=symbol, signal_type="open_long",
            amount=100, price=65.0, signal_ts=signal_ts,
            market_type="spot", leverage=1.0, execution_mode="live",
        )
        assert pid == 500

        # Step 3: worker executes, IBKR rejects → mark_order_failed
        from app.services.live_trading import records
        with patch("app.services.live_trading.records.get_db_connection") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            records.mark_order_failed(
                order_id=500,
                error="ibkr_order_failed:Order Cancelled: Error 10349",
                strategy_id=sid, symbol=symbol,
                signal_type="open_long", signal_ts=signal_ts,
            )

        # Step 4: same signal re-enters — in-memory dedup should pass
        assert not sp_dedup.should_skip_signal_once_per_candle(
            strategy_id=sid, symbol=symbol, signal_type="open_long",
            signal_ts=signal_ts, timeframe_seconds=86400, now_ts=now + 60)

        # Step 5: same signal re-enters enqueuer — DB shows failed, should pass
        enqueuer.data_handler.find_recent_pending_order.return_value = {
            "id": 500, "status": "failed", "created_at": now - 60
        }
        enqueuer.data_handler.insert_pending_order.return_value = 501
        pid2 = enqueuer.enqueue_pending_order(
            strategy_id=sid, symbol=symbol, signal_type="open_long",
            amount=100, price=65.0, signal_ts=signal_ts,
            market_type="spot", leverage=1.0, execution_mode="live",
        )
        assert pid2 == 501
