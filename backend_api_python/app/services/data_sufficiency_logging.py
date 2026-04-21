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


def build_ibkr_open_blocked_insufficient_data_payload(
    *,
    result: DataSufficiencyResult,
    strategy_id: int,
    symbol: str,
    exchange_id: str,
    execution_mode: str,
    signal_type_raw: str,
    effective_intent: str,
    synthetic_evaluation_failure: bool,
) -> Dict[str, object]:
    """Pure builder: stable JSON shape for ``ibkr_open_blocked_insufficient_data`` (Phase 3 correlation).

    Keys (contract):
    - ``event`` — always ``ibkr_open_blocked_insufficient_data``
    - ``strategy_id`` — strategy id
    - ``symbol`` — symbol
    - ``exchange_id`` — from strategy ``exchange_config`` when wired
    - ``execution_mode`` — e.g. ``live``
    - ``signal_type_raw`` — raw ``signal['']`` type before sizing
    - ``effective_intent`` — risk label (``open_long``, ``add_long``, …)
    - ``sufficient`` — always False for this event
    - ``reason_code`` — ``DataSufficiencyReasonCode`` value string
    - ``required_bars`` / ``available_bars`` / ``effective_lookback`` / ``missing_window`` — from result
    - ``schedule_status`` — schedule enum value string
    - ``synthetic_evaluation_failure`` — True when exception was translated to insufficient
    - ``diagnostics_con_id`` — optional copy of ``diagnostics.con_id``
    """
    payload: Dict[str, object] = {
        "event": "ibkr_open_blocked_insufficient_data",
        "strategy_id": strategy_id,
        "symbol": symbol,
        "exchange_id": exchange_id,
        "execution_mode": execution_mode,
        "signal_type_raw": signal_type_raw,
        "effective_intent": effective_intent,
        "sufficient": False,
        "reason_code": result.reason_code.value,
        "required_bars": result.required_bars,
        "available_bars": result.available_bars,
        "effective_lookback": result.effective_lookback,
        "missing_window": result.missing_window,
        "schedule_status": result.schedule_status.value,
        "synthetic_evaluation_failure": synthetic_evaluation_failure,
    }
    if result.diagnostics.con_id is not None:
        payload["diagnostics_con_id"] = result.diagnostics.con_id
    return payload


def emit_ibkr_open_blocked_insufficient_data(
    payload: Dict[str, object],
    logger: Optional[logging.Logger] = None,
) -> None:
    """Emit one structured info line (no notification-store side effects)."""
    log = logger or _LOG
    extra: Dict[str, Any] = {k: v for k, v in payload.items()}
    log.info("ibkr_open_blocked_insufficient_data", extra=extra)