"""Phase 4: bounded retries around ``get_ibkr_schedule_snapshot`` in sufficiency service."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytz

from app.services.data_sufficiency_service import (
    SCHEDULE_SNAPSHOT_MAX_ATTEMPTS,
    evaluate_ibkr_data_sufficiency_and_log,
)
from app.services.live_trading.ibkr_trading import ibkr_schedule_provider as _isp


def _details():
    d = MagicMock()
    d.liquidHours = "20260305:0930-20260305:1600"
    d.timeZoneId = "EST"
    return d


def test_schedule_snapshot_retry_then_success():
    server_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)
    calls: list[int] = []

    def get_kline(market, symbol, tf, limit, before_time=None):
        return [
            {"time": i * 3600, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}
            for i in range(50)
        ]

    real_snap = _isp.get_ibkr_schedule_snapshot

    def snap_side(*a, **kw):
        calls.append(1)
        if len(calls) < SCHEDULE_SNAPSHOT_MAX_ATTEMPTS:
            raise ConnectionError("transient")
        return real_snap(*a, **kw)

    with patch(
        "app.services.data_sufficiency_service.get_ibkr_schedule_snapshot",
        side_effect=snap_side,
    ):
        log = MagicMock()
        evaluate_ibkr_data_sufficiency_and_log(
            _details(),
            server_time_utc=server_utc,
            required_bars=10,
            get_kline_callable=get_kline,
            before_time_utc=None,
            symbol="SPY",
            timeframe="1H",
            market_category="USStock",
            con_id=3,
            logger=log,
            sleep_fn=lambda _s: None,
        )

    assert len(calls) == SCHEDULE_SNAPSHOT_MAX_ATTEMPTS
    assert log.warning.call_count == SCHEDULE_SNAPSHOT_MAX_ATTEMPTS - 1
    w_extra = log.warning.call_args_list[0][1]["extra"]
    assert w_extra["event"] == "ibkr_schedule_snapshot_retry"
    assert log.info.call_count == 1


def test_schedule_snapshot_retry_exhausted_raises():
    server_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)

    def get_kline(*_a, **_kw):
        raise AssertionError("kline must not run when snapshot never succeeds")

    with patch(
        "app.services.data_sufficiency_service.get_ibkr_schedule_snapshot",
        side_effect=RuntimeError("always fail"),
    ):
        log = MagicMock()
        try:
            evaluate_ibkr_data_sufficiency_and_log(
                _details(),
                server_time_utc=server_utc,
                required_bars=10,
                get_kline_callable=get_kline,
                before_time_utc=None,
                symbol="QQQ",
                timeframe="1H",
                market_category="USStock",
                con_id=1,
                logger=log,
                sleep_fn=lambda _s: None,
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected RuntimeError")

    assert log.warning.call_count == SCHEDULE_SNAPSHOT_MAX_ATTEMPTS - 1
    assert log.info.call_count == 0