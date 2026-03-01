"""
测试 app.services.signal_processor：position_state、is_signal_allowed、process_signals
"""
import time
from unittest.mock import MagicMock, patch

from app.services.signal_processor import (
    is_signal_allowed,
    position_state,
    process_signals,
    signal_priority,
)

class TestPositionState:
    def test_empty_positions(self):
        assert position_state([]) == "flat"
        assert position_state(None) == "flat"

    def test_has_long_position(self):
        assert position_state([{"side": "long", "size": 1.0}]) == "long"
        assert position_state([{"side": "LONG", "size": 0.5}]) == "long"

    def test_has_short_position(self):
        assert position_state([{"side": "short", "size": 1.0}]) == "short"

    def test_invalid_side_returns_flat(self):
        assert position_state([{"side": "unknown", "size": 1.0}]) == "flat"


class TestIsSignalAllowed:
    def test_flat_state(self):
        assert is_signal_allowed("flat", "open_long") is True
        assert is_signal_allowed("flat", "open_short") is True
        assert is_signal_allowed("flat", "close_long") is False
        assert is_signal_allowed("flat", "add_long") is False

    def test_long_state(self):
        assert is_signal_allowed("long", "open_long") is False
        assert is_signal_allowed("long", "open_short") is False
        assert is_signal_allowed("long", "add_long") is True
        assert is_signal_allowed("long", "reduce_long") is True
        assert is_signal_allowed("long", "close_long") is True
        assert is_signal_allowed("long", "close_short") is False

    def test_short_state(self):
        assert is_signal_allowed("short", "open_long") is False
        assert is_signal_allowed("short", "open_short") is False
        assert is_signal_allowed("short", "add_short") is True
        assert is_signal_allowed("short", "reduce_short") is True
        assert is_signal_allowed("short", "close_short") is True
        assert is_signal_allowed("short", "close_long") is False

    def test_case_insensitivity(self):
        assert is_signal_allowed("FLAT", "OPEN_LONG") is True


class TestSignalPriority:
    def test_priority_ordering(self):
        assert signal_priority("close_long") == 0
        assert signal_priority("reduce_short") == 1
        assert signal_priority("open_long") == 2
        assert signal_priority("add_long") == 3
        assert signal_priority("unknown") == 99


class TestProcessSignals:
    def setup_method(self):
        self.strategy_ctx = {
            "id": 1,
            "_leverage": 1.0,
            "_market_type": "swap",
            "trading_config": {
                "trade_direction": "both",
                "timeframe": "1m"
            }
        }

    def test_process_signals_empty(self):
        selected, positions = process_signals(self.strategy_ctx, "BTC/USDT", [], 100.0)
        assert selected is None
        assert positions == []

    def test_process_signals_with_tp_sl(self):
        dh = MagicMock()
        dh.get_current_positions.return_value = [{"side": "long", "size": 0.1}]
        sig = {"type": "add_long", "position_size": 0.1, "timestamp": int(time.time())}
        risk_sig = {"type": "close_long", "reason": "tp", "timestamp": int(time.time())}
        
        ctx = dict(self.strategy_ctx)
        ctx["trading_config"]["take_profit_pct"] = 5

        with patch("app.services.signal_processor.check_take_profit_or_trailing_signal", return_value=risk_sig), \
             patch("app.services.signal_processor.check_stop_loss_signal", return_value=None), \
             patch("app.services.signal_processor.DataHandler", return_value=dh):
            selected, positions = process_signals(
                strategy_ctx=ctx, symbol="BTC/USDT", triggered_signals=[sig],
                current_price=100.0,
            )
            assert selected is not None
            assert selected["type"] == "close_long"
            assert selected["reason"] == "tp"

    def test_process_signals_trade_direction_long(self):
        dh = MagicMock()
        dh.get_current_positions.return_value = []
        sig1 = {"type": "open_long", "position_size": 0.1, "timestamp": int(time.time())}
        sig2 = {"type": "open_short", "position_size": 0.1, "timestamp": int(time.time())}
        
        ctx = dict(self.strategy_ctx)
        ctx["trading_config"]["trade_direction"] = "long"

        with patch("app.services.signal_processor.check_take_profit_or_trailing_signal", return_value=None), \
             patch("app.services.signal_processor.check_stop_loss_signal", return_value=None), \
             patch("app.services.signal_processor.DataHandler", return_value=dh):
            selected, positions = process_signals(
                strategy_ctx=ctx, symbol="BTC/USDT", triggered_signals=[sig1, sig2],
                current_price=100.0,
            )
            assert selected is not None
            assert selected["type"] == "open_long"

    def test_process_signals_trade_direction_short(self):
        dh = MagicMock()
        dh.get_current_positions.return_value = []
        sig1 = {"type": "open_long", "position_size": 0.1, "timestamp": int(time.time())}
        sig2 = {"type": "open_short", "position_size": 0.1, "timestamp": int(time.time())}

        ctx = dict(self.strategy_ctx)
        ctx["trading_config"]["trade_direction"] = "short"

        with patch("app.services.signal_processor.check_take_profit_or_trailing_signal", return_value=None), \
             patch("app.services.signal_processor.check_stop_loss_signal", return_value=None), \
             patch("app.services.signal_processor.DataHandler", return_value=dh):
            selected, positions = process_signals(
                strategy_ctx=ctx, symbol="BTC/USDT", triggered_signals=[sig1, sig2],
                current_price=100.0,
            )
            assert selected is not None
            assert selected["type"] == "open_short"

    def test_process_signals_dedup_skips_all(self):
        dh = MagicMock()
        dh.get_current_positions.return_value = []
        sig = {"type": "open_long", "position_size": 0.1, "timestamp": int(time.time())}
        with patch("app.services.signal_processor.check_take_profit_or_trailing_signal", return_value=None), \
             patch("app.services.signal_processor.check_stop_loss_signal", return_value=None), \
             patch("app.services.signal_processor.DataHandler", return_value=dh), \
             patch("app.services.signal_processor.get_signal_deduplicator") as mock_dedup:
            mock_dedup.return_value.should_skip_signal_once_per_candle.return_value = True
            selected, positions = process_signals(
                strategy_ctx=self.strategy_ctx, symbol="BTC/USDT", triggered_signals=[sig],
                current_price=100.0,
            )
            assert selected is None
        dh = MagicMock()
        dh.get_current_positions.return_value = []
        selected, positions = process_signals(
            strategy_ctx=self.strategy_ctx, symbol="BTC/USDT", triggered_signals=[],
            current_price=100.0,
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
                strategy_ctx=self.strategy_ctx, symbol="BTC/USDT", triggered_signals=[sig],
                current_price=100.0,
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
                strategy_ctx=self.strategy_ctx, symbol="BTC/USDT", triggered_signals=[sig],
                current_price=100.0,
            )
        assert selected is None
        assert len(positions) == 1
