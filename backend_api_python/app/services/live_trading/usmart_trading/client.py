from typing import Dict, Optional

from app.services.live_trading.base import BaseRestfulClient, LiveOrderResult
from app.utils.logger import get_logger
from app.services.live_trading.usmart_trading.config import USmartConfig
from app.services.live_trading.usmart_trading.auth import USmartAuth
from app.services.live_trading.usmart_trading.fsm import OrderStateMachine, OrderState, OrderEvent

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
        self._order_fsm: Dict[str, OrderStateMachine] = {}
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
        self._order_fsm.clear()
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

    def map_signal_to_side(self, signal_type: str) -> str:
        signal = signal_type.lower()
        if signal in ("open_long", "add_long"):
            return "buy"
        if signal in ("close_long", "reduce_long"):
            return "sale"
        if signal == "open_short":
            raise ValueError("uSMART 不支持做空")
        if signal == "close_short":
            raise ValueError("uSMART 不支持做空")
        raise ValueError(f"Unsupported signal: {signal_type}")

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        market_type: str = "",
        **kwargs
    ) -> LiveOrderResult:
        del side, kwargs
        return self.place_limit_order(
            symbol=symbol,
            side="buy",
            quantity=quantity,
            price=0,
            market_type=market_type,
            entrust_prop="e"
        )

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        market_type: str = "",
        entrust_prop: str = "e"
    ) -> LiveOrderResult:
        exchange_type = self._get_exchange_type(market_type)

        payload = {
            "exchangeType": exchange_type,
            "stockCode": symbol,
            "entrustAmount": int(quantity),
            "entrustPrice": price,
            "entrustProp": entrust_prop,
            "entrustDirection": side,
        }

        headers = self._build_auth_headers("/stock-order-server/open-api/trade", payload)
        status, resp, _ = self._request(
            "POST",
            "/stock-order-server/open-api/trade",
            json_body=payload,
            headers=headers
        )

        if status == 200 and resp.get("code") == 0:
            data = resp.get("data", {})
            exchange_order_id = data.get("entrustId", "")

            fsm = OrderStateMachine(exchange_order_id)
            fsm.transition(OrderEvent.SUBMIT)
            self._order_fsm[exchange_order_id] = fsm

            return LiveOrderResult(
                success=True,
                exchange_id=self.engine_id,
                exchange_order_id=exchange_order_id,
                filled=0,
                avg_price=price,
                status="submitted",
                message="订单已提交"
            )

        return LiveOrderResult(
            success=False,
            exchange_id=self.engine_id,
            message=resp.get("msg", "下单失败")
        )

    def cancel_order(self, order_id: int) -> bool:
        payload = {
            "entrustId": str(order_id),
        }

        headers = self._build_auth_headers("/stock-order-server/open-api/cancel-entrust", payload)
        status, resp, _ = self._request(
            "POST",
            "/stock-order-server/open-api/cancel-entrust",
            json_body=payload,
            headers=headers
        )

        if status == 200 and resp.get("code") == 0:
            fsm = self._order_fsm.get(str(order_id))
            if fsm:
                fsm.transition(OrderEvent.CANCEL)
            return True
        return False

    def get_order_state(self, order_id: str) -> Optional[OrderState]:
        fsm = self._order_fsm.get(order_id)
        return fsm.state if fsm else None

    def update_order_state(self, order_id: str, event: OrderEvent) -> bool:
        fsm = self._order_fsm.get(order_id)
        if fsm:
            return fsm.transition(event)
        return False

    def get_positions(self) -> list:
        headers = self._build_auth_headers("/stock-order-server/open-api/stock-holding", {})
        status, resp, _ = self._request(
            "POST",
            "/stock-order-server/open-api/stock-holding",
            headers=headers
        )
        if status == 200 and resp.get("code") == 0:
            return resp.get("data", {}).get("list", [])
        return []

    def get_positions_normalized(self) -> list:
        positions = self.get_positions()
        records = []
        for pos in positions:
            records.append({
                "symbol": pos.get("stockCode", ""),
                "side": "long",
                "quantity": float(pos.get("holdAmount", 0)),
                "entry_price": float(pos.get("costPrice", 0)),
                "raw": pos
            })
        return records

    def get_open_orders(self) -> list:
        headers = self._build_auth_headers("/stock-order-server/open-api/entrust-list", {})
        status, resp, _ = self._request(
            "POST",
            "/stock-order-server/open-api/entrust-list",
            headers=headers
        )
        if status == 200 and resp.get("code") == 0:
            return resp.get("data", {}).get("list", [])
        return []

    def get_account_summary(self) -> dict:
        headers = self._build_auth_headers("/stock-order-server/open-api/stock-asset", {})
        status, resp, _ = self._request(
            "POST",
            "/stock-order-server/open-api/stock-asset",
            headers=headers
        )
        if status == 200 and resp.get("code") == 0:
            return resp.get("data", {})
        return {}
