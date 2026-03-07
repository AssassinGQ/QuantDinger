import pytest
from unittest.mock import Mock, patch, MagicMock
import rsa

from app.services.live_trading.usmart_trading.config import USmartConfig
from app.services.live_trading.usmart_trading.auth import USmartAuth
from app.services.live_trading.usmart_trading.client import USmartClient


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


class TestUSmartConfig:
    def test_config_creation(self, config):
        assert config.channel_id == "test_channel"
        assert config.phone_number == "13800138000"
        assert config.password == "test_password"
        assert config.base_url == "https://test.usmart.com"
        assert config.timeout == 15.0

    def test_config_defaults(self):
        config = USmartConfig(
            channel_id="test",
            private_key="key",
            public_key="pub",
            phone_number="123",
            password="pass"
        )
        assert config.area_code == "86"
        assert config.lang == "1"
        assert config.is_pro is False
        assert config.base_url == "https://open-jy.yxzq.com"


class TestUSmartAuth:
    def test_auth_initialization(self, mock_rsa_keys):
        auth = USmartAuth(
            public_key=mock_rsa_keys["public"],
            private_key=mock_rsa_keys["private"],
            channel_id="test_channel",
            lang="1"
        )
        assert auth.channel_id == "test_channel"
        assert auth.lang == "1"

    def test_encrypt_credentials(self, mock_rsa_keys):
        auth = USmartAuth(
            public_key=mock_rsa_keys["public"],
            private_key=mock_rsa_keys["private"],
            channel_id="test_channel"
        )
        phone, password = auth.encrypt_credentials("13800138000", "test_password")
        assert phone is not None
        assert password is not None
        assert isinstance(phone, str)
        assert isinstance(password, str)

    def test_generate_request_id(self, mock_rsa_keys):
        auth = USmartAuth(
            public_key=mock_rsa_keys["public"],
            private_key=mock_rsa_keys["private"],
            channel_id="test_channel"
        )
        request_id = auth.generate_request_id()
        assert isinstance(request_id, str)
        assert len(request_id) <= 19
        assert request_id.isdigit()

    def test_generate_timestamp(self, mock_rsa_keys):
        auth = USmartAuth(
            public_key=mock_rsa_keys["public"],
            private_key=mock_rsa_keys["private"],
            channel_id="test_channel"
        )
        import time
        ts = auth.generate_timestamp()
        current_ts = str(int(time.time()))
        assert ts == current_ts

    def test_sign(self, mock_rsa_keys):
        auth = USmartAuth(
            public_key=mock_rsa_keys["public"],
            private_key=mock_rsa_keys["private"],
            channel_id="test_channel"
        )
        payload = {"phoneNumber": "test", "password": "test"}
        signature = auth.sign(payload)
        assert signature is not None
        assert isinstance(signature, str)

    def test_build_headers(self, mock_rsa_keys):
        auth = USmartAuth(
            public_key=mock_rsa_keys["public"],
            private_key=mock_rsa_keys["private"],
            channel_id="test_channel",
            lang="1"
        )
        payload = {"phoneNumber": "test", "password": "test"}
        headers = auth.build_headers("/test", payload)
        assert "X-Lang" in headers
        assert "X-Request-Id" in headers
        assert "X-Channel" in headers
        assert "X-Time" in headers
        assert "X-Sign" in headers
        assert headers["X-Lang"] == "1"
        assert headers["X-Channel"] == "test_channel"


class TestUSmartClient:
    def test_client_creation(self, config):
        client = USmartClient(config)
        assert client.engine_id == "usmart"
        assert client.config == config
        assert client.connected is False

    def test_supported_markets(self, config):
        client = USmartClient(config)
        assert "HKStock" in client.supported_market_categories
        assert "USStock" in client.supported_market_categories
        assert "AShare" in client.supported_market_categories

    def test_get_exchange_type_hk(self, config):
        client = USmartClient(config)
        assert client._get_exchange_type("HKStock") == "0"
        assert client._get_exchange_type("HShare") == "0"

    def test_get_exchange_type_us(self, config):
        client = USmartClient(config)
        assert client._get_exchange_type("USStock") == "5"
        assert client._get_exchange_type("US") == "5"

    def test_get_exchange_type_cn(self, config):
        client = USmartClient(config)
        assert client._get_exchange_type("AShare") == "1"
        assert client._get_exchange_type("CN") == "1"

    def test_get_exchange_type_default(self, config):
        client = USmartClient(config)
        assert client._get_exchange_type("") == "0"
        assert client._get_exchange_type("unknown") == "0"

    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_connect_success(self, mock_login, config):
        mock_login.return_value = {"code": 0, "data": {"token": "test_token", "accountInfo": {}}}
        client = USmartClient(config)
        result = client.connect()
        assert result is True
        assert client.connected is True
        assert client._token == "test_token"

    @patch('app.services.live_trading.usmart_trading.client.USmartClient._login')
    def test_connect_failure(self, mock_login, config):
        mock_login.return_value = {"code": 1, "msg": "login failed"}
        client = USmartClient(config)
        result = client.connect()
        assert result is False
        assert client.connected is False

    def test_disconnect(self, config):
        client = USmartClient(config)
        client._token = "test_token"
        client._account_info = {"test": "data"}
        client.disconnect()
        assert client._token is None
        assert client._account_info is None
        assert client.connected is False
