"""Tests for IBKR RTH (Regular Trading Hours) gate."""

import datetime
from unittest.mock import MagicMock, patch

import pytz
import pytest

from app.services.live_trading.ibkr_trading.trading_hours import (
    parse_liquid_hours,
    is_rth,
    clear_cache,
    _resolve_tz,
    _fuse_until,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


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


# ── is_rth ────────────────────────────────────────────────────────────

def _make_mock_ib(liquid_hours: str, tz_id: str = "EST",
                  server_utc: datetime.datetime = None):
    """Create a mock IB instance with reqContractDetails and reqCurrentTime."""
    ib = MagicMock()
    details = MagicMock()
    details.liquidHours = liquid_hours
    details.timeZoneId = tz_id
    ib.reqContractDetails.return_value = [details]
    if server_utc is None:
        server_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)
    ib.reqCurrentTime.return_value = server_utc
    return ib


def _make_contract(con_id=12345):
    c = MagicMock()
    c.conId = con_id
    c.symbol = "AAPL"
    return c


class TestIsRTH:

    def test_inside_session_with_server_time(self):
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
            server_utc=datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC),
        )
        contract = _make_contract()
        assert is_rth(ib, contract) is True
        ib.reqCurrentTime.assert_called_once()

    def test_outside_session_with_server_time(self):
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
            server_utc=datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC),
        )
        contract = _make_contract()
        assert is_rth(ib, contract) is False

    def test_now_override_bypasses_server_time(self):
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
        )
        contract = _make_contract()
        tz_ny = pytz.timezone("US/Eastern")
        within = tz_ny.localize(datetime.datetime(2026, 3, 5, 10, 0))
        assert is_rth(ib, contract, now=within) is True
        ib.reqCurrentTime.assert_not_called()

    def test_now_override_outside(self):
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
        )
        contract = _make_contract()
        tz_ny = pytz.timezone("US/Eastern")
        outside = tz_ny.localize(datetime.datetime(2026, 3, 5, 20, 0))
        assert is_rth(ib, contract, now=outside) is False

    def test_hk_market_morning_session(self):
        tz_hk = pytz.timezone("Asia/Hong_Kong")
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1200;20260305:1300-20260305:1600",
            tz_id="HKT",
            server_utc=datetime.datetime(2026, 3, 5, 2, 30, 0, tzinfo=pytz.UTC),
        )
        contract = _make_contract(con_id=99999)
        assert is_rth(ib, contract) is True

    def test_hk_market_lunch_break(self):
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1200;20260305:1300-20260305:1600",
            tz_id="HKT",
            server_utc=datetime.datetime(2026, 3, 5, 4, 30, 0, tzinfo=pytz.UTC),
        )
        contract = _make_contract(con_id=99998)
        assert is_rth(ib, contract) is False

    def test_cache_reuses_details(self):
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
            server_utc=datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC),
        )
        contract = _make_contract(con_id=11111)
        is_rth(ib, contract)
        is_rth(ib, contract)
        ib.reqContractDetails.assert_called_once()
        assert ib.reqCurrentTime.call_count == 2

    def test_fail_open_on_details_error(self):
        ib = MagicMock()
        ib.reqContractDetails.side_effect = Exception("timeout")
        contract = _make_contract(con_id=77777)
        assert is_rth(ib, contract) is False

    def test_fail_open_on_empty_details(self):
        ib = MagicMock()
        ib.reqContractDetails.return_value = []
        contract = _make_contract(con_id=88888)
        assert is_rth(ib, contract) is False

    def test_fail_open_on_no_sessions(self):
        ib = _make_mock_ib(liquid_hours="20260307:CLOSED", tz_id="EST")
        contract = _make_contract(con_id=66666)
        assert is_rth(ib, contract) is False

    def test_server_time_fallback_on_reqCurrentTime_error(self):
        """If reqCurrentTime fails, fall back to local clock."""
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
        )
        ib.reqCurrentTime.side_effect = Exception("disconnected")
        contract = _make_contract(con_id=55555)
        result = is_rth(ib, contract)
        assert isinstance(result, bool)


