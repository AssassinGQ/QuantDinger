"""Tests for sufficiency orchestration service."""

from unittest.mock import MagicMock

import datetime

import pytz

from app.services.data_sufficiency_service import evaluate_ibkr_data_sufficiency_and_log


def test_evaluate_entrypoint_calls_emit_once():
    details = MagicMock()
    details.liquidHours = "20260305:0930-20260305:1600"
    details.timeZoneId = "EST"
    server_utc = datetime.datetime(2026, 3, 5, 15, 0, 0, tzinfo=pytz.UTC)

    def get_kline(market, symbol, tf, limit, before_time=None):
        return [{"time": i * 3600, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0} for i in range(50)]

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
        con_id=7,
        logger=log,
    )
    assert log.info.call_count == 1