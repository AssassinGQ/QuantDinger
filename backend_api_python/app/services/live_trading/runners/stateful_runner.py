from __future__ import annotations

from typing import Any, Dict, Tuple

from app.services.live_trading.base import (
    BaseStatefulClient,
    ExecutionResult,
    OrderContext,
)
from app.services.live_trading.runners.base import OrderRunner
from app.utils.logger import get_logger

logger = get_logger(__name__)


class StatefulClientRunner(OrderRunner):
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
            )

            if not result.success:
                return ExecutionResult(
                    success=False,
                    error=f"{eid}_order_failed:{result.message or ''}",
                )

            filled = float(result.filled or 0.0)
            avg_price = float(result.avg_price or 0.0)
            exchange_order_id = str(result.order_id or "")

            ref_price = float(
                ctx.payload.get("ref_price") or ctx.payload.get("price") or ctx.order_row.get("price") or 0.0
            )
            if filled > 0 and avg_price <= 0 and ref_price > 0:
                avg_price = ref_price

            return ExecutionResult(
                success=True,
                exchange_id=eid,
                exchange_order_id=exchange_order_id,
                filled=filled,
                avg_price=avg_price,
                note=f"{eid}_order_sent",
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
