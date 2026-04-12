"""
Pending order worker.

This worker polls `pending_orders` periodically and dispatches orders based on `execution_mode`:
- signal: send notifications (no real trading).
- live: not implemented (paper mode only).
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from app.services.signal_notifier import SignalNotifier
from app.services.exchange_execution import load_strategy_configs, resolve_exchange_config, safe_exchange_config_for_log
from app.services.live_trading import records
from app.services.live_trading.factory import create_client, get_runner
from app.services.live_trading.base import (
    BaseStatefulClient, OrderContext, ExecutionResult,
)
from app.services.live_trading.runners import SignalRunner
from app.utils.console import console_print
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PendingOrderWorker:
    def __init__(self, poll_interval_sec: float = 1.0, batch_size: int = 50):
        self.poll_interval_sec = float(poll_interval_sec)
        self.batch_size = int(batch_size)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._notifier = SignalNotifier()

        # Reclaim stuck orders (e.g. if the worker crashed after claiming an order).
        try:
            self._stale_processing_sec = int(os.getenv("PENDING_ORDER_STALE_SEC", "90"))
        except Exception:
            self._stale_processing_sec = 90

        logger.info("PendingOrderWorker initialized")

    def start(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="PendingOrderWorker", daemon=True)
            self._thread.start()
            logger.info("PendingOrderWorker started")
            return True

    def stop(self, timeout_sec: float = 5.0) -> None:
        with self._lock:
            self._stop_event.set()
            th = self._thread
        if th and th.is_alive():
            th.join(timeout=timeout_sec)
        logger.info("PendingOrderWorker stopped")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as e:
                logger.warning(f"PendingOrderWorker tick error: {e}")
            time.sleep(self.poll_interval_sec)

    def _tick(self) -> None:
        orders = records.fetch_pending_orders(
            limit=self.batch_size,
            stale_processing_sec=self._stale_processing_sec,
        )
        if not orders:
            return

        for o in orders:
            oid = o.get("id")
            if not oid:
                continue

            if not records.mark_order_processing(int(oid)):
                continue

            try:
                self._dispatch_one(o)
            except Exception as e:
                records.mark_order_failed(order_id=int(oid), error=str(e))

    def _dispatch_one(self, order_row: Dict[str, Any]) -> None:
        order_id = int(order_row["id"])
        mode = (order_row.get("execution_mode") or "signal").strip().lower()
        payload_json = order_row.get("payload_json") or ""

        payload: Dict[str, Any] = {}
        if payload_json and isinstance(payload_json, str):
            try:
                payload = json.loads(payload_json) or {}
            except Exception:
                payload = {}

        signal_type = payload.get("signal_type") or order_row.get("signal_type")
        symbol = payload.get("symbol") or order_row.get("symbol")
        strategy_id = payload.get("strategy_id") or order_row.get("strategy_id")
        price = float(payload.get("price") or order_row.get("price") or 0.0)
        amount = float(payload.get("amount") or order_row.get("amount") or 0.0)
        direction = "short" if "short" in str(signal_type) else "long"
        notification_config = payload.get("notification_config") or {}
        strategy_name = str(payload.get("strategy_name") or "").strip()
        if not strategy_name and strategy_id:
            strategy_name = records.load_strategy_name(int(strategy_id))
        if not strategy_name:
            strategy_name = f"Strategy_{strategy_id}"

        try:
            if mode != "live" and strategy_id:
                sc = load_strategy_configs(int(strategy_id))
                if (sc.get("execution_mode") or "").strip().lower() == "live":
                    mode = "live"
        except Exception:
            pass

        ctx = OrderContext(
            order_id=order_id,
            strategy_id=int(strategy_id or 0),
            symbol=str(symbol or ""),
            signal_type=str(signal_type or ""),
            amount=amount,
            market_type=str(payload.get("market_type") or ""),
            market_category=str(payload.get("market_category") or ""),
            exchange_config={},
            payload=payload,
            order_row=order_row,
            notification_config=notification_config if isinstance(notification_config, dict) else {},
            strategy_name=strategy_name,
            direction=direction,
            price=price,
        )

        if mode == "signal":
            runner = SignalRunner(notifier=self._notifier)
            result = runner.execute(client=None, order_context=ctx)
            if result.success:
                records.mark_order_sent(order_id=order_id, note=result.note[:200])
            else:
                records.mark_order_failed(order_id=order_id, error=result.error or "notify_failed")
            return

        if mode == "live":
            self._execute_live_order(order_id=order_id, order_row=order_row, payload=payload)
            return

        records.mark_order_failed(order_id=order_id, error=f"unsupported_execution_mode:{mode}")

    def _notify_live_best_effort(
        self,
        *,
        order_id: int,
        strategy_id: int,
        payload: Dict[str, Any],
        order_row: Dict[str, Any],
        live_ctx: Dict[str, Any],
        status: str,
        error: str = "",
        exchange_id: str = "",
        exchange_order_id: str = "",
        price_hint: Optional[float] = None,
        amount_hint: Optional[float] = None,
        filled_price: float = 0.0,
        filled_amount: float = 0.0,
        profit: Optional[float] = None,
        entry_price: float = 0.0,
    ) -> None:
        try:
            notification_config = payload.get("notification_config") or {}
            if not notification_config and strategy_id:
                notification_config = records.load_notification_config(int(strategy_id))
            if not notification_config:
                return

            strategy_name = str(payload.get("strategy_name") or "").strip()
            if not strategy_name:
                strategy_name = records.load_strategy_name(int(strategy_id)) or f"Strategy_{strategy_id}"

            sym0 = payload.get("symbol") or order_row.get("symbol") or ""
            sig0 = payload.get("signal_type") or order_row.get("signal_type") or ""
            ref0 = float(payload.get("ref_price") or payload.get("price") or order_row.get("price") or 0.0)
            amt0 = float(payload.get("amount") or order_row.get("amount") or 0.0)

            px = float(price_hint) if (price_hint is not None and float(price_hint or 0.0) > 0) else ref0
            amt = float(amount_hint) if (amount_hint is not None and float(amount_hint or 0.0) > 0) else amt0

            symbol_name = ""
            position_opened_at = ""
            sig_lower = str(sig0 or "").strip().lower()
            is_close_sig = sig_lower.startswith("close_") or sig_lower.startswith("reduce_")

            mkt_cat = str(live_ctx.get("market_category") or "")
            if mkt_cat:
                try:
                    from app.services.symbol_name import resolve_symbol_name
                    symbol_name = resolve_symbol_name(mkt_cat, str(sym0)) or ""
                except Exception:
                    pass

            if is_close_sig and strategy_id:
                try:
                    position_opened_at = records.load_position_opened_at(
                        strategy_id, str(sym0), sig_lower)
                except Exception:
                    pass

            extra_dict: Dict[str, Any] = {
                "pending_order_id": int(order_id),
                "mode": "live",
                "status": str(status or ""),
                "error": str(error or ""),
                "exchange_id": str(exchange_id or live_ctx.get("exchange_id") or ""),
                "exchange_order_id": str(exchange_order_id or ""),
                "market_category": mkt_cat,
                "market_type": str(live_ctx.get("market_type") or ""),
                "filled_price": float(filled_price or 0.0),
                "filled_amount": float(filled_amount or 0.0),
                "symbol_name": symbol_name,
            }
            if is_close_sig:
                extra_dict["profit"] = profit
                extra_dict["entry_price"] = float(entry_price or 0.0)
                if position_opened_at:
                    extra_dict["position_opened_at"] = position_opened_at

            results = self._notifier.notify_signal(
                strategy_id=int(strategy_id),
                strategy_name=str(strategy_name or ""),
                symbol=str(sym0 or ""),
                signal_type=str(sig0 or ""),
                price=float(px or 0.0),
                stake_amount=float(amt or 0.0),
                direction=("short" if "short" in str(sig0 or "").lower() else "long"),
                notification_config=notification_config if isinstance(notification_config, dict) else {},
                extra=extra_dict,
            )
            ok_channels = [c for c, r in (results or {}).items() if (r or {}).get("ok")]
            fail_channels = [c for c, r in (results or {}).items() if not (r or {}).get("ok")]
            if ok_channels or fail_channels:
                logger.info(
                    f"live notify: pending_id={order_id}, strategy_id={strategy_id}, "
                    f"ok={','.join(ok_channels) if ok_channels else '-'} "
                    f"fail={','.join(fail_channels) if fail_channels else '-'}"
                )
        except Exception as e:
            logger.info(f"live notify skipped/failed: pending_id={order_id}, strategy_id={strategy_id}, err={e}")

    def _execute_live_order(self, *, order_id: int, order_row: Dict[str, Any], payload: Dict[str, Any]) -> None:
        """
        Execute a pending order using direct exchange REST clients (no ccxt).
        """
        strategy_id = int(payload.get("strategy_id") or order_row.get("strategy_id") or 0)
        if strategy_id <= 0:
            records.mark_order_failed(order_id=order_id, error="missing_strategy_id")
            return

        live_ctx: Dict[str, Any] = {"market_category": "", "market_type": "", "exchange_id": ""}

        signal_type = payload.get("signal_type") or order_row.get("signal_type")
        symbol = payload.get("symbol") or order_row.get("symbol")
        amount = float(payload.get("amount") or order_row.get("amount") or 0.0)
        _signal_ts_live = int(payload.get("signal_ts") or order_row.get("signal_ts") or 0)
        _dedup_kw_live = dict(strategy_id=strategy_id, symbol=str(symbol or ""), signal_type=str(signal_type or ""), signal_ts=_signal_ts_live)

        if not symbol or not signal_type:
            records.mark_order_failed(order_id=order_id, error="missing_symbol_or_signal_type", **_dedup_kw_live)
            console_print(f"[worker] order rejected: strategy_id={strategy_id} pending_id={order_id} missing symbol/signal_type")
            self._notify_live_best_effort(
                order_id=order_id,
                strategy_id=strategy_id,
                payload=payload,
                order_row=order_row,
                live_ctx=live_ctx,
                status="failed",
                error="missing_symbol_or_signal_type",
            )
            return

        cfg = load_strategy_configs(strategy_id)
        exchange_config = resolve_exchange_config(cfg.get("exchange_config") or {})
        safe_cfg = safe_exchange_config_for_log(exchange_config)
        exchange_id = str(exchange_config.get("exchange_id") or "").strip().lower()
        market_category = str(cfg.get("market_category") or "Crypto").strip()
        live_ctx["market_category"] = market_category
        live_ctx["exchange_id"] = exchange_id

        if market_category in ("AShare", "Futures"):
            records.mark_order_failed(order_id=order_id, error=f"live_trading_not_supported_for_{market_category.lower()}")
            console_print(f"[worker] order rejected: strategy_id={strategy_id} pending_id={order_id} {market_category} does not support live trading")
            self._notify_live_best_effort(
                order_id=order_id,
                strategy_id=strategy_id,
                payload=payload,
                order_row=order_row,
                live_ctx=live_ctx,
                status="failed",
                error=f"live_trading_not_supported_for_{market_category.lower()}",
            )
            return

        _EXCHANGE_MARKET_RULES: Dict[str, set] = {
            "binance": {"Crypto"}, "okx": {"Crypto"}, "bitget": {"Crypto"},
            "bybit": {"Crypto"}, "coinbaseexchange": {"Crypto"},
            "kraken": {"Crypto"}, "kucoin": {"Crypto"}, "gate": {"Crypto"},
            "bitfinex": {"Crypto"}, "deepcoin": {"Crypto"},
        }
        allowed = _EXCHANGE_MARKET_RULES.get(exchange_id)
        if allowed is not None and market_category not in allowed:
            err = f"{exchange_id}_only_supports_{'_'.join(sorted(allowed)).lower()}_got_{market_category.lower()}"
            records.mark_order_failed(order_id=order_id, error=err, **_dedup_kw_live)
            console_print(f"[worker] order rejected: strategy_id={strategy_id} pending_id={order_id} {err}")
            self._notify_live_best_effort(
                order_id=order_id,
                strategy_id=strategy_id,
                payload=payload,
                order_row=order_row,
                live_ctx=live_ctx,
                status="failed",
                error=err,
            )
            return

        market_type = (payload.get("market_type") or order_row.get("market_type") or cfg.get("market_type") or exchange_config.get("market_type") or "swap")
        market_type = str(market_type or "swap").strip().lower()
        if market_type in ("futures", "future", "perp", "perpetual"):
            market_type = "swap"
        live_ctx["market_type"] = market_type

        client = None
        try:
            client = create_client(exchange_config, market_type=market_type)
        except Exception as e:
            records.mark_order_failed(order_id=order_id, error=f"create_client_failed:{e}", **_dedup_kw_live)
            console_print(f"[worker] create_client_failed: strategy_id={strategy_id} pending_id={order_id} err={e}")
            self._notify_live_best_effort(
                order_id=order_id,
                strategy_id=strategy_id,
                payload=payload,
                order_row=order_row,
                live_ctx=live_ctx,
                status="failed",
                error=f"create_client_failed:{e}",
            )
            return

        if isinstance(client, BaseStatefulClient):
            ok, cat_err = client.validate_market_category(market_category)
            if not ok:
                records.mark_order_failed(order_id=order_id, error=cat_err, **_dedup_kw_live)
                console_print(f"[worker] order rejected: strategy_id={strategy_id} pending_id={order_id} {cat_err}")
                self._notify_live_best_effort(
                    order_id=order_id,
                    strategy_id=strategy_id,
                    payload=payload,
                    order_row=order_row,
                    live_ctx=live_ctx,
                    status="failed",
                    error=cat_err,
                )
                return

        row_price = float(order_row.get("price") or 0.0)
        lim_px = float(
            payload.get("limit_price")
            or payload.get("price")
            or row_price
            or 0.0
        )
        ot_live = str(
            payload.get("order_type") or order_row.get("order_type") or "market"
        ).strip().lower()
        if "order_type" not in payload:
            payload["order_type"] = ot_live

        notification_config_live = payload.get("notification_config") or {}
        if not notification_config_live and strategy_id:
            notification_config_live = records.load_notification_config(int(strategy_id))
        if not isinstance(notification_config_live, dict):
            notification_config_live = {}

        strategy_name_live = str(payload.get("strategy_name") or "").strip()
        if not strategy_name_live:
            strategy_name_live = records.load_strategy_name(strategy_id) or f"Strategy_{strategy_id}"

        direction_live = "short" if "short" in str(signal_type or "").lower() else "long"

        runner = get_runner(client)
        ctx = OrderContext(
            order_id=order_id,
            strategy_id=strategy_id,
            symbol=str(symbol or ""),
            signal_type=str(signal_type or ""),
            amount=amount,
            market_type=market_type,
            market_category=market_category,
            exchange_config=exchange_config,
            payload=payload,
            order_row=order_row,
            notification_config=notification_config_live,
            strategy_name=strategy_name_live,
            direction=direction_live,
            price=lim_px,
        )

        pc = runner.pre_check(client=client, order_context=ctx)
        if not pc.ok:
            _fail_kw = dict(order_id=order_id, error=pc.reason)
            if not pc.suppress_dedup_clear:
                _fail_kw.update(_dedup_kw_live)
            records.mark_order_failed(**_fail_kw)
            logger.info(
                "[RTH] order %d blocked by pre_check: strategy=%s symbol=%s reason=%s suppress_dedup=%s",
                order_id, strategy_id, symbol, pc.reason, pc.suppress_dedup_clear,
            )
            console_print(
                f"[worker] order blocked (pre_check): strategy_id={strategy_id} "
                f"pending_id={order_id} reason={pc.reason}"
            )
            self._notify_live_best_effort(
                order_id=order_id,
                strategy_id=strategy_id,
                payload=payload,
                order_row=order_row,
                live_ctx=live_ctx,
                status="failed",
                error=pc.reason,
            )
            return

        result = runner.execute(client=client, order_context=ctx)

        if not result.success:
            records.mark_order_failed(order_id=order_id, error=result.error, **_dedup_kw_live)
            console_print(f"[worker] order failed: strategy_id={strategy_id} pending_id={order_id} err={result.error}")
            self._notify_live_best_effort(
                order_id=order_id,
                strategy_id=strategy_id,
                payload=payload,
                order_row=order_row,
                live_ctx=live_ctx,
                status="failed",
                error=result.error,
            )
            return

        # Fire-and-forget: record "submitted" status only.
        # Fill details (position updates, trade records, notifications)
        # are handled asynchronously by IBKRClient event callbacks.
        try:
            records.mark_order_sent(
                order_id=order_id,
                note=result.note or "live_order_submitted",
                exchange_id=result.exchange_id,
                exchange_order_id=result.exchange_order_id,
                exchange_response_json=json.dumps(result.raw or {}, ensure_ascii=False),
                filled=0.0,
                avg_price=0.0,
            )
            console_print(
                f"[worker] order submitted: strategy_id={strategy_id} pending_id={order_id} "
                f"exchange={result.exchange_id} order_id={result.exchange_order_id}"
            )
        except Exception as e:
            logger.warning(f"mark_sent failed: pending_id={order_id}, err={e}")

        self._notify_live_best_effort(
            order_id=order_id,
            strategy_id=strategy_id,
            payload=payload,
            order_row=order_row,
            live_ctx=live_ctx,
            status="submitted",
            exchange_id=result.exchange_id,
            exchange_order_id=result.exchange_order_id,
        )
