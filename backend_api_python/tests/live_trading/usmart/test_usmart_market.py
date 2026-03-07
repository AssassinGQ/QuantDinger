import pytest
from datetime import datetime, time
import rsa

from app.services.live_trading.usmart_trading.config import USmartConfig
from app.services.live_trading.usmart_trading.client import USmartClient
from app.services.live_trading.usmart_trading.market_hours import MarketHours


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


class TestMarketHours:
    def test_get_hong_kong_hours(self):
        hours = MarketHours.get_market_hours("HKStock")
        assert hours["name"] == "港股"
        assert len(hours["sessions"]) == 2

    def test_get_us_hours(self):
        hours = MarketHours.get_market_hours("USStock")
        assert hours["name"] == "美股"
        assert len(hours["sessions"]) == 1

    def test_get_china_hours(self):
        hours = MarketHours.get_market_hours("AShare")
        assert hours["name"] == "A股"
        assert len(hours["sessions"]) == 2

    def test_is_trading_time_hk_morning(self):
        dt = datetime(2024, 1, 15, 10, 0, 0)
        is_open, msg = MarketHours.is_trading_time("HKStock", dt)
        assert is_open is True

    def test_is_trading_time_hk_lunch(self):
        dt = datetime(2024, 1, 15, 12, 30, 0)
        is_open, msg = MarketHours.is_trading_time("HKStock", dt)
        assert is_open is False
        assert "非交易时间" in msg

    def test_is_trading_time_hk_afternoon(self):
        dt = datetime(2024, 1, 15, 14, 0, 0)
        is_open, msg = MarketHours.is_trading_time("HKStock", dt)
        assert is_open is True

    def test_is_trading_time_hk_after_close(self):
        dt = datetime(2024, 1, 15, 17, 0, 0)
        is_open, msg = MarketHours.is_trading_time("HKStock", dt)
        assert is_open is False

    def test_is_trading_time_us(self):
        dt = datetime(2024, 1, 15, 14, 0, 0)
        is_open, msg = MarketHours.is_trading_time("USStock", dt)
        assert is_open is True

    def test_is_trading_time_cn_morning(self):
        dt = datetime(2024, 1, 15, 10, 0, 0)
        is_open, msg = MarketHours.is_trading_time("AShare", dt)
        assert is_open is True

    def test_is_trading_time_cn_lunch(self):
        dt = datetime(2024, 1, 15, 12, 0, 0)
        is_open, msg = MarketHours.is_trading_time("AShare", dt)
        assert is_open is False

    def test_is_trading_time_cn_afternoon(self):
        dt = datetime(2024, 1, 15, 14, 0, 0)
        is_open, msg = MarketHours.is_trading_time("AShare", dt)
        assert is_open is True


class TestIsMarketOpen:
    def test_is_market_open_hk(self, config):
        client = USmartClient(config)
        is_open, msg = client.is_market_open("00700", "HKStock")
        assert isinstance(is_open, bool)

    def test_is_market_open_us(self, config):
        client = USmartClient(config)
        is_open, msg = client.is_market_open("AAPL", "USStock")
        assert isinstance(is_open, bool)

    def test_is_market_open_cn(self, config):
        client = USmartClient(config)
        is_open, msg = client.is_market_open("600000", "AShare")
        assert isinstance(is_open, bool)


class TestInferMarketType:
    def test_infer_hk_stock_5_digit(self, config):
        client = USmartClient(config)
        assert client._infer_market_type("00700") == "HKStock"

    def test_infer_hk_stock(self, config):
        client = USmartClient(config)
        assert client._infer_market_type("HK00700") == "HKStock"

    def test_infer_ashare_sh(self, config):
        client = USmartClient(config)
        assert client._infer_market_type("600000") == "AShare"

    def test_infer_ashare_sz(self, config):
        client = USmartClient(config)
        assert client._infer_market_type("000001") == "AShare"

    def test_infer_ashare_cyb(self, config):
        client = USmartClient(config)
        assert client._infer_market_type("300001") == "AShare"

    def test_infer_us_stock(self, config):
        client = USmartClient(config)
        assert client._infer_market_type("AAPL") == "USStock"

    def test_infer_empty_symbol(self, config):
        client = USmartClient(config)
        assert client._infer_market_type("") == "HKStock"

    def test_is_market_open_infer_from_symbol(self, config):
        client = USmartClient(config)
        is_open, msg = client.is_market_open(symbol="00700")
        assert isinstance(is_open, bool)
