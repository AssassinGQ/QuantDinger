"""Tests for exchange engine abstraction layer."""
import pytest

from app.services.exchange_engine import ExchangeEngine, OrderResult
from app.services.ibkr_trading.client import IBKRClient
from app.services.mt5_trading.client import MT5Client


class TestOrderResult:

    def test_default_values(self):
        r = OrderResult(success=True)
        assert r.success is True
        assert r.filled == 0.0
        assert r.avg_price == 0.0
        assert r.deal_id == 0
        assert r.exchange_id == ""
        assert r.raw == {}

    def test_full_values(self):
        r = OrderResult(
            success=True, order_id=42, deal_id=99, filled=100.0, avg_price=150.5,
            status="Filled", message="done", exchange_id="ibkr",
            raw={"orderId": 42},
        )
        assert r.order_id == 42
        assert r.deal_id == 99
        assert r.filled == 100.0
        assert r.exchange_id == "ibkr"

    def test_failed_result(self):
        r = OrderResult(success=False, message="timed out")
        assert r.success is False
        assert r.filled == 0.0
        assert r.avg_price == 0.0

    def test_mt5_style_result(self):
        r = OrderResult(
            success=True, order_id=12345, deal_id=67890,
            filled=0.1, avg_price=1.0850, status="filled",
            exchange_id="mt5",
        )
        assert r.deal_id == 67890
        assert r.avg_price == 1.0850
        assert r.exchange_id == "mt5"


class TestExchangeEngineABC:

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            ExchangeEngine()

    def test_ibkr_is_exchange_engine(self):
        assert issubclass(IBKRClient, ExchangeEngine)

    def test_mt5_is_exchange_engine(self):
        assert issubclass(MT5Client, ExchangeEngine)

    def test_ibkr_engine_id(self):
        assert IBKRClient.engine_id == "ibkr"

    def test_mt5_engine_id(self):
        assert MT5Client.engine_id == "mt5"

    def test_ibkr_supported_categories(self):
        assert IBKRClient.supported_market_categories == frozenset({"USStock", "HShare"})

    def test_mt5_supported_categories(self):
        assert MT5Client.supported_market_categories == frozenset({"Forex"})


class TestValidateMarketCategory:

    def _ibkr(self):
        return IBKRClient.__new__(IBKRClient)

    def _mt5(self):
        return MT5Client.__new__(MT5Client)

    def test_ibkr_usstock_ok(self):
        ok, _ = self._ibkr().validate_market_category("USStock")
        assert ok

    def test_ibkr_hshare_ok(self):
        ok, _ = self._ibkr().validate_market_category("HShare")
        assert ok

    def test_ibkr_crypto_rejected(self):
        ok, msg = self._ibkr().validate_market_category("Crypto")
        assert not ok
        assert "Crypto" in msg

    def test_ibkr_forex_rejected(self):
        ok, msg = self._ibkr().validate_market_category("Forex")
        assert not ok

    def test_mt5_forex_ok(self):
        ok, _ = self._mt5().validate_market_category("Forex")
        assert ok

    def test_mt5_usstock_rejected(self):
        ok, msg = self._mt5().validate_market_category("USStock")
        assert not ok
        assert "USStock" in msg


class TestIBKRSignalMapping:

    def _make_client(self):
        client = IBKRClient.__new__(IBKRClient)
        return client

    def test_open_long(self):
        c = self._make_client()
        assert c.map_signal_to_side("open_long") == "buy"

    def test_add_long(self):
        c = self._make_client()
        assert c.map_signal_to_side("add_long") == "buy"

    def test_close_long(self):
        c = self._make_client()
        assert c.map_signal_to_side("close_long") == "sell"

    def test_reduce_long(self):
        c = self._make_client()
        assert c.map_signal_to_side("reduce_long") == "sell"

    def test_short_rejected(self):
        c = self._make_client()
        with pytest.raises(ValueError, match="short"):
            c.map_signal_to_side("open_short")

    def test_close_short_rejected(self):
        c = self._make_client()
        with pytest.raises(ValueError, match="short"):
            c.map_signal_to_side("close_short")

    def test_unknown_signal_rejected(self):
        c = self._make_client()
        with pytest.raises(ValueError, match="Unsupported"):
            c.map_signal_to_side("unknown_signal")

    def test_case_insensitive(self):
        c = self._make_client()
        assert c.map_signal_to_side("OPEN_LONG") == "buy"
        assert c.map_signal_to_side("Close_Long") == "sell"


class TestMT5SignalMapping:

    def _make_client(self):
        client = MT5Client.__new__(MT5Client)
        return client

    def test_open_long(self):
        c = self._make_client()
        assert c.map_signal_to_side("open_long") == "buy"

    def test_close_long(self):
        c = self._make_client()
        assert c.map_signal_to_side("close_long") == "sell"

    def test_open_short(self):
        c = self._make_client()
        assert c.map_signal_to_side("open_short") == "sell"

    def test_close_short(self):
        c = self._make_client()
        assert c.map_signal_to_side("close_short") == "buy"

    def test_add_long(self):
        c = self._make_client()
        assert c.map_signal_to_side("add_long") == "buy"

    def test_add_short(self):
        c = self._make_client()
        assert c.map_signal_to_side("add_short") == "sell"

    def test_reduce_long(self):
        c = self._make_client()
        assert c.map_signal_to_side("reduce_long") == "sell"

    def test_reduce_short(self):
        c = self._make_client()
        assert c.map_signal_to_side("reduce_short") == "buy"

    def test_unknown_rejected(self):
        c = self._make_client()
        with pytest.raises(ValueError, match="Unsupported"):
            c.map_signal_to_side("unknown")

    def test_case_insensitive(self):
        c = self._make_client()
        assert c.map_signal_to_side("OPEN_SHORT") == "sell"
        assert c.map_signal_to_side("Close_Short") == "buy"
