"""Unit tests for pure sufficiency classification."""

import datetime

import pytest

from app.services.data_sufficiency_types import (
    DataSufficiencyDiagnostics,
    FreshnessMetadata,
    IBKRScheduleStatus,
    TIMEFRAME_SECONDS_MAP,
)
from app.services.data_sufficiency_validator import (
    classify_data_sufficiency,
    compute_available_bars_from_kline_fetcher,
)


def _diag():
    return DataSufficiencyDiagnostics(
        parsed_session_count=1,
        schedule_failure_reason=None,
        timezone_id="EST",
        timezone_resolution="explicit",
        prev_close_stale_since=None,
        con_id=1,
    )


def test_available_bars_equals_required_bars():
    r = classify_data_sufficiency(
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        required_bars=100,
        available_bars=100,
        schedule_status=IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN,
        diagnostics=_diag(),
    )
    assert r.sufficient is True
    assert r.reason_code.value == "sufficient"


def test_missing_bars():
    r = classify_data_sufficiency(
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        required_bars=100,
        available_bars=80,
        schedule_status=IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN,
        diagnostics=_diag(),
    )
    assert r.sufficient is False
    assert r.reason_code.value == "missing_bars"
    assert r.missing_window > 0.0


def test_unknown_schedule():
    r = classify_data_sufficiency(
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        required_bars=100,
        available_bars=50,
        schedule_status=IBKRScheduleStatus.SCHEDULE_UNKNOWN,
        diagnostics=_diag(),
    )
    assert r.reason_code.value == "unknown_schedule"


def test_market_closed_gap():
    r = classify_data_sufficiency(
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        required_bars=10,
        available_bars=500,
        schedule_status=IBKRScheduleStatus.SCHEDULE_KNOWN_CLOSED,
        diagnostics=_diag(),
    )
    assert r.reason_code.value == "market_closed_gap"


def test_stale_prev_close():
    meta = FreshnessMetadata(
        prev_close_timestamp_utc=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        prev_close_age_seconds=3600.0,
    )
    r = classify_data_sufficiency(
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        required_bars=10,
        available_bars=3,
        schedule_status=IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN,
        freshness=meta,
        diagnostics=_diag(),
    )
    assert r.reason_code.value == "stale_prev_close"


def test_precedence_unknown_schedule_over_missing_bars():
    r = classify_data_sufficiency(
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        required_bars=100,
        available_bars=50,
        schedule_status=IBKRScheduleStatus.SCHEDULE_UNKNOWN,
        diagnostics=_diag(),
    )
    assert r.reason_code.value == "unknown_schedule"


def test_aggregation_1h_from_5m_mocked_get_kline():
    """Uses ``_AGG_LOWER_LEVELS`` mirroring ``kline_fetcher.LOWER_LEVELS`` (1H → 5m → 1m).

    This encodes only the lower-timeframe walk order and bucket math; it is not a
    substitute for production ``get_kline`` integration drift checks (Phase 2).
    """

    def get_kline(market, symbol, tf, limit, before_time=None):
        if tf == "1H":
            return []
        if tf == "5m":
            return [
                {"time": i * 300, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}
                for i in range(600)
            ]
        if tf == "1m":
            return []
        return []

    n = compute_available_bars_from_kline_fetcher(
        "USStock", "SPY", "1H", 10, None, get_kline
    )
    assert n >= 10
    assert n == 50


def test_missing_window_zero_when_sufficient():
    r = classify_data_sufficiency(
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        required_bars=10,
        available_bars=10,
        schedule_status=IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN,
        diagnostics=_diag(),
    )
    assert r.sufficient is True
    assert abs(r.missing_window - 0.0) < 1e-6


def test_effective_lookback_seconds_boundary():
    r = classify_data_sufficiency(
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        required_bars=10,
        available_bars=10,
        schedule_status=IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN,
        diagnostics=_diag(),
    )
    expected = 10.0 * float(TIMEFRAME_SECONDS_MAP["1H"])
    assert abs(r.effective_lookback - expected) < 1e-6


def test_get_kline_raises_documented_behavior():
    def boom(*_a, **_k):
        raise ValueError("kline down")

    with pytest.raises(ValueError, match="kline down"):
        compute_available_bars_from_kline_fetcher(
            "USStock", "SPY", "1H", 5, None, boom
        )


def test_cross_day_session():
    r = classify_data_sufficiency(
        symbol="EURUSD",
        timeframe="1H",
        market_category="Forex",
        required_bars=5,
        available_bars=100,
        schedule_status=IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN,
        diagnostics=_diag(),
    )
    assert r.reason_code.value != "unknown_schedule"