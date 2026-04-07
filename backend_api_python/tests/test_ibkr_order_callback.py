"""
Tests for IBKR fire-and-forget order callback flow.

Verifies that event callbacks (_on_order_status) correctly dispatch
_handle_fill / _handle_reject to the IO executor via TaskQueue, and that
the DB update logic in those handlers is correct.
"""
import threading
from unittest.mock import MagicMock, patch, call

import pytest

from app.services.live_trading.ibkr_trading.client import (
    IBKRClient,
    IBKRConfig,
    IBKROrderContext,
)


def _make_client():
    """Create a minimal IBKRClient for callback testing."""
    client = IBKRClient.__new__(IBKRClient)
    client.config = IBKRConfig()
    client.mode = "paper"
    client._ib = MagicMock()
    client._account = "DU999"
    client._order_contexts = {}
    client._commission_contexts = {}
    client._events_registered = False
    client._event_map = []
    client._reconnect_thread = None
    client._reconnect_stop = threading.Event()
    client._tq = MagicMock()
    client._ib_executor = MagicMock()
    client._io_executor = MagicMock()
    client._tq.submit.return_value = MagicMock()
    client._fire_submit = lambda fn, is_blocking=False: fn()

    import asyncio

    def _sync_ib(fn, timeout=60.0):
        if asyncio.iscoroutine(fn):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(fn)
            finally:
                loop.close()
        return fn()
    client._submit = _sync_ib

    async def _noop_ensure(*_a, **_kw):
        pass
    client._ensure_connected_async = _noop_ensure

    return client


def _make_ctx(order_id=100, **overrides):
    defaults = dict(
        order_id=order_id,
        pending_order_id=50,
        strategy_id=7,
        symbol="AAPL",
        signal_type="open_long",
        amount=10.0,
        market_type="USStock",
    )
    defaults.update(overrides)
    return IBKROrderContext(**defaults)


def _make_trade(order_id, status, filled=0.0, avg_price=0.0, log_messages=None):
    trade = MagicMock()
    trade.order.orderId = order_id
    trade.orderStatus.status = status
    trade.orderStatus.filled = filled
    trade.orderStatus.avgFillPrice = avg_price
    trade.orderStatus.remaining = 0
    if log_messages:
        trade.log = [MagicMock(message=m) for m in log_messages]
    else:
        trade.log = []
    return trade


# ===========================================================================
# Dispatch routing
# ===========================================================================

