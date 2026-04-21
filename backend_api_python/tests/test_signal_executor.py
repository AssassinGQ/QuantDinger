import time
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
from app.services.ibkr_insufficient_user_alert import reset_insufficient_user_alert_dedup_state
from app.services.signal_executor import SignalExecutor


@pytest.fixture
def mock_dh():
    return MagicMock()


@pytest.fixture
def signal_executor(mock_dh):
    executor = SignalExecutor()
    executor.data_handler = mock_dh
    executor.pending_order_enqueuer = MagicMock()
    return executor


class TestSignalExecutorExecute:
    def test_state_machine_guard_rejects_invalid_signal(self, signal_executor):
        # Long position exists, try to open short (invalid state transition)
        strategy_ctx = {"_market_type": "swap"}
        signal = {"type": "open_short"}
        current_positions = [{"side": "long", "size": 0.1}]

        result = signal_executor.execute(
            strategy_ctx, signal, symbol="BTC/USDT", current_price=100.0, current_positions=current_positions
        )
        assert result is False
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_not_called()

    def test_spot_market_rejects_short(self, signal_executor):
        strategy_ctx = {"_market_type": "spot"}
        signal = {"type": "open_short"}
        current_positions = []

        result = signal_executor.execute(
            strategy_ctx, signal, symbol="BTC/USDT", current_price=100.0, current_positions=current_positions
        )
        assert result is False

    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_open_long_sizing_swap(self, _mock_capital, signal_executor):
        strategy_ctx = {
            "id": 1,
            "_leverage": 2.0,
            "_market_type": "swap",
            "trading_config": {"entry_pct": 0.1}
        }
        signal = {"type": "open_long"}

        # execution_mode defaults to signal if not present
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        result = signal_executor.execute(
            strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=[]
        )

        assert result is True
        # amount = 10000.0 * 0.1 * 2.0 / 50000.0 = 0.04
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_called_once()
        call_kwargs = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]
        assert call_kwargs["amount"] == 0.04
        assert call_kwargs["signal_type"] == "open_long"

    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_reduce_long_sizing(self, _mock_capital, signal_executor):
        strategy_ctx = {"id": 1, "_execution_mode": "live"}
        signal = {"type": "reduce_long", "position_size": 0.5}  # 50% reduction
        current_positions = [{"side": "long", "size": 0.8, "entry_price": 40000.0}]

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        result = signal_executor.execute(
            strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
        )

        assert result is True
        call_kwargs = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]
        assert call_kwargs["amount"] == 0.4
        assert call_kwargs["signal_type"] == "reduce_long"

    def test_close_long_sizing(self, signal_executor):
        strategy_ctx = {"id": 1, "_execution_mode": "live"}
        signal = {"type": "close_long"}
        current_positions = [{"side": "long", "size": 0.8, "entry_price": 40000.0}]

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        result = signal_executor.execute(
            strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
        )

        assert result is True
        call_kwargs = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]
        assert call_kwargs["amount"] == 0.8
        assert call_kwargs["signal_type"] == "close_long"

    def test_open_long_sizing_spot(self, signal_executor):
        strategy_ctx = {
            "id": 1,
            "_leverage": 1.0,
            "_market_type": "spot",
            "trading_config": {"entry_pct": 0.1}
        }
        signal = {"type": "open_long"}
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=[]
            )

        assert result is True
        call_kwargs = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]
        assert call_kwargs["amount"] == 10000.0 * 0.1 / 50000.0
        assert call_kwargs["signal_type"] == "open_long"

    def test_reduce_long_sizing_full_close(self, signal_executor):
        strategy_ctx = {"id": 1, "_execution_mode": "live"}
        signal = {"type": "reduce_long", "position_size": 1.0}  # 100% reduction -> close
        current_positions = [{"side": "long", "size": 0.8, "entry_price": 40000.0}]

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is True
        call_kwargs = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]
        assert call_kwargs["amount"] == 0.8
        assert call_kwargs["signal_type"] == "close_long"

    def test_reduce_long_missing_position(self, signal_executor):
        strategy_ctx = {"id": 1}
        signal = {"type": "reduce_long", "position_size": 0.5}
        current_positions = []

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is False

    def test_reduce_long_zero_size(self, signal_executor):
        strategy_ctx = {"id": 1}
        signal = {"type": "reduce_long", "position_size": 0.5}
        current_positions = [{"side": "long", "size": 0.0}]

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is False

    def test_close_long_missing_position(self, signal_executor):
        strategy_ctx = {"id": 1}
        signal = {"type": "close_long"}
        current_positions = []

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is False

    def test_close_long_zero_size(self, signal_executor):
        strategy_ctx = {"id": 1}
        signal = {"type": "close_long"}
        current_positions = [{"side": "long", "size": 0.0}]

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is False

    def test_open_long_signal_mode_update_db(self, signal_executor):
        strategy_ctx = {"id": 1, "_execution_mode": "signal"}
        signal = {"type": "open_long"}
        current_positions = []

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is True
        signal_executor.data_handler.record_trade.assert_called_once()
        signal_executor.data_handler.update_position.assert_called_once()

    def test_add_long_signal_mode_update_db(self, signal_executor):
        strategy_ctx = {"id": 1, "_execution_mode": "signal"}
        signal = {"type": "add_long"}
        current_positions = [{"side": "long", "size": 0.1, "entry_price": 40000.0}]

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is True
        signal_executor.data_handler.record_trade.assert_called_once()
        signal_executor.data_handler.update_position.assert_called_once()

    def test_reduce_long_signal_mode_update_db(self, signal_executor):
        strategy_ctx = {"id": 1, "_execution_mode": "signal"}
        signal = {"type": "reduce_long", "position_size": 0.5}
        current_positions = [{"side": "long", "size": 0.2, "entry_price": 40000.0}]

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is True
        signal_executor.data_handler.record_trade.assert_called_once()
        signal_executor.data_handler.update_position.assert_called_once()

    def test_reduce_long_signal_mode_full_close(self, signal_executor):
        strategy_ctx = {"id": 1, "_execution_mode": "signal"}
        signal = {"type": "reduce_long", "position_size": 1.0}
        current_positions = [{"side": "long", "size": 0.2, "entry_price": 40000.0}]

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is True
        signal_executor.data_handler.record_trade.assert_called_once()
        signal_executor.data_handler.close_position.assert_called_once()

    def test_close_long_signal_mode_update_db(self, signal_executor):
        strategy_ctx = {"id": 1, "_execution_mode": "signal"}
        signal = {"type": "close_long"}
        current_positions = [{"side": "long", "size": 0.2, "entry_price": 40000.0}]

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is True
        signal_executor.data_handler.record_trade.assert_called_once()
        signal_executor.data_handler.close_position.assert_called_once()

    def test_execute_exception(self, signal_executor):
        strategy_ctx = {"id": 1}
        signal = {"type": "open_long"}

        with patch("app.services.signal_executor._get_available_capital", side_effect=RuntimeError("Error")):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=[]
            )

        assert result is False

    def test_reduce_short_signal_mode_update_db(self, signal_executor):
        strategy_ctx = {"id": 1, "_execution_mode": "signal"}
        signal = {"type": "reduce_short", "position_size": 0.5}
        current_positions = [{"side": "short", "size": 0.2, "entry_price": 60000.0}]

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is True
        signal_executor.data_handler.record_trade.assert_called_once()
        signal_executor.data_handler.update_position.assert_called_once()

    def test_close_short_signal_mode_update_db(self, signal_executor):
        strategy_ctx = {"id": 1, "_execution_mode": "signal"}
        signal = {"type": "close_short"}
        current_positions = [{"side": "short", "size": 0.2, "entry_price": 60000.0}]

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is True
        signal_executor.data_handler.record_trade.assert_called_once()
        signal_executor.data_handler.close_position.assert_called_once()

    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_signal_mode_updates_db(self, _mock_capital, signal_executor):
        strategy_ctx = {
            "id": 1,
            "_execution_mode": "signal",
            "trading_config": {"entry_pct": 0.1}
        }
        signal = {"type": "open_long"}

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        result = signal_executor.execute(
            strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=[]
        )

        assert result is True
        signal_executor.data_handler.record_trade.assert_called_once()
        signal_executor.data_handler.update_position.assert_called_once()

    @patch("app.services.signal_executor.is_entry_ai_filter_enabled")
    @patch("app.services.signal_executor.entry_ai_filter_allows")
    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_ai_filter_rejection(self, _mock_capital, mock_allows, mock_enabled, signal_executor):
        """Test that AI filter rejection prevents order execution."""
        strategy_ctx = {
            "id": 1,
            "_market_type": "swap",
            "trading_config": {},
            "ai_model_config": {"entry_ai_filter_enabled": True}
        }
        signal = {"type": "open_long"}

        mock_enabled.return_value = True
        mock_allows.return_value = (False, {"reason": "direction_mismatch", "ai_decision": "SELL"})

        result = signal_executor.execute(
            strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=[]
        )

        assert result is False
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_not_called()
        signal_executor.data_handler.persist_notification.assert_called_once()

        call_kwargs = signal_executor.data_handler.persist_notification.call_args[1]
        assert call_kwargs["signal_type"] == "ai_filter_hold"
        assert "direction_mismatch" in call_kwargs["message"]

    @patch("app.services.signal_executor.is_entry_ai_filter_enabled")
    @patch("app.services.signal_executor.entry_ai_filter_allows")
    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_ai_filter_approval(self, _mock_capital, mock_allows, mock_enabled, signal_executor):
        """Test that AI filter approval allows order execution."""
        strategy_ctx = {
            "id": 1,
            "_market_type": "swap",
            "trading_config": {},
            "ai_model_config": {"entry_ai_filter_enabled": True}
        }
        signal = {"type": "open_long"}

        mock_enabled.return_value = True
        mock_allows.return_value = (True, {"reason": "match", "ai_decision": "BUY"})
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        result = signal_executor.execute(
            strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=[]
        )

        assert result is True
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_called_once()
        signal_executor.data_handler.persist_notification.assert_not_called()

    def test_execute_order_result_none(self, signal_executor):
        strategy_ctx = {"id": 1, "_execution_mode": "live"}
        signal = {"type": "open_long"}
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = None

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=[]
            )

        assert result is False

    def test_execute_order_result_not_success(self, signal_executor):
        strategy_ctx = {"id": 1, "_execution_mode": "live"}
        signal = {"type": "open_long"}
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": False, "error": "insufficient margin"}

        with patch("app.services.signal_executor._get_available_capital", return_value=10000.0):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=[]
            )

        assert result is False

    def test_handle_reduce_position_no_pos(self, signal_executor):
        # pylint: disable=protected-access
        signal_executor._handle_reduce_position(1, "BTC/USDT", "reduce_long", 0.5, 50000.0, [])
        signal_executor.data_handler.record_trade.assert_not_called()

    def test_handle_reduce_position_zero_entry_price(self, signal_executor):
        # pylint: disable=protected-access
        current_positions = [{"side": "long", "size": 1.0, "entry_price": 0.0}]
        signal_executor._handle_reduce_position(1, "BTC/USDT", "reduce_long", 0.5, 50000.0, current_positions)

        signal_executor.data_handler.record_trade.assert_called_once()
        call_kwargs = signal_executor.data_handler.record_trade.call_args[1]
        assert call_kwargs.get("profit") is None

    def test_handle_close_position_no_pos(self, signal_executor):
        # pylint: disable=protected-access
        signal_executor._handle_close_position(1, "BTC/USDT", "close_long", 1.0, 50000.0, [])
        signal_executor.data_handler.record_trade.assert_not_called()

    def test_handle_close_position_zero_entry_price(self, signal_executor):
        # pylint: disable=protected-access
        current_positions = [{"side": "long", "size": 1.0, "entry_price": 0.0}]
        signal_executor._handle_close_position(1, "BTC/USDT", "close_long", 1.0, 50000.0, current_positions)

        signal_executor.data_handler.record_trade.assert_called_once()
        call_kwargs = signal_executor.data_handler.record_trade.call_args[1]
        assert call_kwargs.get("profit") is None

    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_target_weight_add_position(self, _mock_capital, signal_executor):
        """Test target_weight causing an add_long signal."""
        strategy_ctx = {
            "id": 1,
            "_leverage": 1.0,
            "_market_type": "spot",
            "_execution_mode": "live",
            "ai_model_config": {"entry_ai_filter_enabled": False}
        }
        # Target is 0.5 weight. Capital=10000, price=50000 -> target amount = 0.1 BTC
        signal = {"type": "open_long", "target_weight": 0.5}

        # Currently holding 0.04 BTC, so need to add 0.06 BTC
        current_positions = [{"side": "long", "size": 0.04, "entry_price": 40000.0}]

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        with patch.object(signal_executor, "_check_ai_filter", return_value=True):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is True
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_called_once()
        call_kwargs = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]

        # 0.1 - 0.04 = 0.06
        assert abs(call_kwargs["amount"] - 0.06) < 1e-6
        assert call_kwargs["signal_type"] == "add_long"

    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_target_weight_reduce_position(self, _mock_capital, signal_executor):
        """Test target_weight causing a reduce_long signal."""
        strategy_ctx = {
            "id": 1,
            "_leverage": 1.0,
            "_market_type": "spot",
            "_execution_mode": "live",
            "ai_model_config": {"entry_ai_filter_enabled": False}
        }
        # Target is 0.2 weight. Capital=10000, price=50000 -> target amount = 0.04 BTC
        signal = {"type": "open_long", "target_weight": 0.2}

        # Currently holding 0.1 BTC, so need to reduce 0.06 BTC
        current_positions = [{"side": "long", "size": 0.1, "entry_price": 40000.0}]

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        with patch.object(signal_executor, "_check_ai_filter", return_value=True):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is True
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_called_once()
        call_kwargs = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]

        # 0.1 - 0.04 = 0.06
        assert abs(call_kwargs["amount"] - 0.06) < 1e-6
        assert call_kwargs["signal_type"] == "reduce_long"

    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_target_weight_close_position(self, _mock_capital, signal_executor):
        """Test target_weight causing a close_long signal (target close to 0)."""
        strategy_ctx = {
            "id": 1,
            "_leverage": 1.0,
            "_market_type": "spot",
            "_execution_mode": "live",
            "ai_model_config": {"entry_ai_filter_enabled": False}
        }
        # Target is 0 weight
        signal = {"type": "open_long", "target_weight": 0.0}

        # Currently holding 0.1 BTC
        current_positions = [{"side": "long", "size": 0.1, "entry_price": 40000.0}]

        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        with patch.object(signal_executor, "_check_ai_filter", return_value=True):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
            )

        assert result is True
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_called_once()
        call_kwargs = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]

        # Should close entire 0.1
        assert abs(call_kwargs["amount"] - 0.1) < 1e-6
        assert call_kwargs["signal_type"] == "close_long"

    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_target_weight_no_change(self, _mock_capital, signal_executor):
        """Test target_weight causing no change if already at target."""
        strategy_ctx = {
            "id": 1,
            "_leverage": 1.0,
            "_market_type": "spot",
        }
        # Target is 0.5 weight. Capital=10000, price=50000 -> target amount = 0.1 BTC
        signal = {"type": "open_long", "target_weight": 0.5}

        # Already holding exactly 0.1 BTC
        current_positions = [{"side": "long", "size": 0.1, "entry_price": 40000.0}]

        result = signal_executor.execute(
            strategy_ctx, signal, symbol="BTC/USDT", current_price=50000.0, current_positions=current_positions
        )

        # Amount calculated will be 0, so executor returns False (no trade needed)
        assert result is False
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_not_called()


