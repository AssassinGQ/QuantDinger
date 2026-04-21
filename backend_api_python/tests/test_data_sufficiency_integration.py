"""Phase 1 integration: sufficiency types + IBKR schedule adapter + service wiring.

The ``test_adapter_to_service_emits_ibkr_data_sufficiency_check`` path uses a
``get_kline`` mock whose return shape follows ``LOWER_LEVELS`` aggregation
(1H empty → 5m seed bars). Production drift against real ``kline_fetcher.get_kline``
is additionally gated in Phase 2 (see ``.planning/ROADMAP.md``).
"""

from unittest.mock import MagicMock

import datetime
import pytz

from app.services.data_sufficiency_service import evaluate_ibkr_data_sufficiency_and_log
from app.services.data_sufficiency_types import IBKRScheduleStatus
from app.services.live_trading.ibkr_trading.ibkr_schedule_provider import (
    get_ibkr_schedule_snapshot,
)
from app.services.live_trading.ibkr_trading.trading_hours import parse_liquid_hours


def test_contract_details_to_ibkr_schedule_snapshot():
    details = MagicMock()
    details.liquidHours = "20260305:0930-20260305:1200;20260305:1300-20260305:1600"
    details.timeZoneId = "Asia/Hong_Kong"
    server_utc = datetime.datetime(2026, 3, 5, 2, 30, 0, tzinfo=pytz.UTC)
    tz_hk = pytz.timezone("Asia/Hong_Kong")
    sessions = parse_liquid_hours(details.liquidHours, tz_hk)
    now_local = server_utc.astimezone(tz_hk)
    expected = IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN if any(
        s <= now_local <= e for s, e in sessions
    ) else IBKRScheduleStatus.SCHEDULE_KNOWN_CLOSED

    snap = get_ibkr_schedule_snapshot(
        details,
        server_time_utc=server_utc,
        symbol="0700",
        timeframe="1H",
        market_category="HShare",
        con_id=99,
    )
    assert snap.schedule_status == expected


def test_adapter_to_service_emits_ibkr_data_sufficiency_check():
    details = MagicMock()
    details.liquidHours = "20260305:0930-20260305:1600"
    details.timeZoneId = "EST"
    server_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)

    def get_kline(market, symbol, tf, limit, before_time=None):
        if tf == "1H":
            return []
        if tf == "5m":
            return [
                {"time": i * 300, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}
                for i in range(600)
            ]
        return []

    log = MagicMock()
    evaluate_ibkr_data_sufficiency_and_log(
        details,
        server_time_utc=server_utc,
        required_bars=10,
        get_kline_callable=get_kline,
        before_time_utc=None,
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        con_id=3,
        logger=log,
    )
    assert log.info.call_count == 1
    _args, kwargs = log.info.call_args
    extra = kwargs["extra"]
    assert extra["event"] == "ibkr_data_sufficiency_check"
    assert extra["reason_code"] == "sufficient"