"""
Interactive Brokers Trading Client

Uses ib_insync library to connect to TWS or IB Gateway for trading.
All ib_insync calls are serialized onto a dedicated worker thread to
avoid event-loop conflicts when multiple strategy threads share one client.
"""

import os
import time
import threading
import asyncio
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable, TypeVar
from queue import Queue

from app.utils.logger import get_logger
from app.services.ibkr_trading.symbols import normalize_symbol, format_display_symbol

logger = get_logger(__name__)

T = TypeVar("T")

# Lazy import ib_insync to allow other features to work without it installed
ib_insync = None


def _ensure_ib_insync():
    """Ensure ib_insync is imported."""
    global ib_insync
    if ib_insync is None:
        try:
            import ib_insync as _ib
            ib_insync = _ib
        except ImportError:
            raise ImportError(
                "ib_insync is not installed. Run: pip install ib_insync"
            )
    return ib_insync


@dataclass
class IBKRConfig:
    """IBKR connection configuration."""
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1
    readonly: bool = False
    account: str = ""
    timeout: float = 20.0

    @classmethod
    def from_env(cls) -> "IBKRConfig":
        return cls(
            host=os.environ.get("IBKR_HOST", "127.0.0.1"),
            port=int(os.environ.get("IBKR_PORT", "7497")),
            client_id=int(os.environ.get("IBKR_CLIENT_ID", "1")),
            account=os.environ.get("IBKR_ACCOUNT", ""),
            readonly=False,
        )


@dataclass
class OrderResult:
    """Order execution result."""
    success: bool
    order_id: int = 0
    filled: float = 0.0
    avg_price: float = 0.0
    status: str = ""
    message: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


_SENTINEL = object()


