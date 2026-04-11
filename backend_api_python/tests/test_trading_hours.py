"""Tests for IBKR RTH (Regular Trading Hours) pure logic."""

import datetime
from unittest.mock import MagicMock
import time as _time

import pytz
import pytest

from app.services.live_trading.ibkr_trading.trading_hours import (
    parse_liquid_hours,
    is_rth_check,
    clear_cache,
    _resolve_tz,
    _fuse_until,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


def _make_details(liquid_hours: str, tz_id: str = "EST"):
    """Create a mock ContractDetails with liquidHours and timeZoneId."""
    details = MagicMock()
    details.liquidHours = liquid_hours
    details.timeZoneId = tz_id
    return details


# ── parse_liquid_hours ────────────────────────────────────────────────

class TestParseLiquidHours:
    tz_ny = pytz.timezone("US/Eastern")

    def test_single_session(self):
        raw = "20260305:0930-20260305:1600"
        sessions = parse_liquid_hours(raw, self.tz_ny)
        assert len(sessions) == 1
        s, e = sessions[0]
        assert s.hour == 9 and s.minute == 30
        assert e.hour == 16 and e.minute == 0

    def test_multiple_sessions(self):
        raw = "20260305:0930-20260305:1600;20260306:0930-20260306:1600"
        sessions = parse_liquid_hours(raw, self.tz_ny)
        assert len(sessions) == 2

    def test_closed_day_skipped(self):
        raw = "20260307:CLOSED;20260308:0930-20260308:1600"
        sessions = parse_liquid_hours(raw, self.tz_ny)
        assert len(sessions) == 1

    def test_empty_string(self):
        assert parse_liquid_hours("", self.tz_ny) == []

    def test_garbage_skipped(self):
        raw = "garbage;20260305:0930-20260305:1600"
        sessions = parse_liquid_hours(raw, self.tz_ny)
        assert len(sessions) == 1

    def test_hk_market(self):
        tz_hk = pytz.timezone("Asia/Hong_Kong")
        raw = "20260305:0930-20260305:1200;20260305:1300-20260305:1600"
        sessions = parse_liquid_hours(raw, tz_hk)
        assert len(sessions) == 2
        assert sessions[0][0].hour == 9 and sessions[0][0].minute == 30
        assert sessions[0][1].hour == 12
        assert sessions[1][0].hour == 13
        assert sessions[1][1].hour == 16


# ── _resolve_tz ───────────────────────────────────────────────────────

class TestResolveTz:
    def test_known_abbreviations(self):
        assert _resolve_tz("EST").zone == "US/Eastern"
        assert _resolve_tz("HKT").zone == "Asia/Hong_Kong"
        assert _resolve_tz("JST").zone == "Asia/Tokyo"

    def test_olson_passthrough(self):
        assert _resolve_tz("America/New_York").zone == "America/New_York"

    def test_unknown_falls_back_to_utc(self):
        assert _resolve_tz("XYZABC") == pytz.UTC


# ── is_rth_check ─────────────────────────────────────────────────────

class TestIsRTHCheck:

    def test_inside_session(self):
        details = _make_details("20260305:0930-20260305:1600", "EST")
        server_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)
        assert is_rth_check(details, server_utc, con_id=12345) is True

    def test_outside_session(self):
        details = _make_details("20260305:0930-20260305:1600", "EST")
        server_utc = datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC)
        assert is_rth_check(details, server_utc, con_id=12346) is False

    def test_now_override_inside(self):
        details = _make_details("20260305:0930-20260305:1600", "EST")
        server_utc = datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC)
        tz_ny = pytz.timezone("US/Eastern")
        within = tz_ny.localize(datetime.datetime(2026, 3, 5, 10, 0))
        assert is_rth_check(details, server_utc, now=within) is True

    def test_now_override_outside(self):
        details = _make_details("20260305:0930-20260305:1600", "EST")
        server_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)
        tz_ny = pytz.timezone("US/Eastern")
        outside = tz_ny.localize(datetime.datetime(2026, 3, 5, 20, 0))
        assert is_rth_check(details, server_utc, now=outside) is False

    def test_hk_market_morning_session(self):
        details = _make_details(
            "20260305:0930-20260305:1200;20260305:1300-20260305:1600", "HKT"
        )
        server_utc = datetime.datetime(2026, 3, 5, 2, 30, 0, tzinfo=pytz.UTC)
        assert is_rth_check(details, server_utc, con_id=99999) is True

    def test_hk_market_lunch_break(self):
        details = _make_details(
            "20260305:0930-20260305:1200;20260305:1300-20260305:1600", "HKT"
        )
        server_utc = datetime.datetime(2026, 3, 5, 4, 30, 0, tzinfo=pytz.UTC)
        assert is_rth_check(details, server_utc, con_id=99998) is False

    def test_no_sessions_returns_false(self):
        details = _make_details("20260307:CLOSED", "EST")
        server_utc = datetime.datetime(2026, 3, 7, 15, 0, 0, tzinfo=pytz.UTC)
        assert is_rth_check(details, server_utc) is False

    def test_empty_liquid_hours_returns_false(self):
        details = _make_details("", "EST")
        server_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)
        assert is_rth_check(details, server_utc) is False

    def test_naive_server_time_gets_utc(self):
        """server_time_utc without tzinfo should be treated as UTC."""
        details = _make_details("20260305:0930-20260305:1600", "EST")
        server_naive = datetime.datetime(2026, 3, 5, 15, 0, 0)
        assert is_rth_check(details, server_naive, con_id=12347) is True

    def test_cross_timezone_china_midnight(self):
        """Key scenario: user in China at midnight, US market still open."""
        details = _make_details("20260311:0930-20260311:1600", "EST")
        # 北京时间 03:00 = UTC 19:00 = EDT 15:00 (盘中)
        server_utc = datetime.datetime(2026, 3, 11, 19, 0, 0, tzinfo=pytz.UTC)
        assert is_rth_check(details, server_utc, con_id=10001, symbol="GOOGL") is True


