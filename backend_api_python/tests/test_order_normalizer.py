"""Tests for MarketPreNormalizer hierarchy."""

import importlib

import pytest

from app.services.live_trading.order_normalizer import (
    CryptoPreNormalizer,
    get_market_pre_normalizer,
)
from app.services.live_trading.order_normalizer.us_stock import USStockPreNormalizer
from app.services.live_trading.order_normalizer.hk_share import (
    HSharePreNormalizer,
    HK_LOT_SIZES,
    _hk_symbol_key,
)
from app.services.live_trading.order_normalizer.forex import ForexPreNormalizer


# ── HK symbol key normalization ──────────────────────────────────────

class TestHKSymbolKey:
    def test_strips_leading_zeros(self):
        assert _hk_symbol_key("00005") == "5"

    def test_strips_hk_suffix(self):
        assert _hk_symbol_key("0005.HK") == "5"

    def test_plain_number(self):
        assert _hk_symbol_key("9618") == "9618"

    def test_zero(self):
        assert _hk_symbol_key("0") == "0"

    def test_empty(self):
        assert _hk_symbol_key("") == "0"


# ── USStockPreNormalizer ─────────────────────────────────────────────

class TestUSStockPreNormalizer:
    norm = USStockPreNormalizer()

    def test_pre_normalize_floors(self):
        assert self.norm.pre_normalize(7.8, "AAPL") == 7

    def test_pre_normalize_whole(self):
        assert self.norm.pre_normalize(10.0, "AAPL") == 10

    def test_pre_normalize_small(self):
        assert self.norm.pre_normalize(0.3, "AAPL") == 0

    def test_pre_check_valid(self):
        ok, _ = self.norm.pre_check(10, "AAPL")
        assert ok is True

    def test_pre_check_zero(self):
        ok, reason = self.norm.pre_check(0, "AAPL")
        assert ok is False
        assert "positive" in reason.lower()

    def test_pre_check_negative(self):
        ok, _ = self.norm.pre_check(-5, "AAPL")
        assert ok is False

    def test_pre_check_fractional(self):
        ok, reason = self.norm.pre_check(3.5, "AAPL")
        assert ok is False
        assert "whole number" in reason.lower()

    def test_pre_check_float_whole(self):
        ok, _ = self.norm.pre_check(10.0, "AAPL")
        assert ok is True


# ── HSharePreNormalizer ─────────────────────────────────────────────

class TestHSharePreNormalizer:
    norm = HSharePreNormalizer()

    # pre_normalize
    def test_pre_normalize_hsbc_full_lot(self):
        assert self.norm.pre_normalize(450.0, "00005") == 400

    def test_pre_normalize_hsbc_under_lot(self):
        # Sub-lot positive qty is floored to whole shares so pre_check can emit board-lot errors (not snapped to 0).
        assert self.norm.pre_normalize(399.9, "00005") == 399.0

    def test_pre_normalize_jd_multiple(self):
        assert self.norm.pre_normalize(120.0, "09618") == 100

    def test_pre_normalize_jd_exact(self):
        assert self.norm.pre_normalize(50.0, "09618") == 50

    def test_pre_normalize_byd(self):
        assert self.norm.pre_normalize(1050.7, "01211") == 1000

    def test_pre_normalize_byd_hk_suffix(self):
        assert self.norm.pre_normalize(750.0, "1211.HK") == 500

    def test_pre_normalize_unknown_uses_default_lot(self):
        assert self.norm.pre_normalize(250.0, "06666") == 200

    # pre_check
    def test_pre_check_hsbc_valid(self):
        ok, _ = self.norm.pre_check(400, "00005")
        assert ok is True

    def test_pre_check_hsbc_two_lots(self):
        ok, _ = self.norm.pre_check(800, "00005")
        assert ok is True

    def test_pre_check_hsbc_invalid(self):
        ok, reason = self.norm.pre_check(3, "00005")
        assert ok is False
        assert "400" in reason

    def test_pre_check_jd_valid(self):
        ok, _ = self.norm.pre_check(50, "09618")
        assert ok is True

    def test_pre_check_jd_invalid(self):
        ok, reason = self.norm.pre_check(30, "09618")
        assert ok is False
        assert "50" in reason

    def test_pre_check_byd_valid(self):
        ok, _ = self.norm.pre_check(500, "01211")
        assert ok is True

    def test_pre_check_byd_invalid(self):
        ok, reason = self.norm.pre_check(200, "01211")
        assert ok is False
        assert "500" in reason

    def test_pre_check_zero(self):
        ok, _ = self.norm.pre_check(0, "00005")
        assert ok is False

    def test_pre_check_fractional(self):
        ok, reason = self.norm.pre_check(400.5, "00005")
        assert ok is False
        assert "whole number" in reason.lower()

    def test_pre_check_unknown_uses_default_lot(self):
        ok, reason = self.norm.pre_check(50, "06666")
        assert ok is False
        assert "100" in reason

    def test_pre_check_unknown_default_lot_valid(self):
        ok, _ = self.norm.pre_check(100, "06666")
        assert ok is True


