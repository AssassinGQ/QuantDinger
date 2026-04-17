"""
RTH (Regular Trading Hours) check for IBKR contracts.

Pure logic module — does NOT call ib_insync directly.
All IBKR API calls should happen in IBKRClient; this module only
receives pre-fetched data (contract_details, server_time).

Fuse: after determining a contract is outside RTH, the next session
start time is cached per contract. Subsequent calls return False
immediately until that time is reached.
"""

import datetime
import logging
import time as _time
from typing import Literal, Optional, List, Tuple

import pytz

logger = logging.getLogger(__name__)

_TZ_MAP = {
    "EST": "US/Eastern",
    "EDT": "US/Eastern",
    "CST": "US/Central",
    "CDT": "US/Central",
    "MST": "US/Mountain",
    "MDT": "US/Mountain",
    "PST": "US/Pacific",
    "PDT": "US/Pacific",
    "JST": "Asia/Tokyo",
    "HKT": "Asia/Hong_Kong",
    "GMT": "Europe/London",
    "BST": "Europe/London",
    "CET": "Europe/Berlin",
    "CEST": "Europe/Berlin",
    "AEST": "Australia/Sydney",
    "AEDT": "Australia/Sydney",
    "SGT": "Asia/Singapore",
    "MET": "Europe/Berlin",
}

# conId -> monotonic timestamp before which we skip checks
_fuse_until: dict = {}


def resolve_time_zone_id_for_schedule(
    tz_id: Optional[str],
) -> Tuple[pytz.BaseTzInfo, Literal["explicit", "fallback_utc"]]:
    """Resolve IBKR ``timeZoneId`` for ``liquidHours`` parsing.

    ``fallback_utc`` means the identifier could not be mapped to an Olson zone
    and UTC is used (legacy fail-soft behavior). Downstream adapters may pair
    this with ``schedule_failure_reason="timezone_id_unresolved"``.
    """
    raw = (tz_id or "").strip() or "UTC"
    mapped = _TZ_MAP.get(raw, raw)
    try:
        return pytz.timezone(mapped), "explicit"
    except pytz.UnknownTimeZoneError:
        logger.warning("Unknown timezone '%s', falling back to UTC", raw)
        return pytz.UTC, "fallback_utc"


def _resolve_tz(tz_id: str) -> pytz.BaseTzInfo:
    tz, _res = resolve_time_zone_id_for_schedule(tz_id)
    return tz


def parse_liquid_hours(liquid_hours: str, tz: pytz.BaseTzInfo) -> List[Tuple[datetime.datetime, datetime.datetime]]:
    """Parse IBKR liquidHours string into a list of (start, end) aware datetimes.

    Format: "20260305:0930-20260305:1600;20260306:0930-20260306:1600;20260307:CLOSED"
    """
    sessions = []
    for segment in liquid_hours.split(";"):
        segment = segment.strip()
        if not segment or "CLOSED" in segment.upper():
            continue
        if "-" not in segment:
            continue
        try:
            start_part, end_part = segment.split("-", 1)
            s_date, s_time = start_part.split(":")
            e_date, e_time = end_part.split(":")
            start_dt = tz.localize(datetime.datetime.strptime(f"{s_date}{s_time}", "%Y%m%d%H%M"))
            end_dt = tz.localize(datetime.datetime.strptime(f"{e_date}{e_time}", "%Y%m%d%H%M"))
            sessions.append((start_dt, end_dt))
        except (ValueError, IndexError) as e:
            logger.debug("Skipping unparseable liquidHours segment '%s': %s", segment, e)
    return sessions


def _next_session_start(now: datetime.datetime,
                        sessions: List[Tuple[datetime.datetime, datetime.datetime]],
                        ) -> Optional[datetime.datetime]:
    """Find the earliest session start that is strictly after *now*."""
    future = [s for s, _e in sessions if s > now]
    return min(future) if future else None


_FUSE_THRESHOLD = 30  # seconds; don't bother fusing below this


def _activate_fuse(con_id: int, now, sessions, symbol: str):
    """Set the per-contract fuse timer based on next session start."""
    next_open = _next_session_start(now, sessions)
    if next_open is not None:
        remaining = (next_open - now).total_seconds()
        wait_seconds = remaining / 2
        if wait_seconds >= _FUSE_THRESHOLD:
            _fuse_until[con_id] = _time.monotonic() + wait_seconds
            logger.info(
                "RTH fuse for %s: market closed, next open in %.0f min (%s), "
                "suppressing queries for %.0f min (half of remaining)",
                symbol, remaining / 60,
                next_open.strftime("%H:%M %Z"), wait_seconds / 60,
            )
    else:
        _fuse_until[con_id] = _time.monotonic() + 1800
        logger.info(
            "RTH fuse for %s: no more sessions today, "
            "suppressing queries for 30 min",
            symbol,
        )


def is_rth_check(
    contract_details,
    server_time_utc: datetime.datetime,
    con_id: int = 0,
    symbol: str = "?",
    now: Optional[datetime.datetime] = None,
) -> bool:
    """Pure logic: check whether server_time falls within a liquidHours session.

    Does NOT call any IBKR API. All data must be pre-fetched by the caller.

    Per-contract fuse: once determined outside RTH, further calls return
    False immediately until the next session starts.

    Args:
        contract_details: IBKR ContractDetails object (needs .timeZoneId, .liquidHours)
        server_time_utc: UTC-aware datetime from IBKR server
        con_id: contract ID for fuse tracking
        symbol: symbol name for logging
        now: override for current time (testing only); bypasses fuse
    """
    if now is None:
        fuse_deadline = _fuse_until.get(con_id)
        if fuse_deadline is not None and _time.monotonic() < fuse_deadline:
            return False

    tz = _resolve_tz(contract_details.timeZoneId or "UTC")
    sessions = parse_liquid_hours(contract_details.liquidHours or "", tz)

    if not sessions:
        logger.error("No liquidHours sessions parsed for %s, fail-closed", symbol)
        return False

    if server_time_utc.tzinfo is None:
        server_time_utc = server_time_utc.replace(tzinfo=pytz.UTC)

    if now is None:
        now = server_time_utc.astimezone(tz)

    for start, end in sessions:
        if start <= now <= end:
            _fuse_until.pop(con_id, None)
            return True

    _activate_fuse(con_id, now, sessions, symbol)
    return False


def clear_cache():
    """Clear fuse timers (useful for testing or daily reset)."""
    _fuse_until.clear()
