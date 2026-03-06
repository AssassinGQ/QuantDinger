from __future__ import annotations

from typing import Dict

from app.services.live_trading.base import ExecutionResult, OrderContext
from app.services.live_trading.runners.base import OrderRunner
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SignalRunner(OrderRunner):
    def __init__(self, notifier):
        self._notifier = notifier

    def execute(self, *, client, order_context: OrderContext) -> ExecutionResult:
        from app.services.live_trading.records import load_notification_config

        ctx = order_context
        notification_config = ctx.notification_config
        if (not notification_config) and ctx.strategy_id:
            notification_config = load_notification_config(ctx.strategy_id)

        mkt_cat = str(ctx.payload.get("market_category") or "")
        sym_name = ""
        if mkt_cat:
            try:
                from app.services.symbol_name import resolve_symbol_name
                sym_name = resolve_symbol_name(mkt_cat, str(ctx.symbol)) or ""
            except Exception:
                pass

        results = self._notifier.notify_signal(
            strategy_id=int(ctx.strategy_id or 0),
            strategy_name=str(ctx.strategy_name or ""),
            symbol=str(ctx.symbol or ""),
            signal_type=str(ctx.signal_type or ""),
            price=float(ctx.price or 0.0),
            stake_amount=float(ctx.amount or 0.0),
            direction=str(ctx.direction or "long"),
            notification_config=notification_config if isinstance(notification_config, dict) else {},
            extra={
                "pending_order_id": ctx.order_id,
                "mode": "signal",
                "market_category": mkt_cat,
                "market_type": str(ctx.payload.get("market_type") or ""),
                "symbol_name": sym_name,
            },
        )

        attempted = list(results.keys())
        ok_channels = [c for c, r in results.items() if (r or {}).get("ok")]
        fail_channels = [c for c, r in results.items() if not (r or {}).get("ok")]

        if ok_channels:
            note = f"notified_ok={','.join(ok_channels)}"
            if fail_channels:
                note += f";fail={','.join(fail_channels)}"
            return ExecutionResult(success=True, note=note[:200])

        first_err = ""
        for c in attempted:
            err = (results.get(c) or {}).get("error") or ""
            if err:
                first_err = f"{c}:{err}"
                break
        return ExecutionResult(success=False, error=first_err or "notify_failed")
