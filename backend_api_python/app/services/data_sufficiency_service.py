"""Phase-1 orchestration: schedule snapshot → bars → classify → log.

`market_category` is supplied by the caller and threaded through the adapter
and classifier unchanged; it must align with the first argument passed to
``kline_fetcher.get_kline`` (often labeled ``market``) when wiring production.

Exception contract (Phase 1): ``get_ibkr_schedule_snapshot`` and
``compute_available_bars_from_kline_fetcher`` may raise; this module does not
catch them or substitute zero bars. Callers receive the exception as-is.
Phase 2 open-signal guard must define fail-safe mapping or propagation when
this orchestration is embedded in the execution path (see ROADMAP Phase 2
carryover: orchestration / ``get_kline`` exception contract).

**Schedule snapshot retries (Phase 4):** Only the ``get_ibkr_schedule_snapshot``
call is retried (bounded attempts, no cross-call snapshot cache). On
intermediate failures a structured ``ibkr_schedule_snapshot_retry`` warning is
emitted. ``sleep_fn`` defaults to ``time.sleep`` and can be injected in tests
to avoid wall-clock delays when ``SCHEDULE_SNAPSHOT_RETRY_SLEEP_SECONDS`` > 0.
"""

from __future__ import annotations

import datetime
import logging
import time
from typing import Callable, List, Optional

from app.services.data_sufficiency_logging import (
    build_ibkr_data_sufficiency_check_payload,
    emit_ibkr_data_sufficiency_check,
)
from app.services.data_sufficiency_types import (
    DataSufficiencyDiagnostics,
    DataSufficiencyResult,
    FreshnessMetadata,
    IBKRScheduleSnapshot,
    truncate_evaluation_error_summary,
)
from app.services.data_sufficiency_validator import (
    classify_data_sufficiency,
    compute_available_bars_from_kline_fetcher,
)
from app.services.live_trading.ibkr_trading.ibkr_schedule_provider import (
    get_ibkr_schedule_snapshot,
)

SCHEDULE_SNAPSHOT_MAX_ATTEMPTS = 3
SCHEDULE_SNAPSHOT_RETRY_SLEEP_SECONDS = 0


def _fetch_schedule_snapshot_with_retries(
    contract_details,
    *,
    server_time_utc: datetime.datetime,
    symbol: str,
    timeframe: str,
    market_category: str,
    con_id: int,
    logger: Optional[logging.Logger],
    sleep_fn: Callable[[float], None],
) -> IBKRScheduleSnapshot:
    """Run ``get_ibkr_schedule_snapshot`` with bounded retries; re-raises last error."""
    log = logger
    last_exc: BaseException | None = None
    for attempt in range(1, SCHEDULE_SNAPSHOT_MAX_ATTEMPTS + 1):
        try:
            return get_ibkr_schedule_snapshot(
                contract_details,
                server_time_utc=server_time_utc,
                symbol=symbol,
                timeframe=timeframe,
                market_category=market_category,
                con_id=con_id,
            )
        except Exception as exc:
            last_exc = exc
            if attempt >= SCHEDULE_SNAPSHOT_MAX_ATTEMPTS:
                raise
            if log is not None:
                summary = truncate_evaluation_error_summary(str(exc))
                log.warning(
                    "ibkr_schedule_snapshot_retry",
                    extra={
                        "event": "ibkr_schedule_snapshot_retry",
                        "attempt": attempt,
                        "max_attempts": SCHEDULE_SNAPSHOT_MAX_ATTEMPTS,
                        "symbol": symbol,
                        "exc_type": type(exc).__name__,
                        "error_summary": summary,
                    },
                )
            if SCHEDULE_SNAPSHOT_RETRY_SLEEP_SECONDS > 0:
                sleep_fn(float(SCHEDULE_SNAPSHOT_RETRY_SLEEP_SECONDS))
    raise AssertionError("unreachable") from last_exc


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
    exchange_id: Optional[str] = None,
    strategy_id: Optional[int] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
) -> DataSufficiencyResult:
    """End-to-end sufficiency for IBKR: adapter + kline bar count + pure classify + one log.

    Raises:
        Exception: Any exception raised by ``get_ibkr_schedule_snapshot`` (after retries)
            or ``compute_available_bars_from_kline_fetcher`` (including a mocked
            ``get_kline_callable``) propagates; no log emission occurs after a
            failed bar-count step because classification is not reached.
    """
    sleeper = sleep_fn if sleep_fn is not None else time.sleep
    snap = _fetch_schedule_snapshot_with_retries(
        contract_details,
        server_time_utc=server_time_utc,
        symbol=symbol,
        timeframe=timeframe,
        market_category=market_category,
        con_id=con_id,
        logger=logger,
        sleep_fn=sleeper,
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
    payload = build_ibkr_data_sufficiency_check_payload(
        result,
        exchange_id=exchange_id,
        strategy_id=strategy_id,
    )
    emit_ibkr_data_sufficiency_check(payload, logger=logger)
    return result