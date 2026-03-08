"""
Tests for EFClient.
"""

import pytest
from unittest.mock import Mock, patch

from app.services.live_trading.ef_trading.client import EFClient
from app.services.live_trading.ef_trading.config import EFConfig


class TestEFClient:
    """Test cases for EFClient."""

    def test_init(self):
        """Test client initialization."""
        config = EFConfig(
            account_id="123456789",
            password="test_password"
        )
        client = EFClient(config)
        assert client.config == config
        assert client.engine_id == "eastmoney"
        assert client.connected is False

    def test_supported_market_categories(self):
        """Test supported market categories."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        assert "AShare" in client.supported_market_categories
        assert "HKStock" in client.supported_market_categories
        assert "Bond" in client.supported_market_categories
        assert "ETF" in client.supported_market_categories

    def test_disconnect(self):
        """Test disconnect clears session."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        client._ticket = "test_ticket"
        client._account_info = {"test": "data"}
        client.disconnect()
        assert client._ticket is None
        assert client._account_info is None

    def test_map_signal_to_side_open_long(self):
        """Test signal mapping for open_long."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        assert client.map_signal_to_side("open_long") == "buy"

    def test_map_signal_to_side_add_long(self):
        """Test signal mapping for add_long."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        assert client.map_signal_to_side("add_long") == "buy"

    def test_map_signal_to_side_close_long(self):
        """Test signal mapping for close_long."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        assert client.map_signal_to_side("close_long") == "sale"

    def test_map_signal_to_side_reduce_long(self):
        """Test signal mapping for reduce_long."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        assert client.map_signal_to_side("reduce_long") == "sale"

    def test_map_signal_to_side_case_insensitive(self):
        """Test signal mapping is case insensitive."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        assert client.map_signal_to_side("OPEN_LONG") == "buy"
        assert client.map_signal_to_side("Close_Long") == "sale"

    def test_map_signal_to_side_invalid(self):
        """Test signal mapping raises on invalid signal."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        with pytest.raises(ValueError, match="Unsupported signal"):
            client.map_signal_to_side("open_short")

    def test_map_signal_to_side_unknown(self):
        """Test signal mapping raises on unknown signal."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        with pytest.raises(ValueError, match="Unsupported signal"):
            client.map_signal_to_side("unknown_signal")

    def test_get_connection_status_disconnected(self):
        """Test connection status when disconnected."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        status = client.get_connection_status()
        assert status["connected"] is False
        assert status["engine_id"] == "eastmoney"

    def test_get_connection_status_connected(self):
        """Test connection status when connected."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        client._ticket = "test_ticket"
        status = client.get_connection_status()
        assert status["connected"] is True

    def test_validate_market_category_valid(self):
        """Test market category validation with valid category."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        valid, msg = client.validate_market_category("AShare")
        assert valid is True
        assert msg == ""

    def test_validate_market_category_invalid(self):
        """Test market category validation with invalid category."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        valid, msg = client.validate_market_category("InvalidMarket")
        assert valid is False
        assert "eastmoney only supports" in msg
