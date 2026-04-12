"""Tests for PendingOrderWorker live path (category gate)."""

from unittest.mock import MagicMock, patch

from app.services.live_trading.base import ExecutionResult
from app.services.live_trading.ibkr_trading.client import IBKRClient
from app.services.live_trading.runners.base import PreCheckResult
from app.services.pending_order_worker import PendingOrderWorker


def _ibkr_forex_cfg():
    return {
        "market_category": "Forex",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "forex",
    }


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
    mock_load_cfg.return_value = _ibkr_forex_cfg()
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


@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.records.load_notification_config")
@patch("app.services.pending_order_worker.get_runner")
@patch("app.services.pending_order_worker.create_client")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_uc_03g_order_context_includes_limit_price_and_payload_order_type(
    mock_load_cfg,
    mock_create,
    mock_get_runner,
    mock_load_notif,
    mock_failed,
    mock_sent,
    _mock_notify,
):
    mock_load_cfg.return_value = _ibkr_forex_cfg()
    mock_create.return_value = IBKRClient.__new__(IBKRClient)
    mock_load_notif.return_value = {"email": True}

    runner = MagicMock()
    runner.pre_check.return_value = PreCheckResult(ok=True)
    runner.execute.return_value = ExecutionResult(
        success=True,
        exchange_id="ibkr",
        exchange_order_id="test-limit",
        note="live_order_submitted",
    )
    mock_get_runner.return_value = runner

    w = PendingOrderWorker()
    order_row = {
        "strategy_id": 1,
        "symbol": "EURUSD",
        "signal_type": "open_long",
        "amount": 10000.0,
        "price": 1.2,
        "order_type": "limit",
    }
    payload = {
        "strategy_id": 1,
        "symbol": "EURUSD",
        "signal_type": "open_long",
        "amount": 10000.0,
        "price": 1.2,
        "order_type": "limit",
        "notification_config": {},
    }
    w._execute_live_order(order_id=50, order_row=order_row, payload=payload)

    oc = runner.execute.call_args[1]["order_context"]
    assert abs(oc.price - 1.2) < 1e-9
    assert oc.notification_config == {"email": True}
    assert oc.payload.get("order_type") == "limit"


@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.records.load_notification_config")
@patch("app.services.pending_order_worker.get_runner")
@patch("app.services.pending_order_worker.create_client")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_uc_03g_fallback_limit_price_from_payload_when_row_price_missing(
    mock_load_cfg,
    mock_create,
    mock_get_runner,
    mock_load_notif,
    mock_failed,
    mock_sent,
    _mock_notify,
):
    mock_load_cfg.return_value = _ibkr_forex_cfg()
    mock_create.return_value = IBKRClient.__new__(IBKRClient)
    mock_load_notif.return_value = {}

    runner = MagicMock()
    runner.pre_check.return_value = PreCheckResult(ok=True)
    runner.execute.return_value = ExecutionResult(
        success=True, exchange_id="ibkr", exchange_order_id="y", note="ok",
    )
    mock_get_runner.return_value = runner

    w = PendingOrderWorker()
    order_row = {
        "strategy_id": 1,
        "symbol": "EURUSD",
        "signal_type": "open_long",
        "amount": 100.0,
        "price": None,
        "order_type": "limit",
    }
    payload = {
        "strategy_id": 1,
        "limit_price": 1.255,
        "order_type": "limit",
        "notification_config": {},
    }
    w._execute_live_order(order_id=51, order_row=order_row, payload=payload)

    oc = runner.execute.call_args[1]["order_context"]
    assert abs(oc.price - 1.255) < 1e-9


@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.records.load_notification_config")
@patch("app.services.pending_order_worker.get_runner")
@patch("app.services.pending_order_worker.create_client")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_uc_03h_notification_config_from_payload_skips_db_load(
    mock_load_cfg,
    mock_create,
    mock_get_runner,
    mock_load_notif,
    mock_failed,
    mock_sent,
    _mock_notify,
):
    mock_load_cfg.return_value = _ibkr_forex_cfg()
    mock_create.return_value = IBKRClient.__new__(IBKRClient)

    runner = MagicMock()
    runner.pre_check.return_value = PreCheckResult(ok=True)
    runner.execute.return_value = ExecutionResult(
        success=True, exchange_id="ibkr", exchange_order_id="z", note="ok",
    )
    mock_get_runner.return_value = runner

    w = PendingOrderWorker()
    order_row, payload = _minimal_live_order()
    payload["notification_config"] = {"telegram": {"enabled": True}}

    w._execute_live_order(order_id=52, order_row=order_row, payload=payload)

    mock_load_notif.assert_not_called()
    oc = runner.execute.call_args[1]["order_context"]
    assert oc.notification_config == {"telegram": {"enabled": True}}
