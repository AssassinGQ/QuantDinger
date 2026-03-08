"""
Tests for MarketHours in ef_trading.
"""

import pytest
from datetime import time, datetime
from unittest.mock import patch

from app.services.live_trading.ef_trading.market_hours import MarketHours


class TestMarketHours:
    """Test cases for MarketHours."""

    def test_get_market_hours_ashare(self):
        """Test getting AShare market hours."""
        hours = MarketHours.get_market_hours("AShare")
        assert hours["name"] == "A股"

    def test_get_market_hours_hkstock(self):
        """Test getting HKStock market hours."""
        hours = MarketHours.get_market_hours("HKStock")
        assert hours["name"] == "港股"

    def test_get_market_hours_bond(self):
        """Test getting Bond market hours."""
        hours = MarketHours.get_market_hours("Bond")
        assert hours["name"] == "可转债"

    def test_get_market_hours_etf(self):
        """Test getting ETF market hours."""
        hours = MarketHours.get_market_hours("ETF")
        assert hours["name"] == "ETF"

    def test_get_market_hours_default(self):
        """Test default market hours."""
        hours = MarketHours.get_market_hours("UNKNOWN")
        assert hours["name"] == "A股"

    def test_is_market_open_weekend(self):
        """Test market closed on weekend."""
        with patch("app.services.live_trading.ef_trading.market_hours.MarketHours._to_market_time") as mock_time:
            mock_market_dt = datetime(2024, 1, 6, 10, 0, 0)
            mock_time.return_value = mock_market_dt

            is_open, msg = MarketHours.is_trading_time("AShare")
            assert is_open is False
            assert "周末" in msg

    def test_is_market_open_during_trading(self):
        """Test market open during trading hours."""
        with patch("app.services.live_trading.ef_trading.market_hours.MarketHours._to_market_time") as mock_time:
            mock_market_dt = datetime(2024, 1, 8, 10, 0, 0)
            mock_time.return_value = mock_market_dt

            is_open, msg = MarketHours.is_trading_time("AShare")
            assert is_open is True
            assert msg == ""

    def test_is_market_open_outside_hours(self):
        """Test market closed outside trading hours."""
        with patch("app.services.live_trading.ef_trading.market_hours.MarketHours._to_market_time") as mock_time:
            mock_market_dt = datetime(2024, 1, 8, 17, 0, 0)
            mock_time.return_value = mock_market_dt

            is_open, msg = MarketHours.is_trading_time("AShare")
            assert is_open is False

    def test_is_market_open_hkstock(self):
        """Test HKStock market hours."""
        with patch("app.services.live_trading.ef_trading.market_hours.MarketHours._to_market_time") as mock_time:
            mock_market_dt = datetime(2024, 1, 8, 10, 0, 0)
            mock_time.return_value = mock_market_dt

            is_open, msg = MarketHours.is_trading_time("HKStock")
            assert is_open is True

    def test_is_market_open_hkstock_lunch_break(self):
        """Test HKStock market closed during lunch break."""
        with patch("app.services.live_trading.ef_trading.market_hours.MarketHours._to_market_time") as mock_time:
            mock_market_dt = datetime(2024, 1, 8, 12, 30, 0)
            mock_time.return_value = mock_market_dt

            is_open, msg = MarketHours.is_trading_time("HKStock")
            assert is_open is False
