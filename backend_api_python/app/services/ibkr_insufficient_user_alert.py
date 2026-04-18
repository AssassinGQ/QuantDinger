"""User-visible IBKR insufficient-data alerts (Phase 3).

Deduped notifications when live IBKR open/add is blocked for data sufficiency.

Operator / support copy hints (ROADMAP Phase 3 carryover)
--------------------------------------------------------
- **stale_prev_close**: Explain to users that the prior session close used for
  freshness checks is older than policy allows (see ``FreshnessMetadata`` /
  ``DataSufficiencyReasonCode.STALE_PREV_CLOSE`` in the sufficiency domain), not
  merely “one random stale bar.” Prefer wording that points to prior-close age
  vs. the trading calendar, without dumping raw broker blobs.
- **missing_window** together with **market_closed_gap**: A large
  ``missing_window`` often reflects wall-clock bar shortfall across sessions
  (weekends, holidays, halts), not only “the last K-line is missing.” Pair with
  ``market_closed_gap`` / schedule context when explaining why bars are short
  even though the venue was nominally closed.

For flat alerts (no position on the symbol), ``direction`` passed to
``SignalNotifier.notify_signal`` is **cosmetic** only: ``signal_type ==
IBKR_INSUFFICIENT_DATA_ALERT_SIGNAL_TYPE`` drives ``_signal_meta`` in
``SignalNotifier``, not directional open/add marketing copy (03-REVIEWS R-07).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Final, List, Mapping, Optional, Tuple

from app.services.data_sufficiency_logging import (
    build_ibkr_insufficient_data_alert_sent_payload,
    emit_ibkr_insufficient_data_alert_sent,
)
from app.services.data_sufficiency_types import DataSufficiencyResult
from app.services.signal_notifier import SignalNotifier, _as_list
from app.utils.logger import get_logger

_LOG = get_logger(__name__)

IBKR_INSUFFICIENT_DATA_ALERT_SIGNAL_TYPE: Final[str] = "ibkr_data_insufficient_block"
DEFAULT_COOLDOWN_SECONDS = 300.0

_dedup_lock = threading.Lock()
_last_sent: Dict[Tuple[int, str, str, str], float] = {}


def reset_insufficient_user_alert_dedup_state() -> None:
    with _dedup_lock:
        _last_sent.clear()


def insufficient_user_alert_dedup_key(
    strategy_id: int,
    symbol: str,
    reason_code: str,
    exchange_id: str,
) -> Tuple[int, str, str, str]:
    sym = str(symbol or "").strip()
    rc = str(reason_code or "").strip()
    ex = str(exchange_id or "").strip().lower()
    return (int(strategy_id), sym, rc, ex)


def should_send_insufficient_user_alert(
    now_monotonic: float,
    key: Tuple[int, str, str, str],
    *,
    cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
) -> bool:
    with _dedup_lock:
        last = _last_sent.get(key)
        if last is not None and (now_monotonic - last) < float(cooldown_seconds):
            return False
        _last_sent[key] = float(now_monotonic)
        return True


def _has_open_position_for_symbol(current_positions: Any, symbol: str) -> bool:
    sym = str(symbol or "").strip()
    for p in current_positions or []:
        if not isinstance(p, dict):
            continue
        ps = str(p.get("symbol") or "").strip()
        if ps != sym:
            continue
        try:
            sz = float(p.get("size") or 0.0)
        except (TypeError, ValueError):
            sz = 0.0
        if abs(sz) > 1e-12:
            return True
    return False


def build_insufficient_user_alert_title_body(
    *,
    has_position: bool,
    symbol: str,
    strategy_name: str,
) -> Tuple[str, str]:
    sname = strategy_name or "未命名"
    if has_position:
        title = f"IBKR 数据不足（有持仓）| {symbol}"
        body = (
            f"策略《{sname}》标的 {symbol} 因 IBKR 历史数据不足已阻止开仓/加仓。\n"
            "您当前有持仓，请自行决定平仓或继续持有，并留意数据恢复后的风险。"
        )
    else:
        title = f"IBKR 数据不足 | {symbol}"
        body = (
            f"策略《{sname}》标的 {symbol} 因 IBKR 历史数据不足，当前无法新开/加仓。\n"
            "请等待数据补齐或检查合约/时段配置。"
        )
    return title, body


def build_insufficient_user_alert_extra(
    *,
    blocked_payload: Mapping[str, Any],
    suff_result: DataSufficiencyResult,
    strategy_ctx: Mapping[str, Any],
    current_positions: Any,
    current_price: float,
    strategy_name: str,
) -> Dict[str, Any]:
    _ = current_price
    exchange_id = str(blocked_payload.get("exchange_id") or "")
    sym = str(suff_result.symbol or "")
    has_pos = _has_open_position_for_symbol(current_positions, sym)
    title, plain = build_insufficient_user_alert_title_body(
        has_position=has_pos,
        symbol=sym,
        strategy_name=strategy_name,
    )
    snap: List[Dict[str, Any]] = []
    for p in current_positions or []:
        if not isinstance(p, dict):
            continue
        if str(p.get("symbol") or "").strip() != sym:
            continue
        row = {k: p.get(k) for k in ("side", "size", "entry_price") if k in p}
        if row:
            snap.append(row)

    extra: Dict[str, Any] = {
        "exchange_id": exchange_id,
        "_execution_mode": str(strategy_ctx.get("_execution_mode") or ""),
        "reason_code": suff_result.reason_code.value,
        "required_bars": suff_result.required_bars,
        "available_bars": suff_result.available_bars,
        "effective_lookback": suff_result.effective_lookback,
        "missing_window": suff_result.missing_window,
        "schedule_status": suff_result.schedule_status.value,
        "effective_intent": str(blocked_payload.get("effective_intent") or ""),
        "position_snapshot": snap,
        "user_alert_title": title,
        "user_alert_plain": plain,
        "severity_hint": "warning",
    }
    return extra


def dispatch_insufficient_user_alert_after_block(
    *,
    notifier: SignalNotifier,
    strategy_id: int,
    strategy_name: str,
    symbol: str,
    exchange_id: str,
    notification_config: Optional[Dict[str, Any]],
    price: float,
    direction: str,
    blocked_payload: Mapping[str, Any],
    suff_result: DataSufficiencyResult,
    strategy_ctx: Mapping[str, Any],
    current_positions: Any,
    logger: Optional[Any] = None,
) -> None:
    log = logger or _LOG
    nc = notification_config if isinstance(notification_config, dict) else {}
    channels = _as_list(nc.get("channels"))
    if not channels:
        log.warning(
            "insufficient_user_alert_skip: strategy_id=%s reason=empty_channels",
            strategy_id,
        )
        return

    key = insufficient_user_alert_dedup_key(
        strategy_id,
        symbol,
        suff_result.reason_code.value,
        exchange_id,
    )
    now = time.monotonic()
    if not should_send_insufficient_user_alert(now, key):
        return

    extra = build_insufficient_user_alert_extra(
        blocked_payload=blocked_payload,
        suff_result=suff_result,
        strategy_ctx=strategy_ctx,
        current_positions=current_positions,
        current_price=float(price or 0.0),
        strategy_name=strategy_name,
    )
    try:
        results = notifier.notify_signal(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            symbol=symbol,
            signal_type=IBKR_INSUFFICIENT_DATA_ALERT_SIGNAL_TYPE,
            price=float(price or 0.0),
            stake_amount=0.0,
            direction=direction,
            notification_config=nc,
            extra=extra,
        )
    except Exception as e:
        log.warning(
            "insufficient_user_alert_notify_failed: strategy_id=%s err=%s",
            strategy_id,
            e,
        )
        return

    attempted = list(results.keys()) if results else list(channels)
    channels_ok = {k: bool(v.get("ok")) for k, v in results.items()}
    payload = build_ibkr_insufficient_data_alert_sent_payload(
        strategy_id=strategy_id,
        symbol=symbol,
        exchange_id=exchange_id,
        execution_mode=str(strategy_ctx.get("_execution_mode") or ""),
        reason_code=suff_result.reason_code.value,
        dedup_key=key,
        channels_attempted=attempted,
        channels_ok=channels_ok,
        signal_type=IBKR_INSUFFICIENT_DATA_ALERT_SIGNAL_TYPE,
    )
    emit_ibkr_insufficient_data_alert_sent(payload, logger=log)
