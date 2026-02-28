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
            strategy_ctx, signal, "BTC/USDT", 100.0, current_positions
        )
        assert result is False
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_not_called()

    def test_spot_market_rejects_short(self, signal_executor):
        strategy_ctx = {"_market_type": "spot"}
        signal = {"type": "open_short"}
        current_positions = []
        
        result = signal_executor.execute(
            strategy_ctx, signal, "BTC/USDT", 100.0, current_positions
        )
        assert result is False

    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_open_long_sizing_swap(self, mock_capital, signal_executor):
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
            strategy_ctx, signal, "BTC/USDT", 50000.0, []
        )
        
        assert result is True
        # amount = 10000.0 * 0.1 * 2.0 / 50000.0 = 0.04
        signal_executor.pending_order_enqueuer.execute_exchange_order.assert_called_once()
        call_kwargs = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]
        assert call_kwargs["amount"] == 0.04
        assert call_kwargs["signal_type"] == "open_long"

    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_reduce_long_sizing(self, mock_capital, signal_executor):
        strategy_ctx = {"id": 1, "_execution_mode": "live"}
        signal = {"type": "reduce_long", "position_size": 0.5}  # 50% reduction
        current_positions = [{"side": "long", "size": 0.8, "entry_price": 40000.0}]
        
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}
        
        result = signal_executor.execute(
            strategy_ctx, signal, "BTC/USDT", 50000.0, current_positions
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
            strategy_ctx, signal, "BTC/USDT", 50000.0, current_positions
        )
        
        assert result is True
        call_kwargs = signal_executor.pending_order_enqueuer.execute_exchange_order.call_args[1]
        assert call_kwargs["amount"] == 0.8
        assert call_kwargs["signal_type"] == "close_long"

    @patch("app.services.signal_executor._get_available_capital", return_value=10000.0)
    def test_signal_mode_updates_db(self, mock_capital, signal_executor):
        strategy_ctx = {
            "id": 1,
            "_execution_mode": "signal",
            "trading_config": {"entry_pct": 0.1}
        }
        signal = {"type": "open_long"}
        
        signal_executor.pending_order_enqueuer.execute_exchange_order.return_value = {"success": True}
        
        result = signal_executor.execute(
            strategy_ctx, signal, "BTC/USDT", 50000.0, []
        )
        
        assert result is True
        signal_executor.data_handler.record_trade.assert_called_once()
        signal_executor.data_handler.update_position.assert_called_once()
