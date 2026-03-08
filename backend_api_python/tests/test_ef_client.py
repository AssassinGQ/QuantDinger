"""
Tests for EFClient.
"""

from unittest.mock import patch

import pytest
import requests

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
        client._ticket = "test_ticket"  # pylint: disable=protected-access
        client._account_info = {"test": "data"}  # pylint: disable=protected-access
        client.disconnect()
        assert client._ticket is None  # pylint: disable=protected-access
        assert client._account_info is None  # pylint: disable=protected-access

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
        client._ticket = "test_ticket"  # pylint: disable=protected-access
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

    def test_get_server_address_success(self):
        """Test getting server address from API."""
        config = EFConfig(account_id="123", password="456", market="ab")
        client = EFClient(config)

        with patch("requests.get") as mock_get:
            mock_get.return_value.json.return_value = {
                "code": 0,
                "host": "192.168.1.1",
                "port": "9000"
            }
            address = client._get_server_address()  # pylint: disable=protected-access
            assert address == "http://192.168.1.1:9000"

    def test_get_server_address_fallback(self):
        """Test fallback server address on failure."""
        config = EFConfig(account_id="123", password="456", market="ab")
        client = EFClient(config)

        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Network error")
            address = client._get_server_address()  # pylint: disable=protected-access
            assert address == "http://47.106.76.80:9000"

    def test_login_success(self):
        """Test successful login."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = (200, {
                "code": 0,
                "ticket": "abc123ticket",
                "account_info": {"name": "test"}
            })
            result = client._login()  # pylint: disable=protected-access
            assert result is True
            assert client._ticket == "abc123ticket"  # pylint: disable=protected-access
            assert client._account_info == {"name": "test"}  # pylint: disable=protected-access

    def test_login_failure(self):
        """Test failed login."""
        config = EFConfig(account_id="123456789", password="wrong_pass")
        client = EFClient(config)

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = (200, {
                "code": 1,
                "msg": "Invalid credentials"
            })
            result = client._login()  # pylint: disable=protected-access
            assert result is False
            assert client._ticket is None  # pylint: disable=protected-access

    def test_connect_success(self):
        """Test successful connect."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)

        with patch.object(client, "_login") as mock_login:
            mock_login.return_value = True
            result = client.connect()
            assert result is True

    def test_connect_failure(self):
        """Test failed connect."""
        config = EFConfig(account_id="123456789", password="wrong_pass")
        client = EFClient(config)

        with patch.object(client, "_login") as mock_login:
            mock_login.return_value = False
            result = client.connect()
            assert result is False
            assert client._base_url == ""  # pylint: disable=protected-access

    def test_get_exchange_type_ashare(self):
        """Test exchange type for AShare."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        assert client._get_exchange_type("AShare") == "1"  # pylint: disable=protected-access
        assert client._get_exchange_type("CN") == "1"  # pylint: disable=protected-access

    def test_get_exchange_type_hkstock(self):
        """Test exchange type for HKStock."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        assert client._get_exchange_type("HKStock") == "0"  # pylint: disable=protected-access
        assert client._get_exchange_type("HK") == "0"  # pylint: disable=protected-access

    def test_get_exchange_type_bond(self):
        """Test exchange type for Bond."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        assert client._get_exchange_type("Bond") == "2"  # pylint: disable=protected-access

    def test_get_exchange_type_etf(self):
        """Test exchange type for ETF."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        assert client._get_exchange_type("ETF") == "3"  # pylint: disable=protected-access

    def test_normalize_symbol_ashare(self):
        """Test symbol normalization for AShare."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        assert client._normalize_symbol("600519", "AShare") == "600519"  # pylint: disable=protected-access
        assert client._normalize_symbol("000001", "CN") == "000001"  # pylint: disable=protected-access

    def test_normalize_symbol_hkstock(self):
        """Test symbol normalization for HKStock."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)
        assert client._normalize_symbol("700", "HKStock") == "00700"  # pylint: disable=protected-access
        assert client._normalize_symbol("0700.HK", "HK") == "00700"  # pylint: disable=protected-access

    def test_place_market_order_not_connected(self):
        """Test market order when not connected."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        result = client.place_market_order("600519", "buy", 100, "AShare")
        assert result.success is False
        assert "Not connected" in result.message

    def test_place_limit_order_not_connected(self):
        """Test limit order when not connected."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        result = client.place_limit_order("600519", "buy", 100, 10.0, "AShare")
        assert result.success is False
        assert "Not connected" in result.message

    def test_place_limit_order_success(self):
        """Test successful limit order."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        client._ticket = "test_ticket"  # pylint: disable=protected-access
        client._base_url = "http://test.com"  # pylint: disable=protected-access

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = (200, {
                "code": 0,
                "data": {
                    "order_id": "12345",
                    "deal_amount": 100,
                    "deal_price": 10.0,
                    "status": "submitted"
                }
            })
            result = client.place_limit_order("600519", "buy", 100, 10.0, "AShare")
            assert result.success is True
            assert result.exchange_order_id == "12345"
            assert result.filled == 100.0

    def test_cancel_order_not_connected(self):
        """Test cancel order when not connected."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        result = client.cancel_order(12345)
        assert result is False

    def test_cancel_order_success(self):
        """Test successful cancel order."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        client._ticket = "test_ticket"  # pylint: disable=protected-access
        client._base_url = "http://test.com"  # pylint: disable=protected-access

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = (200, {"code": 0})
            result = client.cancel_order(12345)
            assert result is True

    def test_get_positions_not_connected(self):
        """Test get positions when not connected."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        positions = client.get_positions()
        assert positions == []

    def test_get_positions_success(self):
        """Test successful get positions."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        client._ticket = "test_ticket"  # pylint: disable=protected-access
        client._base_url = "http://test.com"  # pylint: disable=protected-access

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = (200, {
                "code": 0,
                "data": {
                    "list": [
                        {"stock_code": "600519", "hold_amount": 100, "cost_price": 1500.0}
                    ]
                }
            })
            positions = client.get_positions()
            assert len(positions) == 1
            assert positions[0]["stock_code"] == "600519"

    def test_get_positions_normalized(self):
        """Test get normalized positions."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        client._ticket = "test_ticket"  # pylint: disable=protected-access
        client._base_url = "http://test.com"  # pylint: disable=protected-access

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = (200, {
                "code": 0,
                "data": {
                    "list": [
                        {"stock_code": "600519", "hold_amount": 100, "cost_price": 1500.0}
                    ]
                }
            })
            positions = client.get_positions_normalized()
            assert len(positions) == 1
            assert positions[0].symbol == "600519"
            assert positions[0].quantity == 100.0

    def test_get_open_orders_not_connected(self):
        """Test get open orders when not connected."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        orders = client.get_open_orders()
        assert orders == []

    def test_get_open_orders_success(self):
        """Test successful get open orders."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        client._ticket = "test_ticket"  # pylint: disable=protected-access
        client._base_url = "http://test.com"  # pylint: disable=protected-access

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = (200, {
                "code": 0,
                "data": {
                    "list": [
                        {"order_id": "12345", "stock_code": "600519"}
                    ]
                }
            })
            orders = client.get_open_orders()
            assert len(orders) == 1
            assert orders[0]["order_id"] == "12345"

    def test_get_account_summary_not_connected(self):
        """Test get account summary when not connected."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        summary = client.get_account_summary()
        assert summary["success"] is False

    def test_get_account_summary_success(self):
        """Test successful get account summary."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        client._ticket = "test_ticket"  # pylint: disable=protected-access
        client._base_url = "http://test.com"  # pylint: disable=protected-access

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = (200, {
                "code": 0,
                "data": {
                    "total_assets": 100000.0,
                    "available_cash": 50000.0
                }
            })
            summary = client.get_account_summary()
            assert summary["total_assets"] == 100000.0

    def test_is_market_open_not_connected(self):
        """Test is_market_open when not connected."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        is_open, _ = client.is_market_open()
        assert is_open is False

    def test_get_quote_not_connected(self):
        """Test get_quote when not connected."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        quote = client.get_quote("600519")
        assert quote["success"] is False
        assert "Not connected" in quote["error"]

    def test_get_quote_success(self):
        """Test successful get_quote."""
        config = EFConfig(account_id="123456789", password="test_pass")
        client = EFClient(config)
        client._ticket = "test_ticket"  # pylint: disable=protected-access
        client._base_url = "http://test.com"  # pylint: disable=protected-access

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = (200, {
                "code": 0,
                "data": {
                    "price": 1800.0,
                    "open": 1785.0,
                    "high": 1810.0,
                    "low": 1770.0,
                    "volume": 1000000,
                    "amount": 1800000000
                }
            })
            quote = client.get_quote("600519", "AShare")
            assert quote["success"] is True
            assert quote["price"] == 1800.0
            assert quote["open"] == 1785.0
            assert quote["high"] == 1810.0
            assert quote["low"] == 1770.0
            assert quote["volume"] == 1000000
