"""Tests for PendingOrderWorker live path (category gate)."""

from unittest.mock import MagicMock, patch

from app.services.live_trading.base import ExecutionResult
from app.services.live_trading.ibkr_trading.client import IBKRClient
from app.services.live_trading.runners.base import PreCheckResult
from app.services.pending_order_worker import PendingOrderWorker


def _minimal_live_order(strategy_id: int = 1):
    order_row = {
        "strategy_id": strategy_id,
        "symbol": "EURUSD",
        "signal_type": "close_long",
        "amount": 10000.0,
    }
    payload = dict(order_row)
    return order_row, payload


@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.get_runner")
@patch("app.services.pending_order_worker.create_client")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_live_order_forex_passes_category_gate(
    mock_load_cfg,
    mock_create,
    mock_get_runner,
    mock_failed,
    mock_sent,
    _mock_notify,
):
    """UC-4: Forex is not rejected at validate_market_category; order reaches mark_order_sent."""
    mock_load_cfg.return_value = {
        "market_category": "Forex",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "forex",
    }
    mock_create.return_value = IBKRClient.__new__(IBKRClient)

    runner = MagicMock()
    runner.pre_check.return_value = PreCheckResult(ok=True)
    runner.execute.return_value = ExecutionResult(
        success=True,
        exchange_id="ibkr",
        exchange_order_id="test-1",
        note="live_order_submitted",
    )
    mock_get_runner.return_value = runner

    w = PendingOrderWorker()
    order_row, payload = _minimal_live_order()
    w._execute_live_order(order_id=42, order_row=order_row, payload=payload)

    mock_failed.assert_not_called()
    mock_sent.assert_called_once()
    assert mock_sent.call_args[1].get("order_id") == 42


@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.create_client")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_live_order_crypto_rejected_at_category_gate(
    mock_load_cfg,
    mock_create,
    mock_failed,
    mock_sent,
    _mock_notify,
):
    """UC-5: Crypto still rejected by IBKR validate_market_category before runner."""
    mock_load_cfg.return_value = {
        "market_category": "Crypto",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "swap",
    }
    mock_create.return_value = IBKRClient.__new__(IBKRClient)

    w = PendingOrderWorker()
    order_row, payload = _minimal_live_order(strategy_id=2)
    w._execute_live_order(order_id=43, order_row=order_row, payload=payload)

    mock_sent.assert_not_called()
    mock_failed.assert_called_once()
    err = mock_failed.call_args[1].get("error") or ""
    assert "Crypto" in err
    assert "ibkr only supports" in err
