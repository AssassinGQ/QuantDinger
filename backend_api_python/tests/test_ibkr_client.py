"""
Tests for IBKR client: quantity guard, fire-and-forget order flow, connection retry,
RTH gate, and the TaskQueue-based task dispatch mechanism.
"""
import asyncio
import datetime
import logging
import types
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import pytz

from app.services.live_trading.ibkr_trading import trading_hours as _trading_hours_mod
from app.services.live_trading.ibkr_trading.trading_hours import clear_cache as _clear_trading_hours_cache
from app.services.live_trading.ibkr_trading.client import (
    IBKRClient,
    IBKRConfig,
    IBKROrderContext,
)
from app.services.live_trading.base import BaseStatefulClient, LiveOrderResult

_REAL_IS_RTH_CHECK_FN = _trading_hours_mod.is_rth_check

@pytest.fixture(autouse=True)
def _always_rth():
    """Default: assume market is open so is_market_open doesn't block tests."""
    with patch("app.services.live_trading.ibkr_trading.trading_hours.is_rth_check", return_value=True):
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

    class MockForex:
        def __init__(self, pair='', exchange='IDEALPRO', symbol='', currency='', **kwargs):
            if pair:
                assert len(pair) == 6
                symbol = symbol or pair[:3]
                currency = currency or pair[3:]
            self.secType = 'CASH'
            self.symbol = symbol
            self.currency = currency
            self.exchange = exchange

    mock_mod.MarketOrder = MockMarketOrder
    mock_mod.LimitOrder = MockLimitOrder
    mock_mod.Stock = MockStock
    mock_mod.Forex = MockForex
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
    """Create an IBKRClient with mocked internals, bypassing the real TaskQueue.

    _submit_ib / _fire_submit run callables synchronously so tests don't depend
    on threading.
    """
    client = IBKRClient.__new__(IBKRClient)
    client.config = IBKRConfig()
    client.mode = "paper"
    client._ib = MagicMock()
    client._account = "DU123456"
    client._ib.isConnected.return_value = True
    client._ib.qualifyContracts.return_value = [MagicMock()]

    import asyncio
    async def _mock_qualify_async(*contracts):
        if not client._ib.qualifyContracts.return_value:
            return []
        for c in contracts:
            con_id = getattr(c, 'conId', None)
            if not isinstance(con_id, int) or con_id == 0:
                c.conId = 1
            sec = getattr(c, 'secType', None)
            if not isinstance(sec, str):
                c.secType = 'STK'
        return list(contracts)
    client._ib.qualifyContractsAsync = _mock_qualify_async

    _mock_details = MagicMock()
    _mock_details.liquidHours = "20260305:0930-20260305:1600"
    _mock_details.timeZoneId = "EST"

    async def _mock_req_details_async(*args, **kwargs):
        return [_mock_details]
    client._ib.reqContractDetailsAsync = _mock_req_details_async

    async def _mock_req_current_time_async():
        import pytz
        return datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)
    client._ib.reqCurrentTimeAsync = _mock_req_current_time_async

    # Mock TaskQueue & executors
    client._tq = MagicMock()
    client._ib_executor = MagicMock()
    client._io_executor = MagicMock()

    # Fire-and-forget order contexts
    client._order_contexts = {}
    client._commission_contexts = {}
    client._events_registered = False
    client._event_map = []

    # Reconnection thread state
    client._reconnect_thread = None
    client._reconnect_stop = threading.Event()

    # conid to symbol mapping for PnL
    client._conid_to_symbol = {}
    client._subscribed_conids = set()

    import asyncio

    async def _noop_ensure(*_a, **_kw):
        pass

    def _sync_fire_submit(fn, is_blocking=True):
        fn()

    client._fire_submit = MagicMock(side_effect=_sync_fire_submit)

    def _submit(fn, timeout=60.0, is_blocking=False):
        if asyncio.iscoroutine(fn):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(fn)
            finally:
                loop.close()
        return fn()
    client._submit = _submit
    client._ensure_connected_async = _noop_ensure

    return client


def _make_forex_rth_client(liquid_hours: str, time_zone_id: str, server_time_utc: datetime.datetime):
    """IBKRClient with mock IB: fixed ContractDetails liquid hours and reqCurrentTimeAsync UTC."""
    client = _make_client_with_mock_ib()
    det = MagicMock()
    det.liquidHours = liquid_hours
    det.timeZoneId = time_zone_id

    async def _mock_req_details_async(*args, **kwargs):
        return [det]

    client._ib.reqContractDetailsAsync = _mock_req_details_async

    async def _mock_req_current_time_async():
        return server_time_utc

    client._ib.reqCurrentTimeAsync = _mock_req_current_time_async
    return client


# ===========================================================================
# Forex contract creation tests (TDD)
# ===========================================================================

class TestCreateContractForex:
    """UC-1 through UC-6: _create_contract Forex branch and error handling."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_create_contract_forex_eurusd(self):
        """UC-1: Forex EURUSD → secType=CASH, symbol=EUR, currency=USD, exchange=IDEALPRO."""
        client = _make_client_with_mock_ib()
        contract = client._create_contract("EURUSD", "Forex")
        assert contract.secType == "CASH"
        assert contract.symbol == "EUR"
        assert contract.currency == "USD"
        assert contract.exchange == "IDEALPRO"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_create_contract_forex_usdjpy(self):
        """UC-2: Forex USDJPY → secType=CASH, symbol=USD, currency=JPY, exchange=IDEALPRO."""
        client = _make_client_with_mock_ib()
        contract = client._create_contract("USDJPY", "Forex")
        assert contract.secType == "CASH"
        assert contract.symbol == "USD"
        assert contract.currency == "JPY"
        assert contract.exchange == "IDEALPRO"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_create_contract_usstock_regression(self):
        """UC-3: USStock AAPL unchanged → symbol=AAPL, exchange=SMART, currency=USD."""
        client = _make_client_with_mock_ib()
        contract = client._create_contract("AAPL", "USStock")
        assert contract.symbol == "AAPL"
        assert contract.exchange == "SMART"
        assert contract.currency == "USD"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_create_contract_hshare_regression(self):
        """UC-4: HShare 0700.HK unchanged → symbol=700, exchange=SEHK, currency=HKD."""
        client = _make_client_with_mock_ib()
        contract = client._create_contract("0700.HK", "HShare")
        assert contract.symbol == "700"
        assert contract.exchange == "SEHK"
        assert contract.currency == "HKD"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_create_contract_unknown_raises(self):
        """UC-5: Unknown market_type 'Crypto' → ValueError with 'Crypto' in message."""
        client = _make_client_with_mock_ib()
        with pytest.raises(ValueError, match="Crypto"):
            client._create_contract("AAPL", "Crypto")

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_place_order_unknown_market_type_graceful(self):
        """UC-6: ValueError from _create_contract caught by place_market_order → LiveOrderResult(success=False)."""
        client = _make_client_with_mock_ib()
        result = client.place_market_order("AAPL", "buy", 100, "Crypto")
        assert result.success is False


# ===========================================================================
# Forex contract qualification tests (TDD)
# ===========================================================================

class TestQualifyContractForex:
    """UC-1,2,3,7: _qualify_contract_async behavior for Forex contracts."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_forex_qualify_success_fields(self):
        """UC-1: qualifyContractsAsync populates conId, localSymbol on Forex contract."""
        client = _make_client_with_mock_ib()

        async def _mock_qualify_success_forex(*contracts):
            for c in contracts:
                c.conId = 12087792
                c.localSymbol = "EUR.USD"
                c.tradingClass = "EUR.USD"
            return list(contracts)

        client._ib.qualifyContractsAsync = _mock_qualify_success_forex
        mock_ib_insync = _make_mock_ib_insync()
        contract = mock_ib_insync.Forex(pair='EURUSD')

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(client._qualify_contract_async(contract))
        finally:
            loop.close()

        assert result is True
        assert contract.conId == 12087792
        assert contract.localSymbol == "EUR.USD"
        assert contract.exchange == "IDEALPRO"
        assert contract.secType == "CASH"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_forex_qualify_failure(self):
        """UC-2: qualifyContractsAsync returns empty list → False."""
        client = _make_client_with_mock_ib()

        async def _mock_qualify_empty(*contracts):
            return []

        client._ib.qualifyContractsAsync = _mock_qualify_empty
        mock_ib_insync = _make_mock_ib_insync()
        contract = mock_ib_insync.Forex(pair='EURUSD')

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(client._qualify_contract_async(contract))
        finally:
            loop.close()

        assert result is False

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_forex_qualify_exception(self, caplog):
        """UC-3: qualifyContractsAsync raises Exception → returns False, logs WARNING."""
        client = _make_client_with_mock_ib()

        async def _mock_qualify_raise(*contracts):
            raise Exception("Network error")

        client._ib.qualifyContractsAsync = _mock_qualify_raise
        mock_ib_insync = _make_mock_ib_insync()
        contract = mock_ib_insync.Forex(pair='EURUSD')

        loop = asyncio.new_event_loop()
        try:
            with caplog.at_level(logging.WARNING):
                result = loop.run_until_complete(client._qualify_contract_async(contract))
        finally:
            loop.close()

        assert result is False
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) >= 1

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_error_message_includes_market_type(self):
        """UC-7: place_market_order with Forex, qualify fails → message contains 'Forex'."""
        client = _make_client_with_mock_ib()

        async def _mock_qualify_empty(*contracts):
            return []

        client._ib.qualifyContractsAsync = _mock_qualify_empty

        result = client.place_market_order("EURUSD", "buy", 20000, "Forex")
        assert result.success is False
        assert "Forex" in result.message


