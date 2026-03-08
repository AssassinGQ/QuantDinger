import pytest
from unittest.mock import Mock, patch

from app.services.live_trading.usmart_trading.client import USmartClient


class TestGetPositions:
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_get_positions_success(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {
            "code": 0,
            "data": {
                "list": [
                    {"stockCode": "00700", "holdAmount": 1000, "costPrice": 350.0},
                    {"stockCode": "AAPL", "holdAmount": 500, "costPrice": 150.0}
                ]
            }
        }, "")

        client = USmartClient(config)
        client.connect()

        result = client.get_positions()

        assert len(result) == 2
        assert result[0]["stockCode"] == "00700"
        assert result[1]["stockCode"] == "AAPL"

    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_get_positions_empty(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {"code": 0, "data": {"list": []}}, "")

        client = USmartClient(config)
        client.connect()

        result = client.get_positions()

        assert result == []

    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_get_positions_failure(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {"code": 1, "msg": "error"}, "")

        client = USmartClient(config)
        client.connect()

        result = client.get_positions()

        assert result == []


class TestGetPositionsNormalized:
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_get_positions_normalized(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {
            "code": 0,
            "data": {
                "list": [
                    {"stockCode": "00700", "holdAmount": 1000, "costPrice": 350.0}
                ]
            }
        }, "")

        client = USmartClient(config)
        client.connect()

        result = client.get_positions_normalized()

        assert len(result) == 1
        assert result[0]["symbol"] == "00700"
        assert result[0]["side"] == "long"
        assert result[0]["quantity"] == 1000.0
        assert result[0]["entry_price"] == 350.0
        assert "raw" in result[0]


class TestGetOpenOrders:
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_get_open_orders_success(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {
            "code": 0,
            "data": {
                "list": [
                    {"entrustId": "123", "stockCode": "00700", "entrustAmount": 100},
                    {"entrustId": "456", "stockCode": "AAPL", "entrustAmount": 50}
                ]
            }
        }, "")

        client = USmartClient(config)
        client.connect()

        result = client.get_open_orders()

        assert len(result) == 2
        assert result[0]["entrustId"] == "123"

    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_get_open_orders_empty(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {"code": 0, "data": {"list": []}}, "")

        client = USmartClient(config)
        client.connect()

        result = client.get_open_orders()

        assert result == []


class TestGetAccountSummary:
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_get_account_summary_success(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {
            "code": 0,
            "data": {
                "totalAssets": 100000.0,
                "availableCash": 50000.0,
                "marketValue": 50000.0
            }
        }, "")

        client = USmartClient(config)
        client.connect()

        result = client.get_account_summary()

        assert result["totalAssets"] == 100000.0
        assert result["availableCash"] == 50000.0
        assert result["marketValue"] == 50000.0

    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_get_account_summary_failure(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {"code": 1, "msg": "error"}, "")

        client = USmartClient(config)
        client.connect()

        result = client.get_account_summary()

        assert result == {}
