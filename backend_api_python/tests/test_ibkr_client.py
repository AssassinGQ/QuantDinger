"""
Tests for IBKR client: quantity guard, order status polling, connection retry,
RTH gate, and the worker-thread serialization mechanism.
"""
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock
from concurrent.futures import Future

import pytest

from app.services.ibkr_trading.client import (
    IBKRClient,
    IBKRConfig,
    _SENTINEL,
)
from app.services.exchange_engine import ExchangeEngine, OrderResult

@pytest.fixture(autouse=True)
def _always_rth():
    """Default: assume market is open so RTH gate doesn't block tests."""
    with patch("app.services.ibkr_trading.trading_hours.is_rth", return_value=True):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_ib_insync():
    """Create a mock ib_insync module with necessary classes."""
    mock_mod = MagicMock()

    class MockMarketOrder:
        def __init__(self, action, totalQuantity, account=""):
            self.action = action
            self.totalQuantity = totalQuantity
            self.account = account
            self.orderId = 0

    class MockLimitOrder:
        def __init__(self, action, totalQuantity, lmtPrice, account=""):
            self.action = action
            self.totalQuantity = totalQuantity
            self.lmtPrice = lmtPrice
            self.account = account
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

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_accepts_whole_number(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Filled", filled=7, avg_price=150.0)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("AAPL", "buy", 7, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.totalQuantity == 7
        assert result.success is True

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_limit_order_accepts_whole_number(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Filled", filled=3, avg_price=180.0)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_limit_order("GOOGL", "buy", 3, 180.0, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.totalQuantity == 3
        assert result.success is True

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_accepts_float_whole(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Filled", filled=10, avg_price=150.0)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("AAPL", "buy", 10.0, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.totalQuantity == 10.0
        assert result.success is True

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_rejects_fractional(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("AAPL", "buy", 7.8, "USStock")
        assert result.success is False
        assert "whole number" in result.message.lower()
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_limit_order_rejects_fractional(self):
        client = _make_client_with_mock_ib()
        result = client.place_limit_order("AAPL", "buy", 3.5, 150.0, "USStock")
        assert result.success is False
        assert "whole number" in result.message.lower()
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_rejects_zero(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("AAPL", "buy", 0, "USStock")
        assert result.success is False
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_rejects_negative(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("AAPL", "buy", -5, "USStock")
        assert result.success is False
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_hshare_rejects_non_lot_multiple(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("00005", "buy", 3, "HShare")
        assert result.success is False
        assert "400" in result.message
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_hshare_accepts_lot_multiple(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Filled", filled=400, avg_price=130.0)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("00005", "buy", 400, "HShare")
        assert result.success is True

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
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
    """Verify _wait_for_order polls correctly and handles all terminal statuses."""

    def test_filled_immediately(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=10.0, avg_price=155.5)
        result = client._wait_for_order(trade, timeout=5.0)
        assert result.success is True
        assert result.filled == 10.0
        assert result.avg_price == 155.5
        assert result.status == "Filled"

    def test_cancelled_returns_failure(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(
            status="Cancelled", filled=0, avg_price=0,
            log_messages=["Error 10349: Order TIF was set to DAY"]
        )
        result = client._wait_for_order(trade, timeout=5.0)
        assert result.success is False
        assert result.status == "Cancelled"
        assert "10349" in result.message

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

    def test_polls_until_terminal(self):
        client = _make_client_with_mock_ib()
        trade = MagicMock()
        trade.order.orderId = 99
        statuses = iter(["Submitted", "Submitted", "Submitted", "Filled"])
        type(trade.orderStatus).status = PropertyMock(
            side_effect=lambda: next(statuses, "Filled")
        )
        trade.orderStatus.filled = 5.0
        trade.orderStatus.avgFillPrice = 200.0
        trade.orderStatus.remaining = 0.0
        trade.log = []

        result = client._wait_for_order(trade, timeout=10.0)
        assert result.success is True
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

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
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

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_fractional_rejected(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("AAPL", "buy", 0.7, "USStock")
        assert result.success is False
        assert "whole number" in result.message.lower()
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_filled_success(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=400, avg_price=65.5)
        client._ib.placeOrder.return_value = trade
        result = client.place_market_order("5", "buy", 400, "HShare")
        assert result.success is True
        assert result.filled == 400
        assert result.avg_price == 65.5

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
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

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_invalid_contract_rejected(self):
        client = _make_client_with_mock_ib()
        client._ib.qualifyContracts.return_value = []
        result = client.place_market_order("INVALID", "buy", 10, "USStock")
        assert result.success is False
        assert "Invalid contract" in result.message

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_sell_action_correct(self):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=10, avg_price=150.0)
        client._ib.placeOrder.return_value = trade
        client.place_market_order("AAPL", "sell", 10, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.action == "SELL"


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
    """Verify orders are rejected when market is outside RTH."""

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    @patch("app.services.ibkr_trading.trading_hours.is_rth", return_value=False)
    def test_market_order_rejected_outside_rth(self, _mock_rth):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("AAPL", "buy", 10, "USStock")
        assert result.success is False
        assert "market closed" in result.message.lower()
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    @patch("app.services.ibkr_trading.trading_hours.is_rth", return_value=False)
    def test_limit_order_rejected_outside_rth(self, _mock_rth):
        client = _make_client_with_mock_ib()
        result = client.place_limit_order("AAPL", "buy", 10, 150.0, "USStock")
        assert result.success is False
        assert "market closed" in result.message.lower()
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    @patch("app.services.ibkr_trading.trading_hours.is_rth", return_value=True)
    def test_market_order_allowed_during_rth(self, _mock_rth):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=10, avg_price=150.0)
        client._ib.placeOrder.return_value = trade
        result = client.place_market_order("AAPL", "buy", 10, "USStock")
        assert result.success is True
        client._ib.placeOrder.assert_called_once()
