"""Tests for kline_fetcher wall-clock range multiplier (RTH + weekends + holiday headroom)."""

from app.services import kline_fetcher as kf


def test_intraday_equity_multiplier_includes_weekend_and_holiday_headroom():
    m = kf._range_window_seconds_multiplier("USStock", 3600)
    assert abs(m - (24.0 / 6.5) * (7.0 / 5.0) * 2.0) < 1e-9


def test_daily_rth_equity_scales_for_weekends_and_holidays():
    expected = (7.0 / 5.0) * 1.5
    assert kf._range_window_seconds_multiplier("USStock", 86400) == expected
    assert kf._range_window_seconds_multiplier("IndexETF", 86400) == expected


def test_weekly_timeframe_no_multiplier():
    assert kf._range_window_seconds_multiplier("USStock", 604800) == 1.0
    assert kf._range_window_seconds_multiplier("IndexETF", 604800) == 1.0


def test_forex_daily_unscaled():
    assert kf._range_window_seconds_multiplier("Forex", 86400) == 1.0


def test_forex_intraday_unscaled():
    assert kf._range_window_seconds_multiplier("Forex", 3600) == 1.0


def test_hk_and_a_share_match_us_intraday():
    base = (24.0 / 6.5) * (7.0 / 5.0) * 2.0
    assert kf._range_window_seconds_multiplier("HShare", 300) == base
    assert kf._range_window_seconds_multiplier("AShare", 60) == base


def test_index_etf_intraday_matches_us_stock():
    base = (24.0 / 6.5) * (7.0 / 5.0) * 2.0
    assert kf._range_window_seconds_multiplier("IndexETF", 3600) == base
