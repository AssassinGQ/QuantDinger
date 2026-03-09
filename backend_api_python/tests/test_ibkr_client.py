"""
Tests for IBKR client: quantity guard, fire-and-forget order flow, connection retry,
RTH gate, and the AsyncWorker-based task dispatch mechanism.
"""
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.services.live_trading.ibkr_trading.client import (
    IBKRClient,
    IBKRConfig,
    IBKROrderContext,
)
from app.services.live_trading.base import BaseStatefulClient, LiveOrderResult

@pytest.fixture(autouse=True)
def _always_rth():
    """Default: assume market is open so is_market_open doesn't block tests."""
    with patch("app.services.live_trading.ibkr_trading.trading_hours.is_rth", return_value=True):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_ib_insync():
    """Create a mock ib_insync module with necessary classes."""
    mock_mod = MagicMock()

    class MockMarketOrder:
        def __init__(self, action, totalQuantity, account="", tif=""):
            self.action = action
            self.totalQuantity = totalQuantity
            self.account = account
            self.tif = tif
            self.orderId = 0

    class MockLimitOrder:
        def __init__(self, action, totalQuantity, lmtPrice, account="", tif=""):
            self.action = action
            self.totalQuantity = totalQuantity
            self.lmtPrice = lmtPrice
            self.account = account
            self.tif = tif
            self.orderId = 0

    class MockStock:
        def __init__(self, symbol, exchange, currency):
            self.symbol = symbol
            self.exchange = exchange
            self.currency = currency

    mock_mod.MarketOrder = MockMarketOrder
    mock_mod.LimitOrder = MockLimitOrder
    mock_mod.Stock = MockStock
    mock_mod.IB = MagicMock
    return mock_mod


def _make_trade_mock(status="Filled", filled=10.0, avg_price=150.0,
                     remaining=0.0, order_id=42, log_messages=None):
    """Create a mock trade object."""
    trade = MagicMock()
    trade.order.orderId = order_id
    trade.orderStatus.status = status
    trade.orderStatus.filled = filled
    trade.orderStatus.avgFillPrice = avg_price
    trade.orderStatus.remaining = remaining
    if log_messages:
        trade.log = [MagicMock(message=m) for m in log_messages]
    else:
        trade.log = []
    return trade


def _make_client_with_mock_ib():
    """Create an IBKRClient with mocked internals, bypassing the real AsyncWorker.

    _submit_sync runs callables synchronously so tests don't depend on threading.
    """
    client = IBKRClient.__new__(IBKRClient)
    client.config = IBKRConfig()
    client._ib = MagicMock()
    client._account = "DU123456"
    client._ib.isConnected.return_value = True
    client._ib.qualifyContracts.return_value = [MagicMock()]

    # Mock AsyncWorker
    client._worker = MagicMock()
    # Make submit return a MagicMock future (for fire-and-forget in callbacks)
    client._worker.submit.return_value = MagicMock()

    # Fire-and-forget order contexts
    client._order_contexts = {}
    client._events_registered = False

    # Reconnection thread state
    client._reconnect_thread = None
    client._reconnect_stop = threading.Event()

    # Bypass worker: run submitted callables synchronously
    def _sync_submit(fn, timeout=60.0):
        return fn()

    client._submit_sync = _sync_submit

    def _sync_retry(task_factory, timeout=15.0, retries=2, delay=1.0):
        return task_factory()()

    client._submit_with_retry = _sync_retry

    return client


# ===========================================================================
# Worker thread tests (now AsyncWorker-based)
# ===========================================================================

