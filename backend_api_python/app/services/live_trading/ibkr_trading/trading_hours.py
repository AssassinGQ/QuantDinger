"""
RTH (Regular Trading Hours) check via IBKR API.

Uses reqContractDetails().liquidHours for session windows and
reqCurrentTime() for server-side clock — completely independent of
the local system clock.

Fuse: after determining a contract is outside RTH, the next session
start time is cached per contract. Subsequent calls return False
immediately (no IBGateway traffic) until that time is reached.
"""

import datetime
import logging
import time as _time
from typing import Optional, List, Tuple

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

# (conId, date_str) -> (tz, sessions)
_details_cache: dict = {}

# conId -> monotonic timestamp before which we skip IBGateway queries
_fuse_until: dict = {}


def _resolve_tz(tz_id: str) -> pytz.BaseTzInfo:
    mapped = _TZ_MAP.get(tz_id, tz_id)
    try:
        return pytz.timezone(mapped)
    except pytz.UnknownTimeZoneError:
        logger.warning("Unknown timezone '%s', falling back to UTC", tz_id)
        return pytz.UTC


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


def _get_server_time(ib) -> datetime.datetime:
    """Get current time from IBKR server (UTC-aware)."""
    server_time = ib.reqCurrentTime()
    if server_time.tzinfo is None:
        server_time = server_time.replace(tzinfo=pytz.UTC)
    return server_time


def _next_session_start(now: datetime.datetime,
                        sessions: List[Tuple[datetime.datetime, datetime.datetime]],
                        ) -> Optional[datetime.datetime]:
    """Find the earliest session start that is strictly after *now*."""
    future = [s for s, _e in sessions if s > now]
    return min(future) if future else None


def _load_sessions(ib, contract, cache_key):
    """Fetch and cache liquidHours sessions for a contract.

    Returns (tz, sessions) or None on error (caller should fail-open).
    """
    try:
        details_list = ib.reqContractDetails(contract)
    except Exception as e:
        logger.error("reqContractDetails failed for %s: %s", contract, e)
        return None

    if not details_list:
        logger.warning("No contract details for %s, assuming RTH", contract)
        return None

    details = details_list[0]
    tz = _resolve_tz(details.timeZoneId or "UTC")
    sessions = parse_liquid_hours(details.liquidHours or "", tz)
    result = (tz, sessions)
    _details_cache[cache_key] = result
    logger.info(
        "Cached %d liquidHours sessions for %s (tz=%s): %s",
        len(sessions), contract.symbol, details.timeZoneId,
        "; ".join(f"{s.strftime('%H:%M')}-{e.strftime('%H:%M')}" for s, e in sessions),
    )
    return result


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
                "suppressing IBGateway queries for %.0f min (half of remaining)",
                symbol, remaining / 60,
                next_open.strftime("%H:%M %Z"), wait_seconds / 60,
            )
    else:
        _fuse_until[con_id] = _time.monotonic() + 1800
        logger.info(
            "RTH fuse for %s: no more sessions today, "
            "suppressing IBGateway queries for 30 min",
            symbol,
        )


def is_rth(ib, contract, now: Optional[datetime.datetime] = None) -> bool:
    """Check whether the IBKR server time falls within a liquidHours session.

    Per-contract fuse: once determined outside RTH, further calls return
    False without contacting IBGateway until the next session starts.

    Args:
        ib: connected ib_insync.IB instance
        contract: qualified ib_insync contract
        now: override for current time (testing only); bypasses fuse
    """
    con_id = getattr(contract, "conId", 0) or id(contract)

    if now is None:
        fuse_deadline = _fuse_until.get(con_id)
        if fuse_deadline is not None and _time.monotonic() < fuse_deadline:
            return False

    cache_key = (con_id, datetime.date.today().isoformat())
    cached = _details_cache.get(cache_key)
    if cached is None:
        cached = _load_sessions(ib, contract, cache_key)
        if cached is None:
            logger.error("Failed to load sessions for %s, fail-closed", contract)
            return False

    tz, sessions = cached
    if not sessions:
        logger.error("No liquidHours sessions parsed for %s, fail-closed", contract)
        return False

    if now is None:
        try:
            now = _get_server_time(ib).astimezone(tz)
        except Exception as e:
            logger.error("reqCurrentTime failed: %s, fail-closed", e)
            return False

    for start, end in sessions:
        if start <= now <= end:
            _fuse_until.pop(con_id, None)
            return True

    _activate_fuse(con_id, now, sessions, contract.symbol)
    return False


def clear_cache():
    """Clear all caches (useful for testing or daily reset)."""
    _details_cache.clear()
    _fuse_until.clear()
