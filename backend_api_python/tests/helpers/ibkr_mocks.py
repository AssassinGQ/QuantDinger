"""
Shared IBKR paper/E2E test mocks.

Re-exports client skeleton helpers from tests.test_ibkr_client; event/callback
helpers used by smoke and forex E2E tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.live_trading.ibkr_trading.client import IBKRClient

from tests.test_ibkr_client import (
    _make_client_with_mock_ib,
    _make_mock_ib_insync,
    _make_trade_mock,
)

__all__ = [
    "_FakeEvent",
    "_fill_mock_exec",
    "_fire_callbacks_after_fill",
    "_make_client_with_mock_ib",
    "_make_ibkr_client_for_e2e",
    "_make_mock_ib_insync",
    "_make_qualify_for_pair",
    "_make_qualify_for_stock",
    "_make_trade_mock",
    "_wire_ib_events",
    "patched_records",
]


class _FakeEvent:
    """Minimal Event-like object so IBKRClient._register_events (+=) works."""

    def __init__(self):
        self._handlers: list = []

    def __iadd__(self, handler):
        self._handlers.append(handler)
        return self

    def __isub__(self, handler):
        while handler in self._handlers:
            self._handlers.remove(handler)
        return self

    def __contains__(self, handler):
        return handler in self._handlers

    def fire(self, *args, **kwargs):
        for h in list(self._handlers):
            h(*args, **kwargs)


def _wire_ib_events(ib_mock: MagicMock) -> None:
    names = [
        "orderStatusEvent",
        "execDetailsEvent",
        "commissionReportEvent",
        "errorEvent",
        "connectedEvent",
        "disconnectedEvent",
        "newOrderEvent",
        "orderModifyEvent",
        "cancelOrderEvent",
        "openOrderEvent",
        "updatePortfolioEvent",
        "positionEvent",
        "tickNewsEvent",
        "newsBulletinEvent",
        "wshMetaEvent",
        "wshEvent",
        "timeoutEvent",
        "pnlEvent",
        "pnlSingleEvent",
        "accountValueEvent",
        "accountSummaryEvent",
        "pendingTickersEvent",
        "barUpdateEvent",
        "scannerDataEvent",
        "updateEvent",
    ]
    for name in names:
        setattr(ib_mock, name, _FakeEvent())


def _make_qualify_for_pair(
    symbol: str, con_id: int, local_symbol: str, *, sec_type: str = "CASH"
):
    """qualifyContractsAsync mutates contract in place (Forex CASH/IDEALPRO or Metals CMDTY/SMART)."""

    async def _mock_qualify(*contracts):
        for c in contracts:
            c.conId = con_id
            c.localSymbol = local_symbol
            c.secType = sec_type
            if sec_type == "CMDTY" and hasattr(c, "exchange"):
                c.exchange = "SMART"
        return list(contracts)

    return _mock_qualify


def _fill_mock_exec(fill_id: str, side: str, shares: float, price: float) -> MagicMock:
    fill = MagicMock()
    fill.execution.execId = fill_id
    fill.execution.side = side
    fill.execution.shares = shares
    fill.execution.price = price
    return fill


def _fire_callbacks_after_fill(
    client: IBKRClient,
    trade: MagicMock,
    qty: float,
    *,
    position_after: float,
    fill_tag: str,
) -> None:
    """
    Simulate Paper stream after a fill (orderStatus → execDetails → position → pnlSingle).
    """
    price = 1.12345
    trade.orderStatus.status = "Filled"
    trade.orderStatus.filled = qty
    trade.orderStatus.avgFillPrice = price

    client._on_order_status(trade)

    side = "BOT" if trade.order.action == "BUY" else "SLD"
    fill = _fill_mock_exec(f"exec_{fill_tag}", side, qty, price)
    client._on_exec_details(trade, fill)

    pos = MagicMock()
    pos.contract = trade.contract
    pos.account = client._account
    pos.position = position_after
    pos.avgCost = price if position_after else 0.0
    client._on_position(pos)

    ent = MagicMock()
    ent.account = client._account
    ent.conId = getattr(trade.contract, "conId", 0)
    ent.dailyPnL = 0.0
    ent.unrealizedPnL = 0.1
    ent.realizedPnL = 0.0
    ent.position = position_after
    ent.value = abs(position_after) * price
    client._on_pnl_single(ent)


def _make_qualify_for_stock(symbol: str, con_id: int):
    """qualifyContractsAsync for equity: sets secType=STK."""

    async def _mock_qualify(*contracts):
        for c in contracts:
            c.conId = con_id
            c.localSymbol = symbol
            c.secType = "STK"
        return list(contracts)

    return _mock_qualify


def _make_ibkr_client_for_e2e(
    symbol: str,
    con_id: int,
    local_symbol: str,
    *,
    sec_type: str = "CASH",
    size_increment: float = 1.0,
    min_tick: float = 0.0,
):
    """Real IBKRClient with mock ib_insync; wired events + qualify stub.

    When *min_tick* > 0 the reqContractDetailsAsync stub returns real
    sizeIncrement/minTick so limit-order minTick-snap works correctly.
    """
    import types as _t

    client = _make_client_with_mock_ib()
    _wire_ib_events(client._ib)
    if sec_type == "STK":
        client._ib.qualifyContractsAsync = _make_qualify_for_stock(symbol, con_id)
    else:
        client._ib.qualifyContractsAsync = _make_qualify_for_pair(
            symbol, con_id, local_symbol, sec_type=sec_type
        )

    if min_tick > 0:
        IBKRClient._lot_size_cache.pop(con_id, None)
        IBKRClient._mintick_cache.pop(con_id, None)

        async def _mock_details(*_a, **_kw):
            return [
                _t.SimpleNamespace(
                    sizeIncrement=size_increment,
                    minSize=1.0,
                    minTick=min_tick,
                    liquidHours="20260305:0930-20260305:1600",
                    timeZoneId="EST",
                )
            ]

        client._ib.reqContractDetailsAsync = _mock_details

    client._events_registered = False
    client._register_events()

    place_calls: list[MagicMock] = []

    def _place_side_effect(contract, order):
        oid = 60000 + len(place_calls)
        t = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=oid)
        t.contract = contract
        t.order.action = order.action
        t.order.totalQuantity = order.totalQuantity
        if hasattr(order, "lmtPrice"):
            t.order.lmtPrice = order.lmtPrice
        if hasattr(order, "tif"):
            t.order.tif = order.tif
        place_calls.append(t)
        return t

    client._ib.placeOrder.side_effect = _place_side_effect
    return client, place_calls


@pytest.fixture
def patched_records():
    """Mock DB persistence for position/pnl so callbacks don't hit real DB."""
    with patch(
        "app.services.live_trading.records.ibkr_save_position",
        return_value=True,
    ), patch(
        "app.services.live_trading.records.ibkr_save_pnl",
        return_value=True,
    ):
        yield
