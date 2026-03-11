from __future__ import annotations

from typing import Any, Dict, Tuple

from app.services.live_trading.base import (
    BaseStatefulClient,
    ExecutionResult,
    OrderContext,
)
from app.services.live_trading.runners.base import OrderRunner, PreCheckResult
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _is_close_signal(signal_type: str) -> bool:
    """Check if signal is a close signal (close_long, close_short)."""
    return signal_type in ("close_long", "close_short")


class StatefulClientRunner(OrderRunner):
    def pre_check(self, *, client: BaseStatefulClient, order_context: OrderContext) -> PreCheckResult:
        ctx = order_context

        if _is_close_signal(ctx.signal_type):
            logger.info(
                "[RTH] close signal %s for %s, skipping RTH check",
                ctx.signal_type, ctx.symbol,
            )
            return PreCheckResult(ok=True)

        market_type = str(
            ctx.market_category or
            ctx.payload.get("market_type") or
            ctx.payload.get("market_category") or
            ctx.exchange_config.get("market_type") or
            ctx.exchange_config.get("market_category") or
            ""
        ).strip()
        eid = client.engine_id or "engine"
        is_open, reason = client.is_market_open(ctx.symbol, market_type)
        if not is_open:
            logger.info(
                "[RTH] pre_check blocked: strategy=%s symbol=%s reason=%s "
                "(order will NOT clear dedup — same signal suppressed until market opens)",
                ctx.strategy_id, ctx.symbol, reason,
            )
            return PreCheckResult(
                ok=False,
                reason=f"{eid}_market_closed:{reason}",
                suppress_dedup_clear=True,
            )
        return PreCheckResult(ok=True)

    def execute(self, *, client: BaseStatefulClient, order_context: OrderContext) -> ExecutionResult:
        ctx = order_context
        eid = client.engine_id or "engine"

        try:
            action = client.map_signal_to_side(ctx.signal_type)
        except ValueError as e:
            return ExecutionResult(success=False, error=f"{eid}_unsupported_signal:{e}")

        market_type = str(
            ctx.market_category or
            ctx.payload.get("market_type") or
            ctx.payload.get("market_category") or
            ctx.exchange_config.get("market_type") or
            ctx.exchange_config.get("market_category") or
            ""
        ).strip()

        try:
            result = client.place_market_order(
                symbol=ctx.symbol,
                side=action,
                quantity=ctx.amount,
                market_type=market_type,
                pending_order_id=ctx.order_id,
                strategy_id=ctx.strategy_id,
                signal_type=ctx.signal_type,
                payload=ctx.payload,
                order_row=ctx.order_row,
                notification_config=ctx.notification_config,
                strategy_name=ctx.strategy_name,
                market_category=ctx.market_category,
            )

            if not result.success:
                return ExecutionResult(
                    success=False,
                    error=f"{eid}_order_failed:{result.message or ''}",
                )

            exchange_order_id = str(result.order_id or "")

            return ExecutionResult(
                success=True,
                exchange_id=eid,
                exchange_order_id=exchange_order_id,
                filled=0.0,
                avg_price=0.0,
                note=f"{eid}_order_submitted",
                raw=result.raw or {},
            )
        except Exception as e:
            return ExecutionResult(success=False, error=f"{eid}_exception:{e}")

    def sync_positions(
        self, *, client: BaseStatefulClient, exchange_config: Dict[str, Any], market_type: str = "swap"
    ) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]:
        exch_size: Dict[str, Dict[str, float]] = {}
        exch_entry_price: Dict[str, Dict[str, float]] = {}
        for pr in client.get_positions_normalized():
            if pr.symbol and pr.quantity > 0:
                exch_size.setdefault(pr.symbol, {"long": 0.0, "short": 0.0})[pr.side] = pr.quantity
                if pr.entry_price > 0:
                    exch_entry_price.setdefault(pr.symbol, {"long": 0.0, "short": 0.0})[pr.side] = pr.entry_price
        return exch_size, exch_entry_price
