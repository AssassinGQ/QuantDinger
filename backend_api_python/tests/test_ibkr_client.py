"""
Tests for IBKR client: quantity guard, order status polling, connection retry,
RTH gate, and the worker-thread serialization mechanism.
"""
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock
from concurrent.futures import Future

import pytest

from app.services.live_trading.ibkr_trading.client import (
    IBKRClient,
    IBKRConfig,
    _SENTINEL,
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
    """Create an IBKRClient with mocked internals, bypassing real worker thread.

    The worker thread is started but _submit is patched to run synchronously,
    so tests don't depend on threading.
    """
    client = IBKRClient.__new__(IBKRClient)
    client.config = IBKRConfig()
    client._ib = MagicMock()
    client._account = "DU123456"
    client._ib.isConnected.return_value = True
    client._ib.qualifyContracts.return_value = [MagicMock()]

    # Bypass worker thread: run submitted callables synchronously
    client._queue = MagicMock()
    client._worker_thread = MagicMock()
    client._worker_thread.is_alive.return_value = True
    client._started = threading.Event()
    client._started.set()

    # Event-driven order tracking state
    client._order_events = {}
    client._order_results = {}
    client._commission_cache = {}
    client._events_registered = False

    original_submit = IBKRClient._submit

    def _sync_submit(self_inner, fn, timeout=60.0):
        return fn()

    client._submit = lambda fn, timeout=60.0: _sync_submit(client, fn, timeout)

    return client


# ===========================================================================
# Worker thread tests
# ===========================================================================

class TestWorkerThread:
    """Verify the worker thread serialization mechanism."""

    def test_submit_runs_on_worker_thread(self):
        """_submit should execute the callable on the worker thread, not the caller."""
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        from queue import Queue
        client._queue = Queue()
        client._worker_thread = None
        client._started = threading.Event()
        client._start_worker()

        caller_tid = threading.current_thread().ident
        result_holder = {}

        def task():
            result_holder["tid"] = threading.current_thread().ident
            return 42

        result = client._submit(task, timeout=5.0)

        assert result == 42
        assert result_holder["tid"] != caller_tid
        client.shutdown()

    def test_submit_propagates_exception(self):
        """Exceptions in the worker should propagate to the caller."""
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        from queue import Queue
        client._queue = Queue()
        client._worker_thread = None
        client._started = threading.Event()
        client._start_worker()

        def bad_task():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            client._submit(bad_task, timeout=5.0)
        client.shutdown()

    def test_multiple_submits_are_serial(self):
        """Tasks submitted from multiple threads are executed serially."""
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        from queue import Queue
        client._queue = Queue()
        client._worker_thread = None
        client._started = threading.Event()
        client._start_worker()

        order_log = []
        barrier = threading.Barrier(3)

        def make_task(label):
            def task():
                order_log.append(f"{label}_start")
                time.sleep(0.05)
                order_log.append(f"{label}_end")
                return label
            return task

        results = [None, None, None]

        def caller(idx, label):
            barrier.wait()
            results[idx] = client._submit(make_task(label), timeout=10.0)

        threads = [
            threading.Thread(target=caller, args=(i, f"t{i}"))
            for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert all(r is not None for r in results)
        # Verify serial execution: each _start is immediately followed by its _end
        for i in range(0, len(order_log), 2):
            label = order_log[i].replace("_start", "")
            assert order_log[i + 1] == f"{label}_end"

        client.shutdown()

    def test_shutdown_stops_worker(self):
        """shutdown() should stop the worker thread."""
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        from queue import Queue
        client._queue = Queue()
        client._worker_thread = None
        client._started = threading.Event()
        client._start_worker()

        assert client._worker_thread.is_alive()
        client.shutdown()
        assert not client._worker_thread.is_alive()


# ===========================================================================
# Whole-number quantity guard tests
# ===========================================================================

class TestQuantityGuard:
    """Client rejects non-whole-number and non-positive quantities."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_accepts_whole_number(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Filled", filled=7, avg_price=150.0)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("AAPL", "buy", 7, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.totalQuantity == 7
        assert result.success is True

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_limit_order_accepts_whole_number(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Filled", filled=3, avg_price=180.0)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_limit_order("GOOGL", "buy", 3, 180.0, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.totalQuantity == 3
        assert result.success is True

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_accepts_float_whole(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Filled", filled=10, avg_price=150.0)
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
        trade_mock = _make_trade_mock(status="Filled", filled=400, avg_price=130.0)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("00005", "buy", 400, "HShare")
        assert result.success is True

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_hshare_unknown_symbol_accepts_any_integer(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Filled", filled=7, avg_price=50.0)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("00388", "buy", 7, "HShare")
        assert result.success is True


# ===========================================================================
# _wait_for_order polling tests
# ===========================================================================

class TestWaitForOrder:
    """Verify _wait_for_order handles all terminal statuses via event-driven callbacks."""

    def test_filled_immediately(self):
        """Order already in Filled status when _wait_for_order starts."""
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=10.0, avg_price=155.5)
        result = client._wait_for_order(trade, timeout=5.0)
        assert result.success is True
        assert result.filled == 10.0
        assert result.avg_price == 155.5
        assert result.status == "Filled"

    def test_cancelled_returns_failure(self):
        """Cancelled with 0 fills → failure."""
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(
            status="Cancelled", filled=0, avg_price=0,
            log_messages=["Error 10349: Order TIF was set to DAY"]
        )
        result = client._wait_for_order(trade, timeout=5.0)
        assert result.success is False
        assert result.status == "Cancelled"
        assert "10349" in result.message

    def test_cancelled_with_fill_returns_success(self):
        """Cancelled but filled > 0 → success (presubmit scenario)."""
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(
            status="Cancelled", filled=1.0, avg_price=300.6,
            log_messages=["Error 10349: Order TIF was set to DAY"]
        )
        result = client._wait_for_order(trade, timeout=5.0)
        assert result.success is True
        assert result.filled == 1.0
        assert result.avg_price == 300.6

    def test_inactive_returns_failure(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(
            status="Inactive", filled=0, avg_price=0,
            log_messages=["Order rejected"]
        )
        result = client._wait_for_order(trade, timeout=5.0)
        assert result.success is False
        assert result.status == "Inactive"

    def test_api_error_returns_failure(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(
            status="ApiError", filled=0, avg_price=0,
            log_messages=["Error 10243: Fractional-sized order cannot be placed"]
        )
        result = client._wait_for_order(trade, timeout=5.0)
        assert result.success is False
        assert "10243" in result.message

    def test_validation_error_returns_failure(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="ValidationError", filled=0, avg_price=0)
        result = client._wait_for_order(trade, timeout=5.0)
        assert result.success is False
        assert result.status == "ValidationError"

    def test_api_cancelled_returns_failure(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="ApiCancelled", filled=0, avg_price=0)
        result = client._wait_for_order(trade, timeout=5.0)
        assert result.success is False
        assert result.status == "ApiCancelled"

    def test_event_fires_during_sleep(self):
        """Simulate event callback firing during ib.sleep() pump."""
        client = _make_client_with_mock_ib()
        trade = MagicMock()
        trade.order.orderId = 99
        trade.orderStatus.status = "Submitted"
        trade.orderStatus.filled = 0
        trade.orderStatus.avgFillPrice = 0
        trade.orderStatus.remaining = 10.0
        trade.log = []

        def simulate_fill(_sleep_time=0):
            trade.orderStatus.status = "Filled"
            trade.orderStatus.filled = 10.0
            trade.orderStatus.avgFillPrice = 200.0
            client._on_order_status(trade)

        client._ib.sleep.side_effect = simulate_fill

        result = client._wait_for_order(trade, timeout=10.0)
        assert result.success is True
        assert result.filled == 10.0
        assert result.avg_price == 200.0
        assert client._ib.sleep.called

    def test_timeout_zero_fills_returns_failure(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="PendingSubmit", filled=0, avg_price=0)
        result = client._wait_for_order(trade, timeout=0.5)
        assert result.success is False
        assert "timed out" in result.message
        assert result.filled == 0

    def test_presubmitted_times_out(self):
        """PreSubmitted is not terminal — order just times out normally."""
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="PreSubmitted", filled=0, avg_price=0)
        result = client._wait_for_order(trade, timeout=0.5)
        assert result.success is False
        assert "timed out" in result.message

    def test_timeout_with_partial_fills_returns_success(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Submitted", filled=5.0, avg_price=150.0)
        result = client._wait_for_order(trade, timeout=0.5)
        assert result.success is True
        assert result.filled == 5.0

    def test_filled_with_partial_fill(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(
            status="Filled", filled=5.0, avg_price=150.0, remaining=5.0
        )
        result = client._wait_for_order(trade, timeout=5.0)
        assert result.success is True
        assert result.filled == 5.0
        assert result.raw.get("remaining") == 5.0

    def test_empty_log_on_rejection(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Cancelled", filled=0, avg_price=0)
        result = client._wait_for_order(trade, timeout=5.0)
        assert result.success is False
        assert "rejected by IBKR" in result.message

    def test_commission_captured(self):
        """Commission report is attached to the result."""
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=10.0, avg_price=155.0)
        client._commission_cache[trade.order.orderId] = {
            "commission": 1.25, "currency": "USD",
        }
        result = client._wait_for_order(trade, timeout=5.0)
        assert result.success is True
        assert result.fee == 1.25
        assert result.fee_ccy == "USD"

    def test_cleanup_after_wait(self):
        """Event tracking state is cleaned up after _wait_for_order."""
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=5.0, avg_price=100.0)
        oid = trade.order.orderId
        client._wait_for_order(trade, timeout=5.0)
        assert oid not in client._order_events
        assert oid not in client._order_results


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
# Integration: place_market_order → _wait_for_order → result
# ===========================================================================

class TestPlaceOrderIntegration:

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_cancelled_by_ibkr(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(
            status="Cancelled", filled=0, avg_price=0,
            log_messages=["Error 10349: Order TIF was set to DAY but session is closed"]
        )
        client._ib.placeOrder.return_value = trade
        result = client.place_market_order("GOOGL", "buy", 1, "USStock")
        assert result.success is False
        assert "Cancelled" in result.status or "Cancelled" in result.message

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_fractional_rejected(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("AAPL", "buy", 0.7, "USStock")
        assert result.success is False
        assert "whole number" in result.message.lower()
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_filled_success(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=400, avg_price=65.5)
        client._ib.placeOrder.return_value = trade
        result = client.place_market_order("5", "buy", 400, "HShare")
        assert result.success is True
        assert result.filled == 400
        assert result.avg_price == 65.5

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_limit_order_inactive_rejected(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(
            status="Inactive", filled=0, avg_price=0,
            log_messages=["Order rejected by exchange"]
        )
        client._ib.placeOrder.return_value = trade
        result = client.place_limit_order("AAPL", "buy", 5, 100.0, "USStock")
        assert result.success is False
        assert result.status == "Inactive"

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
        trade = _make_trade_mock(status="Filled", filled=10, avg_price=150.0)
        client._ib.placeOrder.return_value = trade
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
        trade = _make_trade_mock(status="Filled", filled=10, avg_price=150.0)
        client._ib.placeOrder.return_value = trade
        client.place_market_order("AAPL", "buy", 10, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.tif == "DAY"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_limit_order_sets_tif_day(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=5, avg_price=180.0)
        client._ib.placeOrder.return_value = trade
        client.place_limit_order("GOOGL", "buy", 5, 180.0, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.tif == "DAY"


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
# Event callback tests
# ===========================================================================

class TestEventCallbacks:
    """Verify event callbacks drive order tracking correctly."""

    def test_on_order_status_sets_event_for_filled(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=10.0, avg_price=155.0)
        oid = trade.order.orderId
        event = threading.Event()
        client._order_events[oid] = event

        client._on_order_status(trade)

        assert event.is_set()
        result = client._order_results[oid]
        assert result.success is True
        assert result.filled == 10.0

    def test_on_order_status_sets_event_for_rejection(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Cancelled", filled=0, avg_price=0,
                                  log_messages=["Error 10349: TIF set to DAY"])
        oid = trade.order.orderId
        event = threading.Event()
        client._order_events[oid] = event

        client._on_order_status(trade)

        assert event.is_set()
        result = client._order_results[oid]
        assert result.success is False
        assert "10349" in result.message

    def test_on_order_status_cancelled_with_fill_is_success(self):
        """Cancelled but with fill > 0 (presubmit scenario) should report success."""
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Cancelled", filled=1.0, avg_price=300.0)
        oid = trade.order.orderId
        event = threading.Event()
        client._order_events[oid] = event

        client._on_order_status(trade)

        assert event.is_set()
        result = client._order_results[oid]
        assert result.success is True
        assert result.filled == 1.0

    def test_on_order_status_ignores_untracked_order(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=10.0, avg_price=155.0)
        client._on_order_status(trade)
        assert trade.order.orderId not in client._order_results

    def test_on_order_status_ignores_non_terminal(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Submitted", filled=0, avg_price=0)
        oid = trade.order.orderId
        event = threading.Event()
        client._order_events[oid] = event
        client._on_order_status(trade)
        assert not event.is_set()

    def test_on_exec_details_updates_result_without_setting_event(self):
        """execDetails updates _order_results but does NOT set() the event.
        This prevents premature completion during multi-fill scenarios.
        """
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Submitted", filled=5.0, avg_price=200.0)
        oid = trade.order.orderId
        event = threading.Event()
        client._order_events[oid] = event

        fill = MagicMock()
        fill.execution.execId = "exec001"
        fill.execution.side = "BOT"
        fill.execution.shares = 5
        fill.execution.price = 200.0

        client._on_exec_details(trade, fill)

        assert not event.is_set()
        result = client._order_results[oid]
        assert result.success is True
        assert result.filled == 5.0

    def test_on_commission_report_accumulates(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=10.0, avg_price=150.0)
        oid = trade.order.orderId
        fill = MagicMock()
        fill.execution.execId = "exec001"
        report1 = MagicMock()
        report1.commission = 0.65
        report1.currency = "USD"
        report1.realizedPNL = 0.0
        report2 = MagicMock()
        report2.commission = 0.35
        report2.currency = "USD"
        report2.realizedPNL = 10.0

        client._on_commission_report(trade, fill, report1)
        client._on_commission_report(trade, fill, report2)

        assert client._commission_cache[oid]["commission"] == pytest.approx(1.0)
        assert client._commission_cache[oid]["currency"] == "USD"


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
    """Verify is_market_open returns correct result based on RTH status.

    RTH check has been lifted from place_*_order into
    StatefulClientRunner.pre_check → client.is_market_open.
    """

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
        trade = _make_trade_mock(status="Filled", filled=10, avg_price=150.0)
        client._ib.placeOrder.return_value = trade
        result = client.place_market_order("AAPL", "buy", 10, "USStock")
        assert result.success is True
        client._ib.placeOrder.assert_called_once()


# ===========================================================================
# Mock IB Gateway: realistic event-sequence scenarios
# ===========================================================================

def _make_stateful_trade(order_id=100):
    """Create a mutable trade mock whose status/filled/avgPrice can be changed."""
    trade = MagicMock()
    trade.order.orderId = order_id
    trade.order.action = "BUY"
    trade.order.totalQuantity = 10
    trade.order.orderType = "MKT"
    trade.order.tif = "DAY"
    trade.contract.symbol = "GOOGL"
    trade.orderStatus.status = "PendingSubmit"
    trade.orderStatus.filled = 0.0
    trade.orderStatus.avgFillPrice = 0.0
    trade.orderStatus.remaining = 10.0
    trade.log = []
    return trade


def _event_sequencer(client, trade, steps):
    """Return a side_effect for ib.sleep() that replays a sequence of
    (status, filled, avg_price, remaining) tuples, driving _on_order_status
    (and optionally _on_exec_details / _on_commission_report) on each pump.
    """
    step_iter = iter(steps)

    def pump(_sleep_time=0):
        step = next(step_iter, None)
        if step is None:
            return
        if isinstance(step, dict):
            action = step.get("action", "status")
            if action == "exec_details":
                trade.orderStatus.status = step.get("status", trade.orderStatus.status)
                trade.orderStatus.filled = step.get("filled", trade.orderStatus.filled)
                trade.orderStatus.avgFillPrice = step.get("avg_price", trade.orderStatus.avgFillPrice)
                trade.orderStatus.remaining = step.get("remaining", trade.orderStatus.remaining)
                fill = MagicMock()
                fill.execution.execId = step.get("exec_id", "exec-001")
                fill.execution.side = "BOT"
                fill.execution.shares = step.get("shares", trade.orderStatus.filled)
                fill.execution.price = step.get("avg_price", 0)
                client._on_exec_details(trade, fill)
            elif action == "commission":
                report = MagicMock()
                report.commission = step.get("commission", 1.0)
                report.currency = step.get("currency", "USD")
                report.realizedPNL = step.get("realizedPNL", 0.0)
                fill = MagicMock()
                fill.execution.execId = step.get("exec_id", "exec-001")
                client._on_commission_report(trade, fill, report)
            elif action == "error":
                client._on_error(
                    trade.order.orderId,
                    step.get("code", 0),
                    step.get("msg", ""),
                    trade.contract,
                )
            elif action == "disconnect":
                client._on_disconnected()
            elif action == "noop":
                pass
            else:
                trade.orderStatus.status = step["status"]
                trade.orderStatus.filled = step.get("filled", trade.orderStatus.filled)
                trade.orderStatus.avgFillPrice = step.get("avg_price", trade.orderStatus.avgFillPrice)
                trade.orderStatus.remaining = step.get("remaining", trade.orderStatus.remaining)
                if "log" in step:
                    trade.log = [MagicMock(message=m) for m in step["log"]]
                client._on_order_status(trade)
        else:
            status, filled, avg_price, remaining = step
            trade.orderStatus.status = status
            trade.orderStatus.filled = filled
            trade.orderStatus.avgFillPrice = avg_price
            trade.orderStatus.remaining = remaining
            client._on_order_status(trade)

    return pump


class TestMockIBGatewayScenarios:
    """End-to-end scenarios simulating real IB Gateway event sequences.

    Each test creates a client + trade, wires up a step sequence via
    _event_sequencer (which runs inside ib.sleep side_effect), then
    calls _wait_for_order and asserts the result.
    """

    def test_scenario_normal_fill(self):
        """Normal flow: PendingSubmit → Submitted → Filled."""
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=200)

        steps = [
            ("Submitted", 0, 0, 10),
            ("Filled", 10, 178.50, 0),
        ]
        client._ib.sleep.side_effect = _event_sequencer(client, trade, steps)

        result = client._wait_for_order(trade, timeout=10.0)
        assert result.success is True
        assert result.filled == 10.0
        assert result.avg_price == 178.50
        assert result.status == "Filled"

    def test_scenario_normal_fill_with_commission(self):
        """Filled via orderStatus + trailing commission report attached."""
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=201)

        steps = [
            ("Submitted", 0, 0, 10),
            ("Filled", 10.0, 178.50, 0),
            {"action": "commission", "commission": 1.25, "currency": "USD"},
        ]
        client._ib.sleep.side_effect = _event_sequencer(client, trade, steps)

        result = client._wait_for_order(trade, timeout=10.0)
        assert result.success is True
        assert result.filled == 10.0
        assert result.status == "Filled"
        assert result.fee == 1.25
        assert result.fee_ccy == "USD"

    def test_scenario_rejected_by_exchange(self):
        """Order immediately rejected: PendingSubmit → Inactive."""
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=202)

        steps = [
            {"action": "status", "status": "Inactive", "filled": 0, "avg_price": 0,
             "remaining": 10, "log": ["Order rejected by exchange"]},
        ]
        client._ib.sleep.side_effect = _event_sequencer(client, trade, steps)

        result = client._wait_for_order(trade, timeout=10.0)
        assert result.success is False
        assert result.status == "Inactive"
        assert "rejected" in result.message.lower()

    def test_scenario_cancelled_zero_fills(self):
        """Pure cancellation with 0 fills → failure."""
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=203)

        steps = [
            {"action": "error", "code": 10349, "msg": "Order TIF was set to DAY"},
            {"action": "status", "status": "Cancelled", "filled": 0, "avg_price": 0,
             "remaining": 10, "log": ["Error 10349: Order TIF was set to DAY"]},
        ]
        client._ib.sleep.side_effect = _event_sequencer(client, trade, steps)

        result = client._wait_for_order(trade, timeout=10.0)
        assert result.success is False
        assert result.status == "Cancelled"
        assert "10349" in result.message

    def test_scenario_cancelled_then_presubmit_then_filled(self):
        """The GOOGL incident: Cancelled → PreSubmitted → Filled.

        This is the key scenario where IBKR cancels but then presubmits
        and eventually fills the order (happens ~30s before market open).

        Current behavior: Cancelled with filled=0 terminates immediately
        as failure. The subsequent PreSubmitted/Filled events are ignored
        because the order tracking has been cleaned up.

        NOTE: with tif='DAY' explicitly set, Error 10349 should no longer
        occur. This test documents the known limitation.
        """
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=204)

        # IBKR fires Cancelled first; since filled=0, our code marks failure
        # immediately. The subsequent events would be too late.
        steps = [
            {"action": "error", "code": 10349, "msg": "Order TIF was set to DAY"},
            {"action": "status", "status": "Cancelled", "filled": 0, "avg_price": 0,
             "remaining": 10, "log": ["Error 10349"]},
        ]
        client._ib.sleep.side_effect = _event_sequencer(client, trade, steps)

        result = client._wait_for_order(trade, timeout=10.0)
        # With current code, Cancelled+filled=0 → failure (known limitation)
        assert result.success is False
        assert result.status == "Cancelled"

    def test_scenario_cancelled_but_already_partially_filled(self):
        """Cancelled but filled > 0 → success.

        This happens when IBKR partially fills then cancels remaining.
        """
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=205)

        steps = [
            ("Submitted", 0, 0, 10),
            {"action": "exec_details", "status": "Submitted", "filled": 3.0,
             "avg_price": 175.0, "remaining": 7, "shares": 3},
            {"action": "status", "status": "Cancelled", "filled": 3.0,
             "avg_price": 175.0, "remaining": 7},
        ]
        client._ib.sleep.side_effect = _event_sequencer(client, trade, steps)

        result = client._wait_for_order(trade, timeout=10.0)
        assert result.success is True
        assert result.filled == 3.0
        assert result.avg_price == 175.0

    def test_scenario_api_error(self):
        """ApiError from IBKR (e.g. fractional shares not supported)."""
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=206)

        steps = [
            {"action": "error", "code": 10243, "msg": "Fractional-sized order cannot be placed"},
            {"action": "status", "status": "ApiError", "filled": 0, "avg_price": 0,
             "remaining": 10, "log": ["Error 10243: Fractional-sized order cannot be placed"]},
        ]
        client._ib.sleep.side_effect = _event_sequencer(client, trade, steps)

        result = client._wait_for_order(trade, timeout=10.0)
        assert result.success is False
        assert "10243" in result.message

    def test_scenario_timeout_no_fill(self):
        """Order stays in Submitted forever → timeout with 0 fills."""
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=207)
        trade.orderStatus.status = "Submitted"

        # No terminal status ever arrives
        client._ib.sleep.side_effect = lambda _t: None

        result = client._wait_for_order(trade, timeout=1.0)
        assert result.success is False
        assert "timed out" in result.message

    def test_scenario_timeout_with_partial_fill(self):
        """Order partially fills then hangs → timeout, but success because filled > 0."""
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=208)

        call_count = [0]
        def partial_fill_then_hang(_t):
            call_count[0] += 1
            if call_count[0] == 1:
                trade.orderStatus.status = "Submitted"
                trade.orderStatus.filled = 5.0
                trade.orderStatus.avgFillPrice = 180.0
                trade.orderStatus.remaining = 5.0

        client._ib.sleep.side_effect = partial_fill_then_hang

        result = client._wait_for_order(trade, timeout=1.5)
        assert result.success is True
        assert result.filled == 5.0

    def test_scenario_disconnect_during_order(self):
        """Connection drops while waiting for order → timeout."""
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=209)
        trade.orderStatus.status = "Submitted"

        steps = [
            {"action": "disconnect"},
            {"action": "noop"},
        ]
        client._ib.sleep.side_effect = _event_sequencer(client, trade, steps)

        result = client._wait_for_order(trade, timeout=1.5)
        assert result.success is False
        assert client._events_registered is False

    def test_scenario_slow_fill_multi_exec(self):
        """Multiple partial fills via execDetails events → final Filled."""
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=210)

        steps = [
            ("Submitted", 0, 0, 10),
            {"action": "exec_details", "status": "Submitted", "filled": 3.0,
             "avg_price": 175.0, "remaining": 7, "shares": 3, "exec_id": "exec-001"},
            {"action": "commission", "commission": 0.40, "currency": "USD", "exec_id": "exec-001"},
            {"action": "exec_details", "status": "Submitted", "filled": 7.0,
             "avg_price": 176.0, "remaining": 3, "shares": 4, "exec_id": "exec-002"},
            {"action": "commission", "commission": 0.50, "currency": "USD", "exec_id": "exec-002"},
            ("Filled", 10.0, 176.5, 0),
            {"action": "commission", "commission": 0.35, "currency": "USD", "exec_id": "exec-003"},
        ]
        client._ib.sleep.side_effect = _event_sequencer(client, trade, steps)

        result = client._wait_for_order(trade, timeout=10.0)
        assert result.success is True
        assert result.filled == 10.0
        assert result.fee == pytest.approx(1.25)
        assert result.fee_ccy == "USD"

    def test_scenario_presubmitted_then_filled(self):
        """PreSubmitted → Submitted → Filled (limit order near market)."""
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=211)

        steps = [
            ("PreSubmitted", 0, 0, 10),
            ("Submitted", 0, 0, 10),
            ("Filled", 10, 179.0, 0),
        ]
        client._ib.sleep.side_effect = _event_sequencer(client, trade, steps)

        result = client._wait_for_order(trade, timeout=10.0)
        assert result.success is True
        assert result.status == "Filled"

    def test_scenario_validation_error(self):
        """ValidationError from IBKR."""
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=212)

        steps = [
            {"action": "status", "status": "ValidationError", "filled": 0,
             "avg_price": 0, "remaining": 10, "log": ["Validation failed"]},
        ]
        client._ib.sleep.side_effect = _event_sequencer(client, trade, steps)

        result = client._wait_for_order(trade, timeout=10.0)
        assert result.success is False
        assert result.status == "ValidationError"

    def test_scenario_exec_details_fires_before_order_status(self):
        """execDetails arrives before orderStatus=Filled (race condition).

        execDetails updates _order_results but doesn't set() event.
        On timeout, the fallback picks up the execDetails result.
        """
        client = _make_client_with_mock_ib()
        trade = _make_stateful_trade(order_id=213)

        steps = [
            ("Submitted", 0, 0, 10),
            {"action": "exec_details", "status": "Submitted", "filled": 10.0,
             "avg_price": 180.0, "remaining": 0, "shares": 10},
        ]
        client._ib.sleep.side_effect = _event_sequencer(client, trade, steps)

        result = client._wait_for_order(trade, timeout=1.5)
        assert result.success is True
        assert result.filled == 10.0
        assert "execDetails" in result.message
