"""
EastMoney (东方财富) Trading Client.

Provides a client for connecting to EastMoney broker API
for A-share, HK-stock, bond, and ETF trading.
"""

from typing import Any, Dict, List, Optional, Tuple
import json
import requests

from app.services.live_trading.base import BaseStatefulClient, LiveOrderResult, PositionRecord
from app.utils.logger import get_logger
from app.services.live_trading.ef_trading.config import EFConfig
from app.services.live_trading.ef_trading.fsm import OrderStateMachine, OrderState, OrderEvent, TERMINAL_STATES
from app.services.live_trading.ef_trading.market_hours import MarketHours

logger = get_logger(__name__)

_MAX_FSM_ENTRIES = 500


class EFClient(BaseStatefulClient):
    """EastMoney trading client."""

    engine_id = "eastmoney"
    supported_market_categories = frozenset({"AShare", "HKStock", "Bond", "ETF"})
    _DEFAULT_SERVER_URL = "http://47.106.76.80:9000"
    _SERVER_DISCOVERY_URL = "http://jvQuant.com/query/server"

    def __init__(self, config: EFConfig):
        self.config = config
        self._base_url: str = ""
        self._ticket: Optional[str] = None
        self._account_info: Optional[dict] = None
        self._order_fsm: Dict[str, OrderStateMachine] = {}

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
        url = self._SERVER_DISCOVERY_URL
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

        return self._DEFAULT_SERVER_URL

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
        self._order_fsm.clear()
        logger.info("EastMoney disconnected")

    @property
    def connected(self) -> bool:
        """Check if client is connected."""
        return self._ticket is not None

    def _get_exchange_type(self, market_type: str) -> str:
        """Convert market_type to exchange type code.

        Args:
            market_type: Market type (AShare, HKStock, Bond, ETF)

        Returns:
            Exchange type code for API
        """
        if market_type in ("AShare", "CN"):
            return "1"
        if market_type in ("HKStock", "HK"):
            return "0"
        if market_type in ("Bond", "bond"):
            return "2"
        if market_type in ("ETF", "etf"):
            return "3"
        return "1"

    def _normalize_symbol(self, symbol: str, market_type: str = "") -> str:
        """Normalize stock symbol to format expected by API.

        Args:
            symbol: Stock symbol
            market_type: Market type

        Returns:
            Normalized symbol
        """
        symbol = symbol.strip().upper().replace(".HK", "").replace(".SH", "").replace(".SZ", "")

        if market_type in ("HKStock", "HK"):
            return symbol.zfill(5)

        return symbol

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        market_type: str = "",
        **kwargs,
    ) -> LiveOrderResult:
        """Place a market order.

        Args:
            symbol: Stock symbol
            side: 'buy' or 'sale'
            quantity: Order quantity
            market_type: Market type

        Returns:
            LiveOrderResult with order execution details
        """
        return self.place_limit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=0,
            market_type=market_type,
            entrust_prop="e",
        )

    def _build_order_params(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        market_type: str,
        entrust_prop: str,
    ) -> Dict[str, Any]:
        """Build order parameters dict."""
        return {
            "token": self.config.token,
            "ticket": self._ticket,
            "code": self._normalize_symbol(symbol, market_type),
            "price": price,
            "volume": int(quantity),
            "direction": side,
            "type": self._get_exchange_type(market_type),
            "entrust_prop": entrust_prop,
        }

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        market_type: str = "",
        entrust_prop: str = "f",
        **kwargs,
    ) -> LiveOrderResult:
        """Place a limit order.

        Args:
            symbol: Stock symbol
            side: 'buy' or 'sale'
            quantity: Order quantity
            price: Limit price (0 for market order)
            market_type: Market type
            entrust_prop: Entrust property (f=limit, e=market)

        Returns:
            LiveOrderResult with order execution details
        """
        if not self.connected:
            return LiveOrderResult(
                success=False,
                message="Not connected to EastMoney API",
            )

        params = self._build_order_params(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            market_type=market_type,
            entrust_prop=entrust_prop,
        )

        path = "/buy" if side == "buy" else "/sale"

        try:
            status, resp = self._request("GET", path, params=params)

            if status == 200 and resp.get("code") == 0:
                data = resp.get("data", {})
                exchange_order_id = str(data.get("order_id", ""))

                if exchange_order_id:
                    fsm = OrderStateMachine(exchange_order_id)
                    fsm.transition(OrderEvent.SUBMIT)
                    self._order_fsm[exchange_order_id] = fsm
                    self._gc_terminal_fsm()

                return LiveOrderResult(
                    success=True,
                    exchange_id=self.engine_id,
                    exchange_order_id=exchange_order_id,
                    filled=float(data.get("deal_amount", 0)),
                    avg_price=float(data.get("deal_price", 0)),
                    status=data.get("status", "submitted"),
                    message="Order submitted successfully",
                )

            return LiveOrderResult(
                success=False,
                message=resp.get("msg", "Order failed"),
            )

        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error("Place order exception: %s", e)
            return LiveOrderResult(
                success=False,
                message=f"Order exception: {e}",
            )

    def cancel_order(self, order_id: int) -> bool:
        """Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancellation successful
        """
        if not self.connected:
            return False

        params = {
            "token": self.config.token,
            "ticket": self._ticket,
            "order_id": str(order_id),
        }

        try:
            status, resp = self._request("GET", "/cancel", params=params)
            if status == 200 and resp.get("code") == 0:
                fsm = self._order_fsm.get(str(order_id))
                if fsm:
                    fsm.transition(OrderEvent.CANCEL)
                return True
            return False
        except (requests.RequestException, json.JSONDecodeError):
            return False

    # ── FSM helpers ───────────────────────────────────────────────

    def get_order_state(self, order_id: str) -> Optional[OrderState]:
        """Get current state of an order."""
        fsm = self._order_fsm.get(order_id)
        return fsm.state if fsm else None

    def update_order_state(self, order_id: str, event: OrderEvent) -> bool:
        """Update order state with an event."""
        fsm = self._order_fsm.get(order_id)
        if fsm:
            return fsm.transition(event)
        return False

    def _gc_terminal_fsm(self) -> None:
        """Garbage collect FSM entries in terminal states."""
        if len(self._order_fsm) <= _MAX_FSM_ENTRIES:
            return
        terminal_ids = [
            oid for oid, fsm in self._order_fsm.items()
            if fsm.state in TERMINAL_STATES
        ]
        for oid in terminal_ids:
            del self._order_fsm[oid]

    def map_signal_to_side(self, signal_type: str) -> str:
        """Convert strategy signal to buy/sell."""
        signal = signal_type.lower()
        if signal in ("open_long", "add_long"):
            return "buy"
        if signal in ("close_long", "reduce_long"):
            return "sale"
        raise ValueError(f"Unsupported signal: {signal_type}")

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions.

        Returns:
            List of position dictionaries
        """
        if not self.connected:
            return []

        params = {
            "token": self.config.token,
            "ticket": self._ticket,
        }

        try:
            status, resp = self._request("GET", "/check_hold", params=params)
            if status == 200 and resp.get("code") == 0:
                data = resp.get("data", {})
                return data.get("list", [])
        except (requests.RequestException, json.JSONDecodeError):
            pass

        return []

    def get_positions_normalized(self) -> List[PositionRecord]:
        """Get normalized positions.

        Returns:
            List of PositionRecord
        """
        positions = self.get_positions()
        records = []

        for pos in positions:
            records.append(PositionRecord(
                symbol=pos.get("stock_code", ""),
                side="long",
                quantity=float(pos.get("hold_amount", 0)),
                entry_price=float(pos.get("cost_price", 0)),
                raw=pos,
            ))

        return records

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get open orders.

        Returns:
            List of order dictionaries
        """
        if not self.connected:
            return []

        params = {
            "token": self.config.token,
            "ticket": self._ticket,
        }

        try:
            status, resp = self._request("GET", "/check_order", params=params)
            if status == 200 and resp.get("code") == 0:
                data = resp.get("data", {})
                return data.get("list", [])
        except (requests.RequestException, json.JSONDecodeError):
            pass

        return []

    def get_account_summary(self) -> Dict[str, Any]:
        """Get account summary.

        Returns:
            Account summary dictionary
        """
        if not self.connected:
            return {"success": False, "error": "Not connected"}

        params = {
            "token": self.config.token,
            "ticket": self._ticket,
        }

        try:
            status, resp = self._request("GET", "/check_money", params=params)
            if status == 200 and resp.get("code") == 0:
                return resp.get("data", {})
        except (requests.RequestException, json.JSONDecodeError):
            pass

        return {"success": False, "error": "Failed to get account summary"}

    def get_connection_status(self) -> Dict[str, Any]:
        """Get connection status."""
        return {"connected": self.connected, "engine_id": self.engine_id}

    def is_market_open(self, symbol: str = "", market_type: str = "") -> Tuple[bool, str]:
        """Check if market is open.

        Args:
            symbol: Stock symbol
            market_type: Market type (AShare, HKStock, Bond, ETF)

        Returns:
            Tuple of (is_open, reason)
        """
        return MarketHours.is_trading_time(market_type or self.config.market)

    def get_quote(self, symbol: str, market_type: str = "") -> Dict[str, Any]:
        """Get real-time quote for a symbol.

        Args:
            symbol: Stock symbol
            market_type: Market type (AShare, HKStock, Bond, ETF)

        Returns:
            Quote data dictionary
        """
        if not self.connected:
            return {"success": False, "error": "Not connected"}

        normalized_symbol = self._normalize_symbol(symbol, market_type or self.config.market)

        params = {
            "token": self.config.token,
            "ticket": self._ticket,
            "code": normalized_symbol,
        }

        try:
            status, resp = self._request("GET", "/check_price", params=params)
            if status == 200 and resp.get("code") == 0:
                data = resp.get("data", {})
                return {
                    "success": True,
                    "symbol": normalized_symbol,
                    "price": data.get("price", 0),
                    "open": data.get("open", 0),
                    "high": data.get("high", 0),
                    "low": data.get("low", 0),
                    "volume": data.get("volume", 0),
                    "amount": data.get("amount", 0),
                }
        except (requests.RequestException, json.JSONDecodeError):
            pass

        return {"success": False, "error": "Failed to get quote"}
