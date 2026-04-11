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
        assert self.norm.normalize(1050.7, "01211") == 1000

    def test_normalize_byd_hk_suffix(self):
        assert self.norm.normalize(750.0, "1211.HK") == 500

    def test_normalize_unknown_uses_default_lot(self):
        assert self.norm.normalize(250.0, "06666") == 200

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
        ok, _ = self.norm.check(500, "01211")
        assert ok is True

    def test_check_byd_invalid(self):
        ok, reason = self.norm.check(200, "01211")
        assert ok is False
        assert "500" in reason

    def test_check_zero(self):
        ok, _ = self.norm.check(0, "00005")
        assert ok is False

    def test_check_fractional(self):
        ok, reason = self.norm.check(400.5, "00005")
        assert ok is False
        assert "whole number" in reason.lower()

    def test_check_unknown_uses_default_lot(self):
        ok, reason = self.norm.check(50, "06666")
        assert ok is False
        assert "100" in reason

    def test_check_unknown_default_lot_valid(self):
        ok, _ = self.norm.check(100, "06666")
        assert ok is True


# ── ForexNormalizer ──────────────────────────────────────────────────

class TestForexNormalizer:
    norm = ForexNormalizer()

    def test_normalize(self):
        assert self.norm.normalize(1000.7, "EURUSD") == 1000.7

    def test_uc_n1_large_fractional_passthrough_eurusd_and_gbpjpy(self):
        """UC-N1: large fractional qty passes through; second symbol sanity check."""
        assert self.norm.normalize(20000.99, "EURUSD") == 20000.99
        assert self.norm.normalize(20000.99, "GBPJPY") == 20000.99

    def test_uc_n2_half_unit_passthrough(self):
        """UC-N2: fractional 0.5 passes through."""
        assert self.norm.normalize(0.5, "EURUSD") == 0.5

    def test_uc_n3_small_positive_passthrough(self):
        """UC-N3: 0.001 passes through."""
        assert self.norm.normalize(0.001, "EURUSD") == 0.001

    def test_uc_n4_large_magnitude_passthrough(self):
        """UC-N4: 1e9 passes through."""
        assert self.norm.normalize(1e9, "EURUSD") == 1e9

    def test_uc_n5_check_rejects_negative(self):
        """UC-N5: check rejects negative qty with positive wording."""
        ok, msg = self.norm.check(-5, "EURUSD")
        assert ok is False
        assert "positive" in msg.lower()
        assert "-5" in msg or "-5.0" in msg

    def test_uc_n6_check_accepts_small_positive(self):
        """UC-N6: small positive qty accepted."""
        ok, reason = self.norm.check(0.001, "EURUSD")
        assert ok is True
        assert reason == ""

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
