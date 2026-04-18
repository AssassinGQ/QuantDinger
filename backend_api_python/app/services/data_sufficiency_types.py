"""Typed sufficiency contracts for IBKR strategies (Phase 1 domain layer).

``TIMEFRAME_SECONDS_MAP`` is the single in-repo mapping of supported timeframe
keys to per-bar duration in seconds; it mirrors ``app.data_sources.base.TIMEFRAME_SECONDS``
used by ``kline_fetcher`` so lookback math stays aligned with storage aggregation.

``market_category`` on ``DataSufficiencyResult`` / ``IBKRScheduleSnapshot`` is a
caller-provided execution bucket (same semantics as the ``market`` argument to
``kline_fetcher.get_kline``). Types do not infer venue from ``ContractDetails``.

``FreshnessMetadata`` holds optional prior-close inputs; absence or ``None``
fields must not alone imply ``stale_prev_close`` (threshold policy is Phase 3;
see ROADMAP).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from app.data_sources.base import TIMEFRAME_SECONDS

TIMEFRAME_SECONDS_MAP: dict[str, float] = {k: float(v) for k, v in TIMEFRAME_SECONDS.items()}


class DataSufficiencyReasonCode(str, Enum):
    """Machine-stable reason codes for sufficiency / guard consumers (D-03)."""

    SUFFICIENT = "sufficient"
    MISSING_BARS = "missing_bars"
    STALE_PREV_CLOSE = "stale_prev_close"
    MARKET_CLOSED_GAP = "market_closed_gap"
    UNKNOWN_SCHEDULE = "unknown_schedule"


class IBKRScheduleStatus(str, Enum):
    """Schedule truth separate from bar-count sufficiency (D-09)."""

    SCHEDULE_KNOWN_OPEN = "schedule_known_open"
    SCHEDULE_KNOWN_CLOSED = "schedule_known_closed"
    SCHEDULE_UNKNOWN = "schedule_unknown"


@dataclass(frozen=True)
class FreshnessMetadata:
    """Optional prior-close freshness inputs (Phase 3 will own thresholds)."""

    prev_close_timestamp_utc: Optional[datetime] = None
    prev_close_age_seconds: Optional[float] = None


@dataclass(frozen=True)
class DataSufficiencyDiagnostics:
    """Bounded diagnostics only — no arbitrary JSON blobs (D-01 / T-01-02)."""

    parsed_session_count: Optional[int]
    schedule_failure_reason: Optional[str]
    timezone_id: Optional[str]
    timezone_resolution: Optional[Literal["explicit", "fallback_utc"]] = None
    prev_close_stale_since: Optional[datetime] = None
    con_id: Optional[int] = None


@dataclass(frozen=True)
class IBKRScheduleSnapshot:
    """Adapter-facing normalized IBKR session view for sufficiency evaluation."""

    symbol: str
    timeframe: str
    market_category: str
    server_time_utc: datetime
    schedule_status: IBKRScheduleStatus
    session_open: bool
    next_session_open_utc: Optional[datetime]
    parsed_session_count: int
    timezone_id: str
    timezone_resolution: Literal["explicit", "fallback_utc"]
    schedule_failure_reason: Optional[str]


@dataclass(frozen=True)
class DataSufficiencyResult:
    """Stable top-level fields for downstream guards and alerts (D-02)."""

    sufficient: bool
    reason_code: DataSufficiencyReasonCode
    required_bars: int
    available_bars: int
    effective_lookback: float
    missing_window: float
    schedule_status: IBKRScheduleStatus
    symbol: str
    timeframe: str
    market_category: str
    diagnostics: DataSufficiencyDiagnostics


def effective_lookback_seconds(timeframe: str, required_bars: int) -> float:
    """Required lookback window in seconds: ``required_bars * bar_duration`` (D-06/D-07)."""
    if required_bars < 0:
        raise ValueError("required_bars must be non-negative")
    duration = TIMEFRAME_SECONDS_MAP.get(timeframe)
    if duration is None:
        raise KeyError(f"Unsupported timeframe for sufficiency contract: {timeframe!r}")
    return float(required_bars) * float(duration)


def missing_window_seconds(
    timeframe: str, required_bars: int, available_bars: int
) -> float:
    """Seconds of lookback missing when ``available_bars < required_bars``; else ``0.0``."""
    if available_bars >= required_bars:
        return 0.0
    gap = required_bars - available_bars
    duration = TIMEFRAME_SECONDS_MAP.get(timeframe)
    if duration is None:
        raise KeyError(f"Unsupported timeframe for sufficiency contract: {timeframe!r}")
    return float(gap) * float(duration)
