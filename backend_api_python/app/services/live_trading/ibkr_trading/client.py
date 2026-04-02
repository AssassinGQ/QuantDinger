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
from typing import Optional, Dict, Any, List, Callable
import math

from app.utils.logger import get_logger
from app.services.live_trading.base import BaseStatefulClient, LiveOrderResult
from app.services.live_trading.ibkr_trading.symbols import normalize_symbol
from app.services.live_trading.ibkr_trading.order_tracker import HARD_TERMINAL
from app.services.live_trading.task_queue import TaskQueue
from app.services.live_trading import records

logger = get_logger(__name__)

ib_insync = None


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
    supported_market_categories = frozenset({"USStock", "HShare"})

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

    _RECONNECT_DELAYS = [2, 5, 10, 30, 60]

    @staticmethod
    def _get_tif_for_signal(signal_type: str, market_type: str = "USStock") -> str:
        """Get TIF (Time in Force) based on signal type and market type.

        Close signals (close_long, close_short) use IOC to allow pre/post-market execution.
        Open signals use DAY to ensure fresh in-session data.

        Note: HShare (Hong Kong stocks) does not support IOC orders.
        """
        is_close = signal_type in ("close_long", "close_short")
        if not is_close:
            return "DAY"
        if market_type == "HShare":
            return "DAY"
        return "IOC"

    def __init__(self, config: Optional[IBKRConfig] = None, mode: str = "paper"):
        self.config = config or IBKRConfig()
        self.mode = mode
        self._ib = None
        self._account = ""

        self._tq = TaskQueue(loop_executor_name="ibkr-loop-executor", pool_executor_name="ibkr-pool-executor", pool_workers=4)
        self._tq.start()

        # Fire-and-forget order context: orderId → IBKROrderContext
        self._order_contexts: Dict[int, IBKROrderContext] = {}
        self._events_registered = False

        self._reconnect_thread: Optional[threading.Thread] = None
        self._reconnect_stop = threading.Event()

        self._conid_to_symbol: Dict[int, str] = {}
        self._subscribed_conids: set = set()

    # ── signal mapping ──────────────────────────────────────────────

    def map_signal_to_side(self, signal_type: str) -> str:
        sig = (signal_type or "").strip().lower()
        if "short" in sig:
            raise ValueError("IBKR stock trading does not support short signals")
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

    def _register_events(self):
        if self._events_registered or self._ib is None:
            return
        ib = self._ib

        # Business logic (6)
        ib.orderStatusEvent      += self._on_order_status
        ib.execDetailsEvent      += self._on_exec_details
        ib.commissionReportEvent += self._on_commission_report
        ib.errorEvent            += self._on_error
        ib.connectedEvent        += self._on_connected
        ib.disconnectedEvent     += self._on_disconnected

        # Order observation (4)
        ib.newOrderEvent         += self._on_new_order
        ib.orderModifyEvent      += self._on_order_modify
        ib.cancelOrderEvent      += self._on_cancel_order
        ib.openOrderEvent        += self._on_open_order

        # Position / portfolio (2)
        ib.updatePortfolioEvent  += self._on_update_portfolio
        ib.positionEvent         += self._on_position

        # News / WSH (4)
        ib.tickNewsEvent         += self._on_tick_news
        ib.newsBulletinEvent     += self._on_news_bulletin
        ib.wshMetaEvent          += self._on_wsh_meta
        ib.wshEvent              += self._on_wsh

        # Timeout (1)
        ib.timeoutEvent          += self._on_timeout

        # High-frequency DEBUG (6)
        ib.pnlEvent              += self._on_pnl
        ib.pnlSingleEvent        += self._on_pnl_single
        ib.accountValueEvent     += self._on_account_value
        ib.accountSummaryEvent   += self._on_account_summary
        ib.pendingTickersEvent   += self._on_pending_tickers
        ib.barUpdateEvent        += self._on_bar_update

        # Scanner (1)
        ib.scannerDataEvent      += self._on_scanner_data

        # Ultra-high-frequency (1)
        ib.updateEvent           += self._on_update

        self._events_registered = True
        logger.info("[IBKR-Event] All 25 IB events registered")

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

    _CONTEXT_LINGER_SEC = 30

    def _on_order_status(self, trade):
        order_id = trade.order.orderId
        status = trade.orderStatus.status
        filled = float(trade.orderStatus.filled or 0)
        avg_price = float(trade.orderStatus.avgFillPrice or 0)
        logger.info(
            "[IBKR-Event] orderStatus: orderId=%s status=%s filled=%s avgPrice=%s",
            order_id, status, filled, avg_price,
        )

        ctx = self._order_contexts.get(order_id)
        if ctx is None:
            return

        if status == "Filled" and filled > 0:
            self._fire_submit(lambda: self._handle_fill(ctx, filled, avg_price), is_blocking=True)
            self._schedule_context_cleanup(order_id)
        elif status == "Cancelled" and filled > 0:
            self._fire_submit(lambda: self._handle_fill(ctx, filled, avg_price), is_blocking=True)
            self._schedule_context_cleanup(order_id)
        elif status in HARD_TERMINAL:
            error_msgs = [e.message for e in (trade.log or []) if e.message]
            self._fire_submit(lambda: self._handle_reject(ctx, status, error_msgs), is_blocking=True)
            self._order_contexts.pop(order_id, None)

    def _schedule_context_cleanup(self, order_id: int):
        """Delay context removal so commissionReportEvent can still access it."""
        def _cleanup():
            time.sleep(self._CONTEXT_LINGER_SEC)
            removed = self._order_contexts.pop(order_id, None)
            if removed:
                logger.debug("[IBKR] Cleaned up lingering context for orderId=%s", order_id)
        t = threading.Thread(target=_cleanup, daemon=True, name=f"ctx-cleanup-{order_id}")
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

        ctx = self._order_contexts.get(order_id)
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

        logger.info(
            "[IBKR-Event] updatePortfolio: symbol=%s pos=%s mktPrice=%.2f mktValue=%.2f unrealPNL=%.2f realPNL=%.2f",
            item.contract.symbol, item.position,
            float(item.marketPrice or 0), value,
            unrealized_pnl, realized_pnl,
        )

        self._conid_to_symbol[item.contract.conId] = item.contract.symbol

        def _save_to_db():
            for attempt in range(3):
                if records.ibkr_save_position(
                    account=item.account,
                    con_id=item.contract.conId,
                    symbol=item.contract.symbol,
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
        symbol = position.contract.symbol or ""
        con_id = position.contract.conId
        account = position.account
        pos = float(position.position or 0)
        avg_cost = float(position.avgCost or 0)

        logger.info(
            "[IBKR-Event] position: account=%s symbol=%s pos=%s avgCost=%.4f",
            account, symbol, pos, avg_cost,
        )

        self._conid_to_symbol[con_id] = symbol

        def _save_to_db():
            for attempt in range(3):
                if records.ibkr_save_position(
                    account=account,
                    con_id=con_id,
                    symbol=symbol,
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
        return ib_insync.Stock(symbol=ib_symbol, exchange=exchange, currency=currency)

    async def _qualify_contract_async(self, contract) -> bool:
        try:
            return len(await self._ib.qualifyContractsAsync(contract)) > 0
        except Exception as e:
            logger.warning("Contract qualification failed: %s", e)
            return False

    # ── fire-and-forget order handlers ──────────────────────────────

    def _handle_fill(self, ctx: IBKROrderContext, filled: float, avg_price: float):
        """Process a fill event — runs in IO thread pool, never blocks event loop."""
        from app.services.live_trading import records

        logger.info(
            "[IBKR-Fill] orderId=%s pending=%s strategy=%s filled=%.2f avg=%.4f",
            ctx.order_id, ctx.pending_order_id, ctx.strategy_id, filled, avg_price,
        )

        if ctx.pending_order_id:
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
                if await self._qualify_contract_async(contract):
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
                return False, f"{symbol} contract not found"

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
                return False, f"{sym} is outside RTH (market closed)"
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
        from app.services.live_trading.ibkr_trading.order_normalizer import get_normalizer
        ok, reason = get_normalizer(market_type).check(quantity, symbol)
        if not ok:
            return LiveOrderResult(success=False, message=reason, exchange_id=self.engine_id)

        signal_type = str(kwargs.get("signal_type", ""))
        tif = self._get_tif_for_signal(signal_type, market_type)

        async def _do():
            await self._ensure_connected_async()
            _ensure_ib_insync()
            contract = self._create_contract(symbol, market_type)
            if not await self._qualify_contract_async(contract):
                return LiveOrderResult(success=False, message=f"Invalid contract: {symbol}",
                                   exchange_id=self.engine_id)
            order = ib_insync.MarketOrder(
                action="BUY" if side.lower() == "buy" else "SELL",
                totalQuantity=quantity, account=self._account,
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
                amount=quantity,
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
        market_type: str = "USStock", **kwargs,
    ) -> LiveOrderResult:
        from app.services.live_trading.ibkr_trading.order_normalizer import get_normalizer
        ok, reason = get_normalizer(market_type).check(quantity, symbol)
        if not ok:
            return LiveOrderResult(success=False, message=reason, exchange_id=self.engine_id)

        signal_type = str(kwargs.get("signal_type", ""))
        tif = self._get_tif_for_signal(signal_type, market_type)

        async def _do():
            await self._ensure_connected_async()
            _ensure_ib_insync()
            contract = self._create_contract(symbol, market_type)
            if not await self._qualify_contract_async(contract):
                return LiveOrderResult(success=False, message=f"Invalid contract: {symbol}",
                                   exchange_id=self.engine_id)
            order = ib_insync.LimitOrder(
                action="BUY" if side.lower() == "buy" else "SELL",
                totalQuantity=quantity, lmtPrice=price, account=self._account,
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
                amount=quantity,
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

                result.append({
                    "symbol": row.get("symbol") or "",
                    "ib_symbol": row.get("symbol") or "",
                    "secType": "STK",
                    "exchange": "SMART",
                    "currency": "USD",
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
            if not await self._qualify_contract_async(contract):
                return {"success": False, "error": f"Invalid contract: {symbol}"}
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
