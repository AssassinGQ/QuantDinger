import time
from unittest.mock import MagicMock, patch
import pytest

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

