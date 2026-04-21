"""Unit tests for typed data sufficiency contracts."""

import importlib

import pytest

from app.services.data_sufficiency_types import (
    DataSufficiencyDiagnostics,
    DataSufficiencyReasonCode,
    DataSufficiencyResult,
    IBKRScheduleStatus,
    effective_lookback_seconds,
    missing_window_seconds,
)


def test_reason_enum_values_match_requirement_literals():
    assert DataSufficiencyReasonCode.SUFFICIENT.value == "sufficient"
    assert DataSufficiencyReasonCode.MISSING_BARS.value == "missing_bars"
    assert DataSufficiencyReasonCode.STALE_PREV_CLOSE.value == "stale_prev_close"
    assert DataSufficiencyReasonCode.MARKET_CLOSED_GAP.value == "market_closed_gap"
    assert DataSufficiencyReasonCode.UNKNOWN_SCHEDULE.value == "unknown_schedule"


def test_equal_boundary():
    eff = effective_lookback_seconds("1H", 100)
    miss = missing_window_seconds("1H", 100, 100)
    diag = DataSufficiencyDiagnostics(
        parsed_session_count=1,
        schedule_failure_reason=None,
        timezone_id="EST",
        timezone_resolution="explicit",
        prev_close_stale_since=None,
        con_id=1,
    )
    res = DataSufficiencyResult(
        sufficient=True,
        reason_code=DataSufficiencyReasonCode.SUFFICIENT,
        required_bars=100,
        available_bars=100,
        effective_lookback=eff,
        missing_window=miss,
        schedule_status=IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN,
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        diagnostics=diag,
    )
    assert res.sufficient is True
    assert res.reason_code == DataSufficiencyReasonCode.SUFFICIENT
    assert abs(res.missing_window - 0.0) < 1e-6


def test_missing_bars_contract():
    eff = effective_lookback_seconds("1H", 100)
    miss = missing_window_seconds("1H", 100, 99)
    diag = DataSufficiencyDiagnostics(
        parsed_session_count=1,
        schedule_failure_reason=None,
        timezone_id="EST",
        timezone_resolution="explicit",
        prev_close_stale_since=None,
        con_id=None,
    )
    res = DataSufficiencyResult(
        sufficient=False,
        reason_code=DataSufficiencyReasonCode.MISSING_BARS,
        required_bars=100,
        available_bars=99,
        effective_lookback=eff,
        missing_window=miss,
        schedule_status=IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN,
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        diagnostics=diag,
    )
    assert res.reason_code == DataSufficiencyReasonCode.MISSING_BARS
    assert res.missing_window > 0.0


def test_unknown_schedule_contract():
    diag = DataSufficiencyDiagnostics(
        parsed_session_count=0,
        schedule_failure_reason="empty_or_unparsable_schedule",
        timezone_id="EST",
        timezone_resolution="explicit",
        prev_close_stale_since=None,
        con_id=None,
    )
    res = DataSufficiencyResult(
        sufficient=False,
        reason_code=DataSufficiencyReasonCode.UNKNOWN_SCHEDULE,
        required_bars=10,
        available_bars=10,
        effective_lookback=effective_lookback_seconds("1H", 10),
        missing_window=0.0,
        schedule_status=IBKRScheduleStatus.SCHEDULE_UNKNOWN,
        symbol="X",
        timeframe="1H",
        market_category="USStock",
        diagnostics=diag,
    )
    assert res.reason_code == DataSufficiencyReasonCode.UNKNOWN_SCHEDULE
    assert res.schedule_status == IBKRScheduleStatus.SCHEDULE_UNKNOWN


def test_closed_session_contract():
    diag = DataSufficiencyDiagnostics(
        parsed_session_count=1,
        schedule_failure_reason=None,
        timezone_id="EST",
        timezone_resolution="explicit",
        prev_close_stale_since=None,
        con_id=None,
    )
    res = DataSufficiencyResult(
        sufficient=False,
        reason_code=DataSufficiencyReasonCode.MARKET_CLOSED_GAP,
        required_bars=10,
        available_bars=500,
        effective_lookback=effective_lookback_seconds("1H", 10),
        missing_window=0.0,
        schedule_status=IBKRScheduleStatus.SCHEDULE_KNOWN_CLOSED,
        symbol="X",
        timeframe="1H",
        market_category="USStock",
        diagnostics=diag,
    )
    assert res.reason_code == DataSufficiencyReasonCode.MARKET_CLOSED_GAP
    assert res.reason_code != DataSufficiencyReasonCode.UNKNOWN_SCHEDULE
    assert res.schedule_status == IBKRScheduleStatus.SCHEDULE_KNOWN_CLOSED


def test_types_import_smoke():
    m = importlib.import_module("app.services.data_sufficiency_types")
    assert hasattr(m, "DataSufficiencyResult")
    assert hasattr(m, "TIMEFRAME_SECONDS_MAP")