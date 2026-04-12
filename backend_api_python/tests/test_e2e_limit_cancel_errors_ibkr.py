"""TRADE-06: Limit-order E2E with mock IBKR — fills, partials, cancel branches, errors.

Covers `IBKRClient._on_order_status` for `Filled`, `PartiallyFilled`, and `Cancelled`
with `filled>0` vs `filled<=0` (see `client.py` ~500–508), plus qualify and
`place_limit_order` validation failures.
"""

from __future__ import annotations

from unittest.mock import patch

from tests.helpers.ibkr_mocks import (
    _fire_callbacks_after_fill,
    _make_ibkr_client_for_e2e,
    _make_mock_ib_insync,
)


# ---------------------------------------------------------------------------
# TRADE-06 core: limit fill, partial → filled, cancel branches
# ---------------------------------------------------------------------------


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.live_trading.records.mark_order_failed")
@patch("app.services.live_trading.records.mark_order_sent")
def test_trade06_limit_filled_full_mock(
    mock_sent,
    mock_failed,
    patched_records,
):
    """TRADE-06: Forex limit via `place_limit_order` → terminal `Filled` drives `_handle_fill`.

    Simulates IBKR stream through `_on_order_status` / `_fire_callbacks_after_fill`.
    """
    ibkr_client, place_calls = _make_ibkr_client_for_e2e(
        "EURUSD", 12087792, "EUR.USD", min_tick=0.00005,
    )
    res = ibkr_client.place_limit_order(
        "EURUSD",
        "buy",
        20000.0,
        1.13456,
        market_type="Forex",
        pending_order_id=601,
        strategy_id=1,
        signal_type="open_long",
    )
    assert res.success is True
    assert len(place_calls) == 1
    mock_failed.assert_not_called()

    t = place_calls[0]
    _fire_callbacks_after_fill(
        ibkr_client, t, 20000.0, position_after=20000.0, fill_tag="trade06_eurusd",
    )
    mock_sent.assert_called_once()


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.live_trading.records.update_pending_order_fill_snapshot")
@patch("app.services.live_trading.records.mark_order_failed")
@patch("app.services.live_trading.records.mark_order_sent")
def test_trade06_limit_partial_then_filled(
    mock_sent,
    mock_failed,
    mock_snapshot,
    patched_records,
):
    """TRADE-06: `PartiallyFilled` snapshots then terminal `Filled` → single `_handle_fill`."""
    ibkr_client, place_calls = _make_ibkr_client_for_e2e(
        "EURUSD", 12087792, "EUR.USD", min_tick=0.00005,
    )
    res = ibkr_client.place_limit_order(
        "EURUSD",
        "buy",
        10000.0,
        1.135,
        market_type="Forex",
        pending_order_id=602,
        strategy_id=5,
        signal_type="open_long",
    )
    assert res.success is True
    assert len(place_calls) == 1
    trade = place_calls[0]
    trade.order.totalQuantity = 10000.0

    trade.orderStatus.status = "PartiallyFilled"
    trade.orderStatus.filled = 3000.0
    trade.orderStatus.remaining = 7000.0
    trade.orderStatus.avgFillPrice = 1.135
    ibkr_client._on_order_status(trade)
    assert mock_snapshot.call_count == 1

    trade.orderStatus.filled = 7000.0
    trade.orderStatus.remaining = 3000.0
    ibkr_client._on_order_status(trade)
    assert mock_snapshot.call_count == 2

    trade.orderStatus.status = "Filled"
    trade.orderStatus.filled = 10000.0
    trade.orderStatus.remaining = 0.0
    trade.orderStatus.avgFillPrice = 1.1348

    with patch.object(ibkr_client, "_handle_fill") as mock_handle_fill:
        ibkr_client._on_order_status(trade)
        mock_handle_fill.assert_called_once()
        args = mock_handle_fill.call_args[0]
        assert args[1] == 10000.0
        assert abs(args[2] - 1.1348) < 1e-9

    assert mock_snapshot.call_count == 2
    mock_failed.assert_not_called()
    mock_sent.assert_not_called()


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.live_trading.records.mark_order_failed")
@patch("app.services.live_trading.records.mark_order_sent")
def test_trade06_cancelled_filled_zero_marks_reject_path(
    mock_sent,
    mock_failed,
    patched_records,
):
    """TRADE-06: `Cancelled` + `filled<=0` → `_handle_reject` / `mark_order_failed` (DAY expiry, no fill)."""
    ibkr_client, place_calls = _make_ibkr_client_for_e2e(
        "EURUSD", 12087792, "EUR.USD", min_tick=0.00005,
    )
    res = ibkr_client.place_limit_order(
        "EURUSD",
        "buy",
        5000.0,
        1.12,
        market_type="Forex",
        pending_order_id=603,
        strategy_id=2,
        signal_type="open_long",
    )
    assert res.success is True
    trade = place_calls[0]
    trade.orderStatus.status = "Cancelled"
    trade.orderStatus.filled = 0.0
    trade.orderStatus.avgFillPrice = 0.0
    trade.log = []

    ibkr_client._on_order_status(trade)

    mock_failed.assert_called_once()
    mock_sent.assert_not_called()
    call_kw = mock_failed.call_args[1]
    assert call_kw["order_id"] == 603
    assert "ibkr_Cancelled" in (call_kw.get("error") or "")


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.live_trading.records.mark_order_failed")
@patch("app.services.live_trading.records.mark_order_sent")
def test_trade06_cancelled_filled_positive_marks_fill_path(
    mock_sent,
    mock_failed,
    patched_records,
):
    """TRADE-06: `Cancelled` + `filled>0` → `_handle_fill` (partial fill before cancel)."""
    ibkr_client, place_calls = _make_ibkr_client_for_e2e(
        "GBPJPY", 12345678, "GBP.JPY", min_tick=0.005,
    )
    res = ibkr_client.place_limit_order(
        "GBPJPY",
        "sell",
        8000.0,
        192.12,
        market_type="Forex",
        pending_order_id=604,
        strategy_id=3,
        signal_type="close_long",
    )
    assert res.success is True
    trade = place_calls[0]
    trade.orderStatus.status = "Cancelled"
    trade.orderStatus.filled = 3000.0
    trade.orderStatus.avgFillPrice = 192.11
    trade.orderStatus.remaining = 0.0

    ibkr_client._on_order_status(trade)

    mock_failed.assert_not_called()
    mock_sent.assert_called_once()
    assert mock_sent.call_args[1]["filled"] == 3000.0


