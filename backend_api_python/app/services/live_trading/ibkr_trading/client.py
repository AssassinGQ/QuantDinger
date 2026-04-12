"""
Interactive Brokers Trading Client

Uses ib_insync library to connect to TWS or IB Gateway for trading.
All ib_insync calls are dispatched via TaskQueue to IBExecutor
(dedicated asyncio event-loop thread), keeping the event loop responsive
and making this client safe to call from any number of strategy / Flask /
worker threads.  DB / notification operations are dispatched to IOExecutor.

Events: all 25 IB events are subscribed. Business-critical ones drive order
flow; the rest log for observability.
"""

import json
import os
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable, Tuple
import math

from app.utils.logger import get_logger
from app.services.live_trading.base import BaseStatefulClient, LiveOrderResult
from app.services.live_trading.ibkr_trading.symbols import normalize_symbol
from app.services.live_trading.ibkr_trading.order_tracker import HARD_TERMINAL
from app.services.live_trading.task_queue import TaskQueue
from app.services.live_trading import records

logger = get_logger(__name__)

ib_insync = None


def _contract_symbol_label(contract) -> str:
    """Prefer IBKR localSymbol (e.g. EUR.USD) over base symbol for stable map/API keys."""
    ls = getattr(contract, "localSymbol", None)
    sym = getattr(contract, "symbol", None)
    if isinstance(ls, str) and ls.strip():
        return ls.strip()
    if isinstance(sym, str) and sym.strip():
        return sym.strip()
    return ""


def _contract_str_field(val) -> str:
    """String metadata from Contract; ignore non-strings (e.g. MagicMock in tests)."""
    if isinstance(val, str):
        return val
    return ""


def _ensure_ib_insync():
    global ib_insync
    if ib_insync is None:
        try:
            import ib_insync as _ib
            ib_insync = _ib
        except ImportError as exc:
            raise ImportError(
                "ib_insync is not installed. Run: pip install ib_insync"
            ) from exc
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
    def from_env(cls, mode: str = "paper") -> "IBKRConfig":
        if mode == "live":
            return cls(
                host=os.environ.get("IBKR_LIVE_HOST", "127.0.0.1"),
                port=int(os.environ.get("IBKR_LIVE_PORT", "4001")),
                client_id=int(os.environ.get("IBKR_LIVE_CLIENT_ID", "1")),
                account=os.environ.get("IBKR_LIVE_ACCOUNT", ""),
                readonly=False,
            )
        return cls(
            host=os.environ.get("IBKR_HOST", "127.0.0.1"),
            port=int(os.environ.get("IBKR_PORT", "7497")),
            client_id=int(os.environ.get("IBKR_CLIENT_ID", "1")),
            account=os.environ.get("IBKR_ACCOUNT", ""),
            readonly=False,
        )


@dataclass
class IBKROrderContext:
    """Registered at order placement, consumed by event callbacks."""
    order_id: int
    pending_order_id: int = 0
    strategy_id: int = 0
    symbol: str = ""
    signal_type: str = ""
    amount: float = 0.0
    market_type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    order_row: Dict[str, Any] = field(default_factory=dict)
    notification_config: Dict[str, Any] = field(default_factory=dict)
    strategy_name: str = ""
    market_category: str = ""


