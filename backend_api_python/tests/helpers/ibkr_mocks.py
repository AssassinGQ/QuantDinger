"""
Shared IBKR paper/E2E test mocks.

Re-exports client skeleton helpers from tests.test_ibkr_client; event/callback
helpers used by smoke and forex E2E tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock

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
    "_make_mock_ib_insync",
    "_make_qualify_for_pair",
    "_make_trade_mock",
    "_wire_ib_events",
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
