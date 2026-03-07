import threading
import time
from typing import Callable, Dict, Optional

from app.utils.logger import get_logger
from app.services.live_trading.usmart_trading.fsm import OrderEvent

logger = get_logger(__name__)


class OrderStatusPoller:
    def __init__(self, client, interval: float = 1.0):
        self.client = client
        self.interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: Dict[str, Callable] = {}
        self._previous_orders: Dict[str, dict] = {}

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("OrderStatusPoller started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("OrderStatusPoller stopped")

    def register_callback(self, event_type: str, callback: Callable):
        self._callbacks[event_type] = callback

    def _poll_loop(self):
        while self._running:
            try:
                if not self.client.connected:
                    time.sleep(self.interval)
                    continue

                current_orders = self.client.get_open_orders()
                current_order_ids = {str(o.get("entrustId", "")) for o in current_orders}

                for order in current_orders:
                    order_id = str(order.get("entrustId", ""))
                    if not order_id:
                        continue

                    if order_id not in self._previous_orders:
                        self._trigger("order_created", order)
                    else:
                        prev_order = self._previous_orders[order_id]
                        prev_status = prev_order.get("entrustStatus", "")
                        curr_status = order.get("entrustStatus", "")

                        if curr_status == "成交" and prev_status != "成交":
                            self._trigger("order_filled", order)
                            self.client.update_order_state(order_id, OrderEvent.FILL)

                        if curr_status == "部分成交":
                            self.client.update_order_state(order_id, OrderEvent.FILL)

                for prev_order_id, prev_order in self._previous_orders.items():
                    if prev_order_id not in current_order_ids:
                        prev_status = prev_order.get("entrustStatus", "")
                        if prev_status == "成交":
                            self._trigger("order_filled", prev_order)
                        else:
                            self._trigger("order_cancelled", prev_order)

                self._previous_orders = {str(o.get("entrustId", "")): o for o in current_orders if o.get("entrustId")}

            except Exception as e:
                logger.error("OrderStatusPoller error: %s", e)

            time.sleep(self.interval)

    def _trigger(self, event_type: str, data: dict):
        callback = self._callbacks.get(event_type)
        if callback:
            try:
                callback(data)
            except Exception as e:
                logger.error("Callback error for %s: %s", event_type, e)
