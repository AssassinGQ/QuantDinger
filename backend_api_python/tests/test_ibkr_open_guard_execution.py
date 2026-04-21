"""Phase 2 IBKR open-path sufficiency guard execution tests."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest
import pytz

from app.services.data_sufficiency_guard import (
    contract_details_missing_fail_closed,
    evaluate_ibkr_open_data_sufficiency,
)
from app.services.data_sufficiency_types import (
    DataSufficiencyReasonCode,
)
from app.services.signal_executor import SignalExecutor


@pytest.fixture
def signal_executor():
    ex = SignalExecutor()
    ex.data_handler = MagicMock()
    ex.pending_order_enqueuer = MagicMock()
    return ex


def test_guard_façade_maps_exception_to_data_evaluation_failed():
    details = MagicMock()
    details.liquidHours = "20260305:0930-20260305:1600"
    details.timeZoneId = "EST"

    with patch(
        "app.services.data_sufficiency_guard.evaluate_ibkr_data_sufficiency_and_log",
        side_effect=RuntimeError("kline boom"),
    ):
        result = evaluate_ibkr_open_data_sufficiency(
            details,
            server_time_utc=datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC),
            symbol="SPY",
            timeframe="1H",
            market_category="USStock",
            required_bars=10,
            before_time_utc=None,
            con_id=1,
            logger=MagicMock(),
        )

    assert result.reason_code == DataSufficiencyReasonCode.DATA_EVALUATION_FAILED
    assert result.sufficient is False
    assert result.diagnostics.evaluation_error_summary is not None


def test_contract_missing_fail_closed_is_insufficient():
    r = contract_details_missing_fail_closed(
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        required_bars=50,
        con_id=0,
    )
    assert r.sufficient is False
    assert r.reason_code == DataSufficiencyReasonCode.DATA_EVALUATION_FAILED


@patch("app.services.kline_fetcher.get_kline")
def test_execution_path_get_kline_lower_levels_alignment(mock_get_kline):
    """LOWER_LEVELS seam: 1H empty → 5m seed bars (aligned with Phase 1 integration test)."""

    def _side(market, symbol, tf, limit=1000, before_time=None):
        if tf == "1H":
            return []
        if tf == "5m":
            return [
                {"time": i * 300, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}
                for i in range(600)
            ]
        return []

    mock_get_kline.side_effect = _side

    details = MagicMock()
    details.liquidHours = "20260305:0930-20260305:1600"
    details.timeZoneId = "EST"
    server_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)

    evaluate_ibkr_open_data_sufficiency(
        details,
        server_time_utc=server_utc,
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        required_bars=10,
        before_time_utc=None,
        con_id=3,
        logger=MagicMock(),
    )

    tfs = [c[0][2] for c in mock_get_kline.call_args_list]
    assert "1H" in tfs
    assert "5m" in tfs


@patch("app.services.signal_executor.evaluate_ibkr_open_data_sufficiency")
def test_reduce_path_does_not_invoke_sufficiency_evaluator(
    mock_eval: MagicMock, signal_executor: SignalExecutor
):
    mock_eval.side_effect = AssertionError("sufficiency must not run on reduce")
    signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {
        "success": True
    }

    strategy_ctx = {
        "id": 1,
        "_execution_mode": "live",
        "exchange_config": {"exchange_id": "ibkr-live"},
        "_market_category": "USStock",
        "trading_config": {"timeframe": "1H", "required_bars": 100},
    }
    signal = {"type": "reduce_long", "position_size": 0.5}
    positions = [{"side": "long", "size": 1.0, "entry_price": 100.0}]

    with patch(
        "app.services.signal_executor._get_available_capital", return_value=10000.0
    ):
        signal_executor.execute(
            strategy_ctx,
            signal,
            symbol="SPY",
            current_price=100.0,
            current_positions=positions,
            exchange=None,
        )

    mock_eval.assert_not_called()