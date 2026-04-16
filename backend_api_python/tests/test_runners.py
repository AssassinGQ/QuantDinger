"""
runner 层的单元测试，补充边缘分支和异常分支覆盖率。
"""
from unittest.mock import MagicMock, patch

from app.strategies.runners.base_runner import BaseStrategyRunner
from app.strategies.runners.single_symbol_runner import SingleSymbolRunner
from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner

class DummyRunner(BaseStrategyRunner):
    """用于测试BaseRunner的虚拟类"""
    def run(self, strategy_id, strategy, strat_instance, exchange):
        """覆盖抽象方法"""

def test_base_runner_is_running():
    """测试基类中从DataHandler获取状态的逻辑"""
    dh = MagicMock()
    runner = DummyRunner(data_handler=dh, signal_executor=MagicMock())

    dh.get_strategy_status.return_value = "running"
    assert runner.is_running(1) is True

    dh.get_strategy_status.return_value = "stopped"
    assert runner.is_running(1) is False

def test_single_symbol_runner_env_interval_error():
    """测试环境变量解析失败时的 fallback 逻辑"""
    runner = SingleSymbolRunner(MagicMock(), MagicMock())
    with patch.dict("os.environ", {"STRATEGY_TICK_INTERVAL_SEC": "invalid"}), \
         patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner.is_running",
             side_effect=[False]
         ):
        runner.run(1, {}, MagicMock(), None)

def test_single_symbol_runner_current_price_none():
    """测试获取价格失败时的 continue 分支"""
    runner = SingleSymbolRunner(MagicMock(), MagicMock())
    runner.price_fetcher = MagicMock()
    runner.price_fetcher.fetch_current_price.return_value = None

    with patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner.is_running",
             side_effect=[True, False]
         ), \
         patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner._wait_for_next_tick",
             return_value=(False, 0, 0)
         ):
        runner.run(1, {}, MagicMock(), None)

def test_single_symbol_runner_ctx_none():
    """测试获取数据上下文失败时的 continue 分支"""
    runner = SingleSymbolRunner(MagicMock(), MagicMock())
    runner.price_fetcher = MagicMock()
    runner.price_fetcher.fetch_current_price.return_value = 100.0
    runner.data_handler.get_input_context_single.return_value = None

    with patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner.is_running",
             side_effect=[True, False]
         ), \
         patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner._wait_for_next_tick",
             return_value=(False, 0, 0)
         ):
        runner.run(1, {}, MagicMock(), None)

def test_single_symbol_runner_keep_running_false():
    """测试策略返回 keep_running=False 时主动退出循环"""
    runner = SingleSymbolRunner(MagicMock(), MagicMock())
    runner.price_fetcher = MagicMock()
    runner.price_fetcher.fetch_current_price.return_value = 100.0
    runner.data_handler.get_input_context_single.return_value = {}

    strat_instance = MagicMock()
    strat_instance.get_signals.return_value = ([], False, False, None)

    with patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner.is_running",
             side_effect=[True, True]
         ), \
         patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner._wait_for_next_tick",
             return_value=(False, 0, 0)
         ):
        runner.run(1, {}, strat_instance, None)
    strat_instance.get_signals.assert_called_once()

def test_single_symbol_runner_exception_in_loop():
    """测试主循环内的异常被捕获且不中断线程"""
    runner = SingleSymbolRunner(MagicMock(), MagicMock())
    runner.price_fetcher = MagicMock()
    runner.price_fetcher.fetch_current_price.side_effect = Exception("Test Exception")

    with patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner.is_running",
             side_effect=[True, False]
         ), \
         patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner._wait_for_next_tick",
             return_value=(False, 0, 0)
         ), \
         patch("time.sleep"):
        runner.run(1, {}, MagicMock(), None)

def test_single_symbol_runner_process_signals_empty():
    """测试 process_and_execute_signals 处理空信号"""
    runner = SingleSymbolRunner(MagicMock(), MagicMock())
    # pylint: disable=protected-access
    runner._process_and_execute_signals({}, [], 100.0)
    runner.signal_executor.execute.assert_not_called()

def test_single_symbol_runner_process_signals_not_selected():
    """测试 process_signals 返回 None 时的卫语句"""
    runner = SingleSymbolRunner(MagicMock(), MagicMock())
    with patch(
             "app.strategies.runners.single_symbol_runner.process_signals",
             return_value=(None, [])
         ):
        # pylint: disable=protected-access
        runner._process_and_execute_signals(
            {"id": 1}, [{"type": "open_long"}], 100.0
        )
    runner.signal_executor.execute.assert_not_called()

def test_single_symbol_runner_process_signals_execute_fail():
    """测试 signal_executor.execute 返回 False 时的卫语句"""
    runner = SingleSymbolRunner(MagicMock(), MagicMock())
    runner.signal_executor.execute.return_value = False
    with patch(
             "app.strategies.runners.single_symbol_runner.process_signals",
             return_value=({"type": "open_long"}, [])
         ):
        with patch(
                 "app.services.portfolio_monitor.notify_strategy_signal_for_positions"
             ) as mock_notify:
            # pylint: disable=protected-access
            runner._process_and_execute_signals(
                {"id": 1}, [{"type": "open_long"}], 100.0
            )
            mock_notify.assert_not_called()