class TestCallbackDispatchRouting:
    """Verify _on_order_status routes to the correct handler."""

    def test_filled_dispatches_handle_fill(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=1)
        client._order_contexts[1] = ctx

        client._on_order_status(_make_trade(1, "Filled", 10.0, 155.0))

        assert 1 not in client._order_contexts  # popped for fill idempotency
        assert 1 in client._commission_contexts  # lingers for commissionReport
        assert len(fire_calls) == 1
        assert callable(fire_calls[0])

    def test_cancelled_with_fill_dispatches_handle_fill(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=2)
        client._order_contexts[2] = ctx

        client._on_order_status(_make_trade(2, "Cancelled", 5.0, 300.0))

        assert 2 not in client._order_contexts  # popped for fill idempotency
        assert 2 in client._commission_contexts  # lingers for commissionReport
        assert len(fire_calls) == 1

    def test_inactive_dispatches_handle_reject(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=3)
        client._order_contexts[3] = ctx

        client._on_order_status(_make_trade(3, "Inactive", 0, 0, ["Order rejected"]))

        assert 3 not in client._order_contexts
        assert len(fire_calls) == 1

    def test_api_error_dispatches_handle_reject(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=4)
        client._order_contexts[4] = ctx

        client._on_order_status(_make_trade(4, "ApiError", 0, 0, ["Error 10243"]))

        assert 4 not in client._order_contexts
        assert len(fire_calls) == 1

    def test_api_cancelled_dispatches_handle_reject(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=5)
        client._order_contexts[5] = ctx

        client._on_order_status(_make_trade(5, "ApiCancelled", 0, 0))

        assert 5 not in client._order_contexts
        assert len(fire_calls) == 1

    def test_validation_error_dispatches_handle_reject(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=6)
        client._order_contexts[6] = ctx

        client._on_order_status(_make_trade(6, "ValidationError", 0, 0))

        assert 6 not in client._order_contexts
        assert len(fire_calls) == 1

    def test_submitted_does_not_dispatch(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=7)
        client._order_contexts[7] = ctx

        client._on_order_status(_make_trade(7, "Submitted", 0, 0))

        assert 7 in client._order_contexts
        assert len(fire_calls) == 0

    def test_presubmitted_does_not_dispatch(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=8)
        client._order_contexts[8] = ctx

        client._on_order_status(_make_trade(8, "PreSubmitted", 0, 0))

        assert 8 in client._order_contexts
        assert len(fire_calls) == 0

    def test_cancelled_zero_fills_dispatches_reject(self):
        """Cancelled(filled=0) is treated as a rejection (e.g. lot-size error)."""
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=9)
        client._order_contexts[9] = ctx

        client._on_order_status(_make_trade(9, "Cancelled", 0, 0))

        assert 9 not in client._order_contexts
        assert len(fire_calls) == 1

    def test_untracked_order_ignored(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        client._on_order_status(_make_trade(999, "Filled", 10.0, 155.0))
        assert len(fire_calls) == 0


# ===========================================================================
# _handle_fill DB integration
# ===========================================================================

class TestHandleFillDB:

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    @patch("app.services.live_trading.records.record_trade")
    @patch("app.services.live_trading.records.apply_fill_to_local_position", return_value=(25.0, {}))
    @patch("app.services.live_trading.records.mark_order_sent")
    def test_full_fill_flow(self, mock_sent, mock_apply, mock_record, mock_notify):
        client = _make_client()
        ctx = _make_ctx(order_id=100, pending_order_id=50, strategy_id=7)

        client._handle_fill(ctx, filled=10.0, avg_price=155.0)

        mock_sent.assert_called_once()
        assert mock_sent.call_args[1]["order_id"] == 50
        assert mock_sent.call_args[1]["filled"] == 10.0
        assert mock_sent.call_args[1]["avg_price"] == 155.0

        mock_apply.assert_called_once_with(
            strategy_id=7, symbol="AAPL", signal_type="open_long",
            filled=10.0, avg_price=155.0,
        )

        mock_record.assert_called_once()
        assert mock_record.call_args[1]["strategy_id"] == 7
        assert mock_record.call_args[1]["price"] == 155.0
        assert mock_record.call_args[1]["amount"] == 10.0
        assert mock_record.call_args[1]["profit"] == 25.0

        mock_notify.assert_called_once_with(
            ctx, "filled", filled=10.0, avg_price=155.0,
        )

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    @patch("app.services.live_trading.records.mark_order_sent")
    def test_fill_without_strategy_skips_position_update(self, mock_sent, mock_notify):
        """If strategy_id=0, skip apply_fill and record_trade."""
        client = _make_client()
        ctx = _make_ctx(order_id=101, pending_order_id=51, strategy_id=0)

        client._handle_fill(ctx, filled=5.0, avg_price=200.0)

        mock_sent.assert_called_once()
        mock_notify.assert_called_once()

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    def test_fill_without_pending_id_skips_mark_sent(self, mock_notify):
        """If pending_order_id=0, skip mark_order_sent."""
        client = _make_client()
        ctx = _make_ctx(order_id=102, pending_order_id=0, strategy_id=0)

        client._handle_fill(ctx, filled=5.0, avg_price=200.0)
        mock_notify.assert_called_once()

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    @patch("app.services.live_trading.records.mark_order_sent", side_effect=Exception("DB error"))
    def test_fill_db_error_does_not_crash(self, mock_sent, mock_notify):
        """DB errors are caught and logged, not re-raised."""
        client = _make_client()
        ctx = _make_ctx(order_id=103, pending_order_id=52)

        client._handle_fill(ctx, filled=10.0, avg_price=155.0)
        mock_notify.assert_called_once()


# ===========================================================================
# _handle_reject DB integration
# ===========================================================================

class TestHandleRejectDB:

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    @patch("app.services.live_trading.records.mark_order_failed")
    def test_reject_marks_failed(self, mock_failed, mock_notify):
        client = _make_client()
        ctx = _make_ctx(order_id=200, pending_order_id=60)

        client._handle_reject(ctx, "Inactive", ["Order rejected by exchange"])

        mock_failed.assert_called_once()
        assert mock_failed.call_args[1]["order_id"] == 60
        assert "Inactive" in mock_failed.call_args[1]["error"]
        assert "Order rejected by exchange" in mock_failed.call_args[1]["error"]

        mock_notify.assert_called_once_with(
            ctx, "failed",
            error="Order rejected by exchange",
        )

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    @patch("app.services.live_trading.records.mark_order_failed")
    def test_reject_empty_error_msgs(self, mock_failed, mock_notify):
        client = _make_client()
        ctx = _make_ctx(order_id=201, pending_order_id=61)

        client._handle_reject(ctx, "ApiError", [])

        mock_failed.assert_called_once()
        assert "ApiError" in mock_failed.call_args[1]["error"]

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    def test_reject_no_pending_id_skips_mark(self, mock_notify):
        client = _make_client()
        ctx = _make_ctx(order_id=202, pending_order_id=0)

        client._handle_reject(ctx, "ApiError", ["Some error"])
        mock_notify.assert_called_once()


# ===========================================================================
# Scenario: full lifecycle
# ===========================================================================

class TestFullOrderLifecycle:
    """End-to-end: place order → event callback → DB update."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync")
    def test_place_then_fill(self, mock_ib_mod):
        mock_ib_mod.MarketOrder = MagicMock(return_value=MagicMock(orderId=0))
        mock_ib_mod.Stock = MagicMock()

        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        trade_mock = MagicMock()
        trade_mock.order.orderId = 777
        trade_mock.orderStatus.status = "Submitted"
        client._ib.placeOrder.return_value = trade_mock
        client._ib.qualifyContracts.return_value = [MagicMock()]

        import asyncio as _aio
        async def _mock_qualify_async(*args):
            return client._ib.qualifyContracts.return_value
        client._ib.qualifyContractsAsync = _mock_qualify_async
        client._ib.isConnected.return_value = True

        result = client.place_market_order(
            "AAPL", "buy", 10, "USStock",
            pending_order_id=88, strategy_id=12, signal_type="open_long",
        )

        assert result.success is True
        assert result.status == "Submitted"
        assert result.order_id == 777
        assert 777 in client._order_contexts

        # Simulate fill event
        fill_trade = MagicMock()
        fill_trade.order.orderId = 777
        fill_trade.orderStatus.status = "Filled"
        fill_trade.orderStatus.filled = 10.0
        fill_trade.orderStatus.avgFillPrice = 155.0
        fill_trade.log = []
        client._on_order_status(fill_trade)

        assert 777 not in client._order_contexts  # popped for fill idempotency
        assert 777 in client._commission_contexts  # lingers for commissionReport
        assert len(fire_calls) == 1
