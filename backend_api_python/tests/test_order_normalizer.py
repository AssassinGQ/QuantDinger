"""Tests for OrderNormalizer hierarchy."""

import pytest
from app.services.live_trading.order_normalizer import (
    CryptoNormalizer,
    get_normalizer,
)
from app.services.live_trading.order_normalizer.us_stock import USStockNormalizer
from app.services.live_trading.order_normalizer.hk_share import (
    HShareNormalizer,
    HK_LOT_SIZES,
    _hk_symbol_key,
)
from app.services.live_trading.order_normalizer.forex import ForexNormalizer


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


# ── USStockNormalizer ────────────────────────────────────────────────

class TestUSStockNormalizer:
    norm = USStockNormalizer()

    def test_normalize_floors(self):
        assert self.norm.normalize(7.8, "AAPL") == 7

    def test_normalize_whole(self):
        assert self.norm.normalize(10.0, "AAPL") == 10

    def test_normalize_small(self):
        assert self.norm.normalize(0.3, "AAPL") == 0

    def test_check_valid(self):
        ok, _ = self.norm.check(10, "AAPL")
        assert ok is True

    def test_check_zero(self):
        ok, reason = self.norm.check(0, "AAPL")
        assert ok is False
        assert "positive" in reason.lower()

    def test_check_negative(self):
        ok, _ = self.norm.check(-5, "AAPL")
        assert ok is False

    def test_check_fractional(self):
        ok, reason = self.norm.check(3.5, "AAPL")
        assert ok is False
        assert "whole number" in reason.lower()

    def test_check_float_whole(self):
        ok, _ = self.norm.check(10.0, "AAPL")
        assert ok is True


# ── HShareNormalizer ─────────────────────────────────────────────────

class TestHShareNormalizer:
    norm = HShareNormalizer()

    # normalize
    def test_normalize_hsbc_full_lot(self):
        assert self.norm.normalize(450.0, "00005") == 400

    def test_normalize_hsbc_under_lot(self):
        assert self.norm.normalize(399.9, "00005") == 0

    def test_normalize_jd_multiple(self):
        assert self.norm.normalize(120.0, "09618") == 100

    def test_normalize_jd_exact(self):
        assert self.norm.normalize(50.0, "09618") == 50

    def test_normalize_byd(self):
        assert self.norm.normalize(350.7, "01211") == 300

    def test_normalize_byd_hk_suffix(self):
        assert self.norm.normalize(250.0, "1211.HK") == 200

    def test_normalize_unknown_floors_to_int(self):
        assert self.norm.normalize(7.8, "00388") == 7

    # check
    def test_check_hsbc_valid(self):
        ok, _ = self.norm.check(400, "00005")
        assert ok is True

    def test_check_hsbc_two_lots(self):
        ok, _ = self.norm.check(800, "00005")
        assert ok is True

    def test_check_hsbc_invalid(self):
        ok, reason = self.norm.check(3, "00005")
        assert ok is False
        assert "400" in reason

    def test_check_jd_valid(self):
        ok, _ = self.norm.check(50, "09618")
        assert ok is True

    def test_check_jd_invalid(self):
        ok, reason = self.norm.check(30, "09618")
        assert ok is False
        assert "50" in reason

    def test_check_byd_valid(self):
        ok, _ = self.norm.check(100, "01211")
        assert ok is True

    def test_check_byd_invalid(self):
        ok, reason = self.norm.check(75, "01211")
        assert ok is False
        assert "100" in reason

    def test_check_zero(self):
        ok, _ = self.norm.check(0, "00005")
        assert ok is False

    def test_check_fractional(self):
        ok, reason = self.norm.check(400.5, "00005")
        assert ok is False
        assert "whole number" in reason.lower()

    def test_check_unknown_any_int(self):
        ok, _ = self.norm.check(7, "00388")
        assert ok is True


# ── ForexNormalizer ──────────────────────────────────────────────────

class TestForexNormalizer:
    norm = ForexNormalizer()

    def test_normalize(self):
        assert self.norm.normalize(1000.7, "EURUSD") == 1000

    def test_check_valid(self):
        ok, _ = self.norm.check(1000, "EURUSD")
        assert ok is True

    def test_check_zero(self):
        ok, _ = self.norm.check(0, "EURUSD")
        assert ok is False


# ── get_normalizer factory ───────────────────────────────────────────

class TestCryptoNormalizer:
    norm = CryptoNormalizer()

    def test_passthrough(self):
        assert self.norm.normalize(0.00123, "BTCUSDT") == 0.00123

    def test_check_valid(self):
        ok, _ = self.norm.check(0.5, "ETHUSDT")
        assert ok is True

    def test_check_zero(self):
        ok, _ = self.norm.check(0, "BTCUSDT")
        assert ok is False


class TestGetNormalizer:
    def test_hshare(self):
        assert isinstance(get_normalizer("HShare"), HShareNormalizer)

    def test_forex(self):
        assert isinstance(get_normalizer("Forex"), ForexNormalizer)

    def test_usstock(self):
        assert isinstance(get_normalizer("USStock"), USStockNormalizer)

    def test_crypto(self):
        assert isinstance(get_normalizer("Crypto"), CryptoNormalizer)

    def test_default(self):
        assert isinstance(get_normalizer(""), USStockNormalizer)

    def test_none(self):
        assert isinstance(get_normalizer(None), USStockNormalizer)


class TestBackwardCompatImport:
    """Ensure old import paths still work."""

    def test_old_import_path(self):
        from app.services.live_trading.ibkr_trading.order_normalizer import get_normalizer as old_get
        assert old_get("HShare").normalize(450, "00005") == 400

    def test_old_submodule_import(self):
        from app.services.live_trading.ibkr_trading.order_normalizer.hk_share import _hk_symbol_key
        assert _hk_symbol_key("00005") == "5"
