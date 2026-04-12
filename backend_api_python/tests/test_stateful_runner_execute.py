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


def test_uc_03e_limit_path_calls_place_limit_order():
    client = MagicMock()
    client.engine_id = "ibkr"
    client.map_signal_to_side.return_value = "buy"
    client.place_limit_order.return_value = LiveOrderResult(success=True, order_id=99)

    ctx = OrderContext(
        order_id=2,
        strategy_id=1,
        symbol="EURUSD",
        signal_type="open_long",
        amount=10000.0,
        market_type="Forex",
        market_category="Forex",
        exchange_config={"market_type": "Forex"},
        payload={"order_type": "limit", "limit_price": 1.101},
        order_row={"order_type": "limit", "price": 1.101},
        price=1.101,
    )

    StatefulClientRunner().execute(client=client, order_context=ctx)

    client.place_limit_order.assert_called_once()
    call_kw = client.place_limit_order.call_args
    assert call_kw[0][3] == 1.101 or call_kw[1].get("price") == 1.101
    client.place_market_order.assert_not_called()


def test_uc_03f_limit_without_price_returns_error():
    client = MagicMock()
    client.engine_id = "ibkr"
    client.map_signal_to_side.return_value = "buy"

    ctx = OrderContext(
        order_id=3,
        strategy_id=1,
        symbol="EURUSD",
        signal_type="open_long",
        amount=10000.0,
        market_type="Forex",
        market_category="Forex",
        exchange_config={},
        payload={"order_type": "limit"},
        order_row={"order_type": "limit", "price": 0.0},
        price=0.0,
    )

    result = StatefulClientRunner().execute(client=client, order_context=ctx)

    assert result.success is False
    assert "ibkr_limit_price_required" in (result.error or "")
    client.place_market_order.assert_not_called()
    client.place_limit_order.assert_not_called()