class TestValidateQualifiedContract:
    """UC-4,5,6,8,9: _validate_qualified_contract post-qualify defensive checks."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_forex_valid(self):
        """UC-4: Forex contract with correct secType and conId → (True, "")."""
        client = _make_client_with_mock_ib()
        mock_ib_insync = _make_mock_ib_insync()
        contract = mock_ib_insync.Forex(pair='EURUSD')
        contract.conId = 12087792
        valid, reason = client._validate_qualified_contract(contract, "Forex")
        assert valid is True
        assert reason == ""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_forex_sectype_mismatch(self):
        """UC-5: Forex contract with secType='STK' → (False, 'Expected secType=CASH...')."""
        client = _make_client_with_mock_ib()
        mock_ib_insync = _make_mock_ib_insync()
        contract = mock_ib_insync.Forex(pair='EURUSD')
        contract.secType = "STK"
        contract.conId = 12087792
        valid, reason = client._validate_qualified_contract(contract, "Forex")
        assert valid is False
        assert "Expected secType=CASH for Forex, got STK" in reason

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_conid_zero(self):
        """UC-6: Contract with conId=0 → (False, contains 'conId is 0')."""
        client = _make_client_with_mock_ib()
        mock_ib_insync = _make_mock_ib_insync()
        contract = mock_ib_insync.Forex(pair='EURUSD')
        contract.conId = 0
        valid, reason = client._validate_qualified_contract(contract, "Forex")
        assert valid is False
        assert "conId is 0" in reason

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_stock_valid(self):
        """UC-8: USStock with secType='STK' and valid conId → (True, "")."""
        client = _make_client_with_mock_ib()
        mock_ib_insync = _make_mock_ib_insync()
        contract = mock_ib_insync.Stock(symbol="AAPL", exchange="SMART", currency="USD")
        contract.secType = "STK"
        contract.conId = 265598
        valid, reason = client._validate_qualified_contract(contract, "USStock")
        assert valid is True
        assert reason == ""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_hshare_valid(self):
        """UC-9: HShare with secType='STK' and valid conId → (True, "")."""
        client = _make_client_with_mock_ib()
        mock_ib_insync = _make_mock_ib_insync()
        contract = mock_ib_insync.Stock(symbol="700", exchange="SEHK", currency="HKD")
        contract.secType = "STK"
        contract.conId = 4157892
        valid, reason = client._validate_qualified_contract(contract, "HShare")
        assert valid is True
        assert reason == ""


# ===========================================================================
# Worker thread tests (now TaskQueue-based)
# ===========================================================================

class TestWorkerThread:
    """Verify the TaskQueue-based task dispatch mechanism."""

    def test_submit_runs_via_taskqueue(self):
        """_submit should execute the callable via TaskQueue → LoopExecutor."""
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        client._order_contexts = {}
        client._events_registered = False
        client._reconnect_thread = None
        client._reconnect_stop = threading.Event()

        from app.services.live_trading.task_queue import TaskQueue
        client._tq = TaskQueue(loop_executor_name="test-loop", pool_executor_name="test-pool", pool_workers=2)
        client._tq.start()

        caller_tid = threading.current_thread().ident
        result_holder = {}

        def task():
            result_holder["tid"] = threading.current_thread().ident
            return 42

        result = client._submit(task, timeout=5.0, is_blocking=False)

        assert result == 42
        assert result_holder["tid"] != caller_tid
        client._tq.shutdown()

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

        from app.services.live_trading.task_queue import TaskQueue
        client._tq = TaskQueue(loop_executor_name="test-loop", pool_executor_name="test-pool", pool_workers=2)
        client._tq.start()

        def bad_task():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            client._submit(bad_task, timeout=5.0, is_blocking=False)
        client._tq.shutdown()

    def test_shutdown_stops_taskqueue(self):
        """shutdown() should stop the TaskQueue."""
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        client._order_contexts = {}
        client._events_registered = False
        client._reconnect_thread = None
        client._reconnect_stop = threading.Event()

        from app.services.live_trading.task_queue import TaskQueue
        client._tq = TaskQueue(loop_executor_name="test-loop", pool_executor_name="test-pool", pool_workers=2)
        client._tq.start()

        client.shutdown()


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
    def test_hshare_unknown_symbol_rejects_non_default_lot(self):
        client = _make_client_with_mock_ib()
        result = client.place_market_order("00388", "buy", 7, "HShare")
        assert result.success is False
        assert "100" in result.message
        client._ib.placeOrder.assert_not_called()

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_hshare_unknown_symbol_accepts_default_lot(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=104)
        client._ib.placeOrder.return_value = trade_mock

        result = client.place_market_order("00388", "buy", 100, "HShare")
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
        assert "Invalid" in result.message and "contract" in result.message

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_sell_action_correct(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=301)
        client._ib.placeOrder.return_value = trade_mock
        client.place_market_order("AAPL", "sell", 10, "USStock")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.action == "SELL"


# ===========================================================================
# TIF policy: USStock non-close uses DAY; Forex uses IOC (TestTifForexPolicy)
# ===========================================================================

class TestTifDay:
    """USStock: non-close paths use tif='DAY' on market/limit orders (Error 10349)."""

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


class TestTifForexPolicy:
    """UC-T1–T8: Forex IOC for every signal; UC-E1–E3: USStock/HShare TIF regression."""

    @pytest.mark.parametrize(
        "signal_type",
        [
            "open_long",  # UC-T1
            "close_long",  # UC-T2
            "open_short",  # UC-T3
            "close_short",  # UC-T4
            "add_long",  # UC-T5
            "add_short",  # UC-T6
            "reduce_long",  # UC-T7
            "reduce_short",  # UC-T8
        ],
        ids=["uc_t1", "uc_t2", "uc_t3", "uc_t4", "uc_t5", "uc_t6", "uc_t7", "uc_t8"],
    )
    def test_forex_signal_returns_ioc(self, signal_type):
        assert IBKRClient._get_tif_for_signal(signal_type, "Forex") == "IOC"

    def test_uc_e1_usstock_open_uses_day(self):
        assert IBKRClient._get_tif_for_signal("open_long", "USStock") == "DAY"

    def test_uc_e2_usstock_close_uses_ioc(self):
        assert IBKRClient._get_tif_for_signal("close_long", "USStock") == "IOC"

    def test_uc_e3_hshare_close_uses_day(self):
        assert IBKRClient._get_tif_for_signal("close_long", "HShare") == "DAY"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_forex_market_order_passes_tif_ioc(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=500)
        client._ib.placeOrder.return_value = trade_mock
        client.place_market_order("EURUSD", "buy", 10000.0, "Forex", signal_type="open_long")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.tif == "IOC"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_forex_limit_order_passes_tif_ioc(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=501)
        client._ib.placeOrder.return_value = trade_mock
        client.place_limit_order("EURUSD", "buy", 10000.0, 1.10, "Forex", signal_type="close_long")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.tif == "IOC"


class TestPlaceMarketOrderForex:
    """UC-M1–M3: Forex market paths; UC-E1–E3: errors; UC-R1–R2: USStock/HShare TIF regression."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_uc_m1_eurusd_buy_market_ioc_cash(self):
        """UC-M1: EURUSD buy 20000 → CASH, EUR/USD, IOC, totalQuantity base units."""
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=600)
        client._ib.placeOrder.return_value = trade_mock
        result = client.place_market_order(
            "EURUSD", "buy", 20000.0, "Forex", signal_type="open_long",
        )
        assert result.success is True
        assert result.status == "Submitted"
        contract, placed_order = client._ib.placeOrder.call_args[0]
        assert contract.secType == "CASH"
        assert contract.symbol == "EUR"
        assert contract.currency == "USD"
        assert placed_order.totalQuantity == 20000
        assert placed_order.tif == "IOC"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_uc_m2_gbpjpy_sell_market(self):
        """UC-M2: GBPJPY sell 50000 → SELL, GBP/JPY, IOC."""
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=601)
        client._ib.placeOrder.return_value = trade_mock
        result = client.place_market_order(
            "GBPJPY", "sell", 50000.0, "Forex", signal_type="open_short",
        )
        assert result.success is True
        contract, placed_order = client._ib.placeOrder.call_args[0]
        assert contract.symbol == "GBP"
        assert contract.currency == "JPY"
        assert placed_order.action == "SELL"
        assert placed_order.totalQuantity == 50000
        assert placed_order.tif == "IOC"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_uc_m3_xauusd_buy_market(self):
        """UC-M3: XAUUSD buy 10 → XAU/USD, IOC."""
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=602)
        client._ib.placeOrder.return_value = trade_mock
        result = client.place_market_order(
            "XAUUSD", "buy", 10.0, "Forex", signal_type="open_long",
        )
        assert result.success is True
        contract, placed_order = client._ib.placeOrder.call_args[0]
        assert contract.symbol == "XAU"
        assert contract.currency == "USD"
        assert float(placed_order.totalQuantity) == 10.0
        assert placed_order.tif == "IOC"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_uc_e1_qualify_failure_unknown_pair(self):
        """UC-E1: unknown 6-letter pair ABCDEF → qualify [], message has Invalid/Forex/ABCDEF."""
        client = _make_client_with_mock_ib()

        async def _mock_qualify_empty(*contracts):
            return []

        client._ib.qualifyContractsAsync = _mock_qualify_empty
        result = client.place_market_order(
            "ABCDEF", "buy", 20000.0, "Forex", signal_type="open_long",
        )
        assert result.success is False
        assert "Invalid" in result.message
        assert "Forex" in result.message
        assert "ABCDEF" in result.message

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_uc_e2_alignment_yields_zero_forex_hint(self):
        """UC-E2: sizeIncrement 25000 with qty 10000 → 0; Forex IDEALPRO hint; no placeOrder."""
        IBKRClient._lot_size_cache.clear()
        try:
            client = _make_client_with_mock_ib()

            async def _mock_details(*args, **kwargs):
                return [types.SimpleNamespace(sizeIncrement=25000.0, minSize=0)]

            client._ib.reqContractDetailsAsync = _mock_details
            trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=603)
            client._ib.placeOrder.return_value = trade_mock
            result = client.place_market_order(
                "EURUSD", "buy", 10000.0, "Forex", signal_type="open_long",
            )
            assert result.success is False
            assert "Quantity 10000.0 rounds to 0" in result.message
            assert (
                "For Forex (IDEALPRO), the amount may be below the minimum tradable size for this pair."
                in result.message
            )
            assert client._ib.placeOrder.call_count == 0
        finally:
            IBKRClient._lot_size_cache.clear()

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_uc_e3_zero_qty_rejected_before_place_order(self):
        """UC-E3: quantity 0 → normalizer; no placeOrder."""
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=604)
        client._ib.placeOrder.return_value = trade_mock
        result = client.place_market_order("EURUSD", "buy", 0.0, "Forex")
        assert result.success is False
        assert "Quantity must be positive" in result.message
        assert client._ib.placeOrder.call_count == 0

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_uc_r1_usstock_open_long_uses_day_tif(self):
        """UC-R1: USStock open_long market order uses tif DAY."""
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=605)
        client._ib.placeOrder.return_value = trade_mock
        client.place_market_order("AAPL", "buy", 100.0, "USStock", signal_type="open_long")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.tif == "DAY"

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_uc_r2_hshare_open_long_uses_day_tif(self):
        """UC-R2: HShare open_long market order uses tif DAY."""
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=606)
        client._ib.placeOrder.return_value = trade_mock
        client.place_market_order("00005", "buy", 400.0, "HShare", signal_type="open_long")
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
    """Verify event callbacks dispatch to _handle_fill/_handle_reject via IO."""

    def test_on_order_status_filled_triggers_handle_fill(self):
        client = _make_client_with_mock_ib()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = IBKROrderContext(order_id=42, pending_order_id=10, strategy_id=5, symbol="AAPL")
        client._order_contexts[42] = ctx

        trade = _make_trade_mock(status="Filled", filled=10.0, avg_price=155.0, order_id=42)
        client._on_order_status(trade)

        assert 42 not in client._order_contexts  # popped for fill idempotency
        assert 42 in client._commission_contexts  # lingers for commissionReport
        assert len(fire_calls) == 1

    def test_on_order_status_cancelled_with_fill_triggers_handle_fill(self):
        client = _make_client_with_mock_ib()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = IBKROrderContext(order_id=43, pending_order_id=11, strategy_id=5, symbol="AAPL")
        client._order_contexts[43] = ctx

        trade = _make_trade_mock(status="Cancelled", filled=5.0, avg_price=300.0, order_id=43)
        client._on_order_status(trade)

        assert 43 not in client._order_contexts  # popped for fill idempotency
        assert 43 in client._commission_contexts  # lingers for commissionReport
        assert len(fire_calls) == 1

    def test_on_order_status_hard_terminal_triggers_handle_reject(self):
        client = _make_client_with_mock_ib()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = IBKROrderContext(order_id=44, pending_order_id=12, strategy_id=5, symbol="AAPL")
        client._order_contexts[44] = ctx

        trade = _make_trade_mock(
            status="Inactive", filled=0, avg_price=0, order_id=44,
            log_messages=["Order rejected"]
        )
        client._on_order_status(trade)

        assert 44 not in client._order_contexts
        assert len(fire_calls) == 1

    def test_on_order_status_ignores_untracked_order(self):
        client = _make_client_with_mock_ib()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        trade = _make_trade_mock(status="Filled", filled=10.0, avg_price=155.0, order_id=99)
        client._on_order_status(trade)
        assert len(fire_calls) == 0

    def test_on_order_status_active_does_not_dispatch(self):
        client = _make_client_with_mock_ib()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = IBKROrderContext(order_id=45, pending_order_id=13, strategy_id=5, symbol="AAPL")
        client._order_contexts[45] = ctx

        trade = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=45)
        client._on_order_status(trade)

        assert 45 in client._order_contexts
        assert len(fire_calls) == 0

    def test_on_order_status_cancelled_zero_fills_rejects(self):
        """Cancelled with 0 fills is treated as a rejection (e.g. lot-size error)."""
        client = _make_client_with_mock_ib()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = IBKROrderContext(order_id=46, pending_order_id=14, strategy_id=5, symbol="AAPL")
        client._order_contexts[46] = ctx

        trade = _make_trade_mock(status="Cancelled", filled=0, avg_price=0, order_id=46)
        client._on_order_status(trade)

        assert 46 not in client._order_contexts
        assert len(fire_calls) == 1


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
        import asyncio
        client = _make_client_with_mock_ib()
        call_count = {"n": 0}

        async def mock_connect():
            call_count["n"] += 1
            if call_count["n"] < 2:
                client._ib.isConnected.return_value = False
                return False
            client._ib.isConnected.return_value = True
            return True

        client._ib.isConnected.return_value = False
        client._do_connect_coro = mock_connect
        client._ensure_connected(retries=3, delay=0.01)
        assert call_count["n"] == 2

    def test_raises_after_all_retries_exhausted(self):
        import asyncio
        client = _make_client_with_mock_ib()
        client._ib.isConnected.return_value = False

        async def mock_connect():
            return False

        client._do_connect_coro = mock_connect
        with pytest.raises(ConnectionError, match="Cannot connect to IBKR after 3 attempts"):
            client._ensure_connected(retries=3, delay=0.01)

    def test_no_retry_when_already_connected(self):
        client = _make_client_with_mock_ib()
        client._ib.isConnected.return_value = True
        call_count = {"n": 0}

        async def mock_connect():
            call_count["n"] += 1
            return True

        client._do_connect_coro = mock_connect
        client._ensure_connected()
        assert call_count["n"] == 0

    def test_do_connect_coro_called_via_submit_ib(self):
        """_ensure_connected submits _do_connect_coro via _submit_ib."""
        import asyncio
        client = _make_client_with_mock_ib()
        client._ib.isConnected.return_value = False
        call_count = {"n": 0}

        async def mock_connect():
            call_count["n"] += 1
            return True

        client._do_connect_coro = mock_connect
        client._ensure_connected(retries=1, delay=0.01)
        assert call_count["n"] == 1


