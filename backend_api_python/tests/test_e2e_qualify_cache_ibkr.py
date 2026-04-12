"""
E2E-style integration tests: IBKRClient qualify cache (TTL, invalidation, reconnect)
and TRADE-05 metals mock chain (qualify → placeOrder → callbacks).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.pending_order_worker import PendingOrderWorker

from tests.helpers.ibkr_mocks import (
    _fire_callbacks_after_fill,
    _make_ibkr_client_for_e2e,
    _make_mock_ib_insync,
)
from tests.test_ibkr_client import _make_client_with_mock_ib, _make_mock_ib_insync as _client_make_mock_ib


# ---------------------------------------------------------------------------
# Task 1: Qualify cache behaviors
# ---------------------------------------------------------------------------


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _client_make_mock_ib())
def test_qualify_cache_hit_no_second_qualify_call(patched_records):
    """Two Forex market orders within TTL: only one qualifyContractsAsync await."""
    client = _make_client_with_mock_ib()

    async def _qualify_side_effect(*contracts):
        for c in contracts:
            c.conId = 12087792
            c.secType = "CASH"
            c.localSymbol = "EUR.USD"
        return list(contracts)

    mock_q = AsyncMock(side_effect=_qualify_side_effect)
    client._ib.qualifyContractsAsync = mock_q

    mock_trade = MagicMock()
    mock_trade.order.orderId = 42
    client._ib.placeOrder = MagicMock(return_value=mock_trade)

    with patch(
        "app.services.live_trading.ibkr_trading.client.time.monotonic",
        return_value=10_000.0,
    ):
        r1 = client.place_market_order("EURUSD", "buy", 20000, "Forex")
        r2 = client.place_market_order("EURUSD", "buy", 20000, "Forex")

    assert r1.success is True
    assert r2.success is True
    assert mock_q.await_count == 1


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _client_make_mock_ib())
def test_qualify_cache_miss_after_ttl(patched_records, monkeypatch):
    """After TTL elapses (monotonic), second order re-qualifies (two awaits)."""
    monkeypatch.setenv("IBKR_QUALIFY_TTL_FOREX_SEC", "2")

    client = _make_client_with_mock_ib()

    async def _qualify_side_effect(*contracts):
        for c in contracts:
            c.conId = 12087792
            c.secType = "CASH"
            c.localSymbol = "EUR.USD"
        return list(contracts)

    mock_q = AsyncMock(side_effect=_qualify_side_effect)
    client._ib.qualifyContractsAsync = mock_q

    mock_trade = MagicMock()
    mock_trade.order.orderId = 42
    client._ib.placeOrder = MagicMock(return_value=mock_trade)

    mono = {"v": 100.0}

    def _mono():
        return mono["v"]

    with patch(
        "app.services.live_trading.ibkr_trading.client.time.monotonic",
        side_effect=_mono,
    ):
        r1 = client.place_market_order("EURUSD", "buy", 20000, "Forex")
        assert r1.success is True
        assert mock_q.await_count == 1
        # Past expiry: first qualify used now≈100, ttl=2 → expires_at=102
        mono["v"] = 250.0
        r2 = client.place_market_order("EURUSD", "buy", 20000, "Forex")

    assert r2.success is True
    assert mock_q.await_count == 2


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _client_make_mock_ib())
def test_qualify_cache_invalidation_on_qualify_exception(patched_records):
    """qualifyContractsAsync raises → cache cleared; next order qualifies again."""
    client = _make_client_with_mock_ib()

    n = [0]

    async def _qualify_side_effect(*contracts):
        n[0] += 1
        if n[0] == 1:
            raise ValueError("simulated IB qualify failure")
        for c in contracts:
            c.conId = 12087792
            c.secType = "CASH"
            c.localSymbol = "EUR.USD"
        return list(contracts)

    mock_q = AsyncMock(side_effect=_qualify_side_effect)
    client._ib.qualifyContractsAsync = mock_q

    mock_trade = MagicMock()
    mock_trade.order.orderId = 42
    client._ib.placeOrder = MagicMock(return_value=mock_trade)

    r1 = client.place_market_order("EURUSD", "buy", 20000, "Forex")
    assert r1.success is False
    assert ("EURUSD", "Forex") not in client._qualify_cache

    r2 = client.place_market_order("EURUSD", "buy", 20000, "Forex")
    assert r2.success is True
    assert mock_q.await_count == 2


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _client_make_mock_ib())
def test_qualify_cache_invalidation_on_empty_qualify(patched_records):
    """Empty qualify result invalidates; retry path calls IB again."""
    client = _make_client_with_mock_ib()
    mock_ib = _client_make_mock_ib()
    contract = mock_ib.Forex(pair="EURUSD")

    calls = {"n": 0}

    async def _qualify_seq(*contracts):
        calls["n"] += 1
        if calls["n"] == 1:
            for c in contracts:
                c.conId = 1
                c.secType = "CASH"
            return list(contracts)
        return []

    client._ib.qualifyContractsAsync = AsyncMock(side_effect=_qualify_seq)
    mock_trade = MagicMock()
    mock_trade.order.orderId = 1
    client._ib.placeOrder = MagicMock(return_value=mock_trade)

    r1 = client.place_market_order("EURUSD", "buy", 20000, "Forex")
    assert r1.success is True
    assert ("EURUSD", "Forex") in client._qualify_cache

    client._qualify_cache[("EURUSD", "Forex")]["expires_at"] = 0.0
    contract2 = mock_ib.Forex(pair="EURUSD")

    loop = asyncio.new_event_loop()
    try:
        r2 = loop.run_until_complete(
            client._qualify_contract_async(contract2, "EURUSD", "Forex"),
        )
        assert r2 is False
        assert ("EURUSD", "Forex") not in client._qualify_cache
    finally:
        loop.close()

    assert client._ib.qualifyContractsAsync.await_count == 2


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _client_make_mock_ib())
def test_qualify_cache_survives_ibkr_disconnect_connect(patched_records):
    """_on_disconnected / _on_connected do not clear _qualify_cache."""
    client = _make_client_with_mock_ib()

    async def _qualify_side_effect(*contracts):
        for c in contracts:
            c.conId = 12087792
            c.secType = "CASH"
            c.localSymbol = "EUR.USD"
        return list(contracts)

    mock_q = AsyncMock(side_effect=_qualify_side_effect)
    client._ib.qualifyContractsAsync = mock_q

    mock_trade = MagicMock()
    mock_trade.order.orderId = 42
    client._ib.placeOrder = MagicMock(return_value=mock_trade)

    r1 = client.place_market_order("EURUSD", "buy", 20000, "Forex")
    assert r1.success is True
    assert ("EURUSD", "Forex") in client._qualify_cache
    assert mock_q.await_count == 1

    client._on_disconnected()
    client._on_connected()

    assert len(client._qualify_cache) >= 1
    r2 = client.place_market_order("EURUSD", "buy", 20000, "Forex")
    assert r2.success is True
    assert mock_q.await_count == 1


def test_qualify_cache_ttl_forex_vs_usstock_distinct(patched_records, monkeypatch):
    """Env IBKR_QUALIFY_TTL_FOREX_SEC vs IBKR_QUALIFY_TTL_USSTOCK_SEC map to _qualify_ttl_seconds."""
    monkeypatch.setenv("IBKR_QUALIFY_TTL_FOREX_SEC", "10")
    monkeypatch.setenv("IBKR_QUALIFY_TTL_USSTOCK_SEC", "99")
    client = _make_client_with_mock_ib()
    assert client._qualify_ttl_seconds("Forex") == 10
    assert client._qualify_ttl_seconds("USStock") == 99


# ---------------------------------------------------------------------------
# Task 2: TRADE-05 metals chain
# ---------------------------------------------------------------------------


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_trade05_metals_mock_ibkr_qualify_order_callback_xagusd(
    mock_load_cfg,
    mock_failed,
    mock_sent,
    _mock_notify,
    patched_records,
):
    """TRADE-05: Metals XAGUSD CMDTY — PendingOrderWorker → qualify → placeOrder → callbacks."""
    mock_load_cfg.return_value = {
        "market_category": "Metals",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "metals",
    }

    ibkr_client, place_calls = _make_ibkr_client_for_e2e(
        "XAGUSD", 77124483, "XAGUSD", sec_type="CMDTY"
    )

    with patch(
        "app.services.pending_order_worker.create_client",
        return_value=ibkr_client,
    ):
        w = PendingOrderWorker()
        w._execute_live_order(
            order_id=501,
            order_row={
                "strategy_id": 10,
                "symbol": "XAGUSD",
                "signal_type": "open_long",
                "amount": 5000.0,
            },
            payload={
                "strategy_id": 10,
                "symbol": "XAGUSD",
                "signal_type": "open_long",
                "amount": 5000.0,
            },
        )

    assert mock_failed.call_count == 0
    assert mock_sent.call_count == 1
    assert len(place_calls) == 1
    t_open = place_calls[0]
    assert getattr(t_open.contract, "secType", None) == "CMDTY"
    assert getattr(t_open.contract, "symbol", None) == "XAGUSD"

    _fire_callbacks_after_fill(
        ibkr_client, t_open, 5000.0, position_after=5000.0, fill_tag="trade05_xag"
    )

