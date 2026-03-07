from typing import Optional

from app.services.live_trading.base import BaseRestfulClient
from app.utils.logger import get_logger
from app.services.live_trading.usmart_trading.config import USmartConfig
from app.services.live_trading.usmart_trading.auth import USmartAuth

logger = get_logger(__name__)


class USmartClient(BaseRestfulClient):
    engine_id = "usmart"
    supported_market_categories = frozenset({"HKStock", "USStock", "AShare"})

    def __init__(self, config: USmartConfig):
        self.config = config
        self._token: Optional[str] = None
        self._account_info: Optional[dict] = None
        self._auth = USmartAuth(
            public_key=config.public_key,
            private_key=config.private_key,
            channel_id=config.channel_id,
            lang=config.lang
        )
        super().__init__(base_url=config.base_url, timeout_sec=config.timeout)

    def connect(self) -> bool:
        try:
            response = self._login()
            if response.get("code") == 0:
                data = response.get("data", {})
                self._token = data.get("token")
                self._account_info = data.get("accountInfo")
                logger.info("USmart connected successfully, token: %s...", self._token[:10])
                return True
            logger.error("USmart login failed: %s", response)
            return False
        except Exception as e:
            logger.error("USmart login exception: %s", e)
            return False

    def disconnect(self) -> None:
        self._token = None
        self._account_info = None
        logger.info("USmart disconnected")

    @property
    def connected(self) -> bool:
        return self._token is not None

    def _login(self) -> dict:
        encrypted_phone, encrypted_pass = self._auth.encrypt_credentials(
            self.config.phone_number,
            self.config.password
        )
        payload = {
            "phoneNumber": encrypted_phone,
            "password": encrypted_pass,
            "areaCode": self.config.area_code
        }
        headers = self._auth.build_headers("/user-server/open-api/login", payload)
        status, resp, _ = self._request(
            "POST",
            "/user-server/open-api/login",
            json_body=payload,
            headers=headers
        )
        if status == 200 and resp.get("code") == 0:
            return resp.get("data", {})
        return resp

    def _get_exchange_type(self, market_type: str) -> str:
        if market_type in ("HKStock", "HShare"):
            return "0"
        if market_type in ("USStock", "US"):
            return "5"
        if market_type in ("AShare", "CN"):
            return "1"
        return "0"

    def _build_auth_headers(self, path: str, payload: dict) -> dict:
        headers = self._auth.build_headers(path, payload)
        if self._token:
            headers["X-Token"] = self._token
        return headers
