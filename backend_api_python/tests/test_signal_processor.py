"""
测试 app.services.signal_processor：position_state、is_signal_allowed、process_signals
"""
import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.signal_processor import (
    is_signal_allowed,
    position_state,
    process_signals,
    signal_priority,
)


class TestPositionState:
    """position_state 返回 flat | long | short"""

    def test_empty_returns_flat(self):
        assert position_state([]) == "flat"

    def test_long_returns_long(self):
        assert position_state([{"side": "long"}]) == "long"

    def test_short_returns_short(self):
        assert position_state([{"side": "short"}]) == "short"

    def test_invalid_returns_flat(self):
        assert position_state([{"side": "unknown"}]) == "flat"


class TestIsSignalAllowed:
    """状态机：flat 只允许 open，long 只允许 add/reduce/close_long，short 同理"""

    def test_flat_accepts_open_long_short(self):
        assert is_signal_allowed("flat", "open_long") is True
        assert is_signal_allowed("flat", "open_short") is True

    def test_flat_rejects_close(self):
        assert is_signal_allowed("flat", "close_long") is False
        assert is_signal_allowed("flat", "add_long") is False

    def test_long_accepts_add_reduce_close(self):
        assert is_signal_allowed("long", "add_long") is True
        assert is_signal_allowed("long", "reduce_long") is True
        assert is_signal_allowed("long", "close_long") is True

    def test_long_rejects_open_short(self):
        assert is_signal_allowed("long", "open_long") is False
        assert is_signal_allowed("long", "close_short") is False

    def test_short_accepts_add_reduce_close(self):
        assert is_signal_allowed("short", "add_short") is True
        assert is_signal_allowed("short", "reduce_short") is True
        assert is_signal_allowed("short", "close_short") is True


class TestSignalPriority:
    """close > reduce > open > add"""

    def test_close_highest(self):
        assert signal_priority("close_long") == 0
        assert signal_priority("close_short") == 0

    def test_reduce_second(self):
        assert signal_priority("reduce_long") == 1

    def test_open_third(self):
        assert signal_priority("open_long") == 2

    def test_add_lowest(self):
        assert signal_priority("add_long") == 3


class TestProcessSignals:
    """process_signals 返回 (selected, current_positions)"""

    def test_empty_returns_none_and_empty_list(self):
        dh = MagicMock()
        dh.get_current_positions.return_value = []
        selected, positions = process_signals(
            strategy_id=1, symbol="BTC/USDT", triggered_signals=[],
            current_price=100.0, trade_direction="both", leverage=1.0,
            market_type="swap", trading_config={}, timeframe_seconds=60,
        )
        assert selected is None
        assert positions == []
        dh.get_current_positions.assert_not_called()

    def test_returns_selected_signal_when_allowed(self):
        dh = MagicMock()
        dh.get_current_positions.return_value = []
        sig = {"type": "open_long", "position_size": 0.1, "timestamp": int(time.time())}
        with patch("app.services.signal_processor.check_take_profit_or_trailing_signal", return_value=None), \
             patch("app.services.signal_processor.check_stop_loss_signal", return_value=None), \
             patch("app.services.signal_processor.DataHandler", return_value=dh):
            selected, positions = process_signals(
                strategy_id=1, symbol="BTC/USDT", triggered_signals=[sig],
                current_price=100.0, trade_direction="both", leverage=1.0,
                market_type="swap", trading_config={}, timeframe_seconds=60,
            )
        assert selected is not None
        assert selected.get("type") == "open_long"
        assert positions == []

    def test_filters_by_state_long_rejects_open(self):
        dh = MagicMock()
        dh.get_current_positions.return_value = [{"side": "long", "size": 0.1}]
        sig = {"type": "open_long", "position_size": 0.1, "timestamp": int(time.time())}
        with patch("app.services.signal_processor.check_take_profit_or_trailing_signal", return_value=None), \
             patch("app.services.signal_processor.check_stop_loss_signal", return_value=None), \
             patch("app.services.signal_processor.DataHandler", return_value=dh):
            selected, positions = process_signals(
                strategy_id=1, symbol="BTC/USDT", triggered_signals=[sig],
                current_price=100.0, trade_direction="both", leverage=1.0,
                market_type="swap", trading_config={}, timeframe_seconds=60,
            )
        assert selected is None
        assert len(positions) == 1
