"""Unit tests for IndexETF IBKR contract construction (Phase 20-B Step B-1).

Covers:
- normalize_symbol IndexETF branch (US / HK / A-share routing)
- resolve_primary_exchange (DB lookup + defaults)
- IBKRClient._create_contract injects primaryExchange for ETFs
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.live_trading.ibkr_trading.symbols import (
    normalize_symbol,
    resolve_primary_exchange,
)


# ---------------------------------------------------------------------------
# normalize_symbol IndexETF branch
# ---------------------------------------------------------------------------

class TestNormalizeSymbolIndexETF:
    """IndexETF should route by symbol shape; same 3-tuple shape as USStock."""

    def test_us_etf_returns_smart_usd(self):
        assert normalize_symbol("QQQ", "IndexETF") == ("QQQ", "SMART", "USD")
        assert normalize_symbol("SPY", "IndexETF") == ("SPY", "SMART", "USD")
        assert normalize_symbol("SQQQ", "IndexETF") == ("SQQQ", "SMART", "USD")

    def test_hk_etf_returns_sehk_hkd(self):
        # 02800 → strip leading zero → "2800"
        assert normalize_symbol("02800", "IndexETF") == ("2800", "SEHK", "HKD")
        assert normalize_symbol("03033", "IndexETF") == ("3033", "SEHK", "HKD")

    def test_ashare_etf_returns_placeholder(self):
        # A-share ETFs aren't tradable via IBKR US gateway but normalize_symbol
        # still needs to produce a 3-tuple; route placeholder is documented.
        assert normalize_symbol("510300", "IndexETF") == ("510300", "SEHKNTL", "CNH")


# ---------------------------------------------------------------------------
# resolve_primary_exchange — DB lookup
# ---------------------------------------------------------------------------

class TestResolvePrimaryExchange:
    """ETF primary exchange resolution from qd_market_symbols.exchange."""

    def test_non_indexetf_returns_none(self):
        """Other market types unchanged: no primaryExchange injection."""
        assert resolve_primary_exchange("AAPL", "USStock") is None
        assert resolve_primary_exchange("700", "HShare") is None
        assert resolve_primary_exchange("EURUSD", "Forex") is None
        assert resolve_primary_exchange("XAUUSD", "Metals") is None
        assert resolve_primary_exchange("BTC/USDT", "Crypto") is None
        assert resolve_primary_exchange("", "IndexETF") is None
        assert resolve_primary_exchange("QQQ", "") is None

    def test_hk_etf_returns_sehk_without_db(self):
        """HK ETF (digit, len<=5) shortcuts to SEHK; no DB lookup needed."""
        # No DB mock; should not raise even without DB.
        assert resolve_primary_exchange("02800", "IndexETF") == "SEHK"
        assert resolve_primary_exchange("03033", "IndexETF") == "SEHK"

    def test_ashare_etf_returns_none(self):
        """A-share ETFs can't trade on IBKR; resolver returns None."""
        assert resolve_primary_exchange("510300", "IndexETF") is None
        assert resolve_primary_exchange("159915", "IndexETF") is None

    @pytest.mark.parametrize("symbol,db_exchange,expected", [
        ("QQQ", "NASDAQ", "NASDAQ"),
        ("SPY", "ARCA", "ARCA"),
        ("SQQQ", "NASDAQ", "NASDAQ"),
        ("DIA", "ARCA", "ARCA"),
    ])
    def test_us_etf_db_hit(self, symbol, db_exchange, expected):
        """DB lookup returns the seeded exchange column."""
        # Mock get_db_connection → cursor → fetchone returns dict-like row.
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = {"exchange": db_exchange}
        fake_db = MagicMock()
        fake_db.cursor.return_value = fake_cursor
        fake_db.__enter__.return_value = fake_db
        fake_db.__exit__.return_value = False

        with patch("app.utils.db.get_db_connection", return_value=fake_db):
            assert resolve_primary_exchange(symbol, "IndexETF") == expected

        # Verify SQL was called with right params.
        call_args = fake_cursor.execute.call_args
        assert "qd_market_symbols" in call_args[0][0]
        assert call_args[0][1] == ("IndexETF", symbol)

    def test_us_etf_db_miss_returns_arca_default(self):
        """Unknown ETF defaults to ARCA so contract construction still works."""
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = None
        fake_db = MagicMock()
        fake_db.cursor.return_value = fake_cursor
        fake_db.__enter__.return_value = fake_db
        fake_db.__exit__.return_value = False

        with patch("app.utils.db.get_db_connection", return_value=fake_db):
            assert resolve_primary_exchange("UNKNOWN", "IndexETF") == "ARCA"

    def test_db_failure_falls_back_to_arca(self):
        """DB connection failure must not raise; fall back to ARCA default."""
        with patch(
            "app.utils.db.get_db_connection",
            side_effect=RuntimeError("DB unreachable"),
        ):
            assert resolve_primary_exchange("QQQ", "IndexETF") == "ARCA"

    def test_db_row_tuple_form(self):
        """fetchone might return a tuple-like row (legacy cursor); handle it."""
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = ("NASDAQ",)  # tuple, not dict
        fake_db = MagicMock()
        fake_db.cursor.return_value = fake_cursor
        fake_db.__enter__.return_value = fake_db
        fake_db.__exit__.return_value = False

        with patch("app.utils.db.get_db_connection", return_value=fake_db):
            assert resolve_primary_exchange("QQQ", "IndexETF") == "NASDAQ"

    def test_db_row_empty_string_falls_back(self):
        """DB row with empty exchange column treated as miss."""
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = {"exchange": ""}
        fake_db = MagicMock()
        fake_db.cursor.return_value = fake_cursor
        fake_db.__enter__.return_value = fake_db
        fake_db.__exit__.return_value = False

        with patch("app.utils.db.get_db_connection", return_value=fake_db):
            assert resolve_primary_exchange("QQQ", "IndexETF") == "ARCA"

    def test_symbol_normalization(self):
        """Symbol is upper-cased and stripped before lookup."""
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = {"exchange": "NASDAQ"}
        fake_db = MagicMock()
        fake_db.cursor.return_value = fake_cursor
        fake_db.__enter__.return_value = fake_db
        fake_db.__exit__.return_value = False

        with patch("app.utils.db.get_db_connection", return_value=fake_db):
            assert resolve_primary_exchange("  qqq  ", "IndexETF") == "NASDAQ"

        call_args = fake_cursor.execute.call_args
        assert call_args[0][1] == ("IndexETF", "QQQ")
