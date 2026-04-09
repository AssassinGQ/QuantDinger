"""
Tests for IBKR symbol normalization, parsing, and display formatting.

Covers Forex symbol support (CONT-02) and regression tests for existing
USStock/HShare behavior.
"""

import pytest
from app.services.live_trading.ibkr_trading.symbols import (
    normalize_symbol, parse_symbol, format_display_symbol
)


class TestNormalizeSymbolForex:
    """CONT-02: normalize_symbol supports Forex symbol formats."""

    @pytest.mark.parametrize("input_sym,expected_pair,expected_quote", [
        ("EURUSD", "EURUSD", "USD"),
        ("USDJPY", "USDJPY", "JPY"),
        ("XAUUSD", "XAUUSD", "USD"),
        ("GBPJPY", "GBPJPY", "JPY"),
        ("AUDUSD", "AUDUSD", "USD"),
        ("CADJPY", "CADJPY", "JPY"),
    ])
    def test_6char_uppercase(self, input_sym, expected_pair, expected_quote):
        pair, exchange, currency = normalize_symbol(input_sym, "Forex")
        assert pair == expected_pair
        assert exchange == "IDEALPRO"
        assert currency == expected_quote

    @pytest.mark.parametrize("input_sym,expected_pair", [
        ("EUR/USD", "EURUSD"),
        ("EUR.USD", "EURUSD"),
        ("eur-usd", "EURUSD"),
        ("Eur_Usd", "EURUSD"),
        ("eur usd", "EURUSD"),
        ("eurusd", "EURUSD"),
    ])
    def test_separator_and_case_variants(self, input_sym, expected_pair):
        pair, exchange, currency = normalize_symbol(input_sym, "Forex")
        assert pair == expected_pair
        assert exchange == "IDEALPRO"

    @pytest.mark.parametrize("bad_symbol", [
        "", "EU", "EURUSDD", "EUR123", "12345", "EUR/US",
    ])
    def test_invalid_forex_raises(self, bad_symbol):
        with pytest.raises(ValueError, match="Invalid Forex symbol"):
            normalize_symbol(bad_symbol, "Forex")

    def test_does_not_default_to_stock(self):
        """Forex symbols must never fall through to Stock default."""
        pair, exchange, _ = normalize_symbol("EURUSD", "Forex")
        assert exchange == "IDEALPRO"
        assert exchange != "SMART"


class TestParseSymbolForex:
    """parse_symbol auto-detects Forex from known pairs."""

    def test_detects_known_forex(self):
        clean, mtype = parse_symbol("EURUSD")
        assert mtype == "Forex"
        assert clean == "EURUSD"

    def test_detects_forex_with_separator(self):
        clean, mtype = parse_symbol("EUR/USD")
        assert mtype == "Forex"
        assert clean == "EURUSD"

    def test_detects_forex_lowercase(self):
        clean, mtype = parse_symbol("eurusd")
        assert mtype == "Forex"
        assert clean == "EURUSD"

    def test_metals_detected_as_forex(self):
        clean, mtype = parse_symbol("XAUUSD")
        assert mtype == "Forex"
        assert clean == "XAUUSD"

    def test_hshare_not_confused_with_forex(self):
        _, mtype = parse_symbol("0700.HK")
        assert mtype == "HShare"

    def test_us_stock_not_confused_with_forex(self):
        _, mtype = parse_symbol("AAPL")
        assert mtype == "USStock"


class TestFormatDisplayForex:
    """format_display_symbol renders Forex pairs as dot-separated."""

    def test_forex_display(self):
        assert format_display_symbol("EURUSD", "IDEALPRO") == "EUR.USD"

    def test_forex_display_usdjpy(self):
        assert format_display_symbol("USDJPY", "IDEALPRO") == "USD.JPY"

    def test_hshare_unchanged(self):
        assert format_display_symbol("700", "SEHK") == "0700.HK"

    def test_us_stock_unchanged(self):
        assert format_display_symbol("AAPL", "SMART") == "AAPL"


class TestNormalizeSymbolRegression:
    """Regression: existing USStock/HShare behavior unchanged."""

    def test_usstock_unchanged(self):
        assert normalize_symbol("AAPL", "USStock") == ("AAPL", "SMART", "USD")

    def test_hshare_with_hk_suffix(self):
        assert normalize_symbol("0700.HK", "HShare") == ("700", "SEHK", "HKD")

    def test_hshare_digits_only(self):
        assert normalize_symbol("00700", "HShare") == ("700", "SEHK", "HKD")

    def test_unknown_market_type_defaults(self):
        assert normalize_symbol("MSFT", "Unknown") == ("MSFT", "SMART", "USD")


class TestParseSymbolRegression:
    """Regression: existing parse_symbol behavior unchanged."""

    def test_hk_suffix(self):
        clean, mtype = parse_symbol("0700.HK")
        assert mtype == "HShare"
        assert clean == "0700.HK"

    def test_digits(self):
        clean, mtype = parse_symbol("700")
        assert mtype == "HShare"
        assert clean == "700"

    def test_us_stock(self):
        clean, mtype = parse_symbol("AAPL")
        assert mtype == "USStock"
        assert clean == "AAPL"