class TestWorkerThread:
    """Verify the AsyncWorker-based task dispatch mechanism."""

    def test_submit_runs_via_worker(self):
        """_submit_sync should execute the callable via AsyncWorker."""
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        client._order_contexts = {}
        client._events_registered = False
        client._reconnect_thread = None
        client._reconnect_stop = threading.Event()

        from app.services.live_trading.async_worker import AsyncWorker
        client._worker = AsyncWorker(name="test-ibkr")
        client._worker.start()

        caller_tid = threading.current_thread().ident
        result_holder = {}

        def task():
            result_holder["tid"] = threading.current_thread().ident
            return 42

        result = client._submit_sync(task, timeout=5.0)

        assert result == 42
        assert result_holder["tid"] != caller_tid
        client._worker.shutdown()

    def test_submit_propagates_exception(self):
        """Exceptions in the worker should propagate to the caller."""
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        client._order_contexts = {}
        client._events_registered = False
        client._reconnect_thread = None
        client._reconnect_stop = threading.Event()

        from app.services.live_trading.async_worker import AsyncWorker
        client._worker = AsyncWorker(name="test-ibkr-exc")
        client._worker.start()

        def bad_task():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            client._submit_sync(bad_task, timeout=5.0)
        client._worker.shutdown()

    def test_shutdown_stops_worker(self):
        """shutdown() should stop the worker."""
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        client._order_contexts = {}
        client._events_registered = False
        client._reconnect_thread = None
        client._reconnect_stop = threading.Event()

        from app.services.live_trading.async_worker import AsyncWorker
        client._worker = AsyncWorker(name="test-ibkr-shutdown")
        client._worker.start()

        assert client._worker.running
        client.shutdown()
        assert not client._worker.running


# ===========================================================================
# Whole-number quantity guard tests
# ===========================================================================