class TestSignalExecutorForexLimitEnqueue:
    """UC-03c / UC-03d: live Forex/Metals + trading_config.live_order limit → limit_price."""

    @patch("app.services.signal_executor._get_available_capital", return_value=100000.0)
    def test_uc_03c_limit_buy_price(self, _mock_capital, signal_executor):
        strategy_ctx = {
            "id": 1,
            "_execution_mode": "live",
            "_market_category": "Forex",
            "_market_type": "forex",
            "trading_config": {
                "live_order": {"order_type": "limit", "max_slippage_pips": 10.0},
            },
        }
        signal = {"type": "open_long"}
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        result = signal_executor.execute(
            strategy_ctx, signal, symbol="EURUSD", current_price=1.1, current_positions=[]
        )

        assert result is True
        kw = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]
        assert kw["order_type"] == "limit"
        assert abs(kw["limit_price"] - 1.101) < 1e-9

    @patch("app.services.signal_executor._get_available_capital", return_value=100000.0)
    def test_uc_03c_limit_sell_price(self, _mock_capital, signal_executor):
        strategy_ctx = {
            "id": 1,
            "_execution_mode": "live",
            "_market_category": "Forex",
            "_market_type": "forex",
            "trading_config": {
                "live_order": {"order_type": "limit", "max_slippage_pips": 10.0},
            },
        }
        signal = {"type": "open_short"}
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        result = signal_executor.execute(
            strategy_ctx, signal, symbol="EURUSD", current_price=1.1, current_positions=[]
        )

        assert result is True
        kw = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]
        assert kw["order_type"] == "limit"
        assert abs(kw["limit_price"] - 1.099) < 1e-9

    @patch("app.services.signal_executor._get_available_capital", return_value=100000.0)
    def test_limit_rejected_non_positive_limit_px(self, _mock_capital, signal_executor):
        strategy_ctx = {
            "id": 1,
            "_execution_mode": "live",
            "_market_category": "Forex",
            "_market_type": "forex",
            "trading_config": {
                "live_order": {"order_type": "limit", "max_slippage_pips": 10.0},
            },
        }
        signal = {"type": "open_short"}
        with patch.object(
            signal_executor, "_calculate_order_amount", return_value=(0.1, "open_short")
        ):
            result = signal_executor.execute(
                strategy_ctx, signal, symbol="EURUSD", current_price=0.0, current_positions=[]
            )

        assert result is False
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_not_called()

    @patch("app.services.signal_executor._get_available_capital", return_value=100000.0)
    def test_signal_mode_ignores_live_order_limit(self, _mock_capital, signal_executor):
        strategy_ctx = {
            "id": 1,
            "_execution_mode": "signal",
            "_market_category": "Forex",
            "_market_type": "forex",
            "trading_config": {
                "live_order": {"order_type": "limit", "max_slippage_pips": 10.0},
            },
        }
        signal = {"type": "open_long"}
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        result = signal_executor.execute(
            strategy_ctx, signal, symbol="EURUSD", current_price=1.1, current_positions=[]
        )

        assert result is True
        kw = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]
        assert kw.get("order_type") == "market"
        assert kw.get("limit_price") is None


