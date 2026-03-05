"""
Tests for IBKR client: fractional share rounding and order status polling.

1. Fractional share → floor to whole shares, reject if qty < 1
2. _wait_for_order polls until terminal status or timeout
3. Rejected statuses (Cancelled, Inactive, ApiError, etc.) → success=False
4. Filled status → success=True with fill data
5. Non-terminal status at timeout → success=True (optimistic)
"""
import math
import time
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass

import pytest

from app.services.ibkr_trading.client import (
    IBKRClient,
    IBKRConfig,
    OrderResult,
)


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
    """Create an IBKRClient with mocked _ib and connection."""
    client = IBKRClient.__new__(IBKRClient)
    client.config = IBKRConfig()
    client._ib = MagicMock()
    client._connected = True
    client._account = "DU123456"
    client._lock = __import__("threading").Lock()
    client._ib.isConnected.return_value = True
    client._ib.qualifyContracts.return_value = [MagicMock()]
    return client


# ===========================================================================
# Fractional share rounding tests
# ===========================================================================

class TestFractionalShareRounding:
    """Verify quantity is floored to whole shares."""

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_floors_quantity(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Filled", filled=7, avg_price=150.0)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("AAPL", "buy", 7.8, "USStock")

        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.totalQuantity == 7
        assert result.success is True

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_limit_order_floors_quantity(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Filled", filled=3, avg_price=180.0)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_limit_order("GOOGL", "buy", 3.99, 180.0, "USStock")

        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.totalQuantity == 3
        assert result.success is True

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_rejects_sub_one(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("AAPL", "buy", 0.5, "USStock")

        assert result.success is False
        assert "too small" in result.message.lower()
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_limit_order_rejects_sub_one(self):
        client = _make_client_with_mock_ib()
        result = client.place_limit_order("AAPL", "buy", 0.3, 150.0, "USStock")

        assert result.success is False
        assert "too small" in result.message.lower()
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_rejects_zero(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("AAPL", "buy", 0.0, "USStock")

        assert result.success is False
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_whole_number_unchanged(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Filled", filled=10, avg_price=150.0)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("AAPL", "buy", 10.0, "USStock")

        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.totalQuantity == 10
        assert result.success is True

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_negative_quantity(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("AAPL", "buy", -5.0, "USStock")

        assert result.success is False
        client._ib.placeOrder.assert_not_called()


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
        """Simulate status transitioning from Submitted → Filled."""
        client = _make_client_with_mock_ib()
        trade = MagicMock()
        trade.order.orderId = 99

        statuses = iter(["Submitted", "Submitted", "Submitted", "Filled"])
        type(trade.orderStatus).status = PropertyMock(side_effect=lambda: next(statuses, "Filled"))
        trade.orderStatus.filled = 5.0
        trade.orderStatus.avgFillPrice = 200.0
        trade.orderStatus.remaining = 0.0
        trade.log = []

        result = client._wait_for_order(trade, timeout=10.0)

        assert result.success is True
        assert client._ib.sleep.called

    def test_timeout_returns_optimistic_success(self):
        """If status never reaches terminal, return success=True (optimistic)."""
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Submitted", filled=0, avg_price=0)

        result = client._wait_for_order(trade, timeout=0.5)

        assert result.success is True
        assert result.status == "Submitted"

    def test_filled_with_partial_fill(self):
        """Partial fill scenario."""
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(
            status="Filled", filled=5.0, avg_price=150.0, remaining=5.0
        )

        result = client._wait_for_order(trade, timeout=5.0)

        assert result.success is True
        assert result.filled == 5.0
        assert result.raw.get("remaining") == 5.0

    def test_empty_log_on_rejection(self):
        """Cancelled with no log messages should still fail with default message."""
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Cancelled", filled=0, avg_price=0)

        result = client._wait_for_order(trade, timeout=5.0)

        assert result.success is False
        assert "rejected by IBKR" in result.message


# ===========================================================================
# Terminal status sets
# ===========================================================================

class TestTerminalStatusSets:
    """Verify the status classification sets are correct."""

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
# Integration: place_market_order → _wait_for_order → rejected
# ===========================================================================

class TestPlaceOrderIntegration:
    """Full flow: place order → wait → check result."""

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_cancelled_by_ibkr(self):
        """Simulate IBKR cancelling a DAY market order placed outside RTH."""
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
        """Simulate IBKR rejecting fractional shares via API error."""
        client = _make_client_with_mock_ib()

        result = client.place_market_order("AAPL", "buy", 0.7, "USStock")

        assert result.success is False
        assert "too small" in result.message.lower()

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_market_order_filled_success(self):
        """Normal successful fill."""
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Filled", filled=100, avg_price=65.5)
        client._ib.placeOrder.return_value = trade

        result = client.place_market_order("5", "buy", 100, "HShare")

        assert result.success is True
        assert result.filled == 100
        assert result.avg_price == 65.5

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_limit_order_inactive_rejected(self):
        """Simulate IBKR rejecting a limit order."""
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
        """Qualify contract fails."""
        client = _make_client_with_mock_ib()
        client._ib.qualifyContracts.return_value = []

        result = client.place_market_order("INVALID", "buy", 10, "USStock")

        assert result.success is False
        assert "Invalid contract" in result.message

    @patch("app.services.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_sell_action_correct(self):
        """Verify sell side creates SELL action."""
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
    """Verify _ensure_connected retries on failure."""

    def test_succeeds_on_first_attempt(self):
        client = _make_client_with_mock_ib()
        client._ib.isConnected.return_value = True
        client._ensure_connected()

    def test_retries_and_succeeds_on_second_attempt(self):
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = MagicMock()
        client._connected = False
        client._account = ""
        client._lock = __import__("threading").Lock()

        call_count = {"n": 0}
        def mock_connect_side_effect():
            call_count["n"] += 1
            if call_count["n"] < 2:
                return False
            client._ib.isConnected.return_value = True
            client._connected = True
            client._ib.managedAccounts.return_value = ["DU999"]
            return True

        client._ib.isConnected.return_value = False
        with patch.object(client, "connect", side_effect=mock_connect_side_effect):
            client._ensure_connected(retries=3, delay=0.01)
        assert call_count["n"] == 2

    def test_raises_after_all_retries_exhausted(self):
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = MagicMock()
        client._connected = False
        client._account = ""
        client._lock = __import__("threading").Lock()
        client._ib.isConnected.return_value = False

        with patch.object(client, "connect", return_value=False):
            with pytest.raises(ConnectionError, match="Cannot connect to IBKR after 3 attempts"):
                client._ensure_connected(retries=3, delay=0.01)

    def test_no_retry_when_already_connected(self):
        client = _make_client_with_mock_ib()
        client._ib.isConnected.return_value = True
        with patch.object(client, "connect") as mock_connect:
            client._ensure_connected()
            mock_connect.assert_not_called()