# ── fuse (circuit breaker) ────────────────────────────────────────

class TestFuse:

    def test_fuse_activates_on_outside_rth(self):
        details = _make_details("20260305:0930-20260305:1600", "EST")
        server_utc = datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC)
        assert is_rth_check(details, server_utc, con_id=40001, symbol="AAPL") is False
        assert 40001 in _fuse_until

    def test_fuse_returns_false_immediately(self):
        details = _make_details("20260305:0930-20260305:1600", "EST")
        server_utc = datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC)
        is_rth_check(details, server_utc, con_id=40002, symbol="AAPL")

        # Second call should return False immediately via fuse
        assert is_rth_check(details, server_utc, con_id=40002, symbol="AAPL") is False

    def test_fuse_does_not_affect_other_contracts(self):
        details = _make_details("20260305:0930-20260305:1600", "EST")
        server_utc_closed = datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC)
        is_rth_check(details, server_utc_closed, con_id=40003, symbol="AAPL")

        server_utc_open = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)
        assert is_rth_check(details, server_utc_open, con_id=40004, symbol="MSFT") is True

    def test_fuse_waits_half_of_remaining(self):
        details = _make_details("20260305:0930-20260305:1600", "EST")
        # Server time 13:00 UTC → 08:00 EST, session starts 09:30 EST = 14:30 UTC
        # remaining = 90 min = 5400s, fuse = half = 2700s
        server_utc = datetime.datetime(2026, 3, 5, 13, 0, 0, tzinfo=pytz.UTC)
        before = _time.monotonic()
        is_rth_check(details, server_utc, con_id=40005, symbol="AAPL")

        fuse_deadline = _fuse_until[40005]
        fuse_duration = fuse_deadline - before
        remaining_seconds = 90 * 60

        assert abs(fuse_duration - remaining_seconds / 2) < 5

    def test_no_fuse_when_near_open(self):
        details = _make_details("20260305:0930-20260305:1600", "EST")
        tz_ny = pytz.timezone("US/Eastern")
        almost_open = tz_ny.localize(datetime.datetime(2026, 3, 5, 9, 29, 10))
        server_utc = datetime.datetime(2026, 3, 5, 14, 29, 10, tzinfo=pytz.UTC)
        is_rth_check(details, server_utc, con_id=40009, symbol="AAPL", now=almost_open)
        assert 40009 not in _fuse_until

    def test_fuse_clears_on_rth(self):
        details = _make_details("20260305:0930-20260305:1600", "EST")
        server_utc_closed = datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC)
        is_rth_check(details, server_utc_closed, con_id=40006, symbol="AAPL")
        assert 40006 in _fuse_until

        _fuse_until[40006] = 0  # expire the fuse
        server_utc_open = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)
        assert is_rth_check(details, server_utc_open, con_id=40006, symbol="AAPL") is True
        assert 40006 not in _fuse_until

    def test_fuse_bypassed_with_now_override(self):
        details = _make_details("20260305:0930-20260305:1600", "EST")
        server_utc = datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC)
        is_rth_check(details, server_utc, con_id=40007, symbol="AAPL")
        assert 40007 in _fuse_until

        tz_ny = pytz.timezone("US/Eastern")
        within = tz_ny.localize(datetime.datetime(2026, 3, 5, 10, 0))
        assert is_rth_check(details, server_utc, con_id=40007, symbol="AAPL", now=within) is True

    def test_no_future_sessions_fuse_30min(self):
        details = _make_details("20260305:0930-20260305:1600", "EST")
        server_utc = datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC)
        before = _time.monotonic()
        is_rth_check(details, server_utc, con_id=40008, symbol="AAPL")

        fuse_deadline = _fuse_until[40008]
        fuse_duration = fuse_deadline - before
        assert 1790 < fuse_duration < 1810  # ~30 min


