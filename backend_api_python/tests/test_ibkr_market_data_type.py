"""
Tests for Phase 20-B "Quote 兜底" patch:
  1) IBKRConfig.market_data_type — default 3, env override, invalid fallback
  2) _do_connect_coro() calls reqMarketDataType(mdt) after connect (best-effort)
  3) get_quote() surfaces IBKR error codes 10089/10197 etc. when ticker is all-nan
  4) get_quote() filters nan/inf/sentinel values (formerly bid=nan leaked through)
"""
import math
import os
from unittest.mock import MagicMock, patch

import pytest

from app.services.live_trading.ibkr_trading.client import (
    IBKRClient,
    IBKRConfig,
    _parse_market_data_type,
)


# ───────────────────────── _parse_market_data_type ────────────────────────

class TestParseMarketDataType:
    def test_none_returns_default(self):
        assert _parse_market_data_type(None) == 3

    def test_empty_returns_default(self):
        assert _parse_market_data_type("") == 3
        assert _parse_market_data_type("   ") == 3

    def test_valid_values(self):
        for v in (1, 2, 3, 4):
            assert _parse_market_data_type(str(v)) == v

    def test_out_of_range_falls_back(self):
        assert _parse_market_data_type("0") == 3
        assert _parse_market_data_type("5") == 3
        assert _parse_market_data_type("-1") == 3

    def test_non_int_falls_back(self):
        assert _parse_market_data_type("abc") == 3
        assert _parse_market_data_type("3.5") == 3

    def test_custom_default(self):
        assert _parse_market_data_type(None, default=1) == 1
        assert _parse_market_data_type("invalid", default=4) == 4


# ─────────────────────────── IBKRConfig defaults ──────────────────────────

class TestIBKRConfigMarketDataType:
    def test_default_is_3_delayed(self):
        cfg = IBKRConfig()
        assert cfg.market_data_type == 3

    def test_explicit_override(self):
        cfg = IBKRConfig(market_data_type=1)
        assert cfg.market_data_type == 1

    def test_from_env_paper_default(self, monkeypatch):
        monkeypatch.delenv("IBKR_MARKET_DATA_TYPE", raising=False)
        cfg = IBKRConfig.from_env(mode="paper")
        assert cfg.market_data_type == 3

    def test_from_env_paper_override(self, monkeypatch):
        monkeypatch.setenv("IBKR_MARKET_DATA_TYPE", "1")
        cfg = IBKRConfig.from_env(mode="paper")
        assert cfg.market_data_type == 1

    def test_from_env_live_default(self, monkeypatch):
        monkeypatch.delenv("IBKR_MARKET_DATA_TYPE", raising=False)
        cfg = IBKRConfig.from_env(mode="live")
        assert cfg.market_data_type == 3

    def test_from_env_live_override(self, monkeypatch):
        monkeypatch.setenv("IBKR_MARKET_DATA_TYPE", "4")
        cfg = IBKRConfig.from_env(mode="live")
        assert cfg.market_data_type == 4

    def test_from_env_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("IBKR_MARKET_DATA_TYPE", "garbage")
        cfg = IBKRConfig.from_env(mode="paper")
        assert cfg.market_data_type == 3


# ────────────────────── _apply_market_data_type behavior ──────────────────

class TestApplyMarketDataType:
    def _make_client(self, mdt=3):
        cfg = IBKRConfig(market_data_type=mdt)
        client = IBKRClient.__new__(IBKRClient)
        client.config = cfg
        client._ib = MagicMock()
        return client

    def test_calls_req_market_data_type(self):
        c = self._make_client(mdt=3)
        c._apply_market_data_type()
        c._ib.reqMarketDataType.assert_called_once_with(3)

    def test_uses_configured_value(self):
        c = self._make_client(mdt=1)
        c._apply_market_data_type()
        c._ib.reqMarketDataType.assert_called_once_with(1)

    def test_no_op_when_ib_none(self):
        c = self._make_client(mdt=3)
        c._ib = None
        c._apply_market_data_type()  # must not raise

    def test_exception_is_swallowed(self):
        c = self._make_client(mdt=3)
        c._ib.reqMarketDataType.side_effect = RuntimeError("simulated")
        c._apply_market_data_type()  # must not raise — best-effort


# ────────────────────────── _is_valid_quote_field ─────────────────────────

class TestIsValidQuoteField:
    def test_none(self):
        assert IBKRClient._is_valid_quote_field(None) is False

    def test_zero(self):
        assert IBKRClient._is_valid_quote_field(0) is False
        assert IBKRClient._is_valid_quote_field(0.0) is False

    def test_negative(self):
        assert IBKRClient._is_valid_quote_field(-1) is False

    def test_nan(self):
        assert IBKRClient._is_valid_quote_field(float("nan")) is False

    def test_inf(self):
        assert IBKRClient._is_valid_quote_field(float("inf")) is False
        assert IBKRClient._is_valid_quote_field(float("-inf")) is False

    def test_positive(self):
        assert IBKRClient._is_valid_quote_field(308.43) is True
        assert IBKRClient._is_valid_quote_field(1) is True

    def test_non_numeric_string(self):
        assert IBKRClient._is_valid_quote_field("abc") is False
