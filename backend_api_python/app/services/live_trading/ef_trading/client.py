"""
EastMoney (东方财富) Trading Client.

Provides a client for connecting to EastMoney broker API
for A-share, HK-stock, bond, and ETF trading.
"""

from typing import Any, Dict, List, Optional, Tuple
import json
import requests

from app.services.live_trading.base import BaseStatefulClient, LiveOrderResult
from app.utils.logger import get_logger
from app.services.live_trading.ef_trading.config import EFConfig

logger = get_logger(__name__)


class EFClient(BaseStatefulClient):
    """EastMoney trading client."""

    engine_id = "eastmoney"
    supported_market_categories = frozenset({"AShare", "HKStock", "Bond", "ETF"})

    def __init__(self, config: EFConfig):
        self.config = config
        self._base_url: str = ""
        self._ticket: Optional[str] = None
        self._account_info: Optional[dict] = None

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        url = self._base_url + path
        resp = requests.request(
            method=method.upper(),
            url=url,
            params=params,
            timeout=self.config.timeout,
        )
        try:
            parsed = resp.json() if resp.text else {}
        except json.JSONDecodeError:
            parsed = {"raw_text": resp.text[:2000] if resp.text else ""}
        return resp.status_code, parsed

    def _get_server_address(self) -> str:
        """Get EastMoney API server address.

        Returns:
            Server URL in format "http://host:port"
        """
        url = "http://jvQuant.com/query/server"
        params = {
            "market": self.config.market,
            "type": "trade",
        }
        if self.config.token:
            params["token"] = self.config.token

        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                host = data.get("host", "")
                port = data.get("port", "")
                return f"http://{host}:{port}"
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.warning("Failed to get server address: %s", e)

        return "http://47.106.76.80:9000"

    def _login(self) -> bool:
        """Login to EastMoney API.

        Returns:
            True if login successful, False otherwise
        """
        self._base_url = self._get_server_address()

        params = {
            "token": self.config.token,
            "acc": self.config.account_id,
            "pass": self.config.password,
        }

        try:
            status, resp = self._request("GET", "/login", params=params)
            if status == 200 and resp.get("code") == 0:
                self._ticket = resp.get("ticket", "")
                self._account_info = resp.get("account_info", {})
                ticket_preview = self._ticket[:10] if self._ticket else "None"
                logger.info("EastMoney login success, ticket: %s...", ticket_preview)
                return True
            logger.error("EastMoney login failed: %s", resp)
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error("EastMoney login exception: %s", e)

        return False

    def connect(self) -> bool:
        """Establish connection to EastMoney API.

        Returns:
            True if connection successful, False otherwise
        """
        if self._login():
            return True
        self._base_url = ""
        return False

    def disconnect(self) -> None:
        """Disconnect from EastMoney API."""
        self._ticket = None
        self._account_info = None
        logger.info("EastMoney disconnected")

    @property
    def connected(self) -> bool:
        """Check if client is connected."""
        return self._ticket is not None

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        market_type: str = "",
        **kwargs,
    ) -> LiveOrderResult:
        """Place a market order."""
        raise NotImplementedError

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        market_type: str = "",
        **kwargs,
    ) -> LiveOrderResult:
        """Place a limit order."""
        raise NotImplementedError

    def cancel_order(self, order_id: int) -> bool:
        """Cancel an order."""
        raise NotImplementedError

    def map_signal_to_side(self, signal_type: str) -> str:
        """Convert strategy signal to buy/sell."""
        signal = signal_type.lower()
        if signal in ("open_long", "add_long"):
            return "buy"
        if signal in ("close_long", "reduce_long"):
            return "sale"
        raise ValueError(f"Unsupported signal: {signal_type}")

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions."""
        raise NotImplementedError

    def get_positions_normalized(self) -> List[Any]:
        """Get normalized positions."""
        raise NotImplementedError

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get open orders."""
        raise NotImplementedError

    def get_account_summary(self) -> Dict[str, Any]:
        """Get account summary."""
        raise NotImplementedError

    def get_connection_status(self) -> Dict[str, Any]:
        """Get connection status."""
        return {"connected": self.connected, "engine_id": self.engine_id}

    def is_market_open(self, symbol: str = "", market_type: str = "") -> Tuple[bool, str]:
        """Check if market is open."""
        raise NotImplementedError