# ===========================================================================
# RTH gate tests
# ===========================================================================

class TestRTHGate:
    """Verify is_market_open returns correct result based on RTH status."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    @patch("app.services.live_trading.ibkr_trading.trading_hours.is_rth_check", return_value=False)
    def test_is_market_open_returns_false_outside_rth(self, _mock_rth):
        client = _make_client_with_mock_ib()
        is_open, reason = client.is_market_open("AAPL", "USStock")
        assert is_open is False
        assert "market closed" in reason.lower()

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    @patch("app.services.live_trading.ibkr_trading.trading_hours.is_rth_check", return_value=True)
    def test_is_market_open_returns_true_during_rth(self, _mock_rth):
        client = _make_client_with_mock_ib()
        is_open, reason = client.is_market_open("AAPL", "USStock")
        assert is_open is True
        assert reason == ""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    @patch("app.services.live_trading.ibkr_trading.trading_hours.is_rth_check", return_value=True)
    def test_market_order_allowed_during_rth(self, _mock_rth):
        client = _make_client_with_mock_ib()
        trade = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=500)
        client._ib.placeOrder.return_value = trade
        result = client.place_market_order("AAPL", "buy", 10, "USStock")
        assert result.success is True
        client._ib.placeOrder.assert_called_once()


@pytest.mark.ForexRTH
class TestForexRTHGate:
    """UC-FX-I01–I05: is_market_open Forex path with real is_rth_check (overrides autouse mock)."""

    @pytest.fixture(autouse=True)
    def _use_real_is_rth_check(self):
        with patch(
            "app.services.live_trading.ibkr_trading.trading_hours.is_rth_check",
            wraps=_REAL_IS_RTH_CHECK_FN,
        ):
            yield

    @pytest.fixture(autouse=True)
    def _patch_ib_insync_forex_rth(self):
        with patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync()):
            yield

    def setup_method(self):
        IBKRClient._rth_details_cache.clear()
        _clear_trading_hours_cache()

    def test_UC_FX_I01_eurusd_cross_day_inside(self):
        """UC-FX-I01: EURUSD cross-day liquidHours; server time inside segment."""
        tz = pytz.timezone("US/Eastern")
        local = tz.localize(datetime.datetime(2026, 3, 9, 14, 0, 0))
        server_utc = local.astimezone(pytz.UTC)
        client = _make_forex_rth_client(
            "20260308:1715-20260309:1700",
            "EST",
            server_utc,
        )
        open_ok, reason = client.is_market_open("EURUSD", "Forex")
        assert open_ok is True
        assert reason == ""

    def test_UC_FX_I02_saturday_closed(self):
        """UC-FX-I02: Saturday with CLOSED schedule → not open."""
        tz = pytz.timezone("US/Eastern")
        local = tz.localize(datetime.datetime(2026, 3, 7, 12, 0, 0))
        server_utc = local.astimezone(pytz.UTC)
        client = _make_forex_rth_client("20260307:CLOSED", "EST", server_utc)
        open_ok, reason = client.is_market_open("EURUSD", "Forex")
        assert open_ok is False
        assert "closed" in reason.lower()

    def test_UC_FX_I03_gbpjpy_jst(self):
        """UC-FX-I03: GBPJPY with JST liquidHours; server UTC matches local session."""
        tz = pytz.timezone("Asia/Tokyo")
        local = tz.localize(datetime.datetime(2026, 3, 10, 14, 0, 0))
        server_utc = local.astimezone(pytz.UTC)
        client = _make_forex_rth_client("20260310:0900-20260310:1800", "JST", server_utc)
        open_ok, reason = client.is_market_open("GBPJPY", "Forex")
        assert open_ok is True
        assert reason == ""

    def test_UC_FX_I04_xagusd_window(self):
        """UC-FX-I04: XAGUSD with dedicated EST day window."""
        tz = pytz.timezone("US/Eastern")
        local = tz.localize(datetime.datetime(2026, 3, 12, 14, 0, 0))
        server_utc = local.astimezone(pytz.UTC)
        client = _make_forex_rth_client(
            "20260312:0800-20260312:2000",
            "EST",
            server_utc,
        )
        open_ok, reason = client.is_market_open("XAGUSD", "Forex")
        assert open_ok is True
        assert reason == ""

    def test_UC_FX_I05_forex_closed_message(self):
        """UC-FX-I05: Forex closed reason includes 24/5 and weekend/maintenance context."""
        tz = pytz.timezone("US/Eastern")
        local = tz.localize(datetime.datetime(2026, 3, 7, 12, 0, 0))
        server_utc = local.astimezone(pytz.UTC)
        client = _make_forex_rth_client("20260307:CLOSED", "EST", server_utc)
        open_ok, reason = client.is_market_open("EURUSD", "Forex")
        assert open_ok is False
        assert "Forex 24/5" in reason
        assert "weekend" in reason.lower() or "maintenance" in reason.lower()


# ===========================================================================
# TaskQueue submit helpers tests
# ===========================================================================

class TestSubmitHelpers:
    """Verify _submit dispatch correctly with is_blocking parameter."""

    def test_submit_runs_on_loop_thread(self):
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        client._order_contexts = {}
        client._events_registered = False
        client._reconnect_thread = None
        client._reconnect_stop = threading.Event()

        from app.services.live_trading.task_queue import TaskQueue
        client._tq = TaskQueue(loop_executor_name="test-loop", pool_executor_name="test-pool", pool_workers=2)
        client._tq.start()

        caller_tid = threading.current_thread().ident

        def task():
            return threading.current_thread().ident

        result = client._submit(task, timeout=5.0, is_blocking=False)
        assert result != caller_tid
        client._tq.shutdown()

    def test_submit_runs_in_pool(self):
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        client._order_contexts = {}
        client._events_registered = False
        client._reconnect_thread = None
        client._reconnect_stop = threading.Event()

        from app.services.live_trading.task_queue import TaskQueue
        client._tq = TaskQueue(loop_executor_name="test-loop", pool_executor_name="test-pool", pool_workers=2)
        client._tq.start()

        def task():
            return threading.current_thread().name

        result = client._submit(task, timeout=5.0, is_blocking=True)
        assert "test-pool" in result
        client._tq.shutdown()

    def test_fire_submit_executes_without_blocking(self):
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        client._order_contexts = {}
        client._events_registered = False
        client._reconnect_thread = None
        client._reconnect_stop = threading.Event()

        from app.services.live_trading.task_queue import TaskQueue
        client._tq = TaskQueue(loop_executor_name="test-loop", pool_executor_name="test-pool", pool_workers=2)
        client._tq.start()

        container = []
        client._fire_submit(lambda: container.append("done"))
        time.sleep(0.5)
        assert container == ["done"]
        client._tq.shutdown()

    def test_submit_propagates_exception(self):
        client = IBKRClient.__new__(IBKRClient)
        client.config = IBKRConfig()
        client._ib = None
        client._account = ""
        client._order_contexts = {}
        client._events_registered = False
        client._reconnect_thread = None
        client._reconnect_stop = threading.Event()

        from app.services.live_trading.task_queue import TaskQueue
        client._tq = TaskQueue(loop_executor_name="test-loop", pool_executor_name="test-pool", pool_workers=2)
        client._tq.start()

        def bad_task():
            raise ValueError("bad value")

        with pytest.raises(ValueError, match="bad value"):
            client._submit(bad_task, timeout=5.0, is_blocking=False)
        client._tq.shutdown()


# ===========================================================================
# PnL Subscription Activation Tests
# ===========================================================================

class TestActivatePnLSubscriptions:
    """Verify _activate_pnl_subscriptions activates reqPnL and reqPositionsAsync."""

    def test_activate_pnl_calls_reqpnl_and_reqpositions(self):
        client = _make_client_with_mock_ib()
        client._account = "DU123456"

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(client._activate_pnl_subscriptions())
        finally:
            loop.close()

        client._ib.reqPnL.assert_called_once_with("DU123456")
        client._ib.reqPositionsAsync.assert_called_once()

    def test_activate_pnl_skips_when_no_account(self):
        client = _make_client_with_mock_ib()
        client._account = ""

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(client._activate_pnl_subscriptions())
        finally:
            loop.close()

        client._ib.reqPnL.assert_not_called()
        client._ib.reqPositionsAsync.assert_not_called()

    def test_activate_pnl_handles_reqpnl_error(self):
        client = _make_client_with_mock_ib()
        client._account = "DU123456"
        client._ib.reqPnL.side_effect = Exception("reqPnL failed")

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(client._activate_pnl_subscriptions())
        finally:
            loop.close()

        client._ib.reqPositionsAsync.assert_called_once()

    def test_activate_pnl_handles_reqpositions_error(self):
        client = _make_client_with_mock_ib()
        client._account = "DU123456"
        client._ib.reqPositionsAsync.side_effect = Exception("reqPositionsAsync failed")

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(client._activate_pnl_subscriptions())
        finally:
            loop.close()

        client._ib.reqPnL.assert_called_once()


# ===========================================================================
# PnL Event Tests
# ===========================================================================

class TestPnLEventCallbacks:
    """Verify PnL event callbacks store data to database correctly."""

    @patch("app.services.live_trading.records.ibkr_save_pnl")
    def test_on_pnl_stores_to_database(self, mock_save_pnl):
        mock_save_pnl.return_value = True
        client = _make_client_with_mock_ib()

        pnl_entry = MagicMock()
        pnl_entry.account = "DU123456"
        pnl_entry.dailyPnL = 100.50
        pnl_entry.unrealizedPnL = 500.25
        pnl_entry.realizedPnL = 200.75

        client._on_pnl(pnl_entry)

        client._fire_submit.assert_called_once()
        mock_save_pnl.assert_called_once_with(
            account="DU123456",
            daily_pnl=100.50,
            unrealized_pnl=500.25,
            realized_pnl=200.75,
        )

    @patch("app.services.live_trading.records.ibkr_save_pnl")
    def test_on_pnl_handles_nan_values(self, mock_save_pnl):
        mock_save_pnl.return_value = True
        client = _make_client_with_mock_ib()

        pnl_entry = MagicMock()
        pnl_entry.account = "DU123456"
        pnl_entry.dailyPnL = float("nan")
        pnl_entry.unrealizedPnL = None
        pnl_entry.realizedPnL = 200.75

        client._on_pnl(pnl_entry)

        client._fire_submit.assert_called_once()
        mock_save_pnl.assert_called_once()
        args = mock_save_pnl.call_args
        assert args[1]["daily_pnl"] == 0.0
        assert args[1]["unrealized_pnl"] == 0.0
        assert args[1]["realized_pnl"] == 200.75

    @patch("app.services.live_trading.records.ibkr_save_pnl")
    def test_on_pnl_logs_error_on_db_failure(self, mock_save_pnl):
        mock_save_pnl.return_value = False
        client = _make_client_with_mock_ib()

        pnl_entry = MagicMock()
        pnl_entry.account = "DU123456"
        pnl_entry.dailyPnL = 100.0
        pnl_entry.unrealizedPnL = 200.0
        pnl_entry.realizedPnL = 50.0

        client._on_pnl(pnl_entry)

        client._fire_submit.assert_called_once()

    @patch("app.services.live_trading.records.ibkr_save_position")
    def test_on_pnl_single_stores_to_database(self, mock_save_position):
        mock_save_position.return_value = True
        client = _make_client_with_mock_ib()
        client._conid_to_symbol = {208813719: "GOOGL"}

        pnl_single = MagicMock()
        pnl_single.account = "DU123456"
        pnl_single.conId = 208813719
        pnl_single.dailyPnL = 10.50
        pnl_single.unrealizedPnL = 50.25
        pnl_single.realizedPnL = 20.75
        pnl_single.position = 1.0
        pnl_single.value = 300.0

        client._on_pnl_single(pnl_single)

        client._fire_submit.assert_called_once()
        mock_save_position.assert_called_once()
        args = mock_save_position.call_args
        assert args[1]["account"] == "DU123456"
        assert args[1]["con_id"] == 208813719
        assert args[1]["symbol"] == "GOOGL"
        assert args[1]["daily_pnl"] == 10.50
        assert args[1]["unrealized_pnl"] == 50.25
        assert args[1]["realized_pnl"] == 20.75
        assert args[1]["position"] == 1.0
        assert args[1]["value"] == 300.0

    @patch("app.services.live_trading.records.ibkr_save_position")
    def test_on_pnl_single_uses_empty_symbol_if_not_in_map(self, mock_save_position):
        mock_save_position.return_value = True
        client = _make_client_with_mock_ib()
        client._conid_to_symbol = {}

        pnl_single = MagicMock()
        pnl_single.account = "DU123456"
        pnl_single.conId = 999999
        pnl_single.dailyPnL = 10.0
        pnl_single.unrealizedPnL = 50.0
        pnl_single.realizedPnL = 20.0
        pnl_single.position = 1.0
        pnl_single.value = 300.0

        client._on_pnl_single(pnl_single)

        client._fire_submit.assert_called_once()
        args = mock_save_position.call_args
        assert args[1]["symbol"] == ""


# ===========================================================================
# Position Event Tests
# ===========================================================================

class TestPositionEventCallback:
    """Verify position event callback stores data and subscribes to PnL."""

    @patch("app.services.live_trading.records.ibkr_save_position")
    def test_on_position_stores_and_subscribes_pnl_single(self, mock_save_position):
        mock_save_position.return_value = True
        client = _make_client_with_mock_ib()

        position = MagicMock()
        position.account = "DU123456"
        position.contract.conId = 208813719
        position.contract.symbol = "GOOGL"
        position.position = 1.0
        position.avgCost = 300.0

        client._on_position(position)

        client._fire_submit.assert_called()
        assert client._fire_submit.call_count == 2

        mock_save_position.assert_called_once()
        args = mock_save_position.call_args
        assert args[1]["account"] == "DU123456"
        assert args[1]["con_id"] == 208813719
        assert args[1]["symbol"] == "GOOGL"
        assert args[1]["position"] == 1.0
        assert args[1]["avg_cost"] == 300.0

        client._ib.reqPnLSingle.assert_called_once_with("DU123456", "", 208813719)

        assert client._conid_to_symbol[208813719] == "GOOGL"

    @patch("app.services.live_trading.records.ibkr_save_position")
    def test_on_position_updates_conid_to_symbol_map(self, mock_save_position):
        mock_save_position.return_value = True
        client = _make_client_with_mock_ib()
        client._conid_to_symbol = {}

        position = MagicMock()
        position.account = "DU123456"
        position.contract.conId = 123456
        position.contract.symbol = "AAPL"
        position.position = 100.0
        position.avgCost = 150.0

        client._on_position(position)

        client._fire_submit.assert_called()
        assert 123456 in client._conid_to_symbol
        assert client._conid_to_symbol[123456] == "AAPL"

    @patch("app.services.live_trading.records.ibkr_save_position")
    def test_on_position_handles_db_error_gracefully(self, mock_save_position):
        mock_save_position.return_value = False
        client = _make_client_with_mock_ib()

        position = MagicMock()
        position.account = "DU123456"
        position.contract.conId = 208813719
        position.contract.symbol = "GOOGL"
        position.position = 1.0
        position.avgCost = 300.0

        client._on_position(position)

        client._fire_submit.assert_called()
        assert client._fire_submit.call_count == 2
        client._ib.reqPnLSingle.assert_called_once()

    @patch("app.services.live_trading.records.ibkr_save_position")
    def test_on_position_handles_reqpnl_single_error(self, mock_save_position):
        mock_save_position.return_value = True
        client = _make_client_with_mock_ib()
        client._ib.reqPnLSingle.side_effect = Exception("reqPnLSingle failed")

        position = MagicMock()
        position.account = "DU123456"
        position.contract.conId = 208813719
        position.contract.symbol = "GOOGL"
        position.position = 1.0
        position.avgCost = 300.0

        client._on_position(position)

        client._fire_submit.assert_called()
        assert client._fire_submit.call_count == 2
        mock_save_position.assert_called_once()

    @patch("app.services.live_trading.records.ibkr_save_position")
    def test_on_position_skips_duplicate_subscription(self, mock_save_position):
        mock_save_position.return_value = True
        client = _make_client_with_mock_ib()
        client._subscribed_conids = {208813719}

        position = MagicMock()
        position.account = "DU123456"
        position.contract.conId = 208813719
        position.contract.symbol = "GOOGL"
        position.position = 1.0
        position.avgCost = 300.0

        client._on_position(position)

        client._fire_submit.assert_called()
        assert client._fire_submit.call_count == 1

        client._ib.reqPnLSingle.assert_not_called()
        assert 208813719 in client._subscribed_conids

    @patch("app.services.live_trading.records.ibkr_save_position")
    def test_on_position_calls_cancel_before_resubscribe(self, mock_save_position):
        mock_save_position.return_value = True
        client = _make_client_with_mock_ib()
        client._ib.cancelPnLSingle = MagicMock()

        position = MagicMock()
        position.account = "DU123456"
        position.contract.conId = 999888
        position.contract.symbol = "TSLA"
        position.position = 50.0
        position.avgCost = 200.0

        client._on_position(position)

        client._fire_submit.assert_called()
        assert client._fire_submit.call_count == 2

        client._ib.cancelPnLSingle.assert_called_once_with("DU123456", "", 999888)
        client._ib.reqPnLSingle.assert_called_once_with("DU123456", "", 999888)


# ===========================================================================
# Phase 10: Forex position / portfolio — localSymbol + contract metadata (RUNT-02)
# ===========================================================================

class TestForexFillsPositionPnLCallbacks:
    """UC-FP1, UC-FP2 — _conid_to_symbol and ibkr_save_position use localSymbol + metadata."""

    @patch("app.services.live_trading.records.ibkr_save_position")
    def test_uc_fp1_position_event_uses_eurusd_label(self, mock_save_position):
        mock_save_position.return_value = True
        client = _make_client_with_mock_ib()

        position = MagicMock()
        position.account = "DU1"
        position.contract.conId = 4242
        position.contract.symbol = "EUR"
        position.contract.localSymbol = "EUR.USD"
        position.contract.secType = "CASH"
        position.contract.exchange = "IDEALPRO"
        position.contract.currency = "USD"
        position.position = 10000.0
        position.avgCost = 1.05

        client._on_position(position)

        assert client._conid_to_symbol[4242] == "EUR.USD"
        mock_save_position.assert_called_once()
        kwargs = mock_save_position.call_args[1]
        assert kwargs["symbol"] == "EUR.USD"
        assert kwargs["sec_type"] == "CASH"
        assert kwargs["exchange"] == "IDEALPRO"
        assert kwargs["currency"] == "USD"

    @patch("app.services.live_trading.records.ibkr_save_position")
    def test_uc_fp2_update_portfolio_matches_forex_metadata(self, mock_save_position):
        mock_save_position.return_value = True
        client = _make_client_with_mock_ib()

        item = MagicMock()
        item.account = "DU1"
        item.contract.conId = 4242
        item.contract.symbol = "EUR"
        item.contract.localSymbol = "EUR.USD"
        item.contract.secType = "CASH"
        item.contract.exchange = "IDEALPRO"
        item.contract.currency = "USD"
        item.position = 10000.0
        item.unrealizedPNL = 10.0
        item.realizedPNL = 0.0
        item.marketValue = 10500.0
        item.marketPrice = 1.05
        item.averageCost = 1.0

        client._on_update_portfolio(item)

        assert client._conid_to_symbol[4242] == "EUR.USD"
        mock_save_position.assert_called_once()
        kwargs = mock_save_position.call_args[1]
        assert kwargs["symbol"] == "EUR.USD"
        assert kwargs["sec_type"] == "CASH"
        assert kwargs["exchange"] == "IDEALPRO"
        assert kwargs["currency"] == "USD"


class TestForexPositionPnLEvents:
    """UC-FP3, UC-FP7 — pnlSingle uses _conid_to_symbol; Forex round-trip to get_positions."""

    @patch("app.services.live_trading.records.ibkr_save_position")
    def test_uc_fp3_pnl_single_uses_conid_map_symbol(self, mock_save_position):
        """UC-FP3: After map is filled with EUR.USD, _on_pnl_single passes that symbol to save."""
        mock_save_position.return_value = True
        client = _make_client_with_mock_ib()
        client._conid_to_symbol[4242] = "EUR.USD"

        pnl_single = MagicMock()
        pnl_single.account = "DU123456"
        pnl_single.conId = 4242
        pnl_single.dailyPnL = 1.0
        pnl_single.unrealizedPnL = 2.0
        pnl_single.realizedPnL = 3.0
        pnl_single.position = 10000.0
        pnl_single.value = 10500.0

        client._on_pnl_single(pnl_single)

        mock_save_position.assert_called_once()
        kwargs = mock_save_position.call_args[1]
        assert kwargs["symbol"] == "EUR.USD"

    @patch("app.services.live_trading.records.ibkr_get_positions")
    @patch("app.services.live_trading.records.ibkr_save_position")
    def test_uc_fp7_forex_round_trip_position_pnl_get_positions(
        self, mock_save_position, mock_get_positions
    ):
        """UC-FP7: Forex mocks — _on_position → _on_pnl_single → get_positions (CASH / IDEALPRO / USD)."""
        mock_save_position.return_value = True
        mock_get_positions.return_value = [
            {
                "account": "DU123456",
                "con_id": 4242,
                "symbol": "EUR.USD",
                "sec_type": "CASH",
                "exchange": "IDEALPRO",
                "currency": "USD",
                "position": 10000.0,
                "avg_cost": 1.05,
                "unrealized_pnl": 1.0,
                "daily_pnl": 0.5,
                "realized_pnl": 0.0,
                "value": 10500.0,
                "updated_at": None,
            },
        ]

        client = _make_client_with_mock_ib()
        client._account = "DU123456"

        position = MagicMock()
        position.account = "DU123456"
        position.contract.conId = 4242
        position.contract.symbol = "EUR"
        position.contract.localSymbol = "EUR.USD"
        position.contract.secType = "CASH"
        position.contract.exchange = "IDEALPRO"
        position.contract.currency = "USD"
        position.position = 10000.0
        position.avgCost = 1.05

        client._on_position(position)
        assert client._conid_to_symbol[4242] == "EUR.USD"
        pos_kw = mock_save_position.call_args_list[0][1]
        assert pos_kw["symbol"] == "EUR.USD"
        assert pos_kw["sec_type"] == "CASH"

        pnl_single = MagicMock()
        pnl_single.account = "DU123456"
        pnl_single.conId = 4242
        pnl_single.dailyPnL = 0.5
        pnl_single.unrealizedPnL = 1.0
        pnl_single.realizedPnL = 0.0
        pnl_single.position = 10000.0
        pnl_single.value = 10500.0

        client._on_pnl_single(pnl_single)
        pnl_kw = mock_save_position.call_args_list[-1][1]
        assert pnl_kw["symbol"] == "EUR.USD"

        def _sync_submit(fn, timeout=60.0, is_blocking=False):
            return fn()
        client._submit = _sync_submit

        out = client.get_positions()
        assert out[0]["symbol"] == "EUR.USD"
        assert out[0]["secType"] == "CASH"
        assert out[0]["exchange"] == "IDEALPRO"
        assert out[0]["currency"] == "USD"


# ===========================================================================
# get_pnl database read tests
# ===========================================================================

class TestGetPnlFromDatabase:
    """Verify get_pnl reads from database correctly."""

    @patch("app.services.live_trading.records.ibkr_get_pnl")
    def test_get_pnl_reads_from_database(self, mock_get_pnl):
        from datetime import datetime
        mock_get_pnl.return_value = {
            "daily_pnl": 100.50,
            "unrealized_pnl": 500.25,
            "realized_pnl": 200.75,
            "updated_at": None,
        }
        client = _make_client_with_mock_ib()
        client._account = "DU123456"

        def _sync_submit(fn, timeout=60.0, is_blocking=False):
            return fn()
        client._submit = _sync_submit

        result = client.get_pnl()

        assert result is not None
        assert result["success"] is True
        assert result["dailyPnL"] == 100.50
        assert result["unrealizedPnL"] == 500.25
        assert result["realizedPnL"] == 200.75
        mock_get_pnl.assert_called_once_with("DU123456")

    @patch("app.services.live_trading.records.ibkr_get_pnl")
    def test_get_pnl_returns_none_when_not_connected(self, mock_get_pnl):
        client = _make_client_with_mock_ib()
        client._account = "DU123456"
        client._ib = None

        result = client.get_pnl()

        assert result is None
        mock_get_pnl.assert_not_called()

    @patch("app.services.live_trading.records.ibkr_get_pnl")
    def test_get_pnl_returns_none_when_no_account(self, mock_get_pnl):
        client = _make_client_with_mock_ib()
        client._account = ""

        result = client.get_pnl()

        assert result is None
        mock_get_pnl.assert_not_called()

    @patch("app.services.live_trading.records.ibkr_get_pnl")
    def test_get_pnl_returns_none_when_no_data(self, mock_get_pnl):
        mock_get_pnl.return_value = None
        client = _make_client_with_mock_ib()
        client._account = "DU123456"

        def _sync_submit(fn, timeout=60.0, is_blocking=False):
            return fn()
        client._submit = _sync_submit

        result = client.get_pnl()

        assert result is None

    @patch("app.services.live_trading.records.ibkr_get_pnl")
    def test_get_pnl_handles_db_error(self, mock_get_pnl):
        mock_get_pnl.side_effect = Exception("DB connection failed")
        client = _make_client_with_mock_ib()
        client._account = "DU123456"

        def _sync_submit(fn, timeout=60.0, is_blocking=False):
            return fn()
        client._submit = _sync_submit

        result = client.get_pnl()

        assert result is None


# ===========================================================================
# get_positions database read tests
# ===========================================================================

class TestGetPositionsFromDatabase:
    """Verify get_positions reads from database correctly."""

    @patch("app.services.live_trading.records.ibkr_get_positions")
    def test_get_positions_reads_from_database(self, mock_get_positions):
        from datetime import datetime
        mock_get_positions.return_value = [
            {
                "account": "DU123456",
                "con_id": 123456,
                "symbol": "AAPL",
                "position": 100.0,
                "avg_cost": 150.0,
                "updated_at": None,
            },
            {
                "account": "DU123456",
                "con_id": 789012,
                "symbol": "GOOGL",
                "position": 50.0,
                "avg_cost": 2800.0,
                "updated_at": None,
            },
        ]
        client = _make_client_with_mock_ib()
        client._account = "DU123456"

        def _sync_submit(fn, timeout=60.0, is_blocking=False):
            return fn()
        client._submit = _sync_submit

        result = client.get_positions()

        assert len(result) == 2
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["quantity"] == 100.0
        assert result[0]["unrealizedPnL"] == 0.0
        assert result[1]["symbol"] == "GOOGL"
        mock_get_positions.assert_called_once_with("DU123456")

    @patch("app.services.live_trading.records.ibkr_get_positions")
    def test_get_positions_returns_empty_when_not_connected(self, mock_get_positions):
        client = _make_client_with_mock_ib()
        client._account = "DU123456"
        client._ib = None

        result = client.get_positions()

        assert result == []
        mock_get_positions.assert_not_called()

    @patch("app.services.live_trading.records.ibkr_get_positions")
    def test_get_positions_returns_empty_when_no_account(self, mock_get_positions):
        client = _make_client_with_mock_ib()
        client._account = ""

        result = client.get_positions()

        assert result == []
        mock_get_positions.assert_not_called()

    @patch("app.services.live_trading.records.ibkr_get_positions")
    def test_get_positions_returns_empty_list_when_no_data(self, mock_get_positions):
        mock_get_positions.return_value = []
        client = _make_client_with_mock_ib()
        client._account = "DU123456"

        def _sync_submit(fn, timeout=60.0, is_blocking=False):
            return fn()
        client._submit = _sync_submit

        result = client.get_positions()

        assert result == []

    @patch("app.services.live_trading.records.ibkr_get_positions")
    def test_get_positions_handles_db_error(self, mock_get_positions):
        mock_get_positions.side_effect = Exception("DB connection failed")
        client = _make_client_with_mock_ib()
        client._account = "DU123456"

        def _sync_submit(fn, timeout=60.0, is_blocking=False):
            return fn()
        client._submit = _sync_submit

        result = client.get_positions()

        assert result == []

    @patch("app.services.live_trading.records.ibkr_get_positions")
    def test_get_positions_calculates_market_value_when_zero(self, mock_get_positions):
        mock_get_positions.return_value = [
            {
                "account": "DU123456",
                "con_id": 123456,
                "symbol": "AAPL",
                "position": 100.0,
                "avg_cost": 150.0,
                "updated_at": None,
            },
        ]
        client = _make_client_with_mock_ib()
        client._account = "DU123456"

        def _sync_submit(fn, timeout=60.0, is_blocking=False):
            return fn()
        client._submit = _sync_submit

        result = client.get_positions()

        assert len(result) == 1
        assert result[0]["marketValue"] == 15000.0

    @patch("app.services.live_trading.records.ibkr_get_positions")
    def test_uc_fp4_get_positions_forex_metadata_from_db(self, mock_get_positions):
        """UC-FP4: Forex row exposes CASH / IDEALPRO / USD from DB-backed sec_type/exchange/currency."""
        mock_get_positions.return_value = [
            {
                "account": "DU123456",
                "con_id": 4242,
                "symbol": "EUR.USD",
                "sec_type": "CASH",
                "exchange": "IDEALPRO",
                "currency": "USD",
                "position": 10000.0,
                "avg_cost": 1.05,
                "unrealized_pnl": 5.0,
                "daily_pnl": 0.0,
                "realized_pnl": 0.0,
                "value": 10000.0,
                "updated_at": None,
            },
        ]
        client = _make_client_with_mock_ib()
        client._account = "DU123456"

        def _sync_submit(fn, timeout=60.0, is_blocking=False):
            return fn()
        client._submit = _sync_submit

        result = client.get_positions()
        assert len(result) == 1
        r = result[0]
        assert r["secType"] == "CASH"
        assert r["exchange"] == "IDEALPRO"
        assert r["currency"] == "USD"
        assert r["quantity"] == 10000.0

    @patch("app.services.live_trading.records.ibkr_get_positions")
    def test_uc_fp5_get_positions_stock_regression(self, mock_get_positions):
        """UC-FP5: US stock row still yields STK/SMART/USD when DB holds equity metadata (no accidental CASH)."""
        mock_get_positions.return_value = [
            {
                "account": "DU123456",
                "con_id": 123,
                "symbol": "AAPL",
                "sec_type": "STK",
                "exchange": "SMART",
                "currency": "USD",
                "position": 10.0,
                "avg_cost": 150.0,
                "unrealized_pnl": 0.0,
                "daily_pnl": 0.0,
                "realized_pnl": 0.0,
                "value": 1500.0,
                "updated_at": None,
            },
        ]
        client = _make_client_with_mock_ib()
        client._account = "DU123456"

        def _sync_submit(fn, timeout=60.0, is_blocking=False):
            return fn()
        client._submit = _sync_submit

        result = client.get_positions()
        assert len(result) == 1
        assert result[0]["secType"] == "STK"
        assert result[0]["exchange"] == "SMART"
        assert result[0]["currency"] == "USD"
        assert result[0]["symbol"] == "AAPL"


# ===========================================================================
# IBKROrderContext lifecycle tests
# ===========================================================================

class TestOrderContextLifecycle:
    """Verify order contexts are properly registered and cleaned up."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_context_registered_and_lingers_on_fill(self):
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=500)
        client._ib.placeOrder.return_value = trade_mock

        client.place_market_order("AAPL", "buy", 10, "USStock", pending_order_id=99)
        assert 500 in client._order_contexts

        fill_trade = _make_trade_mock(status="Filled", filled=10.0, avg_price=155.0, order_id=500)
        client._on_order_status(fill_trade)
        assert 500 not in client._order_contexts  # popped for fill idempotency
        assert 500 in client._commission_contexts  # lingers for commissionReport

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
    def test_context_removed_on_cancelled_zero_fills(self):
        """Cancelled with 0 fills is treated as rejection — context is removed."""
        client = _make_client_with_mock_ib()
        trade_mock = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=502)
        client._ib.placeOrder.return_value = trade_mock

        client.place_market_order("AAPL", "buy", 10, "USStock", pending_order_id=101)
        assert 502 in client._order_contexts

        cancel_trade = _make_trade_mock(status="Cancelled", filled=0, avg_price=0, order_id=502)
        client._on_order_status(cancel_trade)
        assert 502 not in client._order_contexts