# ── ForexPreNormalizer ───────────────────────────────────────────────

class TestForexPreNormalizer:
    norm = ForexPreNormalizer()

    def test_pre_normalize(self):
        assert self.norm.pre_normalize(1000.7, "EURUSD") == 1000.7

    def test_uc_n1_large_fractional_passthrough_eurusd_and_gbpjpy(self):
        """UC-N1: large fractional qty passes through; second symbol sanity check."""
        assert self.norm.pre_normalize(20000.99, "EURUSD") == 20000.99
        assert self.norm.pre_normalize(20000.99, "GBPJPY") == 20000.99

    def test_uc_n2_half_unit_passthrough(self):
        """UC-N2: fractional 0.5 passes through."""
        assert self.norm.pre_normalize(0.5, "EURUSD") == 0.5

    def test_uc_n3_small_positive_passthrough(self):
        """UC-N3: 0.001 passes through."""
        assert self.norm.pre_normalize(0.001, "EURUSD") == 0.001

    def test_uc_n4_large_magnitude_passthrough(self):
        """UC-N4: 1e9 passes through."""
        assert self.norm.pre_normalize(1e9, "EURUSD") == 1e9

    def test_uc_n5_pre_check_rejects_negative(self):
        """UC-N5: pre_check rejects negative qty with positive wording."""
        ok, msg = self.norm.pre_check(-5, "EURUSD")
        assert ok is False
        assert "positive" in msg.lower()
        assert "-5" in msg or "-5.0" in msg

    def test_uc_n6_pre_check_accepts_small_positive(self):
        """UC-N6: small positive qty accepted."""
        ok, reason = self.norm.pre_check(0.001, "EURUSD")
        assert ok is True
        assert reason == ""

    def test_pre_check_valid(self):
        ok, _ = self.norm.pre_check(1000, "EURUSD")
        assert ok is True

    def test_pre_check_zero(self):
        ok, _ = self.norm.pre_check(0, "EURUSD")
        assert ok is False


# ── get_market_pre_normalizer factory ────────────────────────────────

class TestCryptoPreNormalizer:
    norm = CryptoPreNormalizer()

    def test_passthrough(self):
        assert self.norm.pre_normalize(0.00123, "BTCUSDT") == 0.00123

    def test_pre_check_valid(self):
        ok, _ = self.norm.pre_check(0.5, "ETHUSDT")
        assert ok is True

    def test_pre_check_zero(self):
        ok, _ = self.norm.pre_check(0, "BTCUSDT")
        assert ok is False


class TestGetMarketPreNormalizer:
    def test_hshare(self):
        assert isinstance(get_market_pre_normalizer("HShare"), HSharePreNormalizer)

    def test_forex(self):
        assert isinstance(get_market_pre_normalizer("Forex"), ForexPreNormalizer)

    def test_usstock(self):
        assert isinstance(get_market_pre_normalizer("USStock"), USStockPreNormalizer)

    def test_crypto(self):
        assert isinstance(get_market_pre_normalizer("Crypto"), CryptoPreNormalizer)

    def test_default(self):
        assert isinstance(get_market_pre_normalizer(""), USStockPreNormalizer)

    def test_none(self):
        assert isinstance(get_market_pre_normalizer(None), USStockPreNormalizer)


# ── Phase 16: Metals → ForexPreNormalizer (UC-16-T2) ─────────────────

def test_uc_16_t2_01_metals_factory_returns_forex_pre_normalizer():
    """UC-16-T2-01: get_market_pre_normalizer('Metals') → ForexPreNormalizer."""
    n = get_market_pre_normalizer("Metals")
    assert isinstance(n, ForexPreNormalizer)


def test_uc_16_t2_02_metals_pre_check_positive():
    """UC-16-T2-02: ForexPreNormalizer pre_check positive qty for XAUUSD."""
    n = ForexPreNormalizer()
    ok, msg = n.pre_check(1.0, "XAUUSD")
    assert ok is True
    assert msg == ""


def test_uc_16_t2_03_metals_pre_check_rejects_non_positive():
    """UC-16-T2-03: pre_check rejects non-positive qty for XAGUSD."""
    n = ForexPreNormalizer()
    ok, msg = n.pre_check(0.0, "XAGUSD")
    assert ok is False
    assert msg


def test_tc_15_t4_02_shim_module_removed():
    """TC-15-T4-02: legacy shim package under live_trading.ibkr_trading is removed."""
    _shim = "app.services.live_trading." + "ibkr_trading" + "." + "order_normalizer"
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(_shim)