def test_single_symbol_runner_notify_exception():
    """测试通知组件异常不影响主流程"""
    runner = SingleSymbolRunner(MagicMock(), MagicMock())
    runner.signal_executor.execute.return_value = True
    with patch(
             "app.strategies.runners.single_symbol_runner.process_signals",
             return_value=({"type": "open_long"}, [])
         ):
        with patch(
                 "app.services.portfolio_monitor.notify_strategy_signal_for_positions",
                 side_effect=Exception("Notify Err")
             ):
            # pylint: disable=protected-access
            runner._process_and_execute_signals(
                {}, [{"type": "open_long"}], 100.0
            )

def test_single_symbol_runner_alerts_when_prev_close_stale():
    """prev_close 新鲜度 >1 天时，按策略通知配置发送告警"""
    runner = SingleSymbolRunner(MagicMock(), MagicMock())
    runner.price_fetcher = MagicMock()
    runner.price_fetcher.get_last_ticker_meta.return_value = {
        "last": 31.5,
        "previousClose": 31.3,
        "previousCloseAgeDays": 1.5,
    }
    strategy = {
        "_strategy_name": "s540",
        "_execution_mode": "live",
        "_notification_config": {"channels": ["browser"]},
    }
    with patch("app.services.signal_notifier.SignalNotifier.notify_signal") as mock_notify:
        # pylint: disable=protected-access
        runner._maybe_notify_prev_close_stale(540, strategy, "XAGUSD", "Forex")
        mock_notify.assert_called_once()
        kwargs = mock_notify.call_args.kwargs
        assert kwargs["strategy_id"] == 540
        assert kwargs["symbol"] == "XAGUSD"
        assert kwargs["notification_config"] == {"channels": ["browser"]}
        assert kwargs["signal_type"] == "risk_data_stale_prev_close"
        assert kwargs["extra"]["prev_close_source"] == ""

def test_single_symbol_runner_alert_throttled():
    """同一策略在冷却窗口内不会重复发 stale 告警"""
    runner = SingleSymbolRunner(MagicMock(), MagicMock())
    runner.price_fetcher = MagicMock()
    runner.price_fetcher.get_last_ticker_meta.return_value = {
        "last": 31.5,
        "previousClose": 31.3,
        "previousCloseAgeDays": 2.0,
    }
    strategy = {"_notification_config": {"channels": ["browser"]}}
    with patch("app.services.signal_notifier.SignalNotifier.notify_signal") as mock_notify:
        # pylint: disable=protected-access
        runner._maybe_notify_prev_close_stale(541, strategy, "XAUUSD", "Forex")
        runner._maybe_notify_prev_close_stale(541, strategy, "XAUUSD", "Forex")
        assert mock_notify.call_count == 1

def test_single_symbol_runner_alert_not_triggered_on_non_forex():
    """非 Forex/Metals 不触发 stale 告警"""
    runner = SingleSymbolRunner(MagicMock(), MagicMock())
    runner.price_fetcher = MagicMock()
    runner.price_fetcher.get_last_ticker_meta.return_value = {
        "previousCloseAgeDays": 99.0,
    }
    with patch("app.services.signal_notifier.SignalNotifier.notify_signal") as mock_notify:
        # pylint: disable=protected-access
        runner._maybe_notify_prev_close_stale(542, {}, "BTC/USDT", "Crypto")
        mock_notify.assert_not_called()

def test_cross_sectional_runner_interval_less_than_1():
    """测试截面策略时间间隔配置异常的 fallback"""
    runner = CrossSectionalRunner(MagicMock(), MagicMock())
    with patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner.is_running",
             side_effect=[False]
         ):
        runner.run(1, {"trading_config": {"decide_interval": 0}}, MagicMock(), None)

def test_cross_sectional_runner_keep_running_false():
    """测试截面策略返回 keep_running=False 时主动退出循环"""
    runner = CrossSectionalRunner(MagicMock(), MagicMock())
    runner.data_handler.get_input_context_cross.return_value = {}

    strat_instance = MagicMock()
    strat_instance.should_execute.return_value = True
    strat_instance.get_signals.return_value = ([], False, False, None)

    with patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner.is_running",
             side_effect=[True, True]
         ), \
         patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner._wait_for_next_tick",
             return_value=(False, 0, 0)
         ):
        runner.run(1, {}, strat_instance, None)
    strat_instance.get_signals.assert_called_once()

def test_cross_sectional_runner_exception_in_loop():
    """测试截面策略主循环内异常被捕获且不中断线程"""
    runner = CrossSectionalRunner(MagicMock(), MagicMock())
    runner.data_handler.get_last_rebalance_at.side_effect = Exception("Cross Exception")

    with patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner.is_running",
             side_effect=[True, False]
         ), \
         patch(
             "app.strategies.runners.base_runner.BaseStrategyRunner._wait_for_next_tick",
             return_value=(False, 0, 0)
         ), \
         patch("time.sleep"):
        runner.run(1, {}, MagicMock(), None)
