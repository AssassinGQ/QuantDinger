"""IBKR schedule adapter over ``trading_hours`` public seams (D-09–D-11).

Invalid ``timeZoneId`` may still yield ``schedule_known_open`` or
``schedule_known_closed`` if sessions parse under UTC fallback; in that case
``timezone_resolution="fallback_utc"`` and ``schedule_failure_reason="timezone_id_unresolved"``
together mean parsed windows are not timezone-trusted until corrected.
"""

from __future__ import annotations

import datetime
import logging
from typing import List, Optional, Tuple

import pytz

from app.services.data_sufficiency_types import IBKRScheduleSnapshot, IBKRScheduleStatus
from app.services.live_trading.ibkr_trading.trading_hours import (
    is_rth_check,
    parse_liquid_hours,
    resolve_time_zone_id_for_schedule,
)

logger = logging.getLogger(__name__)


def _normalize_server_time_utc(server_time_utc: datetime.datetime) -> datetime.datetime:
    if server_time_utc.tzinfo is None:
        return server_time_utc.replace(tzinfo=pytz.UTC)
    return server_time_utc.astimezone(pytz.UTC)


def _empty_sessions_schedule_status(liquid_hours: str) -> IBKRScheduleStatus:
    raw = (liquid_hours or "").strip()
    if not raw:
        return IBKRScheduleStatus.SCHEDULE_UNKNOWN
    if "CLOSED" in raw.upper():
        return IBKRScheduleStatus.SCHEDULE_KNOWN_CLOSED
    return IBKRScheduleStatus.SCHEDULE_UNKNOWN


def _calendar_in_session(
    sessions: List[Tuple[datetime.datetime, datetime.datetime]],
    now_local: datetime.datetime,
) -> bool:
    for start, end in sessions:
        if start <= now_local <= end:
            return True
    return False


def _next_session_start_utc(
    sessions: List[Tuple[datetime.datetime, datetime.datetime]],
    now_local: datetime.datetime,
) -> Optional[datetime.datetime]:
    starts_after = [s for s, _e in sessions if s > now_local]
    if not starts_after:
        return None
    nxt_local = min(starts_after)
    return nxt_local.astimezone(pytz.UTC)


def get_ibkr_schedule_snapshot(
    contract_details,
    *,
    server_time_utc: datetime.datetime,
    symbol: str,
    timeframe: str,
    market_category: str,
    con_id: int = 0,
) -> IBKRScheduleSnapshot:
    """Build a typed snapshot from IBKR ``ContractDetails`` and an explicit clock.

    ``server_time_utc`` must be injected by callers so tests stay deterministic.
    """
    lh_raw = getattr(contract_details, "liquidHours", None) or ""
    tz_id_raw = getattr(contract_details, "timeZoneId", None)
    tz_id_display = (tz_id_raw or "").strip()

    tz, tz_resolution = resolve_time_zone_id_for_schedule(tz_id_raw)
    schedule_failure_reason: Optional[str] = None
    if tz_resolution == "fallback_utc":
        schedule_failure_reason = "timezone_id_unresolved"
        logger.warning(
            "IBKR schedule: unresolved timeZoneId for symbol=%s con_id=%s; "
            "using UTC fallback for liquidHours parsing.",
            symbol,
            con_id,
        )

    sessions = parse_liquid_hours(lh_raw, tz)
    server_utc = _normalize_server_time_utc(server_time_utc)
    now_local = server_utc.astimezone(tz)

    if not sessions:
        st = _empty_sessions_schedule_status(lh_raw)
        if st == IBKRScheduleStatus.SCHEDULE_UNKNOWN and schedule_failure_reason is None:
            schedule_failure_reason = "empty_or_unparsable_schedule"
        return IBKRScheduleSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            market_category=market_category,
            server_time_utc=server_utc,
            schedule_status=st,
            session_open=False,
            next_session_open_utc=None,
            parsed_session_count=0,
            timezone_id=tz_id_display,
            timezone_resolution=tz_resolution,
            schedule_failure_reason=schedule_failure_reason,
        )

    in_window = _calendar_in_session(sessions, now_local)
    schedule_status = (
        IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN
        if in_window
        else IBKRScheduleStatus.SCHEDULE_KNOWN_CLOSED
    )
    session_open = bool(
        is_rth_check(contract_details, server_utc, con_id=con_id, symbol=symbol, now=None)
    )
    next_open = _next_session_start_utc(sessions, now_local)

    return IBKRScheduleSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        market_category=market_category,
        server_time_utc=server_utc,
        schedule_status=schedule_status,
        session_open=session_open,
        next_session_open_utc=next_open,
        parsed_session_count=len(sessions),
        timezone_id=tz_id_display,
        timezone_resolution=tz_resolution,
        schedule_failure_reason=schedule_failure_reason,
    )