class IBKRClient(BaseStatefulClient):
    """
    Interactive Brokers Trading Client.

    All ib_insync interactions run on the IBExecutor event-loop thread via
    TaskQueue, making this client safe to call from any number of threads.
    """

    engine_id = "ibkr"
    supported_market_categories = frozenset({"USStock", "HShare", "Forex", "Metals"})

    @staticmethod
    def validate_market_category_static(market_category: str) -> Tuple[bool, str]:
        cat = str(market_category or "").strip()
        if not IBKRClient.supported_market_categories:
            return True, ""
        if cat in IBKRClient.supported_market_categories:
            return True, ""
        return False, (
            f"{IBKRClient.engine_id} only supports "
            f"{', '.join(sorted(IBKRClient.supported_market_categories))}, "
            f"got {cat}"
        )

    _TERMINAL_STATUSES = frozenset({
        "Filled", "Cancelled", "ApiCancelled", "Inactive",
        "ApiError", "ValidationError",
    })
    _REJECTED_STATUSES = frozenset({
        "Cancelled", "ApiCancelled", "Inactive",
        "ApiError", "ValidationError",
    })

    _SIGNAL_MAP = {
        "open_long": "buy",
        "add_long": "buy",
        "close_long": "sell",
        "reduce_long": "sell",
    }

    _FOREX_SIGNAL_MAP = {
        "open_long": "buy",
        "add_long": "buy",
        "close_long": "sell",
        "reduce_long": "sell",
        "open_short": "sell",
        "add_short": "sell",
        "close_short": "buy",
        "reduce_short": "buy",
    }

    _RECONNECT_DELAYS = [2, 5, 10, 30, 60]

    @staticmethod
    def _get_tif_for_signal(
        signal_type: str, market_type: str = "USStock", order_type: str = "market",
    ) -> str:
        """Get TIF (Time in Force) based on signal type, market type, and order kind.

        **Limit orders (automation / default REST):** ``order_type=="limit"`` → ``"DAY"``
        for every market (resting until session end or fill); ``signal_type`` and
        ``market_type`` do not change TIF for limits.

        **Market orders:** For ``market_type`` in ``("Forex", "USStock", "HShare", "Metals")``,
        all signal types use ``"IOC"`` (unified policy; ``signal_type`` is ignored).
        IBKR lists IOC for the relevant venues including SEHK; see
        https://www.interactivebrokers.com/en/trading/order-type-exchanges.php?ot=ioc

        For any other ``market_type`` not explicitly handled here, returns ``"DAY"``
        as a conservative default until support is added.
        """
        if (order_type or "").lower() == "limit":
            return "DAY"
        if market_type in ("Forex", "USStock", "HShare", "Metals"):
            return "IOC"
        return "DAY"

    def __init__(self, config: Optional[IBKRConfig] = None, mode: str = "paper"):
        self.config = config or IBKRConfig()
        self.mode = mode
        self._ib = None
        self._account = ""

        self._tq = TaskQueue(loop_executor_name="ibkr-loop-executor", pool_executor_name="ibkr-pool-executor", pool_workers=4)
        self._tq.start()

        # Fire-and-forget order context: orderId → IBKROrderContext
        self._order_contexts: Dict[int, IBKROrderContext] = {}
        self._commission_contexts: Dict[int, IBKROrderContext] = {}
        self._events_registered = False
        self._event_map: List[tuple] = []

        self._reconnect_thread: Optional[threading.Thread] = None
        self._reconnect_stop = threading.Event()

        self._conid_to_symbol: Dict[int, str] = {}
        self._subscribed_conids: set = set()

        # Per-(symbol, market_type) cache for successful qualifyContractsAsync (TTL via monotonic clock).
        self._qualify_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

    # ── signal mapping ──────────────────────────────────────────────

    def map_signal_to_side(self, signal_type: str, *, market_category: str = "") -> str:
        sig = (signal_type or "").strip().lower()
        cat = (market_category or "").strip()
        if cat in ("Forex", "Metals"):
            side = self._FOREX_SIGNAL_MAP.get(sig)
            if side is None:
                raise ValueError(f"Unsupported signal_type for IBKR: {signal_type}")
            return side
        if "short" in sig:
            raise ValueError(f"IBKR 美股/港股不支持 short 信号: {signal_type}")
        side = self._SIGNAL_MAP.get(sig)
        if side is None:
            raise ValueError(f"Unsupported signal_type for IBKR: {signal_type}")
        return side

    # ── submit helpers ──────────────────────────────────────────────

    def _submit(self, fn, timeout: float = 60.0, is_blocking: bool = False):
        """Submit a callable or coroutine to the IB event-loop thread and block."""
        return self._tq.submit(fn, is_blocking=is_blocking).result(timeout=timeout)

    def _submit_with_retry(self, fn, is_blocking: bool = False, timeout_per_try: float = 15.0, max_retries: int = 3, retry_delay: float = 1.0):
        """Submit with retry logic: retry the entire fn execution on failure."""
        last_error = None
        for i in range(max_retries):
            if i > 0:
                time.sleep(retry_delay)
            try:
                result = self._submit(fn, timeout=timeout_per_try, is_blocking=is_blocking)
                if result:
                    return result
            except Exception as e:
                last_error = e
                logger.warning("[Retry] attempt %d/%d failed: %s", i + 1, max_retries, e)
        if last_error:
            raise last_error
        return None

    def _fire_submit(self, fn: Callable, is_blocking: bool = False):
        """Fire-and-forget submit to IB or IO executor. Returns Future."""
        return self._tq.submit(fn, is_blocking=is_blocking)

    # ── connection ──────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        if self._ib is None:
            return False
        try:
            return self._ib.isConnected()
        except Exception:
            return False

    def connect(self) -> bool:
        self._reconnect_stop.clear()
        return self._submit(self._do_connect_coro(), timeout=60)

    async def _do_connect_coro(self) -> bool:
        """Async connect — must run on the IB event-loop thread."""
        if self.connected:
            self._register_events()
            return True
        try:
            _ensure_ib_insync()
            if self._ib is None:
                self._ib = ib_insync.IB()
                self._ib.RequestTimeout = 10

            logger.info(
                "Connecting to IBKR: %s:%s (clientId=%s)",
                self.config.host, self.config.port, self.config.client_id,
            )
            await self._ib.connectAsync(
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
            self._register_events()

            await self._activate_pnl_subscriptions()

            return True
        except Exception as e:
            logger.error("IBKR connection failed: %s", e)
            return False

    def disconnect(self):
        self._reconnect_stop.set()
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            self._reconnect_thread.join(timeout=3)

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
        except Exception as e:
            logger.warning("Disconnect submit failed: %s", e)

    async def _ensure_connected_async(self, retries: int = 3, delay: float = 2.0):
        """Async version — awaitable from coroutines on the IB loop."""
        if self.connected:
            return
        import asyncio as _aio
        for attempt in range(1, retries + 1):
            if await self._do_connect_coro():
                return
            if attempt < retries:
                logger.warning(
                    "IBKR connect attempt %d/%d failed, retrying in %.1fs",
                    attempt, retries, delay,
                )
                await _aio.sleep(delay)
        raise ConnectionError(f"Cannot connect to IBKR after {retries} attempts")

    def _ensure_connected(self, retries: int = 3, delay: float = 2.0):
        """Sync version — used in tests and sync contexts."""
        if self.connected:
            return
        for attempt in range(1, retries + 1):
            if self._submit(self._do_connect_coro(), timeout=60):
                return
            if attempt < retries:
                logger.warning(
                    "IBKR connect attempt %d/%d failed, retrying in %.1fs",
                    attempt, retries, delay,
                )
                time.sleep(delay)
        raise ConnectionError(f"Cannot connect to IBKR after {retries} attempts")

    async def _health_check_async(self) -> bool:
        try:
            dt = await self._ib.reqCurrentTimeAsync()
            return dt is not None
        except Exception:
            return False

    # ── event registration (all 25 IB events) ─────────────────────

    def _build_event_map(self):
        """Build (event_name, handler) pairs once; reused by register/unregister."""
        if self._event_map:
            return
        self._event_map = [
            ("orderStatusEvent",      self._on_order_status),
            ("execDetailsEvent",      self._on_exec_details),
            ("commissionReportEvent", self._on_commission_report),
            ("errorEvent",            self._on_error),
            ("connectedEvent",        self._on_connected),
            ("disconnectedEvent",     self._on_disconnected),
            ("newOrderEvent",         self._on_new_order),
            ("orderModifyEvent",      self._on_order_modify),
            ("cancelOrderEvent",      self._on_cancel_order),
            ("openOrderEvent",        self._on_open_order),
            ("updatePortfolioEvent",  self._on_update_portfolio),
            ("positionEvent",         self._on_position),
            ("tickNewsEvent",         self._on_tick_news),
            ("newsBulletinEvent",     self._on_news_bulletin),
            ("wshMetaEvent",          self._on_wsh_meta),
            ("wshEvent",              self._on_wsh),
            ("timeoutEvent",          self._on_timeout),
            ("pnlEvent",              self._on_pnl),
            ("pnlSingleEvent",        self._on_pnl_single),
            ("accountValueEvent",     self._on_account_value),
            ("accountSummaryEvent",   self._on_account_summary),
            ("pendingTickersEvent",   self._on_pending_tickers),
            ("barUpdateEvent",        self._on_bar_update),
            ("scannerDataEvent",      self._on_scanner_data),
            ("updateEvent",           self._on_update),
        ]

    def _unregister_events(self):
        """Remove all previously registered handlers to prevent accumulation."""
        if self._ib is None:
            return
        ib = self._ib
        self._build_event_map()
        for event_name, handler in self._event_map:
            event = getattr(ib, event_name, None)
            if event is None:
                continue
            try:
                while handler in event:
                    event -= handler
            except Exception:
                pass

    def _register_events(self):
        if self._events_registered or self._ib is None:
            return
        ib = self._ib
        self._build_event_map()

        self._unregister_events()

        for event_name, handler in self._event_map:
            event = getattr(ib, event_name, None)
            if event is not None:
                event += handler

        self._events_registered = True
        logger.info("[IBKR-Event] All %d IB events registered (clean)", len(self._event_map))

    async def _activate_pnl_subscriptions(self):
        """Activate PnL subscriptions after connection."""
        if not self._account:
            logger.warning("[IBKR] No account available for PnL subscriptions")
            return
        try:
            self._ib.reqPnL(self._account)
            logger.info("[IBKR] reqPnL subscription activated for account: %s", self._account)
        except Exception as e:
            logger.error("[IBKR] Failed to activate reqPnL: %s", e)
        try:
            positions = await self._ib.reqPositionsAsync()
            logger.info("[IBKR] reqPositionsAsync returned %d positions", len(positions))
        except Exception as e:
            logger.error("[IBKR] Failed to activate reqPositionsAsync: %s", e)

    # ── event callbacks: business logic ───────────────────────────

    _COMMISSION_LINGER_SEC = 30

    def _on_order_status(self, trade):
        order_id = trade.order.orderId
        status = trade.orderStatus.status
        filled = float(trade.orderStatus.filled or 0)
        avg_price = float(trade.orderStatus.avgFillPrice or 0)
        logger.info(
            "[IBKR-Event] orderStatus: orderId=%s status=%s filled=%s avgPrice=%s",
            order_id, status, filled, avg_price,
        )

        ctx = self._order_contexts.pop(order_id, None)
        if ctx is None:
            return

        if status == "Filled" and filled > 0:
            self._fire_submit(lambda: self._handle_fill(ctx, filled, avg_price), is_blocking=True)
            self._keep_for_commission(order_id, ctx)
        elif status == "Cancelled" and filled > 0:
            self._fire_submit(lambda: self._handle_fill(ctx, filled, avg_price), is_blocking=True)
            self._keep_for_commission(order_id, ctx)
        elif status == "Cancelled" and filled <= 0:
            error_msgs = [e.message for e in (trade.log or []) if e.message]
            self._fire_submit(lambda: self._handle_reject(ctx, status, error_msgs), is_blocking=True)
        elif status in HARD_TERMINAL:
            error_msgs = [e.message for e in (trade.log or []) if e.message]
            self._fire_submit(lambda: self._handle_reject(ctx, status, error_msgs), is_blocking=True)
        else:
            self._order_contexts[order_id] = ctx

    def _keep_for_commission(self, order_id: int, ctx: IBKROrderContext):
        """Retain context for commissionReportEvent, then clean up after delay."""
        self._commission_contexts[order_id] = ctx

        def _cleanup():
            time.sleep(self._COMMISSION_LINGER_SEC)
            removed = self._commission_contexts.pop(order_id, None)
            if removed:
                logger.debug("[IBKR] Cleaned up commission context for orderId=%s", order_id)

        t = threading.Thread(target=_cleanup, daemon=True, name=f"comm-ctx-{order_id}")
        t.start()

    def _on_exec_details(self, trade, fill):
        order_id = trade.order.orderId
        exec_id = fill.execution.execId
        filled = float(trade.orderStatus.filled or 0)
        avg_price = float(trade.orderStatus.avgFillPrice or 0)
        logger.info(
            "[IBKR-Event] execDetails: orderId=%s execId=%s side=%s shares=%s price=%s cumFilled=%s avgPrice=%s",
            order_id, exec_id, fill.execution.side, fill.execution.shares,
            fill.execution.price, filled, avg_price,
        )

    def _on_commission_report(self, trade, fill, report):
        order_id = trade.order.orderId
        commission = float(report.commission or 0)
        currency = report.currency or ""
        realized_pnl = float(report.realizedPNL or 0)
        logger.info(
            "[IBKR-Event] commissionReport: orderId=%s execId=%s commission=%.4f currency=%s realizedPNL=%.2f",
            order_id, fill.execution.execId,
            commission, currency, realized_pnl,
        )

        ctx = self._commission_contexts.get(order_id)
        if ctx and ctx.strategy_id and commission > 0:
            strategy_id = ctx.strategy_id
            symbol = ctx.symbol
            signal_type = ctx.signal_type

            def _do_update():
                from app.services.live_trading import records
                records.update_trade_commission(
                    strategy_id=strategy_id,
                    symbol=symbol,
                    trade_type=signal_type,
                    commission=commission,
                    commission_ccy=currency,
                )
                logger.info("[IBKR-Commission] Updated commission for strategy=%s symbol=%s", strategy_id, symbol)

            self._submit_with_retry(
                _do_update,
                is_blocking=True,
                max_retries=3,
                retry_delay=1.0,
            )

    def _on_error(self, reqId, errorCode, errorString, contract):
        sym = getattr(contract, "symbol", "") if contract else ""
        logger.warning(
            "[IBKR-Event] error: reqId=%s code=%s msg=%s contract=%s",
            reqId, errorCode, errorString, sym,
        )

    # ── event callbacks: connection lifecycle ─────────────────────

    def _on_connected(self):
        logger.info("[IBKR-Event] connectedEvent — connection established")

    def _on_disconnected(self):
        logger.warning("[IBKR-Event] disconnectedEvent — connection lost")
        self._events_registered = False
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        if self._reconnect_stop.is_set():
            return
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop, daemon=True, name="ibkr-reconnect",
        )
        self._reconnect_thread.start()

    def _reconnect_loop(self):
        for attempt, delay in enumerate(self._RECONNECT_DELAYS, 1):
            if self._reconnect_stop.is_set():
                return
            logger.info(
                "[IBKR-Reconnect] attempt %d/%d in %ds",
                attempt, len(self._RECONNECT_DELAYS), delay,
            )
            if self._reconnect_stop.wait(timeout=delay):
                return
            try:
                result = self._tq.submit(self._do_connect_coro(), is_blocking=False).result(timeout=30)
                if result:
                    logger.info("[IBKR-Reconnect] reconnected successfully")
                    return
            except Exception as e:
                logger.warning("[IBKR-Reconnect] attempt %d failed: %s", attempt, e)

        logger.error(
            "[IBKR-Reconnect] all %d attempts exhausted, giving up",
            len(self._RECONNECT_DELAYS),
        )

    # ── event callbacks: observation (INFO) ───────────────────────

    def _on_new_order(self, trade):
        logger.info(
            "[IBKR-Event] newOrder: orderId=%s symbol=%s action=%s qty=%s type=%s tif=%s",
            trade.order.orderId, trade.contract.symbol,
            trade.order.action, trade.order.totalQuantity,
            trade.order.orderType, getattr(trade.order, "tif", ""),
        )

    def _on_order_modify(self, trade):
        logger.info(
            "[IBKR-Event] orderModify: orderId=%s symbol=%s status=%s",
            trade.order.orderId, trade.contract.symbol, trade.orderStatus.status,
        )

    def _on_cancel_order(self, trade):
        logger.info(
            "[IBKR-Event] cancelOrder: orderId=%s symbol=%s status=%s filled=%s",
            trade.order.orderId, trade.contract.symbol,
            trade.orderStatus.status, trade.orderStatus.filled,
        )

    def _on_open_order(self, trade):
        logger.info(
            "[IBKR-Event] openOrder: orderId=%s symbol=%s action=%s status=%s",
            trade.order.orderId, trade.contract.symbol,
            trade.order.action, trade.orderStatus.status,
        )

    def _on_update_portfolio(self, item):
        unrealized_pnl = float(item.unrealizedPNL or 0)
        realized_pnl = float(item.realizedPNL or 0)
        value = float(item.marketValue or 0)
        contract = item.contract
        label = _contract_symbol_label(contract)

        logger.info(
            "[IBKR-Event] updatePortfolio: symbol=%s pos=%s mktPrice=%.2f mktValue=%.2f unrealPNL=%.2f realPNL=%.2f",
            label, item.position,
            float(item.marketPrice or 0), value,
            unrealized_pnl, realized_pnl,
        )

        self._conid_to_symbol[contract.conId] = label

        def _save_to_db():
            for attempt in range(3):
                if records.ibkr_save_position(
                    account=item.account,
                    con_id=contract.conId,
                    symbol=label,
                    sec_type=_contract_str_field(getattr(contract, "secType", None)),
                    exchange=_contract_str_field(getattr(contract, "exchange", None)),
                    currency=_contract_str_field(getattr(contract, "currency", None)),
                    position=float(item.position or 0),
                    avg_cost=float(item.averageCost or 0),
                    daily_pnl=0.0,
                    unrealized_pnl=unrealized_pnl,
                    realized_pnl=realized_pnl,
                    value=value,
                ):
                    return
                if attempt < 2:
                    logger.warning("[IBKR-Event] Retry save updatePortfolio to DB (attempt %d/3)", attempt + 1)
                    time.sleep(0.5 * (attempt + 1))
            logger.error("[IBKR-Event] Failed to save updatePortfolio to DB after 3 attempts")

        self._fire_submit(_save_to_db, is_blocking=True)

    def _on_position(self, position):
        contract = position.contract
        label = _contract_symbol_label(contract)
        con_id = contract.conId
        account = position.account
        pos = float(position.position or 0)
        avg_cost = float(position.avgCost or 0)

        logger.info(
            "[IBKR-Event] position: account=%s symbol=%s pos=%s avgCost=%.4f",
            account, label, pos, avg_cost,
        )

        self._conid_to_symbol[con_id] = label

        def _save_to_db():
            for attempt in range(3):
                if records.ibkr_save_position(
                    account=account,
                    con_id=con_id,
                    symbol=label,
                    sec_type=_contract_str_field(getattr(contract, "secType", None)),
                    exchange=_contract_str_field(getattr(contract, "exchange", None)),
                    currency=_contract_str_field(getattr(contract, "currency", None)),
                    position=pos,
                    avg_cost=avg_cost,
                ):
                    return
                if attempt < 2:
                    logger.warning("[IBKR-Event] Retry save position to DB (attempt %d/3)", attempt + 1)
                    time.sleep(0.5 * (attempt + 1))
            logger.error("[IBKR-Event] Failed to save position to DB after 3 attempts")

        self._fire_submit(_save_to_db, is_blocking=True)

        if con_id in self._subscribed_conids:
            logger.debug("[IBKR-Event] conId=%s already subscribed, skipping reqPnLSingle", con_id)
            return

        def _subscribe_pnl_single():
            try:
                self._ib.cancelPnLSingle(account, "", con_id)
            except Exception:
                pass
            try:
                self._ib.reqPnLSingle(account, "", con_id)
                self._subscribed_conids.add(con_id)
                logger.debug("[IBKR-Event] reqPnLSingle: account=%s conId=%s", account, con_id)
            except Exception as e:
                logger.error("[IBKR-Event] Failed to reqPnLSingle: %s", e)

        self._fire_submit(_subscribe_pnl_single, is_blocking=False)

    def _on_tick_news(self, news):
        logger.info(
            "[IBKR-Event] tickNews: time=%s providerCode=%s articleId=%s headline=%s",
            news.timeStamp, news.providerCode, news.articleId,
            (news.headline or "")[:120],
        )

    def _on_news_bulletin(self, bulletin):
        logger.info(
            "[IBKR-Event] newsBulletin: msgId=%s msgType=%s message=%s",
            bulletin.msgId, bulletin.msgType, (bulletin.message or "")[:200],
        )

    def _on_wsh_meta(self, dataJson):
        logger.info("[IBKR-Event] wshMeta: %s", (dataJson or "")[:200])

    def _on_wsh(self, dataJson):
        logger.info("[IBKR-Event] wsh: %s", (dataJson or "")[:200])

    def _on_timeout(self, idlePeriod):
        logger.info("[IBKR-Event] timeout: no data for %.1f seconds", idlePeriod)

    # ── event callbacks: observation (DEBUG, high-frequency) ──────

    def _on_pnl(self, entry):
        def _safe_float(val):
            if val is None:
                return 0.0
            try:
                f = float(val)
                if math.isnan(f) or math.isinf(f):
                    return 0.0
                return f
            except (ValueError, TypeError):
                return 0.0

        daily_pnl = _safe_float(entry.dailyPnL)
        unrealized_pnl = _safe_float(entry.unrealizedPnL)
        realized_pnl = _safe_float(entry.realizedPnL)

        logger.debug(
            "[IBKR-Event] pnl: dailyPnL=%.2f unrealizedPnL=%.2f realizedPnL=%.2f",
            daily_pnl, unrealized_pnl, realized_pnl,
        )

        def _save_to_db():
            for attempt in range(3):
                if records.ibkr_save_pnl(
                    account=entry.account,
                    daily_pnl=daily_pnl,
                    unrealized_pnl=unrealized_pnl,
                    realized_pnl=realized_pnl,
                ):
                    return
                if attempt < 2:
                    logger.warning("[IBKR-Event] Retry save pnl to DB (attempt %d/3)", attempt + 1)
                    time.sleep(0.5 * (attempt + 1))
            logger.error("[IBKR-Event] Failed to save pnl to DB after 3 attempts")

        self._fire_submit(_save_to_db, is_blocking=True)

    def _on_pnl_single(self, entry):
        def _safe_float(val):
            if val is None:
                return 0.0
            try:
                f = float(val)
                if math.isnan(f) or math.isinf(f):
                    return 0.0
                return f
            except (ValueError, TypeError):
                return 0.0

        daily_pnl = _safe_float(entry.dailyPnL)
        unrealized_pnl = _safe_float(entry.unrealizedPnL)
        realized_pnl = _safe_float(entry.realizedPnL)
        position = _safe_float(entry.position)
        value = _safe_float(entry.value)

        logger.debug(
            "[IBKR-Event] pnlSingle: conId=%s dailyPnL=%.2f unrealizedPnL=%.2f realizedPnL=%.2f pos=%s value=%.2f",
            entry.conId, daily_pnl, unrealized_pnl, realized_pnl, position, value,
        )

        symbol = self._conid_to_symbol.get(entry.conId, "")

        def _save_to_db():
            for attempt in range(3):
                if records.ibkr_save_position(
                    account=entry.account,
                    con_id=entry.conId,
                    symbol=symbol,
                    position=position,
                    avg_cost=value / position if position != 0 else 0.0,
                    daily_pnl=daily_pnl,
                    unrealized_pnl=unrealized_pnl,
                    realized_pnl=realized_pnl,
                    value=value,
                ):
                    return
                if attempt < 2:
                    logger.warning("[IBKR-Event] Retry save pnl_single to DB (attempt %d/3)", attempt + 1)
                    time.sleep(0.5 * (attempt + 1))
            logger.error("[IBKR-Event] Failed to save pnl_single to DB after 3 attempts")

        self._fire_submit(_save_to_db, is_blocking=True)

    def _on_account_value(self, value):
        logger.debug(
            "[IBKR-Event] accountValue: tag=%s value=%s currency=%s account=%s",
            value.tag, value.value, value.currency, value.account,
        )

    def _on_account_summary(self, value):
        logger.debug(
            "[IBKR-Event] accountSummary: tag=%s value=%s currency=%s account=%s",
            value.tag, value.value, value.currency, value.account,
        )

    def _on_pending_tickers(self, tickers):
        logger.debug("[IBKR-Event] pendingTickers: %d tickers updated", len(tickers))

    def _on_bar_update(self, bars, hasNewBar):
        logger.debug(
            "[IBKR-Event] barUpdate: symbol=%s bars=%d hasNewBar=%s",
            getattr(bars.contract, "symbol", "?") if hasattr(bars, "contract") else "?",
            len(bars), hasNewBar,
        )

    def _on_scanner_data(self, data):
        logger.debug("[IBKR-Event] scannerData: %d items", len(data))

    def _on_update(self):
        pass

    # ── contract helpers ───────────────────────────────────────────

    def _create_contract(self, symbol: str, market_type: str):
        _ensure_ib_insync()
        ib_symbol, exchange, currency = normalize_symbol(symbol, market_type)
        if market_type == "Forex":
            return ib_insync.Forex(pair=ib_symbol)
        elif market_type == "Metals":
            return ib_insync.Contract(
                symbol=ib_symbol,
                secType="CMDTY",
                exchange=exchange,
                currency=currency,
            )
        elif market_type in ("USStock", "HShare"):
            return ib_insync.Stock(symbol=ib_symbol, exchange=exchange, currency=currency)
        else:
            raise ValueError(f"Unsupported market_type: {market_type}")

    def _qualify_ttl_seconds(self, market_type: str) -> int:
        if market_type in ("Forex", "Metals"):
            # Metals shares Forex TTL env (paper-validated CMDTY qualify cache).
            return int(os.environ.get("IBKR_QUALIFY_TTL_FOREX_SEC", "600"))
        if market_type == "USStock":
            return int(os.environ.get("IBKR_QUALIFY_TTL_USSTOCK_SEC", "600"))
        if market_type == "HShare":
            return int(os.environ.get("IBKR_QUALIFY_TTL_HSHARE_SEC", "600"))
        return 600

    def _invalidate_qualify_cache(self, symbol: str, market_type: str) -> None:
        self._qualify_cache.pop((symbol, market_type), None)

    @staticmethod
    def _qualify_snapshot_from_contract(contract) -> Dict[str, Any]:
        snap: Dict[str, Any] = {}
        for attr in ("conId", "secType", "localSymbol", "exchange", "currency", "tradingClass"):
            if hasattr(contract, attr):
                snap[attr] = getattr(contract, attr, None)
        return snap

    @staticmethod
    def _qualify_apply_snapshot_to_contract(contract, snapshot: Dict[str, Any]) -> None:
        for attr, val in snapshot.items():
            if val is not None:
                setattr(contract, attr, val)

    async def _qualify_contract_async(self, contract, symbol: str, market_type: str) -> bool:
        key = (symbol, market_type)
        ttl = self._qualify_ttl_seconds(market_type)
        now = time.monotonic()
        entry = self._qualify_cache.get(key)
        if entry and now < float(entry.get("expires_at", 0)):
            self._qualify_apply_snapshot_to_contract(contract, entry.get("snapshot") or {})
            return True

        if key in self._qualify_cache:
            self._qualify_cache.pop(key, None)

        try:
            qualified = await self._ib.qualifyContractsAsync(contract)
        except Exception as e:
            logger.warning("Contract qualification failed: %s", e)
            self._invalidate_qualify_cache(symbol, market_type)
            return False

        if len(qualified) == 0:
            self._invalidate_qualify_cache(symbol, market_type)
            return False

        snapshot = self._qualify_snapshot_from_contract(contract)
        self._qualify_cache[key] = {
            "expires_at": time.monotonic() + float(ttl),
            "snapshot": snapshot,
        }
        return True

    _EXPECTED_SEC_TYPES = {
        "Forex": "CASH",
        "USStock": "STK",
        "HShare": "STK",
        "Metals": "CMDTY",
    }

    def _validate_qualified_contract(self, contract, market_type: str) -> tuple:
        con_id = getattr(contract, "conId", 0) or 0
        if con_id == 0:
            return (False, f"conId is 0 after qualification for {market_type} contract")
        expected = self._EXPECTED_SEC_TYPES.get(market_type)
        if expected and contract.secType != expected:
            return (False, f"Expected secType={expected} for {market_type}, got {contract.secType}")
        return (True, "")

    _lot_size_cache: Dict[int, float] = {}
    _mintick_cache: Dict[int, float] = {}

    async def _contract_increment_and_mintick(
        self, contract, symbol: str, *, need_mintick: bool = False,
    ) -> Tuple[Optional[float], Optional[float]]:
        """Single ``reqContractDetailsAsync`` path: lot increment and optional minTick (cached per conId)."""
        con_id = getattr(contract, "conId", 0) or 0
        cached_inc = self._lot_size_cache.get(con_id) if con_id else None
        cached_mt = self._mintick_cache.get(con_id) if con_id else None

        if cached_inc and cached_inc > 0:
            if not need_mintick:
                return cached_inc, None
            if cached_mt and cached_mt > 0:
                return cached_inc, cached_mt

        try:
            details_list = await self._ib.reqContractDetailsAsync(contract)
            if not details_list:
                return (cached_inc if cached_inc and cached_inc > 0 else None), None
            d = details_list[0]

            def _detail_float(name: str) -> float:
                try:
                    v = float(getattr(d, name, 0) or 0)
                    if math.isnan(v) or math.isinf(v):
                        return 0.0
                    return v
                except (TypeError, ValueError):
                    return 0.0

            increment = _detail_float("sizeIncrement")
            if increment <= 0:
                increment = _detail_float("minSize")
            min_tick = _detail_float("minTick")
            if increment > 0 and con_id:
                self._lot_size_cache[con_id] = increment
            if min_tick > 0 and con_id:
                self._mintick_cache[con_id] = min_tick
            inc_out = increment if increment > 0 else (cached_inc if cached_inc and cached_inc > 0 else None)
            mt_out = min_tick if min_tick > 0 else (cached_mt if cached_mt and cached_mt > 0 else None)
            return inc_out, mt_out
        except Exception as e:
            logger.warning("[IBKR] reqContractDetails failed for %s: %s", symbol, e)
            return (cached_inc if cached_inc and cached_inc > 0 else None), (
                cached_mt if cached_mt and cached_mt > 0 else None
            )

    async def _align_qty_to_contract(self, contract, quantity: float, symbol: str) -> float:
        """Query IBKR ContractDetails for sizeIncrement and floor-align quantity."""
        increment, _ = await self._contract_increment_and_mintick(
            contract, symbol, need_mintick=False,
        )

        if not increment or increment <= 0:
            return quantity

        aligned = math.floor(quantity / increment) * increment
        if aligned != quantity:
            logger.info(
                "[IBKR] Quantity aligned to contract sizeIncrement: %.2f -> %.0f (increment=%s, symbol=%s)",
                quantity, aligned, increment, symbol,
            )
        return aligned

    @staticmethod
    def _snap_limit_price_to_mintick(side: str, raw: float, min_tick: float) -> float:
        """BUY: floor to tick; SELL: ceil to tick."""
        s = (side or "").lower()
        if s == "buy":
            return math.floor(raw / min_tick) * min_tick
        return math.ceil(raw / min_tick) * min_tick

    # ── fire-and-forget order handlers ──────────────────────────────

    def _handle_fill(self, ctx: IBKROrderContext, filled: float, avg_price: float):
        """Process a fill event — runs in IO thread pool, never blocks event loop."""
        from app.services.live_trading import records

        logger.info(
            "[IBKR-Fill] orderId=%s pending=%s strategy=%s filled=%.2f avg=%.4f",
            ctx.order_id, ctx.pending_order_id, ctx.strategy_id, filled, avg_price,
        )

        if ctx.pending_order_id:
            if records.has_trade_for_pending_order(ctx.pending_order_id):
                logger.warning(
                    "[IBKR-Fill] DUPLICATE skipped: trade already exists for pending_order_id=%s",
                    ctx.pending_order_id,
                )
                return

            try:
                records.mark_order_sent(
                    order_id=ctx.pending_order_id,
                    note="ibkr_filled",
                    exchange_id=self.engine_id,
                    exchange_order_id=str(ctx.order_id),
                    exchange_response_json=json.dumps({
                        "orderId": ctx.order_id, "status": "Filled",
                        "filled": filled, "avgPrice": avg_price,
                    }),
                    filled=filled,
                    avg_price=avg_price,
                    executed_at=int(time.time()),
                )
            except Exception as e:
                logger.warning("[IBKR-Fill] mark_order_sent failed: %s", e)

        if ctx.strategy_id and filled > 0 and avg_price > 0:
            try:
                profit, _pos = records.apply_fill_to_local_position(
                    strategy_id=ctx.strategy_id,
                    symbol=ctx.symbol,
                    signal_type=ctx.signal_type,
                    filled=filled,
                    avg_price=avg_price,
                )
                records.record_trade(
                    strategy_id=ctx.strategy_id,
                    symbol=ctx.symbol,
                    trade_type=ctx.signal_type,
                    price=avg_price,
                    amount=filled,
                    commission=0.0,
                    commission_ccy="",
                    profit=profit,
                    pending_order_id=ctx.pending_order_id,
                )
            except Exception as e:
                logger.warning("[IBKR-Fill] record_trade/position failed: %s", e)

        self._notify_order_event(ctx, "filled", filled=filled, avg_price=avg_price)

    def _handle_reject(self, ctx: IBKROrderContext, status: str, error_msgs: List[str]):
        """Process a rejection event — runs in IO thread pool."""
        from app.services.live_trading import records

        error_str = "; ".join(error_msgs) if error_msgs else f"Order {status}"
        logger.warning(
            "[IBKR-Reject] orderId=%s pending=%s strategy=%s status=%s error=%s",
            ctx.order_id, ctx.pending_order_id, ctx.strategy_id, status, error_str,
        )

        if ctx.pending_order_id:
            try:
                records.mark_order_failed(
                    order_id=ctx.pending_order_id,
                    error=f"ibkr_{status}:{error_str}",
                    strategy_id=ctx.strategy_id,
                    symbol=ctx.symbol,
                    signal_type=ctx.signal_type,
                )
            except Exception as e:
                logger.warning("[IBKR-Reject] mark_order_failed failed: %s", e)

        self._notify_order_event(ctx, "failed", error=error_str)

    def _notify_order_event(
        self, ctx: IBKROrderContext, status: str, *,
        filled: float = 0.0, avg_price: float = 0.0, error: str = "",
    ):
        """Send notification for order event (best-effort)."""
        try:
            notification_config = ctx.notification_config
            if not notification_config and ctx.strategy_id:
                from app.services.live_trading import records
                notification_config = records.load_notification_config(ctx.strategy_id)
            if not notification_config:
                return

            strategy_name = ctx.strategy_name
            if not strategy_name and ctx.strategy_id:
                from app.services.live_trading import records
                strategy_name = records.load_strategy_name(ctx.strategy_id) or f"Strategy_{ctx.strategy_id}"

            from app.services.notification import send_notification
            send_notification(
                notification_config=notification_config,
                strategy_name=strategy_name,
                symbol=ctx.symbol,
                signal_type=ctx.signal_type,
                price=avg_price,
                amount=filled if filled > 0 else ctx.amount,
                mode="live",
                status=status,
                error=error,
                extra={
                    "pending_order_id": ctx.pending_order_id,
                    "exchange_id": self.engine_id,
                    "exchange_order_id": str(ctx.order_id),
                    "market_category": ctx.market_category,
                    "filled_price": avg_price,
                    "filled_amount": filled,
                },
            )
        except Exception as e:
            logger.debug("[IBKR-Notify] notification failed: %s", e)

    # ── RTH check ──────────────────────────────────────────────────

    _RTH_QUALIFY_RETRIES = 2
    _rth_details_cache: dict = {}  # (conId, date_str) -> ContractDetails

    def is_market_open(self, symbol: str, market_type: str = "USStock"):
        import asyncio as _aio
        import pytz as _pytz

        async def _task():
            from app.services.live_trading.ibkr_trading.trading_hours import is_rth_check
            await self._ensure_connected_async()
            _ensure_ib_insync()
            contract = self._create_contract(symbol, market_type)

            qualified = False
            for attempt in range(1, self._RTH_QUALIFY_RETRIES + 1):
                if await self._qualify_contract_async(contract, symbol, market_type):
                    qualified = True
                    break
                if attempt < self._RTH_QUALIFY_RETRIES:
                    logger.info(
                        "[RTH] contract qualify attempt %d/%d failed for %s, retrying",
                        attempt, self._RTH_QUALIFY_RETRIES, symbol,
                    )
                    await _aio.sleep(1)

            if not qualified:
                logger.warning(
                    "[RTH] contract qualification failed for %s (%s) after %d attempts, "
                    "blocking order as safety measure",
                    symbol, market_type, self._RTH_QUALIFY_RETRIES,
                )
                return False, f"Invalid {market_type} contract: {symbol}"

            valid, reason = self._validate_qualified_contract(contract, market_type)
            if not valid:
                logger.warning("[RTH] post-qualify validation failed for %s: %s", symbol, reason)
                self._invalidate_qualify_cache(symbol, market_type)
                return False, reason

            server_time = await self._ib.reqCurrentTimeAsync()
            if server_time.tzinfo is None:
                server_time = server_time.replace(tzinfo=_pytz.UTC)

            con_id = getattr(contract, "conId", 0) or 0
            cache_key = (con_id, server_time.date().isoformat())
            details = self._rth_details_cache.get(cache_key)

            if details is None:
                details_list = await self._ib.reqContractDetailsAsync(contract)
                if not details_list:
                    logger.warning("[RTH] no contract details for %s, fail-closed", symbol)
                    return False, f"{symbol} contract details not found"
                details = details_list[0]
                self._rth_details_cache[cache_key] = details

            sym = getattr(contract, "symbol", symbol)
            if not is_rth_check(details, server_time, con_id=con_id, symbol=sym):
                reason = f"{sym} is outside RTH (market closed)"
                if market_type == "Forex":
                    reason += (
                        " — Forex 24/5: closed outside liquid hours (weekend or "
                        "daily maintenance window)."
                    )
                elif market_type == "Metals":
                    reason += (
                        " — precious metals (CMDTY/SMART): often closed outside "
                        "liquid hours (weekends/session breaks; not Forex 24/5 IDEALPRO)."
                    )
                return False, reason
            return True, ""

        try:
            return self._submit(_task(), timeout=30.0)
        except Exception as e:
            logger.error(
                "[RTH] is_market_open failed for %s (%s): %s, "
                "blocking order as safety measure (fail-closed)",
                symbol, market_type, e,
            )
            return False, f"RTH check failed: {e}"

    # ── order execution ────────────────────────────────────────────

    def place_market_order(
        self, symbol: str, side: str, quantity: float,
        market_type: str = "USStock", **kwargs,
    ) -> LiveOrderResult:
        from app.services.live_trading.order_normalizer import get_market_pre_normalizer

        n = get_market_pre_normalizer(market_type)
        qty = n.pre_normalize(quantity, symbol)
        ok, reason = n.pre_check(qty, symbol)
        if not ok:
            return LiveOrderResult(success=False, message=reason, exchange_id=self.engine_id)

        signal_type = str(kwargs.get("signal_type", ""))
        tif = self._get_tif_for_signal(signal_type, market_type, order_type="market")

        async def _do():
            await self._ensure_connected_async()
            _ensure_ib_insync()
            contract = self._create_contract(symbol, market_type)
            if not await self._qualify_contract_async(contract, symbol, market_type):
                return LiveOrderResult(success=False, message=f"Invalid {market_type} contract: {symbol}",
                                   exchange_id=self.engine_id)

            valid, reason = self._validate_qualified_contract(contract, market_type)
            if not valid:
                self._invalidate_qualify_cache(symbol, market_type)
                return LiveOrderResult(success=False, message=reason,
                                   exchange_id=self.engine_id)

            aligned = await self._align_qty_to_contract(contract, qty, symbol)
            if aligned <= 0:
                msg = (
                    f"Quantity {aligned} rounds to 0 after lot-size alignment for {symbol}"
                )
                if market_type == "Forex":
                    msg += (
                        " For Forex (IDEALPRO), the amount may be below the minimum "
                        "tradable size for this pair."
                    )
                elif market_type == "Metals":
                    msg += (
                        " For precious metals (CMDTY on SMART), each contract is in "
                        "troy ounces; typical sizeIncrement=1.0 and minSize=1.0. "
                        "Approximate USD notionals per 1 troy ounce (not live quotes): "
                        "XAUUSD ~3200; XAGUSD ~32."
                    )
                return LiveOrderResult(
                    success=False,
                    message=msg,
                    exchange_id=self.engine_id,
                )

            order = ib_insync.MarketOrder(
                action="BUY" if side.lower() == "buy" else "SELL",
                totalQuantity=aligned, account=self._account,
                tif=tif,
            )
            trade = self._ib.placeOrder(contract, order)
            oid = trade.order.orderId

            self._order_contexts[oid] = IBKROrderContext(
                order_id=oid,
                pending_order_id=int(kwargs.get("pending_order_id") or 0),
                strategy_id=int(kwargs.get("strategy_id") or 0),
                symbol=symbol,
                signal_type=str(kwargs.get("signal_type") or ""),
                amount=aligned,
                market_type=market_type,
                payload=kwargs.get("payload") or {},
                order_row=kwargs.get("order_row") or {},
                notification_config=kwargs.get("notification_config") or {},
                strategy_name=str(kwargs.get("strategy_name") or ""),
                market_category=str(kwargs.get("market_category") or ""),
            )

            return LiveOrderResult(
                success=True,
                order_id=oid,
                status="Submitted",
                exchange_id=self.engine_id,
                message="Order submitted (fire-and-forget)",
            )

        try:
            return self._submit(_do(), timeout=15.0)
        except Exception as e:
            logger.error("Order failed: %s", e)
            return LiveOrderResult(success=False, message=str(e), exchange_id=self.engine_id)

    def place_limit_order(
        self, symbol: str, side: str, quantity: float, price: float,
        market_type: str = "USStock",
        time_in_force: Optional[str] = None,
        **kwargs,
    ) -> LiveOrderResult:
        from app.services.live_trading.order_normalizer import get_market_pre_normalizer

        n = get_market_pre_normalizer(market_type)
        qty = n.pre_normalize(quantity, symbol)
        ok, reason = n.pre_check(qty, symbol)
        if not ok:
            return LiveOrderResult(success=False, message=reason, exchange_id=self.engine_id)

        signal_type = str(kwargs.get("signal_type", ""))
        if time_in_force is None:
            tif = self._get_tif_for_signal(signal_type, market_type, order_type="limit")
        else:
            u = (time_in_force or "").strip().upper()
            allowed = ("IOC", "DAY", "GTC")
            if u not in allowed:
                return LiveOrderResult(
                    success=False,
                    message=f"invalid_time_in_force:{time_in_force!r} (allowed: {', '.join(allowed)})",
                    exchange_id=self.engine_id,
                )
            tif = u

        async def _do():
            await self._ensure_connected_async()
            _ensure_ib_insync()
            contract = self._create_contract(symbol, market_type)
            if not await self._qualify_contract_async(contract, symbol, market_type):
                return LiveOrderResult(success=False, message=f"Invalid {market_type} contract: {symbol}",
                                   exchange_id=self.engine_id)

            valid, reason = self._validate_qualified_contract(contract, market_type)
            if not valid:
                self._invalidate_qualify_cache(symbol, market_type)
                return LiveOrderResult(success=False, message=reason,
                                   exchange_id=self.engine_id)

            increment, min_tick = await self._contract_increment_and_mintick(
                contract, symbol, need_mintick=True,
            )
            aligned = qty
            if increment and increment > 0:
                aligned = math.floor(qty / increment) * increment
                if aligned != qty:
                    logger.info(
                        "[IBKR] Quantity aligned to contract sizeIncrement: %.2f -> %.0f (increment=%s, symbol=%s)",
                        qty, aligned, increment, symbol,
                    )
            if aligned <= 0:
                msg = (
                    f"Quantity {aligned} rounds to 0 after lot-size alignment for {symbol}"
                )
                if market_type == "Forex":
                    msg += (
                        " For Forex (IDEALPRO), the amount may be below the minimum "
                        "tradable size for this pair."
                    )
                elif market_type == "Metals":
                    msg += (
                        " For precious metals (CMDTY on SMART), each contract is in "
                        "troy ounces; typical sizeIncrement=1.0 and minSize=1.0. "
                        "Approximate USD notionals per 1 troy ounce (not live quotes): "
                        "XAUUSD ~3200; XAGUSD ~32."
                    )
                return LiveOrderResult(
                    success=False,
                    message=msg,
                    exchange_id=self.engine_id,
                )

            snap_price = float(price)
            if min_tick and min_tick > 0:
                snap_price = self._snap_limit_price_to_mintick(side, snap_price, min_tick)
            else:
                logger.warning(
                    "[IBKR] minTick missing or invalid for %s; limit price not snapped to tick grid",
                    symbol,
                )

            if snap_price <= 0:
                return LiveOrderResult(
                    success=False,
                    message=f"Limit price after minTick alignment is non-positive for {symbol}",
                    exchange_id=self.engine_id,
                )

            order = ib_insync.LimitOrder(
                action="BUY" if side.lower() == "buy" else "SELL",
                totalQuantity=aligned, lmtPrice=snap_price, account=self._account,
                tif=tif,
            )
            trade = self._ib.placeOrder(contract, order)
            oid = trade.order.orderId

            self._order_contexts[oid] = IBKROrderContext(
                order_id=oid,
                pending_order_id=int(kwargs.get("pending_order_id") or 0),
                strategy_id=int(kwargs.get("strategy_id") or 0),
                symbol=symbol,
                signal_type=str(kwargs.get("signal_type") or ""),
                amount=aligned,
                market_type=market_type,
                payload=kwargs.get("payload") or {},
                order_row=kwargs.get("order_row") or {},
                notification_config=kwargs.get("notification_config") or {},
                strategy_name=str(kwargs.get("strategy_name") or ""),
                market_category=str(kwargs.get("market_category") or ""),
            )

            return LiveOrderResult(
                success=True,
                order_id=oid,
                status="Submitted",
                exchange_id=self.engine_id,
                message="Limit order submitted (fire-and-forget)",
            )

        try:
            return self._submit(_do(), timeout=15.0)
        except Exception as e:
            logger.error("Limit order failed: %s", e)
            return LiveOrderResult(success=False, message=str(e), exchange_id=self.engine_id)

    def cancel_order(self, order_id: int) -> bool:
        async def _do():
            await self._ensure_connected_async()
            for trade in self._ib.openTrades():
                if trade.order.orderId == order_id:
                    self._ib.cancelOrder(trade.order)
                    logger.info("Order %s cancelled", order_id)
                    return True
            logger.warning("Order not found: %s", order_id)
            return False

        try:
            return self._submit(_do(), timeout=15.0)
        except Exception as e:
            logger.error("Cancel order failed: %s", e)
            return False

    # ── query ──────────────────────────────────────────────────────

    def get_account_summary(self) -> Dict[str, Any]:
        async def _task():
            await self._ensure_connected_async()
            summary = await self._ib.accountSummaryAsync(self._account)
            result = {}
            for item in summary:
                result[item.tag] = {"value": item.value, "currency": item.currency}
            return {"account": self._account, "summary": result, "success": True}

        try:
            return self._submit(_task(), timeout=15.0)
        except Exception as e:
            logger.error("Get account summary failed: %s", e)
            return {"success": False, "error": str(e)}

    def get_pnl(self) -> Dict[str, Any]:
        if not self.connected:
            logger.warning("[IBKR] get_pnl called but not connected")
            return None

        account = self._account
        if not account:
            logger.warning("[IBKR] get_pnl called but no account configured")
            return None

        def _query():
            return records.ibkr_get_pnl(account)

        try:
            row = self._submit(_query, timeout=15.0)
            if row:
                updated_at = row.get("updated_at")
                return {
                    "success": True,
                    "dailyPnL": float(row.get("daily_pnl") or 0),
                    "unrealizedPnL": float(row.get("unrealized_pnl") or 0),
                    "realizedPnL": float(row.get("realized_pnl") or 0),
                    "updatedAt": updated_at.isoformat() if updated_at else None,
                }
            logger.warning("[IBKR] No PnL data found in DB for account: %s", account)
            return None
        except Exception as e:
            logger.error("[IBKR] Failed to get PnL from DB: %s", e)
            return None

    def get_positions(self) -> List[Dict[str, Any]]:
        if not self.connected:
            logger.warning("[IBKR] get_positions called but not connected")
            return []

        account = self._account
        if not account:
            logger.warning("[IBKR] get_positions called but no account configured")
            return []

        def _query():
            return records.ibkr_get_positions(account)

        try:
            rows = self._submit(_query, timeout=15.0)
            result = []
            for row in rows:
                unrealized_pnl = float(row.get("unrealized_pnl") or 0)
                market_value = float(row.get("value") or 0)
                position = float(row.get("position") or 0)
                avg_cost = float(row.get("avg_cost") or 0)
                if market_value == 0.0:
                    market_value = position * avg_cost

                st_raw = (row.get("sec_type") or "").strip()
                ex_raw = (row.get("exchange") or "").strip()
                cc_raw = (row.get("currency") or "").strip()

                result.append({
                    "symbol": row.get("symbol") or "",
                    "ib_symbol": row.get("symbol") or "",
                    "secType": st_raw or "STK",
                    "exchange": ex_raw or "SMART",
                    "currency": cc_raw or "USD",
                    "quantity": position,
                    "avgCost": avg_cost,
                    "marketValue": market_value,
                    "unrealizedPnL": unrealized_pnl,
                    "dailyPnL": float(row.get("daily_pnl") or 0),
                })
            return result
        except Exception as e:
            logger.error("[IBKR] Failed to get positions from DB: %s", e)
            return []

    def get_positions_normalized(self):
        from app.services.live_trading.base import PositionRecord
        position_records = []
        for p in self.get_positions():
            qty = float(p.get("quantity") or 0)
            if abs(qty) <= 0:
                continue
            position_records.append(PositionRecord(
                symbol=str(p.get("symbol") or ""),
                side="long" if qty > 0 else "short",
                quantity=abs(qty),
                entry_price=float(p.get("avgCost") or 0),
                raw=p,
            ))
        return position_records

    def get_open_orders(self) -> List[Dict[str, Any]]:
        async def _task():
            await self._ensure_connected_async()
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
            return self._submit(_task(), timeout=15.0)
        except Exception as e:
            logger.error("Get orders failed: %s", e)
            return []

    def get_quote(self, symbol: str, market_type: str = "USStock") -> Dict[str, Any]:
        import asyncio as _aio

        async def _task():
            await self._ensure_connected_async()
            contract = self._create_contract(symbol, market_type)
            if not await self._qualify_contract_async(contract, symbol, market_type):
                return {"success": False, "error": f"Invalid {market_type} contract: {symbol}"}

            valid, reason = self._validate_qualified_contract(contract, market_type)
            if not valid:
                self._invalidate_qualify_cache(symbol, market_type)
                return {"success": False, "error": reason}
            ticker = self._ib.reqMktData(contract, "", False, False)
            await _aio.sleep(2)
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
            return self._submit(_task(), timeout=15.0)
        except Exception as e:
            logger.error("Get quote failed: %s", e)
            return {"success": False, "error": str(e)}

    def get_connection_status(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "engine_id": self.engine_id,
            "host": self.config.host,
            "port": self.config.port,
            "clientId": self.config.client_id,
            "account": self._account,
            "readonly": self.config.readonly,
        }

    def shutdown(self):
        self._tq.shutdown()


