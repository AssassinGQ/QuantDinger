"""Structured logging for sufficiency decisions (N3)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.services.data_sufficiency_types import DataSufficiencyResult
from app.utils.logger import get_logger

_LOG = get_logger(__name__)


def build_ibkr_data_sufficiency_check_payload(result: DataSufficiencyResult) -> Dict[str, object]:
    """Pure: stable machine payload for ``ibkr_data_sufficiency_check``."""
    payload: Dict[str, object] = {
        "event": "ibkr_data_sufficiency_check",
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "market_category": result.market_category,
        "sufficient": result.sufficient,
        "reason_code": result.reason_code.value,
        "required_bars": result.required_bars,
        "available_bars": result.available_bars,
        "effective_lookback": result.effective_lookback,
        "missing_window": result.missing_window,
        "schedule_status": result.schedule_status.value,
    }
    if result.diagnostics.con_id is not None:
        payload["con_id"] = result.diagnostics.con_id
    return payload


def emit_ibkr_data_sufficiency_check(
    payload: Dict[str, object],
    logger: Optional[logging.Logger] = None,
) -> None:
    """Emit one structured ``info`` line; side effects live here only."""
    log = logger or _LOG
    extra: Dict[str, Any] = {k: v for k, v in payload.items()}
    log.info("ibkr_data_sufficiency_check", extra=extra)