"""
Tests for EFConfig.
"""

from app.services.live_trading.ef_trading.config import EFConfig


class TestEFConfig:
    """Test cases for EFConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = EFConfig(
            account_id="123456789",
            password="test_password"
        )
        assert config.account_id == "123456789"
        assert config.password == "test_password"
        assert config.market == "ab"
        assert config.token == ""
        assert config.base_url == ""

    def test_custom_values(self):
        """Test custom configuration values."""
        config = EFConfig(
            account_id="987654321",
            password="custom_pass",
            market="hk",
            token="my_token",
            base_url="http://custom.api.com"
        )
        assert config.account_id == "987654321"
        assert config.password == "custom_pass"
        assert config.market == "hk"
        assert config.token == "my_token"
        assert config.base_url == "http://custom.api.com"

    def test_market_options(self):
        """Test market configuration options."""
        config_ab = EFConfig(account_id="123", password="456", market="ab")
        config_hk = EFConfig(account_id="123", password="456", market="hk")
        config_us = EFConfig(account_id="123", password="456", market="us")

        assert config_ab.market == "ab"
        assert config_hk.market == "hk"
        assert config_us.market == "us"
