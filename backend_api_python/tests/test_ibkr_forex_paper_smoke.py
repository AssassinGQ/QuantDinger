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

from tests.helpers.ibkr_mocks import (
    _fire_callbacks_after_fill,
    _make_client_with_mock_ib,
    _make_mock_ib_insync,
    _make_qualify_for_pair,
    _make_trade_mock,
    _wire_ib_events,
)


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