class TestSignalExecutorMarketPreNormalize:
    """TC-15-T3-03: enqueue path uses get_market_pre_normalizer().pre_normalize before execute_exchange_order."""

    @patch("app.services.signal_executor.get_market_pre_normalizer")
    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_tc_15_t3_03_enqueue_uses_pre_normalize(
        self, _mock_capital, mock_get_pre_norm, signal_executor
    ):
        """TC-15-T3-03: execute_exchange_order amount equals mocked pre_normalize output."""
        mock_normalizer = MagicMock()
        mock_normalizer.pre_normalize.return_value = 42.0
        mock_get_pre_norm.return_value = mock_normalizer

        strategy_ctx = {
            "id": 1,
            "_leverage": 2.0,
            "_market_type": "swap",
            "_market_category": "Crypto",
            "trading_config": {"entry_pct": 0.1},
        }
        signal = {"type": "open_long"}
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}

        result = signal_executor.execute(
            strategy_ctx,
            signal,
            symbol="BTC/USDT",
            current_price=50000.0,
            current_positions=[],
        )

        assert result is True
        mock_normalizer.pre_normalize.assert_called_once()
        call_kwargs = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]
        assert call_kwargs["amount"] == 42.0


class TestGetAvailableCapital:
    """_get_available_capital 函数测试"""

    @patch("app.services.signal_executor.DataHandler")
    def test_returns_available_capital_with_no_positions(self, mock_data_handler_class):
        from app.services.signal_executor import _get_available_capital

        mock_dh = MagicMock()
        mock_dh.get_position_used_capital.return_value = 0.0
        mock_dh.get_pending_order_amount.return_value = 0.0
        mock_data_handler_class.return_value = mock_dh

        result = _get_available_capital(1, 10000.0)
        assert result == 10000.0
        mock_dh.get_position_used_capital.assert_called_once_with(1)
        mock_dh.get_pending_order_amount.assert_called_once_with(1)

    @patch("app.services.signal_executor.DataHandler")
    def test_returns_available_capital_with_positions(self, mock_data_handler_class):
        from app.services.signal_executor import _get_available_capital

        mock_dh = MagicMock()
        mock_dh.get_position_used_capital.return_value = 3000.0
        mock_dh.get_pending_order_amount.return_value = 1000.0
        mock_data_handler_class.return_value = mock_dh

        result = _get_available_capital(1, 10000.0)
        assert result == 6000.0

    @patch("app.services.signal_executor.DataHandler")
    def test_returns_zero_when_capital_exhausted(self, mock_data_handler_class):
        from app.services.signal_executor import _get_available_capital

        mock_dh = MagicMock()
        mock_dh.get_position_used_capital.return_value = 8000.0
        mock_dh.get_pending_order_amount.return_value = 3000.0
        mock_data_handler_class.return_value = mock_dh

        result = _get_available_capital(1, 10000.0)
        assert result == 0.0

    @patch("app.services.signal_executor.DataHandler")
    def test_returns_initial_capital_on_exception(self, mock_data_handler_class):
        from app.services.signal_executor import _get_available_capital

        mock_dh = MagicMock()
        mock_dh.get_position_used_capital.side_effect = Exception("DB Error")
        mock_data_handler_class.return_value = mock_dh

        result = _get_available_capital(1, 10000.0)
        assert result == 10000.0


