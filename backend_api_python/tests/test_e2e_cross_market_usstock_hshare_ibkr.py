"""E2E: USStock + HShare full-chain PendingOrderWorker → IBKRClient (mock IBKR).

Cross-market integration (TRADE-05 / TRADE-06) beyond Forex/Metals: normalize, qualify,
and TIF paths for STK on SMART vs SEHK.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import patch

for mod in ("jwt", "psycopg2", "psycopg2.pool", "psycopg2.extras"):
    sys.modules.setdefault(mod, types.ModuleType(mod))

from app.services.pending_order_worker import PendingOrderWorker

from tests.helpers.ibkr_mocks import (
    _fire_callbacks_after_fill,
    _make_ibkr_client_for_e2e,
    _make_mock_ib_insync,
)


# ---------------------------------------------------------------------------
# Task 1: market-order full chain
# ---------------------------------------------------------------------------


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_cross_market_usstock_open_long_full_chain(
    mock_load_cfg,
    mock_failed,
    mock_sent,
    _mock_notify,
    patched_records,
):
    """USStock AAPL: Worker → runner → place_market_order → STK contract; placeOrder called."""
    mock_load_cfg.return_value = {
        "market_category": "USStock",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "usstock",
    }

    ibkr_client, place_calls = _make_ibkr_client_for_e2e("AAPL", 265598, "AAPL", sec_type="STK")

    with patch(
        "app.services.pending_order_worker.create_client",
        return_value=ibkr_client,
    ):
        w = PendingOrderWorker()
        w._execute_live_order(
            order_id=7001,
            order_row={
                "strategy_id": 2,
                "symbol": "AAPL",
                "signal_type": "open_long",
                "amount": 10.0,
            },
            payload={
                "strategy_id": 2,
                "symbol": "AAPL",
                "signal_type": "open_long",
                "amount": 10.0,
            },
        )

    mock_failed.assert_not_called()
    mock_sent.assert_called_once()
    assert len(place_calls) == 1
    trade = place_calls[0]
    assert trade.contract.secType == "STK"
    assert ibkr_client._ib.placeOrder.call_count == 1

    _fire_callbacks_after_fill(
        ibkr_client, trade, 10.0, position_after=10.0, fill_tag="cross_usstock"
    )


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_cross_market_hshare_open_long_full_chain(
    mock_load_cfg,
    mock_failed,
    mock_sent,
    _mock_notify,
    patched_records,
):
    """HShare 0700.HK: Worker → STK + SEHK-style contract; placeOrder called."""
    mock_load_cfg.return_value = {
        "market_category": "HShare",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "hshare",
    }

    ibkr_client, place_calls = _make_ibkr_client_for_e2e(
        "0700.HK", 9919029, "700", sec_type="STK"
    )

    with patch(
        "app.services.pending_order_worker.create_client",
        return_value=ibkr_client,
    ):
        w = PendingOrderWorker()
        w._execute_live_order(
            order_id=7002,
            order_row={
                "strategy_id": 3,
                "symbol": "0700.HK",
                "signal_type": "open_long",
                "amount": 400.0,
            },
            payload={
                "strategy_id": 3,
                "symbol": "0700.HK",
                "signal_type": "open_long",
                "amount": 400.0,
            },
        )

    mock_failed.assert_not_called()
    mock_sent.assert_called_once()
    assert len(place_calls) == 1
    trade = place_calls[0]
    assert trade.contract.secType == "STK"
    assert getattr(trade.contract, "exchange", None) == "SEHK"
    assert ibkr_client._ib.placeOrder.call_count == 1

    _fire_callbacks_after_fill(
        ibkr_client, trade, 400.0, position_after=400.0, fill_tag="cross_hshare"
    )
