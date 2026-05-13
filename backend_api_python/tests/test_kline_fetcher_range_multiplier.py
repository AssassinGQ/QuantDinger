"""Tests for kline_fetcher wall-clock range multiplier (RTH + weekends)."""

from app.services import kline_fetcher as kf


def test_intraday_equity_multiplier_includes_weekend_stretch():
    m = kf._range_window_seconds_multiplier("USStock", 3600)
    assert abs(m - (24.0 / 6.5) * (7.0 / 5.0) * 2) < 1e-9


def test_daily_timeframe_no_multiplier():
    assert kf._range_window_seconds_multiplier("USStock", 86400) == 1.0


def test_forex_intraday_unscaled():
    assert kf._range_window_seconds_multiplier("Forex", 3600) == 1.0


def test_hk_and_a_share_match_us_intraday():
    base = (24.0 / 6.5) * (7.0 / 5.0) * 2
    assert kf._range_window_seconds_multiplier("HShare", 300) == base
    assert kf._range_window_seconds_multiplier("AShare", 60) == base