class TestQuantityGuard:
    """Client rejects non-whole-number and non-positive quantities."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_accepts_whole_number(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=100)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("AAPL", "buy", 7, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.totalQuantity == 7
        assert result.success is True

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_limit_order_accepts_whole_number(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=101)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_limit_order("GOOGL", "buy", 3, 180.0, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.totalQuantity == 3
        assert result.success is True

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_accepts_float_whole(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=102)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("AAPL", "buy", 10.0, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.totalQuantity == 10.0
        assert result.success is True

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_rejects_fractional(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("AAPL", "buy", 7.8, "USStock")
        assert result.success is False
        assert "whole number" in result.message.lower()
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_limit_order_rejects_fractional(self):
        client = _make_client_with_mock_ib()
        result = client.place_limit_order("AAPL", "buy", 3.5, 150.0, "USStock")
        assert result.success is False
        assert "whole number" in result.message.lower()
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_rejects_zero(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("AAPL", "buy", 0, "USStock")
        assert result.success is False
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_rejects_negative(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("AAPL", "buy", -5, "USStock")
        assert result.success is False
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_hshare_rejects_non_lot_multiple(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("00005", "buy", 3, "HShare")
        assert result.success is False
        assert "400" in result.message
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_hshare_accepts_lot_multiple(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=103)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("00005", "buy", 400, "HShare")
        assert result.success is True

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_hshare_unknown_symbol_accepts_any_integer(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=104)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("00388", "buy", 7, "HShare")
        assert result.success is True


# ===========================================================================
# Fire-and-forget order tests
# ===========================================================================

class TestFireAndForgetOrder:
    """Verify place_market_order/place_limit_order return immediately with Submitted status."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_returns_submitted(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=200)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("AAPL", "buy", 10, "USStock")
        assert result.success is True
        assert result.status == "Submitted"
        assert result.order_id == 200
        assert result.filled == 0.0
        assert result.avg_price == 0.0

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_limit_order_returns_submitted(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=201)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_limit_order("AAPL", "buy", 10, 150.0, "USStock")
        assert result.success is True
        assert result.status == "Submitted"
        assert result.order_id == 201

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_order_context_registered_on_placement(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=300)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order(
            "AAPL", "buy", 10, "USStock",
            pending_order_id=55, strategy_id=7, signal_type="open_long",
            strategy_name="TestStrat",
        )

        assert result.success is True
        assert 300 in client._order_contexts
        ctx = client._order_contexts[300]
        assert ctx.pending_order_id == 55
        assert ctx.strategy_id == 7
        assert ctx.signal_type == "open_long"
        assert ctx.symbol == "AAPL"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_invalid_contract_rejected(self):
        client = _make_client_with_mock_ib()
        client._ib.qualifyContracts.return_value = []
        result = client.place_market_order("INVALID", "buy", 10, "USStock")
        assert result.success is False
        assert "Invalid contract" in result.message

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_sell_action_correct(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=301)
        client._ib.placeOrder.return_value = trade_mock
        client.place_market_order("AAPL", "sell", 10, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.action == "SELL"


# ===========================================================================
# TIF = 'DAY' tests
# ===========================================================================

class TestTifDay:
    """Verify that orders explicitly set tif='DAY' to prevent Error 10349."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_sets_tif_day(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=400)
        client._ib.placeOrder.return_value = trade_mock
        client.place_market_order("AAPL", "buy", 10, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.tif == "DAY"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_limit_order_sets_tif_day(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=401)
        client._ib.placeOrder.return_value = trade_mock
        client.place_limit_order("GOOGL", "buy", 5, 180.0, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.tif == "DAY"


# ===========================================================================
# Terminal status sets
# ===========================================================================

class TestTerminalStatusSets:

    def test_terminal_statuses(self):
        expected = {"Filled", "Cancelled", "ApiCancelled", "Inactive", "ApiError", "ValidationError"}
        assert IBKRClient._TERMINAL_STATUSES == expected

    def test_rejected_statuses(self):
        expected = {"Cancelled", "ApiCancelled", "Inactive", "ApiError", "ValidationError"}
        assert IBKRClient._REJECTED_STATUSES == expected

    def test_filled_is_terminal_not_rejected(self):
        assert "Filled" in IBKRClient._TERMINAL_STATUSES
        assert "Filled" not in IBKRClient._REJECTED_STATUSES

    def test_submitted_is_not_terminal(self):
        assert "Submitted" not in IBKRClient._TERMINAL_STATUSES

    def test_presubmitted_is_not_terminal(self):
        assert "PreSubmitted" not in IBKRClient._TERMINAL_STATUSES


# ===========================================================================
# Event registration tests
# ===========================================================================

class TestEventRegistration:
    """Verify event registration and callback lifecycle."""

    def test_register_events_sets_flag(self):
        client = _make_client_with_mock_ib()
        assert client._events_registered is False
        client._register_events()
        assert client._events_registered is True

    def test_register_events_idempotent(self):
        client = _make_client_with_mock_ib()
        client._register_events()
        first_call_count = client._ib.orderStatusEvent.__iadd__.call_count
        client._register_events()
        assert client._ib.orderStatusEvent.__iadd__.call_count == first_call_count

    def test_disconnected_resets_flag(self):
        client = _make_client_with_mock_ib()
        client._events_registered = True
        client._on_disconnected()
        assert client._events_registered is False

    def test_register_events_requires_ib(self):
        client = _make_client_with_mock_ib()
        client._ib = None
        client._register_events()
        assert client._events_registered is False


# ===========================================================================
# Event callback tests (fire-and-forget)
# ===========================================================================

class TestEventCallbacks:
    """Verify event callbacks dispatch to _handle_fill/_handle_reject."""

    def test_on_order_status_filled_triggers_handle_fill(self):
        client = _make_client_with_mock_ib()
        ctx = IBKROrderContext(order_id=42, pending_order_id=10, strategy_id=5, symbol="AAPL")
        client._order_contexts[42] = ctx

        trade = _make_trade_mock(status="Filled", filled=10.0, avg_price=155.0, order_id=42)
        client._on_order_status(trade)

        # Context should be consumed
        assert 42 not in client._order_contexts
        # _handle_fill was dispatched via worker.submit
        client._worker.submit.assert_called_once()

    def test_on_order_status_cancelled_with_fill_triggers_handle_fill(self):
        client = _make_client_with_mock_ib()
        ctx = IBKROrderContext(order_id=43, pending_order_id=11, strategy_id=5, symbol="AAPL")
        client._order_contexts[43] = ctx

        trade = _make_trade_mock(status="Cancelled", filled=5.0, avg_price=300.0, order_id=43)
        client._on_order_status(trade)

        assert 43 not in client._order_contexts
        client._worker.submit.assert_called_once()

    def test_on_order_status_hard_terminal_triggers_handle_reject(self):
        client = _make_client_with_mock_ib()
        ctx = IBKROrderContext(order_id=44, pending_order_id=12, strategy_id=5, symbol="AAPL")
        client._order_contexts[44] = ctx

        trade = _make_trade_mock(
            status="Inactive", filled=0, avg_price=0, order_id=44,
            log_messages=["Order rejected"]
        )
        client._on_order_status(trade)

        assert 44 not in client._order_contexts
        client._worker.submit.assert_called_once()

    def test_on_order_status_ignores_untracked_order(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=10.0, avg_price=155.0, order_id=99)
        client._on_order_status(trade)
        client._worker.submit.assert_not_called()

    def test_on_order_status_active_does_not_dispatch(self):
        client = _make_client_with_mock_ib()
        ctx = IBKROrderContext(order_id=45, pending_order_id=13, strategy_id=5, symbol="AAPL")
        client._order_contexts[45] = ctx

        trade = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=45)
        client._on_order_status(trade)

        # Still tracked, not consumed
        assert 45 in client._order_contexts
        client._worker.submit.assert_not_called()

    def test_on_order_status_cancelled_zero_fills_waits(self):
        """Cancelled with 0 fills is NOT a rejection — IBKR can recover."""
        client = _make_client_with_mock_ib()
        ctx = IBKROrderContext(order_id=46, pending_order_id=14, strategy_id=5, symbol="AAPL")
        client._order_contexts[46] = ctx

        trade = _make_trade_mock(status="Cancelled", filled=0, avg_price=0, order_id=46)
        client._on_order_status(trade)

        # Cancelled with 0 fills: not in HARD_TERMINAL, not filled>0 → no dispatch
        # Context stays because IBKR may recover (Cancelled → PreSubmitted → Filled)
        assert 46 in client._order_contexts
        client._worker.submit.assert_not_called()


# ===========================================================================
# _handle_fill / _handle_reject unit tests
# ===========================================================================

class TestHandleFill:
    """Verify _handle_fill calls the right DB operations."""

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    @patch("app.services.live_trading.records.record_trade")
    @patch("app.services.live_trading.records.apply_fill_to_local_position", return_value=(10.5, {}))
    @patch("app.services.live_trading.records.mark_order_sent")
    def test_handle_fill_updates_db(self, mock_sent, mock_apply, mock_trade, mock_notify):
        client = _make_client_with_mock_ib()
        ctx = IBKROrderContext(
            order_id=100, pending_order_id=55, strategy_id=7,
            symbol="AAPL", signal_type="open_long", amount=10,
        )

        client._handle_fill(ctx, filled=10.0, avg_price=155.0)

        mock_sent.assert_called_once()
        sent_kwargs = mock_sent.call_args
        assert sent_kwargs[1]["order_id"] == 55
        assert sent_kwargs[1]["filled"] == 10.0

        mock_apply.assert_called_once_with(
            strategy_id=7, symbol="AAPL", signal_type="open_long",
            filled=10.0, avg_price=155.0,
        )

        mock_trade.assert_called_once()
        mock_notify.assert_called_once()

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    @patch("app.services.live_trading.records.mark_order_sent")
    def test_handle_fill_no_strategy_skips_position(self, mock_sent, mock_notify):
        client = _make_client_with_mock_ib()
        ctx = IBKROrderContext(order_id=101, pending_order_id=56, strategy_id=0, symbol="AAPL")

        client._handle_fill(ctx, filled=10.0, avg_price=155.0)

        mock_sent.assert_called_once()
        mock_notify.assert_called_once()

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    def test_handle_fill_no_pending_id_skips_mark(self, mock_notify):
        client = _make_client_with_mock_ib()
        ctx = IBKROrderContext(order_id=102, pending_order_id=0, strategy_id=0, symbol="AAPL")

        client._handle_fill(ctx, filled=10.0, avg_price=155.0)
        mock_notify.assert_called_once()


class TestHandleReject:

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    @patch("app.services.live_trading.records.mark_order_failed")
    def test_handle_reject_marks_failed(self, mock_failed, mock_notify):
        client = _make_client_with_mock_ib()
        ctx = IBKROrderContext(
            order_id=200, pending_order_id=60, strategy_id=8,
            symbol="GOOGL", signal_type="open_long",
        )

        client._handle_reject(ctx, "Inactive", ["Order rejected by exchange"])

        mock_failed.assert_called_once()
        args = mock_failed.call_args
        assert args[1]["order_id"] == 60
        assert "Inactive" in args[1]["error"]
        mock_notify.assert_called_once()

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    def test_handle_reject_no_pending_id_skips_mark(self, mock_notify):
        client = _make_client_with_mock_ib()
        ctx = IBKROrderContext(order_id=201, pending_order_id=0, strategy_id=0, symbol="AAPL")

        client._handle_reject(ctx, "ApiError", ["Error"])
        mock_notify.assert_called_once()


# ===========================================================================
# Connection retry tests
# ===========================================================================

class TestConnectionRetry:

    def test_succeeds_on_first_attempt(self):
        client = _make_client_with_mock_ib()
        client._ib.isConnected.return_value = True
        client._ensure_connected()

    def test_retries_and_succeeds_on_second_attempt(self):
        client = _make_client_with_mock_ib()
        call_count = {"n": 0}

        def mock_connect():
            call_count["n"] += 1
            if call_count["n"] < 2:
                client._ib.isConnected.return_value = False
                return False
            client._ib.isConnected.return_value = True
            return True

        client._ib.isConnected.return_value = False
        with patch.object(client, "_do_connect", side_effect=mock_connect):
            client._ensure_connected(retries=3, delay=0.01)
        assert call_count["n"] == 2

    def test_raises_after_all_retries_exhausted(self):
        client = _make_client_with_mock_ib()
        client._ib.isConnected.return_value = False

        with patch.object(client, "_do_connect", return_value=False):
            with pytest.raises(ConnectionError, match="Cannot connect to IBKR after 3 attempts"):
                client._ensure_connected(retries=3, delay=0.01)

    def test_no_retry_when_already_connected(self):
        client = _make_client_with_mock_ib()
        client._ib.isConnected.return_value = True
        with patch.object(client, "_do_connect") as mock_connect:
            client._ensure_connected()
            mock_connect.assert_not_called()


# ===========================================================================
# RTH gate tests
# ===========================================================================

class TestRTHGate:
    """Verify is_market_open returns correct result based on RTH status."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    @patch("app.services.live_trading.ibkr_trading.trading_hours.is_rth", return_value=False)
    def test_is_market_open_returns_false_outside_rth(self, _mock_rth):
        client = _make_client_with_mock_ib()
        is_open, reason = client.is_market_open("AAPL", "USStock")
        assert is_open is False
        assert "market closed" in reason.lower()

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    @patch("app.services.live_trading.ibkr_trading.trading_hours.is_rth", return_value=True)
    def test_is_market_open_returns_true_during_rth(self, _mock_rth):
        client = _make_client_with_mock_ib()
        is_open, reason = client.is_market_open("AAPL", "USStock")
        assert is_open is True
        assert reason == ""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    @patch("app.services.live_trading.ibkr_trading.trading_hours.is_rth", return_value=True)
    def test_market_order_allowed_during_rth(self, _mock_rth):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=500)
        client._ib.placeOrder.return_value = trade
        result = client.place_market_order("AAPL", "buy", 10, "USStock")
        assert result.success is True
        client._ib.placeOrder.assert_called_once()