# ── Forex liquidHours (UC-FX-L01–L09) ─────────────────────────────────

@pytest.mark.Forex
class TestForexLiquidHours:
    """UC-FX-L01–L09: IBKR Forex-style liquidHours via parse_liquid_hours / is_rth_check."""

    tz_ny = pytz.timezone("US/Eastern")
    tz_tokyo = pytz.timezone("Asia/Tokyo")

    def test_UC_FX_L01_cross_day_single_segment_parse(self):
        """UC-FX-L01: One session spanning two calendar dates (EST)."""
        raw = "20260308:1715-20260309:1700"
        sessions = parse_liquid_hours(raw, self.tz_ny)
        assert len(sessions) == 1
        start, end = sessions[0]
        assert start.date() != end.date()
        assert start == self.tz_ny.localize(datetime.datetime(2026, 3, 8, 17, 15))
        assert end == self.tz_ny.localize(datetime.datetime(2026, 3, 9, 17, 0))

    def test_UC_FX_L02_weekday_mid_session_tuesday(self):
        """UC-FX-L02: Tuesday afternoon inside a same-calendar-day window (EST)."""
        details = _make_details("20260310:0100-20260310:2300", "EST")
        server_utc = datetime.datetime(2026, 3, 10, 19, 0, 0, tzinfo=pytz.UTC)
        now = self.tz_ny.localize(datetime.datetime(2026, 3, 10, 14, 0))
        assert is_rth_check(details, server_utc, con_id=91001, now=now) is True

    def test_UC_FX_L03_friday_after_week_close(self):
        """UC-FX-L03: After last Friday segment end (17:01); 17:00 inclusive edge."""
        details = _make_details("20260306:0100-20260306:1700", "EST")
        server_utc = datetime.datetime(2026, 3, 6, 22, 0, 0, tzinfo=pytz.UTC)
        at_close = self.tz_ny.localize(datetime.datetime(2026, 3, 6, 17, 0, 0))
        assert is_rth_check(details, server_utc, con_id=91002, now=at_close) is True
        after = self.tz_ny.localize(datetime.datetime(2026, 3, 6, 17, 1, 0))
        assert is_rth_check(details, server_utc, con_id=91003, now=after) is False

    def test_UC_FX_L04_saturday_closed(self):
        """UC-FX-L04: Saturday with only CLOSED / no session."""
        details = _make_details("20260307:CLOSED", "EST")
        server_utc = datetime.datetime(2026, 3, 7, 17, 0, 0, tzinfo=pytz.UTC)
        now = self.tz_ny.localize(datetime.datetime(2026, 3, 7, 12, 0))
        assert is_rth_check(details, server_utc, con_id=91004, now=now) is False

    def test_UC_FX_L05_sunday_week_open_boundary(self):
        """UC-FX-L05: Sunday 17:15 open; 17:14 still closed (cross-day segment)."""
        details = _make_details("20260308:1715-20260309:1700", "EST")
        server_utc = datetime.datetime(2026, 3, 8, 22, 0, 0, tzinfo=pytz.UTC)
        open_sun = self.tz_ny.localize(datetime.datetime(2026, 3, 8, 17, 15))
        assert is_rth_check(details, server_utc, con_id=91005, now=open_sun) is True
        before = self.tz_ny.localize(datetime.datetime(2026, 3, 8, 17, 14))
        assert is_rth_check(details, server_utc, con_id=91006, now=before) is False

    def test_UC_FX_L06_daily_maintenance_gap(self):
        """UC-FX-L06: Gap 17:00–17:15 between two segments (Mon 2026-03-09)."""
        lh = (
            "20260308:1715-20260309:1700;"
            "20260309:1715-20260310:1700"
        )
        details = _make_details(lh, "EST")
        server_utc = datetime.datetime(2026, 3, 9, 22, 0, 0, tzinfo=pytz.UTC)
        in_gap = self.tz_ny.localize(datetime.datetime(2026, 3, 9, 17, 5))
        assert is_rth_check(details, server_utc, con_id=91007, now=in_gap) is False

    def test_UC_FX_L07_holiday_closed_skipped(self):
        """UC-FX-L07: CLOSED segment skipped; midday on that day has no session."""
        lh = (
            "20260324:0930-20260324:1700;"
            "20260325:CLOSED;"
            "20260326:0930-20260326:1700"
        )
        details = _make_details(lh, "EST")
        assert "CLOSED" in lh.upper()
        closed_seg_skipped = parse_liquid_hours(lh, self.tz_ny)
        assert len(closed_seg_skipped) == 2
        server_utc = datetime.datetime(2026, 3, 25, 16, 0, 0, tzinfo=pytz.UTC)
        now = self.tz_ny.localize(datetime.datetime(2026, 3, 25, 12, 0))
        assert is_rth_check(details, server_utc, con_id=91008, now=now) is False

    def test_UC_FX_L08_gbpjpy_jst(self):
        """UC-FX-L08: JST timeZoneId; Tokyo-local liquidHours; in/out of window."""
        lh = "20260310:0900-20260310:1800"
        details = _make_details(lh, "JST")
        server_utc = datetime.datetime(2026, 3, 10, 5, 0, 0, tzinfo=pytz.UTC)
        inside = self.tz_tokyo.localize(datetime.datetime(2026, 3, 10, 14, 0))
        assert is_rth_check(details, server_utc, con_id=91009, now=inside) is True
        outside = self.tz_tokyo.localize(datetime.datetime(2026, 3, 10, 19, 0))
        assert is_rth_check(details, server_utc, con_id=91010, now=outside) is False

    def test_UC_FX_L09_xagusd_distinct_window(self):
        """UC-FX-L09: XAGUSD-style shorter EST window vs L02; inside window → True."""
        details = _make_details("20260311:0800-20260311:2000", "EST")
        server_utc = datetime.datetime(2026, 3, 11, 19, 0, 0, tzinfo=pytz.UTC)
        now = self.tz_ny.localize(datetime.datetime(2026, 3, 11, 14, 0))
        assert is_rth_check(details, server_utc, con_id=91011, now=now) is True