# ── fuse (circuit breaker) ────────────────────────────────────────

class TestFuse:

    def test_fuse_activates_on_outside_rth(self):
        """After detecting outside-RTH, fuse should be set for this contract."""
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
            server_utc=datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC),
        )
        contract = _make_contract(con_id=40001)
        assert is_rth(ib, contract) is False
        assert 40001 in _fuse_until

    def test_fuse_skips_ibgateway_queries(self):
        """While fuse is active, no reqCurrentTime or reqContractDetails calls."""
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
            server_utc=datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC),
        )
        contract = _make_contract(con_id=40002)
        is_rth(ib, contract)

        ib.reset_mock()
        assert is_rth(ib, contract) is False
        ib.reqCurrentTime.assert_not_called()
        ib.reqContractDetails.assert_not_called()

    def test_fuse_does_not_affect_other_contracts(self):
        """Fuse is per-contract; other contracts still query normally."""
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
            server_utc=datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC),
        )
        contract_a = _make_contract(con_id=40003)
        is_rth(ib, contract_a)

        ib2 = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
            server_utc=datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC),
        )
        contract_b = _make_contract(con_id=40004)
        assert is_rth(ib2, contract_b) is True

    def test_fuse_waits_half_of_remaining(self):
        """Fuse duration should be half the time until next session."""
        import time as _time

        # Server time 13:00 UTC, session starts 09:30 EST = 14:30 UTC
        # remaining = 90 min = 5400s, fuse = half = 2700s
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
            server_utc=datetime.datetime(2026, 3, 5, 13, 0, 0, tzinfo=pytz.UTC),
        )
        contract = _make_contract(con_id=40005)
        before = _time.monotonic()
        is_rth(ib, contract)

        fuse_deadline = _fuse_until[40005]
        fuse_duration = fuse_deadline - before
        remaining_seconds = 90 * 60  # 5400s

        assert abs(fuse_duration - remaining_seconds / 2) < 5  # ~2700s

    def test_no_fuse_when_near_open(self):
        """When remaining < 60s (half < 30s threshold), no fuse is set."""
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
        )
        contract = _make_contract(con_id=40009)
        tz_ny = pytz.timezone("US/Eastern")
        almost_open = tz_ny.localize(datetime.datetime(2026, 3, 5, 9, 29, 10))
        is_rth(ib, contract, now=almost_open)
        assert 40009 not in _fuse_until

    def test_fuse_clears_on_rth(self):
        """When market opens, fuse should be cleared."""
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
            server_utc=datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC),
        )
        contract = _make_contract(con_id=40006)
        is_rth(ib, contract)
        assert 40006 in _fuse_until

        _fuse_until[40006] = 0  # expire the fuse
        ib.reqCurrentTime.return_value = datetime.datetime(
            2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC
        )
        assert is_rth(ib, contract) is True
        assert 40006 not in _fuse_until

    def test_fuse_bypassed_with_now_override(self):
        """now= override should bypass fuse (for testing)."""
        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
            server_utc=datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC),
        )
        contract = _make_contract(con_id=40007)
        is_rth(ib, contract)  # activates fuse
        assert 40007 in _fuse_until

        tz_ny = pytz.timezone("US/Eastern")
        within = tz_ny.localize(datetime.datetime(2026, 3, 5, 10, 0))
        assert is_rth(ib, contract, now=within) is True

    def test_no_future_sessions_fuse_30min(self):
        """When no future sessions exist today, fuse for 30 min."""
        import time as _time
        tz_ny = pytz.timezone("US/Eastern")

        ib = _make_mock_ib(
            liquid_hours="20260305:0930-20260305:1600",
            tz_id="EST",
            server_utc=datetime.datetime(2026, 3, 5, 22, 0, 0, tzinfo=pytz.UTC),
        )
        contract = _make_contract(con_id=40008)
        before = _time.monotonic()
        is_rth(ib, contract)

        fuse_deadline = _fuse_until[40008]
        fuse_duration = fuse_deadline - before
        assert 1790 < fuse_duration < 1810  # ~30 min