# ===========================================================================
# Submit-with-retry tests
# ===========================================================================

class TestSubmitWithRetry:
    """Verify _submit_with_retry provides automatic retry on connection failures."""

    def test_succeeds_on_first_attempt(self):
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        client._order_contexts = {}
        client._events_registered = False
        client._reconnect_thread = None
        client._reconnect_stop = threading.Event()

        from app.services.live_trading.async_worker import AsyncWorker
        client._worker = AsyncWorker(name="test-retry")
        client._worker.start()

        result = client._submit_with_retry(
            lambda: lambda: 42, timeout=5.0, retries=2,
        )
        assert result == 42
        client._worker.shutdown()

    def test_retries_on_connection_error(self):
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = MagicMock()
        client._ib.isConnected.return_value = True
        client._account = ""
        client._order_contexts = {}
        client._events_registered = False
        client._reconnect_thread = None
        client._reconnect_stop = threading.Event()

        from app.services.live_trading.async_worker import AsyncWorker
        client._worker = AsyncWorker(name="test-retry2")
        client._worker.start()

        call_count = [0]
        def task():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ConnectionError("disconnected")
            return "ok"

        with patch.object(client, "_do_connect", return_value=True):
            result = client._submit_with_retry(
                lambda: task, timeout=5.0, retries=3, delay=0.01,
            )
        assert result == "ok"
        assert call_count[0] == 2
        client._worker.shutdown()

    def test_raises_after_all_retries_exhausted(self):
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = MagicMock()
        client._ib.isConnected.return_value = False
        client._account = ""
        client._order_contexts = {}
        client._events_registered = False
        client._reconnect_thread = None
        client._reconnect_stop = threading.Event()

        from app.services.live_trading.async_worker import AsyncWorker
        client._worker = AsyncWorker(name="test-retry3")
        client._worker.start()

        def always_fail():
            raise ConnectionError("still disconnected")

        with patch.object(client, "_do_connect", return_value=False):
            with pytest.raises(ConnectionError, match="still disconnected"):
                client._submit_with_retry(
                    lambda: always_fail, timeout=5.0, retries=2, delay=0.01,
                )
        client._worker.shutdown()

    def test_non_connection_error_not_retried(self):
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        client._order_contexts = {}
        client._events_registered = False
        client._reconnect_thread = None
        client._reconnect_stop = threading.Event()

        from app.services.live_trading.async_worker import AsyncWorker
        client._worker = AsyncWorker(name="test-retry4")
        client._worker.start()

        call_count = [0]
        def task():
            call_count[0] += 1
            raise ValueError("bad value")

        with pytest.raises(ValueError, match="bad value"):
            client._submit_with_retry(
                lambda: task, timeout=5.0, retries=3, delay=0.01,
            )
        assert call_count[0] == 1
        client._worker.shutdown()