# ── Global singleton ──────────────────────────────────────────────

_global_paper_client: Optional[IBKRClient] = None
_global_live_client: Optional[IBKRClient] = None
_paper_lock = threading.Lock()
_live_lock = threading.Lock()


def get_ibkr_client(config: Optional[IBKRConfig] = None, mode: str = "paper") -> IBKRClient:
    global _global_paper_client, _global_live_client

    if mode == "live":
        with _live_lock:
            if _global_live_client is None:
                cfg = config or IBKRConfig.from_env("live")
                _global_live_client = IBKRClient(cfg, mode="live")
            if not _global_live_client.connected:
                _global_live_client.connect()
            return _global_live_client
    else:
        with _paper_lock:
            if _global_paper_client is None:
                cfg = config or IBKRConfig.from_env("paper")
                _global_paper_client = IBKRClient(cfg, mode="paper")
            if not _global_paper_client.connected:
                _global_paper_client.connect()
            return _global_paper_client


def reset_ibkr_client(mode: str = None):
    """重置指定的 Gateway 连接，或重置所有"""
    global _global_paper_client, _global_live_client

    if mode == "live":
        with _live_lock:
            if _global_live_client is not None:
                _global_live_client.disconnect()
                _global_live_client.shutdown()
                _global_live_client = None
    elif mode == "paper":
        with _paper_lock:
            if _global_paper_client is not None:
                _global_paper_client.disconnect()
                _global_paper_client.shutdown()
                _global_paper_client = None
    else:
        with _paper_lock:
            if _global_paper_client is not None:
                _global_paper_client.disconnect()
                _global_paper_client.shutdown()
                _global_paper_client = None
        with _live_lock:
            if _global_live_client is not None:
                _global_live_client.disconnect()
                _global_live_client.shutdown()
                _global_live_client = None