# ---------------------------------------------------------------------------
# Error paths: qualify, post-qualify validation, non-positive limit price
# ---------------------------------------------------------------------------


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
def test_error_qualify_raises_no_security_definition(patched_records):
    """Qualify raises Error 200 / no definition → `place_limit_order` fails; cache not retained.

    Rejection layer: `IBKRClient._qualify_contract_async` (exception branch) in
    `app/services/live_trading/ibkr_trading/client.py`.
    """
    ibkr_client, _place_calls = _make_ibkr_client_for_e2e(
        "EURUSD", 12087792, "EUR.USD", min_tick=0.00005,
    )

    async def _boom(*_contracts):
        raise RuntimeError("200: No security definition has been found for request")

    ibkr_client._ib.qualifyContractsAsync = _boom

    res = ibkr_client.place_limit_order(
        "EURUSD",
        "buy",
        1000.0,
        1.1,
        market_type="Forex",
    )
    assert res.success is False
    assert "Invalid" in (res.message or "") or "contract" in (res.message or "").lower()
    assert ("EURUSD", "Forex") not in ibkr_client._qualify_cache


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
def test_error_post_qualify_validation_rejects(patched_records):
    """Post-qualify `secType` mismatch for Forex → `LiveOrderResult(success=False)`.

    Rejection layer: `IBKRClient._validate_qualified_contract` after
    `_qualify_contract_async` in `app/services/live_trading/ibkr_trading/client.py`.
    """
    ibkr_client, _place_calls = _make_ibkr_client_for_e2e(
        "EURUSD", 12087792, "EUR.USD", min_tick=0.00005,
    )

    async def _wrong_sec(*contracts):
        for c in contracts:
            c.conId = 12087792
            c.localSymbol = "EUR.USD"
            c.secType = "STK"
        return list(contracts)

    ibkr_client._ib.qualifyContractsAsync = _wrong_sec

    res = ibkr_client.place_limit_order(
        "EURUSD",
        "buy",
        1000.0,
        1.1,
        market_type="Forex",
    )
    assert res.success is False
    assert "secType" in (res.message or "")
    assert ("EURUSD", "Forex") not in ibkr_client._qualify_cache


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
def test_error_limit_price_non_positive_rejected(patched_records):
    """Limit price snaps to non-positive → reject at `place_limit_order` (no enqueue).

    Rejection layer: `IBKRClient.place_limit_order` (snap/validation) in
    `app/services/live_trading/ibkr_trading/client.py`.
    """
    ibkr_client, place_calls = _make_ibkr_client_for_e2e(
        "EURUSD", 12087792, "EUR.USD", min_tick=0.00005,
    )
    res = ibkr_client.place_limit_order(
        "EURUSD",
        "buy",
        1000.0,
        0.0,
        market_type="Forex",
    )
    assert res.success is False
    assert "non-positive" in (res.message or "").lower() or "positive" in (res.message or "").lower()
    assert len(place_calls) == 0
