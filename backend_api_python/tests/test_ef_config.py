from app.services.live_trading.ef_trading.config import EFConfig


class TestEFConfig:
    def test_default_values(self):
        config = EFConfig(
            account_id="123456789",
            password="test_password"
        )
        assert config.account_id == "123456789"
        assert config.password == "test_password"
        assert config.market == "ab"
        assert config.token == ""
        assert config.base_url == ""
        assert config.timeout == 15.0

    def test_custom_values(self):
        config = EFConfig(
            account_id="987654321",
            password="secure_pass",
            market="sz",
            token="my_token",
            base_url="http://custom.server:8080",
            timeout=30.0
        )
        assert config.account_id == "987654321"
        assert config.password == "secure_pass"
        assert config.market == "sz"
        assert config.token == "my_token"
        assert config.base_url == "http://custom.server:8080"
        assert config.timeout == 30.0

    def test_market_options(self):
        markets = ["ab", "sz", "sh"]
        for market in markets:
            config = EFConfig(
                account_id="123456789",
                password="password",
                market=market
            )
            assert config.market == market
