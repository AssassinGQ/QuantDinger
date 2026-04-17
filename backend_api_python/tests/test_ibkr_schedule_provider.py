"""Tests for IBKR schedule adapter over ``trading_hours`` public API."""

import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytz
import pytest

from app.services.data_sufficiency_types import IBKRScheduleStatus
from app.services.live_trading.ibkr_trading.ibkr_schedule_provider import (
    get_ibkr_schedule_snapshot,
)
from app.services.live_trading.ibkr_trading.trading_hours import (
    clear_cache,
    is_rth_check,
    parse_liquid_hours,
    _fuse_until,
)


@pytest.fixture(autouse=True)
def _clear_fuse():
    clear_cache()
    yield
    clear_cache()


def _make_details(liquid_hours: str, tz_id: str = "EST"):
    details = MagicMock()
    details.liquidHours = liquid_hours
    details.timeZoneId = tz_id
    return details


def test_unknown_schedule():
    details = _make_details("", "EST")
    server_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)
    snap = get_ibkr_schedule_snapshot(
        details,
        server_time_utc=server_utc,
        symbol="X",
        timeframe="1H",
        market_category="USStock",
        con_id=1,
    )
    assert snap.schedule_status == IBKRScheduleStatus.SCHEDULE_UNKNOWN
    assert snap.next_session_open_utc is None
    assert snap.parsed_session_count == 0


def test_market_closed_gap():
    raw = "20260305:0930-20260305:1600;20260306:0930-20260306:1600"
    details = _make_details(raw, "EST")
    server_utc = datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC)
    snap = get_ibkr_schedule_snapshot(
        details,
        server_time_utc=server_utc,
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        con_id=2,
    )
    assert snap.schedule_status == IBKRScheduleStatus.SCHEDULE_KNOWN_CLOSED
    tz = pytz.timezone("US/Eastern")
    sessions = parse_liquid_hours(raw, tz)
    now_local = server_utc.astimezone(tz)
    expected_next = min(s for s, _e in sessions if s > now_local).astimezone(pytz.UTC)
    assert snap.next_session_open_utc == expected_next


def test_session_known_open():
    details = _make_details("20260305:0930-20260305:1600", "EST")
    server_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)
    snap = get_ibkr_schedule_snapshot(
        details,
        server_time_utc=server_utc,
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        con_id=3,
    )
    assert snap.schedule_status == IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN
    assert snap.session_open is True


def test_cross_day_session():
    raw = "20260308:1715-20260309:1700"
    details = _make_details(raw, "EST")
    server_utc = datetime.datetime(2026, 3, 8, 22, 0, 0, tzinfo=pytz.UTC)
    snap = get_ibkr_schedule_snapshot(
        details,
        server_time_utc=server_utc,
        symbol="EURUSD",
        timeframe="1H",
        market_category="Forex",
        con_id=4,
    )
    assert snap.schedule_status == IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN


def test_cross_timezone_server_utc_market_hkt():
    details = _make_details(
        "20260305:0930-20260305:1200;20260305:1300-20260305:1600",
        "Asia/Hong_Kong",
    )
    server_utc = datetime.datetime(2026, 3, 5, 2, 30, 0, tzinfo=pytz.UTC)
    tz_hk = pytz.timezone("Asia/Hong_Kong")
    sessions = parse_liquid_hours(details.liquidHours, tz_hk)
    now_local = server_utc.astimezone(tz_hk)
    expected_open = any(s <= now_local <= e for s, e in sessions)

    snap = get_ibkr_schedule_snapshot(
        details,
        server_time_utc=server_utc,
        symbol="0700",
        timeframe="1H",
        market_category="HShare",
        con_id=5,
    )
    assert snap.timezone_id == "Asia/Hong_Kong"
    assert (snap.schedule_status == IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN) == expected_open


def test_timezone_fallback_metadata():
    details = _make_details("20260305:0930-20260305:1600", "NotAReal/Zone_XYZ")
    server_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)
    snap = get_ibkr_schedule_snapshot(
        details,
        server_time_utc=server_utc,
        symbol="Z",
        timeframe="1H",
        market_category="USStock",
        con_id=6,
    )
    assert snap.timezone_resolution == "fallback_utc"
    assert snap.schedule_failure_reason == "timezone_id_unresolved"
    assert snap.schedule_status in (
        IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN,
        IBKRScheduleStatus.SCHEDULE_KNOWN_CLOSED,
    )


def test_fuse_transition_open_after_expiry():
    details = _make_details("20260305:0930-20260305:1600", "EST")
    cid = 50_001
    closed_utc = datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC)
    snap_closed = get_ibkr_schedule_snapshot(
        details,
        server_time_utc=closed_utc,
        symbol="FUSE",
        timeframe="1H",
        market_category="USStock",
        con_id=cid,
    )
    assert snap_closed.schedule_status == IBKRScheduleStatus.SCHEDULE_KNOWN_CLOSED
    assert cid in _fuse_until

    _fuse_until[cid] = 0
    open_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)
    snap_open = get_ibkr_schedule_snapshot(
        details,
        server_time_utc=open_utc,
        symbol="FUSE",
        timeframe="1H",
        market_category="USStock",
        con_id=cid,
    )
    assert snap_open.schedule_status == IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN
    assert snap_open.session_open is True
    assert cid not in _fuse_until


def test_next_session_open_utc_populated():
    raw = "20260305:0930-20260305:1600;20260306:0930-20260306:1600"
    details = _make_details(raw, "EST")
    tz = pytz.timezone("US/Eastern")
    server_utc = datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC)
    sessions = parse_liquid_hours(raw, tz)
    now_local = server_utc.astimezone(tz)
    expected_next = min(s for s, _e in sessions if s > now_local).astimezone(pytz.UTC)

    snap = get_ibkr_schedule_snapshot(
        details,
        server_time_utc=server_utc,
        symbol="POP",
        timeframe="1H",
        market_category="USStock",
        con_id=7,
    )
    assert snap.next_session_open_utc == expected_next


def test_no_trading_hours_private_imports():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "live_trading" / "ibkr_trading"
    src = (root / "ibkr_schedule_provider.py").read_text(encoding="utf-8")
    assert "trading_hours._" not in src
    assert "import _" not in src


def test_adapter_does_not_mutate_trading_hours_cache():
    clear_cache()
    details = _make_details("20260305:0930-20260305:1600", "EST")
    server_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)
    snap = get_ibkr_schedule_snapshot(
        details,
        server_time_utc=server_utc,
        symbol="CACHE",
        timeframe="1H",
        market_category="USStock",
        con_id=8,
    )
    assert snap.session_open is True
    clear_cache()
    snap2 = get_ibkr_schedule_snapshot(
        details,
        server_time_utc=server_utc,
        symbol="CACHE",
        timeframe="1H",
        market_category="USStock",
        con_id=8,
    )
    assert snap2.session_open is True