# ===========================================================================
# IBKROrderContext lifecycle tests
# ===========================================================================

class TestOrderContextLifecycle:
    """Verify order contexts are properly registered and cleaned up."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_context_registered_and_cleaned_on_fill(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=500)
        client._ib.placeOrder.return_value = trade_mock

        client.place_market_order("AAPL", "buy", 10, "USStock", pending_order_id=99)
        assert 500 in client._order_contexts

        fill_trade = _make_trade_mock(status="Filled", filled=10.0, avg_price=155.0, order_id=500)
        client._on_order_status(fill_trade)
        assert 500 not in client._order_contexts

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_context_cleaned_on_reject(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=501)
        client._ib.placeOrder.return_value = trade_mock

        client.place_market_order("AAPL", "buy", 10, "USStock", pending_order_id=100)
        assert 501 in client._order_contexts

        reject_trade = _make_trade_mock(status="Inactive", filled=0, avg_price=0, order_id=501)
        client._on_order_status(reject_trade)
        assert 501 not in client._order_contexts

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_context_survives_cancelled_zero_fills(self):
        """Cancelled with 0 fills doesn't clean up — IBKR may recover."""
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=502)
        client._ib.placeOrder.return_value = trade_mock

        client.place_market_order("AAPL", "buy", 10, "USStock", pending_order_id=101)
        assert 502 in client._order_contexts

        cancel_trade = _make_trade_mock(status="Cancelled", filled=0, avg_price=0, order_id=502)
        client._on_order_status(cancel_trade)
        assert 502 in client._order_contexts  # still tracked
