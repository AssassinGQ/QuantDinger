"""Phase 2 execution-path façade over Phase 1 IBKR sufficiency orchestration.

Execution path overrides Phase 1 library propagation per ``02-CONTEXT.md`` (D-01–D-04): any
exception raised inside ``evaluate_ibkr_data_sufficiency_and_log`` is translated here into a
synthetic insufficient ``DataSufficiencyResult`` with ``DATA_EVALUATION_FAILED`` instead of
propagating to callers. Phase 1 ``data_sufficiency_service`` continues to raise when embedded
outside this façade.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, List, Literal, Optional

from app.services import kline_fetcher
from app.services.data_sufficiency_service import evaluate_ibkr_data_sufficiency_and_log
from app.services.data_sufficiency_types import (
    DataSufficiencyDiagnostics,
    DataSufficiencyReasonCode,
    DataSufficiencyResult,
    IBKRScheduleStatus,
    effective_lookback_seconds,
    truncate_evaluation_error_summary,
)
from app.utils.logger import get_logger

_LOG = get_logger(__name__)


class EvaluationPathError(Exception):
    """Optional marker for categorizing orchestration failures (unused unless re-raised)."""


def _infer_evaluation_error_category(
    exc: BaseException,
) -> Literal["schedule", "kline", "unknown"]:
    """Coarse bucket from exception type/message (no stack traces in payloads)."""
    msg = str(exc).lower()
    if any(
        x in msg
        for x in (
            "schedule",
            "timezone",
            "liquid",
            "hour",
            "session",
        )
    ):
        return "schedule"
    if any(x in msg for x in ("kline", "bar", "aggregation")):
        return "kline"
    cls = type(exc).__name__.lower()
    if "schedule" in cls or "timezone" in cls:
        return "schedule"
    if "kline" in cls or "runtime" in cls:
        return "kline"
    return "unknown"


def _synthetic_data_evaluation_failed_result(
    *,
    symbol: str,
    timeframe: str,
    market_category: str,
    required_bars: int,
    con_id: int,
    exc: BaseException,
) -> DataSufficiencyResult:
    eff = effective_lookback_seconds(timeframe, required_bars)
    miss = eff
    cid = con_id if con_id else None
    diag = DataSufficiencyDiagnostics(
        parsed_session_count=None,
        schedule_failure_reason=None,
        timezone_id=None,
        timezone_resolution=None,
        prev_close_stale_since=None,
        con_id=cid,
        evaluation_error_summary=truncate_evaluation_error_summary(str(exc)),
        evaluation_error_category=_infer_evaluation_error_category(exc),
    )
    return DataSufficiencyResult(
        sufficient=False,
        reason_code=DataSufficiencyReasonCode.DATA_EVALUATION_FAILED,
        required_bars=required_bars,
        available_bars=0,
        effective_lookback=eff,
        missing_window=miss,
        schedule_status=IBKRScheduleStatus.SCHEDULE_UNKNOWN,
        symbol=symbol,
        timeframe=timeframe,
        market_category=market_category,
        diagnostics=diag,
    )


def contract_details_missing_fail_closed(
    *,
    symbol: str,
    timeframe: str,
    market_category: str,
    required_bars: int,
    con_id: int = 0,
    reason_message: str = "contract_details_unresolved",
) -> DataSufficiencyResult:
    """Fail closed for IBKR open/add when exchange or ``ContractDetails`` is unavailable."""
    exc = EvaluationPathError(reason_message)
    return _synthetic_data_evaluation_failed_result(
        symbol=symbol,
        timeframe=timeframe,
        market_category=market_category,
        required_bars=required_bars,
        con_id=con_id,
        exc=exc,
    )


def evaluate_ibkr_open_data_sufficiency(
    contract_details,
    *,
    server_time_utc: datetime,
    symbol: str,
    timeframe: str,
    market_category: str,
    required_bars: int,
    before_time_utc: Optional[int],
    con_id: int,
    logger: Optional[logging.Logger] = None,
    exchange_id: Optional[str] = None,
    strategy_id: Optional[int] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
) -> DataSufficiencyResult:
    """Evaluate sufficiency for IBKR execution path; never raises — maps failures to synthetic results."""

    log = logger or _LOG

    def get_kline_callable(
        market: str,
        sym: str,
        tf: str,
        *,
        limit: int,
        before_time: Optional[int],
    ) -> List[dict]:
        return kline_fetcher.get_kline(
            market, sym, tf, limit=limit, before_time=before_time
        )

    try:
        return evaluate_ibkr_data_sufficiency_and_log(
            contract_details,
            server_time_utc=server_time_utc,
            required_bars=required_bars,
            get_kline_callable=get_kline_callable,
            before_time_utc=before_time_utc,
            symbol=symbol,
            timeframe=timeframe,
            market_category=market_category,
            con_id=con_id,
            freshness=None,
            logger=log,
            exchange_id=exchange_id,
            strategy_id=strategy_id,
            sleep_fn=sleep_fn,
        )
    except Exception as exc:
        log.exception(
            "ibkr_open_data_sufficiency evaluation failed symbol=%s tf=%s",
            symbol,
            timeframe,
        )
        return _synthetic_data_evaluation_failed_result(
            symbol=symbol,
            timeframe=timeframe,
            market_category=market_category,
            required_bars=required_bars,
            con_id=con_id,
            exc=exc,
        )