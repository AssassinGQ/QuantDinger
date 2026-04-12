"""
Mock IBKR Paper — no live connection.

Plausible callback order after each placeOrder (see _fire_callbacks_after_fill):
1) orderStatusEvent → Filled (drives _on_order_status → _handle_fill when ctx exists)
2) execDetailsEvent
3) positionEvent (non-zero after open, zero after close)
4) pnlSingleEvent
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.live_trading.ibkr_trading.client import IBKRClient
from app.services.live_trading.base import LiveOrderResult

# Reuse ib_insync mock + client skeleton from test_ibkr_client.py (pattern documented there).
from tests.test_ibkr_client import (
    _make_client_with_mock_ib,
    _make_mock_ib_insync,
    _make_trade_mock,
)


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


def _run_open_close_cycle(
    client: IBKRClient,
    symbol: str,
    qty: float,
    *,
    market_type: str = "Forex",
    market_category: str = "Forex",
) -> tuple[LiveOrderResult, LiveOrderResult, list[MagicMock]]:
    """Two place_market_order calls (open_long then close_long) + simulated callbacks each."""
    place_calls: list[MagicMock] = []

    def _place_side_effect(contract, order):
        oid = 50000 + len(place_calls)
        t = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=oid)
        t.contract = contract
        t.order.action = order.action
        t.order.totalQuantity = order.totalQuantity
        place_calls.append(t)
        return t

    client._ib.placeOrder.side_effect = _place_side_effect

    side_buy = client.map_signal_to_side("open_long", market_category=market_category)
    side_sell = client.map_signal_to_side("close_long", market_category=market_category)

    r_open = client.place_market_order(
        symbol,
        side_buy,
        qty,
        market_type=market_type,
        signal_type="open_long",
        market_category=market_category,
    )
    assert r_open.success is True
    t_open = place_calls[0]
    _fire_callbacks_after_fill(client, t_open, qty, position_after=qty, fill_tag="a")

    r_close = client.place_market_order(
        symbol,
        side_sell,
        qty,
        market_type=market_type,
        signal_type="close_long",
        market_category=market_category,
    )
    assert r_close.success is True
    t_close = place_calls[1]
    _fire_callbacks_after_fill(client, t_close, qty, position_after=0.0, fill_tag="b")

    assert client._ib.placeOrder.call_count == 2
    return r_open, r_close, place_calls


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


@pytest.fixture
def patched_records():
    with patch(
        "app.services.live_trading.records.ibkr_save_position",
        return_value=True,
    ), patch(
        "app.services.live_trading.records.ibkr_save_pnl",
        return_value=True,
    ):
        yield


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
def test_forex_paper_smoke_eurusd_uc_sa_smk_01(patched_records):
    """UC-SA-SMK-01: EURUSD mock Paper open+close; qualify uses conId 12087792 / EUR.USD."""
    client = _make_client_with_mock_ib()
    _wire_ib_events(client._ib)
    client._ib.qualifyContractsAsync = _make_qualify_for_pair("EURUSD", 12087792, "EUR.USD")
    client._events_registered = False
    client._register_events()

    r1, r2, _place_calls = _run_open_close_cycle(client, "EURUSD", 10000.0)
    assert isinstance(r1, LiveOrderResult) and r1.success
    assert isinstance(r2, LiveOrderResult) and r2.success


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
def test_forex_paper_smoke_gbpjpy_uc_sa_smk_02(patched_records):
    """UC-SA-SMK-02: GBPJPY cross; fake conId 12345678 / GBP.JPY."""
    client = _make_client_with_mock_ib()
    _wire_ib_events(client._ib)
    client._ib.qualifyContractsAsync = _make_qualify_for_pair("GBPJPY", 12345678, "GBP.JPY")
    client._events_registered = False
    client._register_events()

    r1, r2, _place_calls = _run_open_close_cycle(client, "GBPJPY", 10000.0)
    assert r1.success and r2.success


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
def test_forex_paper_smoke_xagusd_uc_sa_smk_03(patched_records):
    """UC-SA-SMK-03 / UC-16-T6-01: XAGUSD Metals path; qualify CMDTY/SMART; conId 77124483."""
    client = _make_client_with_mock_ib()
    _wire_ib_events(client._ib)
    client._ib.qualifyContractsAsync = _make_qualify_for_pair(
        "XAGUSD", 77124483, "XAGUSD", sec_type="CMDTY"
    )
    client._events_registered = False
    client._register_events()

    r1, r2, place_calls = _run_open_close_cycle(
        client,
        "XAGUSD",
        10000.0,
        market_type="Metals",
        market_category="Metals",
    )
    assert r1.success and r2.success
    assert place_calls[0].contract.secType == "CMDTY"
