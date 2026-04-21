"""Tests for structured sufficiency logging."""

import pathlib
from unittest.mock import MagicMock

from app.services.data_sufficiency_logging import (
    build_ibkr_data_sufficiency_check_payload,
    build_ibkr_open_blocked_insufficient_data_payload,
    emit_ibkr_data_sufficiency_check,
    emit_ibkr_open_blocked_insufficient_data,
)
from app.services.data_sufficiency_types import (
    DataSufficiencyDiagnostics,
    DataSufficiencyReasonCode,
    DataSufficiencyResult,
    IBKRScheduleStatus,
    effective_lookback_seconds,
    missing_window_seconds,
)


def _result(reason: DataSufficiencyReasonCode, st: IBKRScheduleStatus):
    diag = DataSufficiencyDiagnostics(
        parsed_session_count=1,
        schedule_failure_reason=None,
        timezone_id="EST",
        timezone_resolution="explicit",
        prev_close_stale_since=None,
        con_id=42,
    )
    return DataSufficiencyResult(
        sufficient=reason == DataSufficiencyReasonCode.SUFFICIENT,
        reason_code=reason,
        required_bars=10,
        available_bars=10,
        effective_lookback=effective_lookback_seconds("1H", 10),
        missing_window=missing_window_seconds("1H", 10, 10),
        schedule_status=st,
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        diagnostics=diag,
    )


def test_sufficient_log_payload():
    r = _result(DataSufficiencyReasonCode.SUFFICIENT, IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN)
    p = build_ibkr_data_sufficiency_check_payload(r)
    assert p["event"] == "ibkr_data_sufficiency_check"
    assert p["reason_code"] == "sufficient"
    assert p["required_bars"] == 10
    assert p["available_bars"] == 10
    assert p["con_id"] == 42


def test_unknown_schedule_log_payload():
    r = _result(DataSufficiencyReasonCode.UNKNOWN_SCHEDULE, IBKRScheduleStatus.SCHEDULE_UNKNOWN)
    p = build_ibkr_data_sufficiency_check_payload(r)
    assert p["event"] == "ibkr_data_sufficiency_check"
    assert p["reason_code"] == "unknown_schedule"
    assert p["schedule_status"] == "schedule_unknown"


def test_no_raw_broker_payload():
    r = DataSufficiencyResult(
        sufficient=False,
        reason_code=DataSufficiencyReasonCode.UNKNOWN_SCHEDULE,
        required_bars=1,
        available_bars=1,
        effective_lookback=effective_lookback_seconds("1H", 1),
        missing_window=0.0,
        schedule_status=IBKRScheduleStatus.SCHEDULE_UNKNOWN,
        symbol="X",
        timeframe="1H",
        market_category="USStock",
        diagnostics=DataSufficiencyDiagnostics(
            parsed_session_count=0,
            schedule_failure_reason="empty_or_unparsable_schedule",
            timezone_id="EST",
            timezone_resolution="explicit",
            prev_close_stale_since=None,
            con_id=None,
        ),
    )
    p = build_ibkr_data_sufficiency_check_payload(r)
    assert "liquidHours" not in p
    assert "contract_details" not in p


def test_market_closed_gap_log_payload():
    r = _result(DataSufficiencyReasonCode.MARKET_CLOSED_GAP, IBKRScheduleStatus.SCHEDULE_KNOWN_CLOSED)
    p = build_ibkr_data_sufficiency_check_payload(r)
    assert p["reason_code"] == "market_closed_gap"
    assert p["schedule_status"] == "schedule_known_closed"


def test_emit_once_per_call():
    r = _result(DataSufficiencyReasonCode.SUFFICIENT, IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN)
    p = build_ibkr_data_sufficiency_check_payload(r)
    log = MagicMock()
    emit_ibkr_data_sufficiency_check(p, logger=log)
    assert log.info.call_count == 1


def test_blocked_open_payload_required_keys():
    r = _result(DataSufficiencyReasonCode.MISSING_BARS, IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN)
    p = build_ibkr_open_blocked_insufficient_data_payload(
        result=r,
        strategy_id=7,
        symbol="SPY",
        exchange_id="ibkr-paper",
        execution_mode="live",
        signal_type_raw="open_long",
        effective_intent="open_long",
        synthetic_evaluation_failure=False,
    )
    required = {
        "event",
        "strategy_id",
        "symbol",
        "exchange_id",
        "execution_mode",
        "signal_type_raw",
        "effective_intent",
        "sufficient",
        "reason_code",
        "required_bars",
        "available_bars",
        "effective_lookback",
        "missing_window",
        "schedule_status",
        "synthetic_evaluation_failure",
        "diagnostics_con_id",
    }
    assert required == set(p.keys())
    assert p["event"] == "ibkr_open_blocked_insufficient_data"
    assert p["synthetic_evaluation_failure"] is False
    assert p["reason_code"] == "missing_bars"
    for k, v in p.items():
        if isinstance(v, str):
            assert len(v) <= 512, k


def test_blocked_open_payload_synthetic_evaluation_failed():
    diag = DataSufficiencyDiagnostics(
        parsed_session_count=1,
        schedule_failure_reason=None,
        timezone_id="EST",
        timezone_resolution="explicit",
        prev_close_stale_since=None,
        con_id=None,
    )
    r = DataSufficiencyResult(
        sufficient=False,
        reason_code=DataSufficiencyReasonCode.DATA_EVALUATION_FAILED,
        required_bars=10,
        available_bars=0,
        effective_lookback=effective_lookback_seconds("1H", 10),
        missing_window=missing_window_seconds("1H", 10, 0),
        schedule_status=IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN,
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        diagnostics=diag,
    )
    p = build_ibkr_open_blocked_insufficient_data_payload(
        result=r,
        strategy_id=1,
        symbol="SPY",
        exchange_id="ibkr-live",
        execution_mode="live",
        signal_type_raw="open_long",
        effective_intent="open_long",
        synthetic_evaluation_failure=True,
    )
    assert p["synthetic_evaluation_failure"] is True
    assert p["reason_code"] == "data_evaluation_failed"
    assert "diagnostics_con_id" not in p


def test_emit_blocked_open_log_smoke():
    r = _result(DataSufficiencyReasonCode.MISSING_BARS, IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN)
    p = build_ibkr_open_blocked_insufficient_data_payload(
        result=r,
        strategy_id=1,
        symbol="SPY",
        exchange_id="ibkr-paper",
        execution_mode="live",
        signal_type_raw="open_long",
        effective_intent="open_long",
        synthetic_evaluation_failure=False,
    )
    log = MagicMock()
    emit_ibkr_open_blocked_insufficient_data(p, logger=log)
    assert log.info.call_count == 1
    call_kw = log.info.call_args[1]["extra"]
    assert call_kw.get("event") == "ibkr_open_blocked_insufficient_data"


def test_logging_module_does_not_define_phase3_alert_event():
    root = pathlib.Path(__file__).resolve().parents[1]
    src = (root / "app/services/data_sufficiency_logging.py").read_text(encoding="utf-8")
    assert "ibkr_insufficient_data_alert_sent" not in src
    assert "persist_notification" not in src