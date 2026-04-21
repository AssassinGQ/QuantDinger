"""Phase-1 orchestration: schedule snapshot → bars → classify → log."""

from __future__ import annotations

import datetime
import logging
from typing import Callable, List, Optional

from app.services.data_sufficiency_logging import (
    build_ibkr_data_sufficiency_check_payload,
    emit_ibkr_data_sufficiency_check,
)
from app.services.data_sufficiency_types import (
    DataSufficiencyDiagnostics,
    DataSufficiencyResult,
    FreshnessMetadata,
)
from app.services.data_sufficiency_validator import (
    classify_data_sufficiency,
    compute_available_bars_from_kline_fetcher,
)
from app.services.live_trading.ibkr_trading.ibkr_schedule_provider import (
    get_ibkr_schedule_snapshot,
)


def evaluate_ibkr_data_sufficiency_and_log(
    contract_details,
    *,
    server_time_utc: datetime.datetime,
    required_bars: int,
    get_kline_callable: Callable[..., List[dict]],
    before_time_utc: Optional[int],
    symbol: str,
    timeframe: str,
    market_category: str,
    con_id: int = 0,
    freshness: Optional[FreshnessMetadata] = None,
    logger: Optional[logging.Logger] = None,
) -> DataSufficiencyResult:
    """End-to-end sufficiency for IBKR: adapter + kline bar count + pure classify + one log."""
    snap = get_ibkr_schedule_snapshot(
        contract_details,
        server_time_utc=server_time_utc,
        symbol=symbol,
        timeframe=timeframe,
        market_category=market_category,
        con_id=con_id,
    )
    available = compute_available_bars_from_kline_fetcher(
        market_category,
        symbol,
        timeframe,
        required_bars,
        before_time_utc,
        get_kline_callable,
    )
    cid = con_id if con_id else None
    diag = DataSufficiencyDiagnostics(
        parsed_session_count=snap.parsed_session_count,
        schedule_failure_reason=snap.schedule_failure_reason,
        timezone_id=snap.timezone_id or None,
        timezone_resolution=snap.timezone_resolution,
        prev_close_stale_since=None,
        con_id=cid,
    )
    result = classify_data_sufficiency(
        symbol=symbol,
        timeframe=timeframe,
        market_category=market_category,
        required_bars=required_bars,
        available_bars=available,
        schedule_status=snap.schedule_status,
        freshness=freshness,
        diagnostics=diag,
    )
    payload = build_ibkr_data_sufficiency_check_payload(result)
    emit_ibkr_data_sufficiency_check(payload, logger=logger)
    return result