class IBKRClient:
    """
    Interactive Brokers Trading Client.

    All ib_insync interactions run on a single dedicated worker thread,
    making this client safe to call from any number of strategy threads.
    """

    _TERMINAL_STATUSES = frozenset({
        "Filled", "Cancelled", "ApiCancelled", "Inactive",
        "ApiError", "ValidationError",
    })
    _REJECTED_STATUSES = frozenset({
        "Cancelled", "ApiCancelled", "Inactive",
        "ApiError", "ValidationError",
    })

    def __init__(self, config: Optional[IBKRConfig] = None):
        self.config = config or IBKRConfig()
        self._ib = None
        self._account = ""

        self._queue: Queue = Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._started = threading.Event()
        self._start_worker()

    # ── worker thread ──────────────────────────────────────────────

    def _start_worker(self):
        """Launch the dedicated ib_insync worker thread."""
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return
        self._started.clear()
        t = threading.Thread(target=self._worker_loop, daemon=True, name="ibkr-worker")
        t.start()
        self._worker_thread = t
        self._started.wait(timeout=5)

    def _worker_loop(self):
        """Run on the worker thread: create event loop, then process queue items."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._started.set()

        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                break
            fn, future = item
            try:
                result = fn()
                future.set_result(result)
            except Exception as exc:
                future.set_exception(exc)

    def _submit(self, fn: Callable[[], T], timeout: float = 60.0) -> T:
        """Submit *fn* to the worker thread and block until it completes."""
        if not (self._worker_thread and self._worker_thread.is_alive()):
            self._start_worker()
        fut: Future[T] = Future()
        self._queue.put((fn, fut))
        return fut.result(timeout=timeout)

    # ── connection ─────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        if self._ib is None:
            return False
        try:
            return self._ib.isConnected()
        except Exception:
            return False

    def connect(self) -> bool:
        return self._submit(self._do_connect)

    def _do_connect(self) -> bool:
        if self.connected:
            return True
        try:
            _ensure_ib_insync()
            if self._ib is None:
                self._ib = ib_insync.IB()

            logger.info(
                "Connecting to IBKR: %s:%s (clientId=%s)",
                self.config.host, self.config.port, self.config.client_id,
            )
            self._ib.connect(
                host=self.config.host,
                port=self.config.port,
                clientId=self.config.client_id,
                readonly=self.config.readonly,
                timeout=self.config.timeout,
            )
            accounts = self._ib.managedAccounts()
            if accounts:
                self._account = self.config.account or accounts[0]
                logger.info("IBKR connected, account: %s", self._account)
            else:
                logger.warning("IBKR connected but no account info retrieved")
            return True
        except Exception as e:
            logger.error("IBKR connection failed: %s", e)
            return False

    def disconnect(self):
        def _do():
            if self._ib is not None:
                try:
                    self._ib.disconnect()
                except Exception as e:
                    logger.warning("IBKR disconnect exception: %s", e)
                finally:
                    logger.info("IBKR disconnected")
        try:
            self._submit(_do, timeout=10)
        except Exception:
            pass

    def _ensure_connected(self, retries: int = 3, delay: float = 2.0):
        """Called from within the worker thread."""
        if self.connected:
            return
        for attempt in range(1, retries + 1):
            if self._do_connect():
                return
            if attempt < retries:
                logger.warning(
                    "IBKR connect attempt %d/%d failed, retrying in %.1fs",
                    attempt, retries, delay,
                )
                time.sleep(delay)
        raise ConnectionError(f"Cannot connect to IBKR after {retries} attempts")

    # ── contract helpers ───────────────────────────────────────────

    def _create_contract(self, symbol: str, market_type: str):
        _ensure_ib_insync()
        ib_symbol, exchange, currency = normalize_symbol(symbol, market_type)
        return ib_insync.Stock(symbol=ib_symbol, exchange=exchange, currency=currency)

    def _qualify_contract(self, contract) -> bool:
        try:
            return len(self._ib.qualifyContracts(contract)) > 0
        except Exception as e:
            logger.warning("Contract qualification failed: %s", e)
            return False

    # ── order helpers (run on worker thread) ────────────────────────

    def _wait_for_order(self, trade, timeout: float = 30.0) -> OrderResult:
        import time as _time
        deadline = _time.monotonic() + timeout
        while _time.monotonic() < deadline:
            self._ib.sleep(0.2)
            if trade.orderStatus.status in self._TERMINAL_STATUSES:
                break

        status = trade.orderStatus.status
        filled = float(trade.orderStatus.filled or 0)
        avg_price = float(trade.orderStatus.avgFillPrice or 0)

        if status in self._REJECTED_STATUSES:
            error_msgs = [e.message for e in (trade.log or []) if e.message]
            return OrderResult(
                success=False,
                order_id=trade.order.orderId,
                filled=0, avg_price=0, status=status,
                message=f"Order {status}: {'; '.join(error_msgs) or 'rejected by IBKR'}",
                raw={"orderId": trade.order.orderId, "status": status},
            )

        if status not in self._TERMINAL_STATUSES:
            logger.warning(
                "Order %s timed out in status '%s' after %ss",
                trade.order.orderId, status, timeout,
            )

        return OrderResult(
            success=True,
            order_id=trade.order.orderId,
            filled=filled, avg_price=avg_price, status=status,
            message="Order submitted" if status != "Filled" else "Order filled",
            raw={
                "orderId": trade.order.orderId,
                "status": status,
                "filled": filled,
                "remaining": float(trade.orderStatus.remaining or 0),
            },
        )

    # ── public order API ───────────────────────────────────────────

    def place_market_order(
        self, symbol: str, side: str, quantity: float,
        market_type: str = "USStock",
    ) -> OrderResult:
        from app.services.ibkr_trading.order_normalizer import get_normalizer
        ok, reason = get_normalizer(market_type).check(quantity, symbol)
        if not ok:
            return OrderResult(success=False, message=reason)

        def _do():
            self._ensure_connected()
            _ensure_ib_insync()
            contract = self._create_contract(symbol, market_type)
            if not self._qualify_contract(contract):
                return OrderResult(success=False, message=f"Invalid contract: {symbol}")
            order = ib_insync.MarketOrder(
                action="BUY" if side.lower() == "buy" else "SELL",
                totalQuantity=quantity, account=self._account,
            )
            trade = self._ib.placeOrder(contract, order)
            return self._wait_for_order(trade, timeout=30.0)

        try:
            return self._submit(_do, timeout=60.0)
        except Exception as e:
            logger.error("Order failed: %s", e)
            return OrderResult(success=False, message=str(e))

    def place_limit_order(
        self, symbol: str, side: str, quantity: float, price: float,
        market_type: str = "USStock",
    ) -> OrderResult:
        from app.services.ibkr_trading.order_normalizer import get_normalizer
        ok, reason = get_normalizer(market_type).check(quantity, symbol)
        if not ok:
            return OrderResult(success=False, message=reason)

        def _do():
            self._ensure_connected()
            _ensure_ib_insync()
            contract = self._create_contract(symbol, market_type)
            if not self._qualify_contract(contract):
                return OrderResult(success=False, message=f"Invalid contract: {symbol}")
            order = ib_insync.LimitOrder(
                action="BUY" if side.lower() == "buy" else "SELL",
                totalQuantity=quantity, lmtPrice=price, account=self._account,
            )
            trade = self._ib.placeOrder(contract, order)
            return self._wait_for_order(trade, timeout=30.0)

        try:
            return self._submit(_do, timeout=60.0)
        except Exception as e:
            logger.error("Limit order failed: %s", e)
            return OrderResult(success=False, message=str(e))

    def cancel_order(self, order_id: int) -> bool:
        def _do():
            self._ensure_connected()
            for trade in self._ib.openTrades():
                if trade.order.orderId == order_id:
                    self._ib.cancelOrder(trade.order)
                    logger.info("Order %s cancelled", order_id)
                    return True
            logger.warning("Order not found: %s", order_id)
            return False

        try:
            return self._submit(_do, timeout=15.0)
        except Exception as e:
            logger.error("Cancel order failed: %s", e)
            return False

    # ── public query API ───────────────────────────────────────────

    def get_account_summary(self) -> Dict[str, Any]:
        def _do():
            self._ensure_connected()
            summary = self._ib.accountSummary(self._account)
            result = {}
            for item in summary:
                result[item.tag] = {"value": item.value, "currency": item.currency}
            return {"account": self._account, "summary": result, "success": True}

        try:
            return self._submit(_do, timeout=15.0)
        except Exception as e:
            logger.error("Get account summary failed: %s", e)
            return {"success": False, "error": str(e)}

    def get_positions(self) -> List[Dict[str, Any]]:
        def _do():
            self._ensure_connected()
            positions = self._ib.positions(self._account)
            result = []
            for pos in positions:
                contract = pos.contract
                exchange = contract.exchange or contract.primaryExchange or "SMART"
                result.append({
                    "symbol": format_display_symbol(contract.symbol, exchange),
                    "ib_symbol": contract.symbol,
                    "secType": contract.secType,
                    "exchange": exchange,
                    "currency": contract.currency,
                    "quantity": float(pos.position),
                    "avgCost": float(pos.avgCost),
                    "marketValue": float(pos.position) * float(pos.avgCost),
                })
            return result

        try:
            return self._submit(_do, timeout=15.0)
        except Exception as e:
            logger.error("Get positions failed: %s", e)
            return []

    def get_open_orders(self) -> List[Dict[str, Any]]:
        def _do():
            self._ensure_connected()
            trades = self._ib.openTrades()
            result = []
            for trade in trades:
                order = trade.order
                contract = trade.contract
                status = trade.orderStatus
                result.append({
                    "orderId": order.orderId,
                    "symbol": contract.symbol,
                    "action": order.action,
                    "quantity": float(order.totalQuantity),
                    "orderType": order.orderType,
                    "limitPrice": getattr(order, "lmtPrice", None),
                    "status": status.status,
                    "filled": float(status.filled or 0),
                    "remaining": float(status.remaining or 0),
                    "avgFillPrice": float(status.avgFillPrice or 0),
                })
            return result

        try:
            return self._submit(_do, timeout=15.0)
        except Exception as e:
            logger.error("Get orders failed: %s", e)
            return []

    def get_quote(self, symbol: str, market_type: str = "USStock") -> Dict[str, Any]:
        def _do():
            self._ensure_connected()
            contract = self._create_contract(symbol, market_type)
            if not self._qualify_contract(contract):
                return {"success": False, "error": f"Invalid contract: {symbol}"}
            ticker = self._ib.reqMktData(contract, "", False, False)
            self._ib.sleep(2)
            result = {
                "success": True, "symbol": symbol,
                "bid": ticker.bid if ticker.bid and ticker.bid > 0 else None,
                "ask": ticker.ask if ticker.ask and ticker.ask > 0 else None,
                "last": ticker.last if ticker.last and ticker.last > 0 else None,
                "high": ticker.high if ticker.high and ticker.high > 0 else None,
                "low": ticker.low if ticker.low and ticker.low > 0 else None,
                "volume": ticker.volume if ticker.volume and ticker.volume > 0 else None,
                "close": ticker.close if ticker.close and ticker.close > 0 else None,
            }
            self._ib.cancelMktData(contract)
            return result

        try:
            return self._submit(_do, timeout=15.0)
        except Exception as e:
            logger.error("Get quote failed: %s", e)
            return {"success": False, "error": str(e)}

    def get_connection_status(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "host": self.config.host,
            "port": self.config.port,
            "clientId": self.config.client_id,
            "account": self._account,
            "readonly": self.config.readonly,
        }

    def shutdown(self):
        """Gracefully stop the worker thread."""
        self._queue.put(_SENTINEL)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)


# ── Global singleton ──────────────────────────────────────────────

_global_client: Optional[IBKRClient] = None
_global_lock = threading.Lock()


def get_ibkr_client(config: Optional[IBKRConfig] = None) -> IBKRClient:
    """
    Get global IBKR client singleton with auto-reconnect.

    All ib_insync operations are serialized onto the client's worker thread,
    so this is safe to call from any number of strategy threads concurrently.
    """
    global _global_client

    with _global_lock:
        if _global_client is None:
            cfg = config or IBKRConfig.from_env()
            _global_client = IBKRClient(cfg)
        if not _global_client.connected:
            _global_client.connect()
        return _global_client


def reset_ibkr_client():
    """Reset global client (disconnect and clear instance)."""
    global _global_client

    with _global_lock:
        if _global_client is not None:
            _global_client.disconnect()
            _global_client.shutdown()
            _global_client = None