# ===========================================================================
# Integration tests - real IBKR connection
#
# Env vars:
#   IBKR_HOST  (default: ib-gateway)
#   IBKR_PORT  (default: 4004)
#
# Run:
#   IBKR_HOST=hgq-nas pytest tests/test_ibkr_client.py -v -m integration
# ===========================================================================

@pytest.fixture(scope="module")
def ibkr_client():
    import os
    host = os.environ.get("IBKR_HOST", "ib-gateway")
    port = int(os.environ.get("IBKR_PORT", "4004"))
    config = IBKRConfig(host=host, port=port, client_id=99)
    client = IBKRClient(config)
    connected = client.connect()
    if not connected:
        pytest.skip(f"Cannot connect to IBKR at {host}:{port}")
    yield client
    client.shutdown()


@pytest.mark.integration
class TestRealIBKRConnection:
    """Integration tests — requires a running IB Gateway."""

    def test_connect(self, ibkr_client):
        assert ibkr_client.connected
        assert ibkr_client._account

    def test_get_account_summary(self, ibkr_client):
        result = ibkr_client.get_account_summary()
        assert result["success"] is True
        assert "summary" in result
        summary = result["summary"]
        assert "NetLiquidation" in summary, f"Missing NetLiquidation, got keys: {list(summary.keys())}"
        net_liq = summary["NetLiquidation"]
        assert "value" in net_liq
        assert float(net_liq["value"]) > 0, "NetLiquidation should be positive"

    def test_get_account_summary_has_key_fields(self, ibkr_client):
        result = ibkr_client.get_account_summary()
        summary = result["summary"]
        for tag in ("TotalCashValue", "AvailableFunds", "BuyingPower"):
            assert tag in summary, f"Missing {tag}"
            assert "value" in summary[tag]
            assert "currency" in summary[tag]

    def test_get_pnl(self, ibkr_client):
        result = ibkr_client.get_pnl()
        assert result["success"] is True
        for key in ("dailyPnL", "unrealizedPnL", "realizedPnL"):
            assert key in result, f"Missing {key}"
            assert isinstance(result[key], float)

    def test_get_positions(self, ibkr_client):
        positions = ibkr_client.get_positions()
        assert isinstance(positions, list)
        if positions:
            pos = positions[0]
            for field in ("symbol", "quantity", "avgCost", "marketValue", "unrealizedPnL"):
                assert field in pos, f"Position missing field: {field}"
            assert isinstance(pos["quantity"], float)
            assert isinstance(pos["avgCost"], float)

    def test_get_positions_normalized(self, ibkr_client):
        records = ibkr_client.get_positions_normalized()
        assert isinstance(records, list)
        if records:
            r = records[0]
            assert r.symbol
            assert r.side in ("long", "short")
            assert r.quantity > 0

    def test_get_open_orders(self, ibkr_client):
        orders = ibkr_client.get_open_orders()
        assert isinstance(orders, list)
        if orders:
            o = orders[0]
            for field in ("orderId", "symbol", "action", "quantity", "status"):
                assert field in o, f"Order missing field: {field}"

    def test_get_quote(self, ibkr_client):
        result = ibkr_client.get_quote("AAPL", "USStock")
        assert result.get("success") is True or "error" in result
        if result.get("success"):
            assert result["symbol"] == "AAPL"

    def test_get_connection_status(self, ibkr_client):
        status = ibkr_client.get_connection_status()
        assert status["connected"] is True
        assert status["engine_id"] == "ibkr"
        assert status["account"]

    def test_concurrent_queries(self, ibkr_client):
        """Multiple threads calling different query methods simultaneously."""
        import threading
        results = {}
        errors = []

        def run(name, fn):
            try:
                results[name] = fn()
            except Exception as e:
                errors.append(f"{name}: {e}")

        threads = [
            threading.Thread(target=run, args=("summary", ibkr_client.get_account_summary)),
            threading.Thread(target=run, args=("pnl", ibkr_client.get_pnl)),
            threading.Thread(target=run, args=("positions", ibkr_client.get_positions)),
            threading.Thread(target=run, args=("orders", ibkr_client.get_open_orders)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Concurrent query errors: {errors}"
        assert results["summary"]["success"] is True
        assert results["pnl"]["success"] is True
        assert isinstance(results["positions"], list)
        assert isinstance(results["orders"], list)

    def test_disconnect_and_reconnect(self, ibkr_client):
        ibkr_client.disconnect()
        assert not ibkr_client.connected
        time.sleep(3)
        success = ibkr_client.connect()
        assert success, "Reconnect failed — IB Gateway may need a few seconds after disconnect"
        assert ibkr_client.connected
