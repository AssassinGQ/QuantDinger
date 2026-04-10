"""StatefulClientRunner.execute passes market_category into map_signal_to_side (UC-R1)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.live_trading.base import LiveOrderResult, OrderContext
from app.services.live_trading.runners.stateful_runner import StatefulClientRunner


def test_execute_passes_market_category_to_map_signal_uc_r1():
    client = MagicMock()
    client.engine_id = "ibkr"
    client.map_signal_to_side.return_value = "sell"
    client.place_market_order.return_value = LiveOrderResult(success=True, order_id=1)

    ctx = OrderContext(
        order_id=1,
        strategy_id=1,
        symbol="EURUSD",
        signal_type="open_short",
        amount=10000.0,
        market_type="Forex",
        market_category="Forex",
        exchange_config={"market_type": "Forex"},
        payload={},
        order_row={},
    )

    StatefulClientRunner().execute(client=client, order_context=ctx)

    client.map_signal_to_side.assert_called_once_with("open_short", market_category="Forex")
