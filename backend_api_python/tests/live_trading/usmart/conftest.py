import pytest
import rsa

from app.services.live_trading.usmart_trading.config import USmartConfig


@pytest.fixture
def mock_rsa_keys():
    (pub_key, priv_key) = rsa.newkeys(2048)
    return {
        "public": pub_key.save_pkcs1().decode("utf-8"),
        "private": priv_key.save_pkcs1().decode("utf-8"),
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
        timeout=15.0,
    )
