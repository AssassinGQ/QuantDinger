import pytest
from unittest.mock import Mock, patch, MagicMock
import rsa

from app.services.live_trading.usmart_trading.config import USmartConfig
from app.services.live_trading.usmart_trading.client import USmartClient
from app.services.live_trading.usmart_trading.fsm import OrderState


@pytest.fixture
def mock_rsa_keys():
    (pub_key, priv_key) = rsa.newkeys(2048)
    return {
        "public": pub_key.save_pkcs1().decode('utf-8'),
        "private": priv_key.save_pkcs1().decode('utf-8')
    }


@pytest.fixture
def config(mock_rsa_keys):
    return USmartConfig(
        channel_id="test_channel",
        private_key=mock_rsa_keys["private"],
        public_key=mock_rsa_keys["public"],
        phone_number="13800138000",
        password="test_password",
        area_code="86",
        lang="1",
        is_pro=False,
        base_url="https://test.usmart.com",
        timeout=15.0
    )


class TestMapSignalToSide:
    def test_open_long_to_buy(self, config):
        client = USmartClient(config)
        assert client.map_signal_to_side("open_long") == "buy"

    def test_add_long_to_buy(self, config):
        client = USmartClient(config)
        assert client.map_signal_to_side("add_long") == "buy"

    def test_close_long_to_sale(self, config):
        client = USmartClient(config)
        assert client.map_signal_to_side("close_long") == "sale"

    def test_reduce_long_to_sale(self, config):
        client = USmartClient(config)
        assert client.map_signal_to_side("reduce_long") == "sale"

    def test_open_short_raises(self, config):
        client = USmartClient(config)
        with pytest.raises(ValueError, match="不支持做空"):
            client.map_signal_to_side("open_short")

    def test_close_short_raises(self, config):
        client = USmartClient(config)
        with pytest.raises(ValueError, match="不支持做空"):
            client.map_signal_to_side("close_short")

    def test_case_insensitive(self, config):
        client = USmartClient(config)
        assert client.map_signal_to_side("OPEN_LONG") == "buy"
        assert client.map_signal_to_side("Close_Long") == "sale"

    def test_unknown_signal_raises(self, config):
        client = USmartClient(config)
        with pytest.raises(ValueError, match="Unsupported signal"):
            client.map_signal_to_side("unknown_signal")


class TestPlaceLimitOrder:
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_place_limit_order_success(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {"code": 0, "data": {"entrustId": "12345"}}, "")
        
        client = USmartClient(config)
        client.connect()
        
        result = client.place_limit_order(
            symbol="00700",
            side="buy",
            quantity=100,
            price=350.0,
            market_type="HKStock"
        )
        
        assert result.success is True
        assert result.exchange_order_id == "12345"
        assert result.status == "submitted"
        assert "12345" in client._order_fsm

    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_place_limit_order_failure(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {"code": 1, "msg": "insufficient balance"}, "")
        
        client = USmartClient(config)
        client.connect()
        
        result = client.place_limit_order(
            symbol="00700",
            side="buy",
            quantity=100,
            price=350.0
        )
        
        assert result.success is False
        assert "insufficient" in result.message.lower()

    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_place_limit_order_hk_stock(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {"code": 0, "data": {"entrustId": "12345"}}, "")
        
        client = USmartClient(config)
        client.connect()
        
        result = client.place_limit_order(
            symbol="00700",
            side="buy",
            quantity=100,
            price=350.0,
            market_type="HKStock"
        )
        
        assert result.success is True

    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_place_limit_order_us_stock(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {"code": 0, "data": {"entrustId": "12345"}}, "")
        
        client = USmartClient(config)
        client.connect()
        
        result = client.place_limit_order(
            symbol="AAPL",
            side="buy",
            quantity=10,
            price=150.0,
            market_type="USStock"
        )
        
        assert result.success is True


class TestPlaceMarketOrder:
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_place_market_order_calls_limit_order(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {"code": 0, "data": {"entrustId": "12345"}}, "")
        
        client = USmartClient(config)
        client.connect()
        
        result = client.place_market_order(
            symbol="00700",
            side="buy",
            quantity=100,
            market_type="HKStock"
        )
        
        assert result.success is True


class TestCancelOrder:
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_cancel_order_success(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {"code": 0, "data": {}}, "")
        
        client = USmartClient(config)
        client.connect()
        
        fsm = client._order_fsm.get("12345")
        assert fsm is None
        
        result = client.cancel_order(12345)
        
        assert result is True

    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_cancel_order_failure(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {"code": 1, "msg": "order not found"}, "")
        
        client = USmartClient(config)
        client.connect()
        
        result = client.cancel_order(12345)
        
        assert result is False


class TestOrderStateManagement:
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_get_order_state_after_order(self, mock_login, mock_request, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {"code": 0, "data": {"entrustId": "12345"}}, "")
        
        client = USmartClient(config)
        client.connect()
        
        client.place_limit_order(
            symbol="00700",
            side="buy",
            quantity=100,
            price=350.0
        )
        
        state = client.get_order_state("12345")
        assert state == OrderState.SUBMITTED

    @patch('app.services.live_trading.usmart_trading.client.USmartClient._request')
    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_update_order_state(self, mock_login, mock_request, config):
        from app.services.live_trading.usmart_trading.fsm import OrderEvent
        
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        mock_request.return_value = (200, {"code": 0, "data": {"entrustId": "12345"}}, "")
        
        client = USmartClient(config)
        client.connect()
        
        client.place_limit_order(
            symbol="00700",
            side="buy",
            quantity=100,
            price=350.0
        )
        
        result = client.update_order_state("12345", OrderEvent.ACCEPT)
        assert result is True
        assert client.get_order_state("12345") == OrderState.ACCEPTED


class TestDisconnect:
    def test_disconnect_clears_order_fsm(self, config):
        client = USmartClient(config)
        client._token = "test_token"
        client._order_fsm["12345"] = MagicMock()
        
        client.disconnect()
        
        assert len(client._order_fsm) == 0
