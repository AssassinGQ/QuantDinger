"""Pure sufficiency classification and kline-shaped bar counting.

``compute_available_bars_from_kline_fetcher`` mirrors the *intent* of
``kline_fetcher.get_kline`` lower-timeframe aggregation (see ``_AGG_LOWER_LEVELS``,
aligned with ``kline_fetcher.LOWER_LEVELS``). It does **not** reproduce DB/cache
behavior; production drift is gated under Phase 2.

If ``get_kline_callable`` raises, the exception propagates to the caller so
insufficient-data is not silently masked as zero bars.

``missing_window`` vs calendar/storage gaps: this helper only counts bars from
the injected callable; distinguishing storage gaps from calendar coverage is
documented here and tightened with real-path tests in Phase 2.

Lookback math uses the same seconds semantics as ``DataSufficiencyResult`` fields
``effective_lookback`` and ``missing_window`` (internally derived as
``effective_lookback_seconds`` and ``missing_window_seconds`` before packaging).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, List, Optional

from app.services.data_sufficiency_types import (
    DataSufficiencyDiagnostics,
    DataSufficiencyReasonCode,
    DataSufficiencyResult,
    FreshnessMetadata,
    IBKRScheduleStatus,
    TIMEFRAME_SECONDS_MAP,
    effective_lookback_seconds,
    missing_window_seconds,
)

_AGG_LOWER_LEVELS: Dict[str, List[str]] = {
    "1W": ["1D", "4H", "1H", "5m", "1m"],
    "1D": ["4H", "1H", "5m", "1m"],
    "4H": ["1H", "5m", "1m"],
    "1H": ["5m", "1m"],
    "30m": ["1H", "5m", "1m"],
    "15m": ["5m", "1m"],
    "5m": ["1m"],
    "1m": [],
}


def _aggregate_bars_to_interval(bars: List[dict], interval_sec: int) -> List[dict]:
    """Bucket OHLCV bars to *interval_sec* (mirrors ``kline_fetcher._aggregate_bars``)."""
    if not bars:
        return []
    if interval_sec <= 60:
        return bars
    buckets: dict[int, list] = defaultdict(list)
    for b in bars:
        t = int(b["time"])
        bucket = (t // interval_sec) * interval_sec
        buckets[bucket].append(b)
    out: List[dict] = []
    for bucket in sorted(buckets.keys()):
        group = sorted(buckets[bucket], key=lambda x: x["time"])
        o, h = group[0]["open"], max(x["high"] for x in group)
        l, c = min(x["low"] for x in group), group[-1]["close"]
        v = sum(int(x.get("volume", 0) or 0) for x in group)
        out.append({"time": bucket, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return out


def compute_available_bars_from_kline_fetcher(
    market: str,
    symbol: str,
    timeframe: str,
    required_bars: int,
    before_time_utc: Optional[int],
    get_kline_callable: Callable[..., List[dict]],
) -> int:
    """Count available bars at *timeframe* using native then lower-TF aggregation."""
    if required_bars < 1:
        return 0
    limit = max(required_bars, 1)
    direct = get_kline_callable(
        market, symbol, timeframe, limit=limit, before_time=before_time_utc
    )
    n_direct = len(direct or [])
    if n_direct >= required_bars:
        return n_direct

    target_sec = int(TIMEFRAME_SECONDS_MAP[timeframe])
    best = n_direct
    for lower_tf in _AGG_LOWER_LEVELS.get(timeframe, []):
        lower_sec = int(TIMEFRAME_SECONDS_MAP.get(lower_tf, 60))
        ratio = max(1, (target_sec + lower_sec - 1) // lower_sec)
        fetch_limit = max(required_bars * ratio + 20, limit)
        lower_bars = get_kline_callable(
            market, symbol, lower_tf, limit=fetch_limit, before_time=before_time_utc
        )
        agg = _aggregate_bars_to_interval(lower_bars or [], target_sec)
        best = max(best, len(agg))
        if len(agg) >= required_bars:
            return len(agg)
    return best


def _caller_reports_stale_prev_close(meta: Optional[FreshnessMetadata]) -> bool:
    if meta is None:
        return False
    if meta.prev_close_timestamp_utc is None or meta.prev_close_age_seconds is None:
        return False
    return meta.prev_close_age_seconds >= 1.0


def classify_data_sufficiency(
    *,
    symbol: str,
    timeframe: str,
    market_category: str,
    required_bars: int,
    available_bars: int,
    schedule_status: IBKRScheduleStatus,
    freshness: Optional[FreshnessMetadata] = None,
    diagnostics: Optional[DataSufficiencyDiagnostics] = None,
) -> DataSufficiencyResult:
    """Classify sufficiency using deterministic precedence (no side effects)."""
    eff = effective_lookback_seconds(timeframe, required_bars)
    miss = missing_window_seconds(timeframe, required_bars, available_bars)
    diag = diagnostics or DataSufficiencyDiagnostics(
        parsed_session_count=None,
        schedule_failure_reason=None,
        timezone_id=None,
        timezone_resolution=None,
        prev_close_stale_since=None,
        con_id=None,
    )

    if schedule_status == IBKRScheduleStatus.SCHEDULE_UNKNOWN:
        return DataSufficiencyResult(
            sufficient=False,
            reason_code=DataSufficiencyReasonCode.UNKNOWN_SCHEDULE,
            required_bars=required_bars,
            available_bars=available_bars,
            effective_lookback=eff,
            missing_window=0.0,
            schedule_status=schedule_status,
            symbol=symbol,
            timeframe=timeframe,
            market_category=market_category,
            diagnostics=diag,
        )

    if _caller_reports_stale_prev_close(freshness):
        return DataSufficiencyResult(
            sufficient=False,
            reason_code=DataSufficiencyReasonCode.STALE_PREV_CLOSE,
            required_bars=required_bars,
            available_bars=available_bars,
            effective_lookback=eff,
            missing_window=miss,
            schedule_status=schedule_status,
            symbol=symbol,
            timeframe=timeframe,
            market_category=market_category,
            diagnostics=diag,
        )

    if schedule_status == IBKRScheduleStatus.SCHEDULE_KNOWN_CLOSED:
        return DataSufficiencyResult(
            sufficient=False,
            reason_code=DataSufficiencyReasonCode.MARKET_CLOSED_GAP,
            required_bars=required_bars,
            available_bars=available_bars,
            effective_lookback=eff,
            missing_window=0.0,
            schedule_status=schedule_status,
            symbol=symbol,
            timeframe=timeframe,
            market_category=market_category,
            diagnostics=diag,
        )

    if available_bars < required_bars:
        return DataSufficiencyResult(
            sufficient=False,
            reason_code=DataSufficiencyReasonCode.MISSING_BARS,
            required_bars=required_bars,
            available_bars=available_bars,
            effective_lookback=eff,
            missing_window=miss,
            schedule_status=schedule_status,
            symbol=symbol,
            timeframe=timeframe,
            market_category=market_category,
            diagnostics=diag,
        )

    return DataSufficiencyResult(
        sufficient=True,
        reason_code=DataSufficiencyReasonCode.SUFFICIENT,
        required_bars=required_bars,
        available_bars=available_bars,
        effective_lookback=eff,
        missing_window=0.0,
        schedule_status=schedule_status,
        symbol=symbol,
        timeframe=timeframe,
        market_category=market_category,
        diagnostics=diag,
    )