def _missing_bars_result() -> DataSufficiencyResult:
    diag = DataSufficiencyDiagnostics(
        parsed_session_count=1,
        schedule_failure_reason=None,
        timezone_id="EST",
        timezone_resolution="explicit",
        prev_close_stale_since=None,
        con_id=None,
    )
    return DataSufficiencyResult(
        sufficient=False,
        reason_code=DataSufficiencyReasonCode.MISSING_BARS,
        required_bars=100,
        available_bars=0,
        effective_lookback=effective_lookback_seconds("1H", 100),
        missing_window=missing_window_seconds("1H", 100, 0),
        schedule_status=IBKRScheduleStatus.SCHEDULE_KNOWN_OPEN,
        symbol="SPY",
        timeframe="1H",
        market_category="USStock",
        diagnostics=diag,
    )


class TestIBKROpenSufficiencyGate:
    """IBKR live open/add sufficiency choke point (Phase 2)."""

    @patch("app.services.signal_executor.evaluate_ibkr_open_data_sufficiency")
    @patch.object(SignalExecutor, "_resolve_ibkr_contract_details_for_symbol")
    def test_ibkr_live_open_blocked_when_insufficient(
        self, mock_resolve, mock_eval, signal_executor
    ):
        mock_resolve.return_value = MagicMock(contract=MagicMock(conId=99))
        mock_eval.return_value = _missing_bars_result()
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {
            "success": True
        }
        strategy_ctx = {
            "id": 1,
            "_execution_mode": "live",
            "exchange_config": {"exchange_id": "ibkr-paper"},
            "_market_category": "USStock",
            "trading_config": {"timeframe": "1H", "required_bars": 100},
        }
        signal = {"type": "open_long"}

        with patch(
            "app.services.signal_executor._get_available_capital", return_value=10000.0
        ):
            result = signal_executor.execute(
                strategy_ctx,
                signal,
                symbol="SPY",
                current_price=100.0,
                current_positions=[],
                exchange=object(),
            )

        assert result is False
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_not_called()

    @patch("app.services.signal_executor.evaluate_ibkr_open_data_sufficiency")
    def test_reduce_not_blocked_by_sufficiency(self, mock_eval, signal_executor):
        mock_eval.side_effect = AssertionError("reduce must not invoke sufficiency")
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {
            "success": True
        }
        strategy_ctx = {
            "id": 1,
            "_execution_mode": "live",
            "_market_type": "swap",
            "exchange_config": {"exchange_id": "ibkr-live"},
            "_market_category": "Crypto",
        }
        signal = {"type": "reduce_long", "position_size": 0.5}
        positions = [{"side": "long", "size": 1.0, "entry_price": 50.0}]

        with patch(
            "app.services.signal_executor._get_available_capital", return_value=10000.0
        ):
            signal_executor.execute(
                strategy_ctx,
                signal,
                symbol="BTC/USDT",
                current_price=100.0,
                current_positions=positions,
                exchange=None,
            )

        mock_eval.assert_not_called()
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_called_once()

    @patch("app.services.signal_executor.evaluate_ibkr_open_data_sufficiency")
    def test_non_ibkr_exchange_skips_sufficiency_guard(
        self, mock_eval, signal_executor
    ):
        mock_eval.side_effect = AssertionError("non-IBKR must skip sufficiency")
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {
            "success": True
        }
        strategy_ctx = {
            "id": 1,
            "_execution_mode": "live",
            "exchange_config": {"exchange_id": "binance"},
            "_market_category": "USStock",
            "trading_config": {"entry_pct": 0.1},
        }
        signal = {"type": "open_long"}

        with patch(
            "app.services.signal_executor._get_available_capital", return_value=10000.0
        ):
            signal_executor.execute(
                strategy_ctx,
                signal,
                symbol="BTC/USDT",
                current_price=50000.0,
                current_positions=[],
                exchange=None,
            )

        mock_eval.assert_not_called()

    @patch("app.services.signal_executor.evaluate_ibkr_open_data_sufficiency")
    def test_joint_gate_skips_guard_when_not_live(self, mock_eval, signal_executor):
        mock_eval.side_effect = AssertionError("non-live must skip sufficiency")
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {
            "success": True
        }
        strategy_ctx = {
            "id": 1,
            "_execution_mode": "signal",
            "exchange_config": {"exchange_id": "ibkr-paper"},
            "_market_category": "USStock",
            "trading_config": {"entry_pct": 0.1},
        }
        signal = {"type": "open_long"}

        with patch(
            "app.services.signal_executor._get_available_capital", return_value=10000.0
        ):
            signal_executor.execute(
                strategy_ctx,
                signal,
                symbol="SPY",
                current_price=100.0,
                current_positions=[],
                exchange=None,
            )

        mock_eval.assert_not_called()

    @patch.object(SignalExecutor, "_resolve_ibkr_contract_details_for_symbol", return_value=None)
    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_ibkr_insufficient_block_triggers_user_notify(
        self, _mock_capital, _mock_details, signal_executor
    ):
        reset_insufficient_user_alert_dedup_state()
        sn = MagicMock()
        sn.notify_signal.return_value = {"browser": {"ok": True, "error": ""}}
        signal_executor.signal_notifier = sn
        strategy_ctx = {
            "id": 501,
            "_execution_mode": "live",
            "exchange_config": {"exchange_id": "ibkr-paper"},
            "_market_category": "USStock",
            "trading_config": {"timeframe": "1H", "required_bars": 100},
            "_notification_config": {"channels": ["browser"], "targets": {}},
        }
        signal = {"type": "open_long", "timestamp": 1}
        result = signal_executor.execute(
            strategy_ctx,
            signal,
            symbol="SPY",
            current_price=400.0,
            current_positions=[],
            exchange=MagicMock(),
        )
        assert result is False
        sn.notify_signal.assert_called_once()
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_not_called()

    @patch("app.services.signal_executor.load_notification_config")
    @patch.object(SignalExecutor, "_resolve_ibkr_contract_details_for_symbol", return_value=None)
    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_ibkr_insufficient_block_loads_notification_config_when_missing(
        self, _mock_capital, _mock_details, mock_load, signal_executor
    ):
        reset_insufficient_user_alert_dedup_state()
        mock_load.return_value = {"channels": ["browser"], "targets": {}}
        sn = MagicMock()
        sn.notify_signal.return_value = {"browser": {"ok": True, "error": ""}}
        signal_executor.signal_notifier = sn
        strategy_ctx = {
            "id": 502,
            "_execution_mode": "live",
            "exchange_config": {"exchange_id": "ibkr-paper"},
            "_market_category": "USStock",
            "trading_config": {"timeframe": "1H", "required_bars": 100},
            "_notification_config": {"channels": [], "targets": {}},
        }
        signal = {"type": "open_long", "timestamp": 1}
        result = signal_executor.execute(
            strategy_ctx,
            signal,
            symbol="SPY",
            current_price=400.0,
            current_positions=[],
            exchange=MagicMock(),
        )
        assert result is False
        mock_load.assert_called_with(502)
        sn.notify_signal.assert_called_once()


class TestExecuteBatchExchange:
    def test_execute_batch_forwards_exchange_to_execute(self, signal_executor):
        mock_ex = MagicMock()
        with patch.object(signal_executor, "execute", return_value=True) as mock_exec:
            with patch.object(
                signal_executor, "_fetch_price_for_signal", return_value=50.0
            ):
                signal_executor.execute_batch(
                    strategy_ctx={"id": 1, "_market_category": "Crypto"},
                    signals=[
                        {"symbol": "BTC/USDT", "type": "open_long", "timestamp": 1}
                    ],
                    all_positions=[],
                    current_time=1,
                    exchange=mock_ex,
                )
        assert mock_exec.call_args[1]["exchange"] is mock_ex