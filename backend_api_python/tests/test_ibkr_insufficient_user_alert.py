"""Tests for IBKR insufficient-data user alerts (Phase 3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.data_sufficiency_types import (
    DataSufficiencyDiagnostics,
    DataSufficiencyReasonCode,
    DataSufficiencyResult,
    IBKRScheduleStatus,
    effective_lookback_seconds,
    missing_window_seconds,
)
from app.services.ibkr_insufficient_user_alert import (
    IBKR_INSUFFICIENT_DATA_ALERT_SIGNAL_TYPE,
    build_insufficient_user_alert_extra,
    dispatch_insufficient_user_alert_after_block,
    reset_insufficient_user_alert_dedup_state,
)


def _suff(*, reason: DataSufficiencyReasonCode = DataSufficiencyReasonCode.MISSING_BARS):
    diag = DataSufficiencyDiagnostics(
        parsed_session_count=1,
        schedule_failure_reason=None,
        timezone_id="EST",
        timezone_resolution="explicit",
        prev_close_stale_since=None,
        con_id=1,
    )
    return DataSufficiencyResult(
        sufficient=False,
        reason_code=reason,
        required_bars=10,
        available_bars=0,
        effective_lookback=effective_lookback_seconds("1H", 10),
        missing_window=missing_window_seconds("1H", 10, 0),
        schedule_status=IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN,
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        diagnostics=diag,
    )


@pytest.fixture(autouse=True)
def _reset_dedup():
    reset_insufficient_user_alert_dedup_state()
    yield
    reset_insufficient_user_alert_dedup_state()


def _blocked():
    return {
        "event": "ibkr_open_blocked_insufficient_data",
        "exchange_id": "ibkr-paper",
        "effective_intent": "open_long",
    }


def test_dedup_suppresses_second_send_within_cooldown():
    notifier = MagicMock()
    notifier.notify_signal.return_value = {"browser": {"ok": True, "error": ""}}
    suff = _suff()
    nc = {"channels": ["browser"], "targets": {}}
    mono = iter([0.0, 150.0])

    def _next_mono():
        return next(mono)

    with patch("app.services.ibkr_insufficient_user_alert.time.monotonic", side_effect=_next_mono):
        dispatch_insufficient_user_alert_after_block(
            notifier=notifier,
            strategy_id=1,
            strategy_name="S",
            symbol="SPY",
            exchange_id="ibkr-paper",
            notification_config=nc,
            price=100.0,
            direction="long",
            blocked_payload=_blocked(),
            suff_result=suff,
            strategy_ctx={"_execution_mode": "live"},
            current_positions=[],
        )
        dispatch_insufficient_user_alert_after_block(
            notifier=notifier,
            strategy_id=1,
            strategy_name="S",
            symbol="SPY",
            exchange_id="ibkr-paper",
            notification_config=nc,
            price=100.0,
            direction="long",
            blocked_payload=_blocked(),
            suff_result=suff,
            strategy_ctx={"_execution_mode": "live"},
            current_positions=[],
        )
    assert notifier.notify_signal.call_count == 1


def test_dedup_allows_after_cooldown_elapsed():
    notifier = MagicMock()
    notifier.notify_signal.return_value = {"browser": {"ok": True, "error": ""}}
    suff = _suff()
    nc = {"channels": ["browser"], "targets": {}}
    with patch(
        "app.services.ibkr_insufficient_user_alert.time.monotonic",
        side_effect=[0.0, 301.0],
    ):
        dispatch_insufficient_user_alert_after_block(
            notifier=notifier,
            strategy_id=2,
            strategy_name="S",
            symbol="SPY",
            exchange_id="ibkr-paper",
            notification_config=nc,
            price=1.0,
            direction="long",
            blocked_payload=_blocked(),
            suff_result=suff,
            strategy_ctx={"_execution_mode": "live"},
            current_positions=[],
        )
        dispatch_insufficient_user_alert_after_block(
            notifier=notifier,
            strategy_id=2,
            strategy_name="S",
            symbol="SPY",
            exchange_id="ibkr-paper",
            notification_config=nc,
            price=1.0,
            direction="long",
            blocked_payload=_blocked(),
            suff_result=suff,
            strategy_ctx={"_execution_mode": "live"},
            current_positions=[],
        )
    assert notifier.notify_signal.call_count == 2


def test_dedup_key_isolates_exchange_id():
    notifier = MagicMock()
    notifier.notify_signal.return_value = {"browser": {"ok": True, "error": ""}}
    suff = _suff()
    nc = {"channels": ["browser"], "targets": {}}
    with patch("app.services.ibkr_insufficient_user_alert.time.monotonic", return_value=0.0):
        b1 = {**_blocked(), "exchange_id": "ibkr-paper"}
        dispatch_insufficient_user_alert_after_block(
            notifier=notifier,
            strategy_id=3,
            strategy_name="S",
            symbol="SPY",
            exchange_id="ibkr-paper",
            notification_config=nc,
            price=1.0,
            direction="long",
            blocked_payload=b1,
            suff_result=suff,
            strategy_ctx={"_execution_mode": "live"},
            current_positions=[],
        )
        b2 = {**_blocked(), "exchange_id": "ibkr-live"}
        dispatch_insufficient_user_alert_after_block(
            notifier=notifier,
            strategy_id=3,
            strategy_name="S",
            symbol="SPY",
            exchange_id="ibkr-live",
            notification_config=nc,
            price=1.0,
            direction="long",
            blocked_payload=b2,
            suff_result=suff,
            strategy_ctx={"_execution_mode": "live"},
            current_positions=[],
        )
    assert notifier.notify_signal.call_count == 2


def test_dedup_key_isolates_reason_code():
    notifier = MagicMock()
    notifier.notify_signal.return_value = {"browser": {"ok": True, "error": ""}}
    nc = {"channels": ["browser"], "targets": {}}
    with patch("app.services.ibkr_insufficient_user_alert.time.monotonic", return_value=0.0):
        dispatch_insufficient_user_alert_after_block(
            notifier=notifier,
            strategy_id=4,
            strategy_name="S",
            symbol="SPY",
            exchange_id="ibkr-paper",
            notification_config=nc,
            price=1.0,
            direction="long",
            blocked_payload=_blocked(),
            suff_result=_suff(reason=DataSufficiencyReasonCode.MISSING_BARS),
            strategy_ctx={"_execution_mode": "live"},
            current_positions=[],
        )
        dispatch_insufficient_user_alert_after_block(
            notifier=notifier,
            strategy_id=4,
            strategy_name="S",
            symbol="SPY",
            exchange_id="ibkr-paper",
            notification_config=nc,
            price=1.0,
            direction="long",
            blocked_payload=_blocked(),
            suff_result=_suff(reason=DataSufficiencyReasonCode.STALE_PREV_CLOSE),
            strategy_ctx={"_execution_mode": "live"},
            current_positions=[],
        )
    assert notifier.notify_signal.call_count == 2


def test_empty_channels_skips_notify_signal():
    notifier = MagicMock()
    suff = _suff()
    dispatch_insufficient_user_alert_after_block(
        notifier=notifier,
        strategy_id=5,
        strategy_name="S",
        symbol="SPY",
        exchange_id="ibkr-paper",
        notification_config={"channels": [], "targets": {}},
        price=1.0,
        direction="long",
        blocked_payload=_blocked(),
        suff_result=suff,
        strategy_ctx={"_execution_mode": "live"},
        current_positions=[],
    )
    notifier.notify_signal.assert_not_called()


def test_flat_alert_copy_has_no_position_prompt():
    suff = _suff()
    extra = build_insufficient_user_alert_extra(
        blocked_payload=_blocked(),
        suff_result=suff,
        strategy_ctx={"_execution_mode": "live"},
        current_positions=[],
        current_price=10.0,
        strategy_name="T",
    )
    merged = f"{extra.get('user_alert_title', '')}\n{extra.get('user_alert_plain', '')}"
    assert "有持仓" not in merged
    assert "平仓" not in merged and "持有" not in merged


def test_positioned_alert_copy_requires_hold_close_prompt():
    suff = _suff()
    positions = [{"symbol": "SPY", "side": "long", "size": 1.0, "entry_price": 400.0}]
    extra = build_insufficient_user_alert_extra(
        blocked_payload=_blocked(),
        suff_result=suff,
        strategy_ctx={"_execution_mode": "live"},
        current_positions=positions,
        current_price=10.0,
        strategy_name="T",
    )
    merged = f"{extra.get('user_alert_title', '')}\n{extra.get('user_alert_plain', '')}"
    assert "有持仓" in merged
    assert "请自行决定平仓或继续持有" in merged


def test_notify_signal_receives_signal_type_constant():
    notifier = MagicMock()
    notifier.notify_signal.return_value = {"browser": {"ok": True, "error": ""}}
    suff = _suff()
    nc = {"channels": ["browser"], "targets": {}}
    with patch("app.services.ibkr_insufficient_user_alert.time.monotonic", return_value=0.0):
        dispatch_insufficient_user_alert_after_block(
            notifier=notifier,
            strategy_id=9,
            strategy_name="S",
            symbol="SPY",
            exchange_id="ibkr-paper",
            notification_config=nc,
            price=1.0,
            direction="long",
            blocked_payload=_blocked(),
            suff_result=suff,
            strategy_ctx={"_execution_mode": "live"},
            current_positions=[],
        )
    kw = notifier.notify_signal.call_args[1]
    assert kw["signal_type"] == IBKR_INSUFFICIENT_DATA_ALERT_SIGNAL_TYPE
    assert kw["notification_config"] == nc