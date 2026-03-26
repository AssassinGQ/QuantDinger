"""
Tests for SingleRegimeWeightedRunner.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.strategies.runners.single_regime_weighted_runner import (
    SingleRegimeWeightedRunner,
    _TickArgs,
)
from app.strategies.regime_mixin import check_rebalance_due
from app.strategies.runners.factory import create_runner


class TestCheckRebalanceDue:
    """check_rebalance_due 函数的各种场景。"""

    def test_none_last_rebalance_returns_true(self):
        """首次运行（无 last_rebalance）应触发再平衡。"""
        assert check_rebalance_due("daily", None) is True

    def test_daily_fresh_returns_false(self):
        """刚刚 rebalance 过不应再次触发。"""
        recent = datetime.now() - timedelta(hours=1)
        assert check_rebalance_due("daily", recent) is False

    def test_daily_stale_returns_true(self):
        """超过 1 天应触发 daily rebalance。"""
        old = datetime.now() - timedelta(days=2)
        assert check_rebalance_due("daily", old) is True

    def test_weekly_within_range(self):
        """3 天前的 weekly 不应触发。"""
        recent = datetime.now() - timedelta(days=3)
        assert check_rebalance_due("weekly", recent) is False

    def test_weekly_stale(self):
        """8 天前的 weekly 应触发。"""
        old = datetime.now() - timedelta(days=8)
        assert check_rebalance_due("weekly", old) is True

    def test_monthly_within_range(self):
        """15 天前的 monthly 不应触发。"""
        recent = datetime.now() - timedelta(days=15)
        assert check_rebalance_due("monthly", recent) is False

    def test_monthly_stale(self):
        """31 天前的 monthly 应触发。"""
        old = datetime.now() - timedelta(days=31)
        assert check_rebalance_due("monthly", old) is True

    def test_unknown_freq_defaults_to_daily(self):
        """未知频率按 daily 处理。"""
        old = datetime.now() - timedelta(days=2)
        assert check_rebalance_due("hourly", old) is True


class TestRunnerFactory:
    """Runner 工厂正确分发 single_regime_weighted 类型。"""

    def test_creates_single_regime_weighted_runner(self):
        """single_regime_weighted 应创建 SingleRegimeWeightedRunner。"""
        dh = MagicMock()
        se = MagicMock()
        runner = create_runner("single_regime_weighted", dh, se)
        assert isinstance(runner, SingleRegimeWeightedRunner)

    def test_single_still_creates_base_runner(self):
        """single 类型不应创建 SingleRegimeWeightedRunner。"""
        dh = MagicMock()
        se = MagicMock()
        runner = create_runner("single", dh, se)
        assert not isinstance(runner, SingleRegimeWeightedRunner)


class TestSingleRegimeWeightedRunnerTick:
    """SingleRegimeWeightedRunner._run_single_tick 行为。"""

    def _make_runner(self):
        """构造 runner 及 mock 依赖。"""
        dh = MagicMock()
        se = MagicMock()
        runner = SingleRegimeWeightedRunner(dh, se)
        runner.price_fetcher = MagicMock()
        return runner, dh, se

    def _make_strategy(self, **config_overrides):
        """构造最小策略配置。"""
        tc = {
            "symbol": "BTC",
            "timeframe": "1H",
            "rebalance_frequency": "daily",
        }
        tc.update(config_overrides)
        return {
            "id": 1,
            "trading_config": tc,
            "_market_type": "swap",
            "_market_category": "Crypto",
            "_indicator_code": "",
        }

    def _make_tick_args(self, strategy, strat=None):
        """构造 _TickArgs。"""
        return _TickArgs(
            strategy_id=1,
            strategy=strategy,
            strat_instance=strat or MagicMock(),
            exchange=None,
            current_time=1000.0,
        )

    def test_injects_should_regime_rebalance_true(self):
        """last_rebalance=None 时 ctx 中 should_regime_rebalance=True。"""
        runner, dh, _se = self._make_runner()
        runner.price_fetcher.fetch_current_price.return_value = 100.0
        dh.get_last_rebalance_at.return_value = None
        dh.get_input_context_single.return_value = {
            "df": MagicMock(), "positions": [], "symbol": "BTC",
            "current_price": 100.0,
        }

        strat = MagicMock()
        strat.get_data_request.return_value = MagicMock()
        strat.get_signals.return_value = ([], True, False, None)

        args = self._make_tick_args(self._make_strategy(), strat)
        runner.run_tick(args)

        call_ctx = strat.get_signals.call_args[0][0]
        assert call_ctx["should_regime_rebalance"] is True

    def test_injects_should_regime_rebalance_false(self):
        """刚 rebalance 过时 ctx 中 should_regime_rebalance=False。"""
        runner, dh, _se = self._make_runner()
        runner.price_fetcher.fetch_current_price.return_value = 100.0
        dh.get_last_rebalance_at.return_value = datetime.now()
        dh.get_input_context_single.return_value = {
            "df": MagicMock(), "positions": [], "symbol": "BTC",
            "current_price": 100.0,
        }

        strat = MagicMock()
        strat.get_data_request.return_value = MagicMock()
        strat.get_signals.return_value = ([], True, False, None)

        args = self._make_tick_args(self._make_strategy(), strat)
        runner.run_tick(args)

        call_ctx = strat.get_signals.call_args[0][0]
        assert call_ctx["should_regime_rebalance"] is False

    def test_updates_last_rebalance_when_flagged(self):
        """update_rebalance=True 时调用 data_handler.update_last_rebalance。"""
        runner, dh, _se = self._make_runner()
        runner.price_fetcher.fetch_current_price.return_value = 100.0
        dh.get_last_rebalance_at.return_value = None
        dh.get_input_context_single.return_value = {
            "df": MagicMock(), "positions": [],
        }

        strat = MagicMock()
        strat.get_data_request.return_value = MagicMock()
        strat.get_signals.return_value = ([], True, True, {"current_regime": "normal"})

        args = self._make_tick_args(self._make_strategy(), strat)
        runner.run_tick(args)
        dh.update_last_rebalance.assert_called_once_with(1)

    def test_does_not_update_rebalance_when_not_flagged(self):
        """update_rebalance=False 时不更新 last_rebalance。"""
        runner, dh, _se = self._make_runner()
        runner.price_fetcher.fetch_current_price.return_value = 100.0
        dh.get_last_rebalance_at.return_value = None
        dh.get_input_context_single.return_value = {
            "df": MagicMock(), "positions": [],
        }

        strat = MagicMock()
        strat.get_data_request.return_value = MagicMock()
        strat.get_signals.return_value = ([], True, False, None)

        args = self._make_tick_args(self._make_strategy(), strat)
        runner.run_tick(args)
        dh.update_last_rebalance.assert_not_called()

    def test_saves_metadata_to_status_info(self):
        """有 meta 时应调用 update_strategy_status_info。"""
        runner, dh, _se = self._make_runner()
        runner.price_fetcher.fetch_current_price.return_value = 100.0
        dh.get_last_rebalance_at.return_value = None
        dh.get_input_context_single.return_value = {
            "df": MagicMock(), "positions": [],
        }

        meta = {"current_regime": "panic", "capital_ratio": 0.2}
        strat = MagicMock()
        strat.get_data_request.return_value = MagicMock()
        strat.get_signals.return_value = ([], True, False, meta)

        args = self._make_tick_args(self._make_strategy(), strat)
        runner.run_tick(args)
        dh.update_strategy_status_info.assert_called_once_with(1, meta)

    def test_returns_true_on_no_price(self):
        """取不到价格时返回 True（继续循环）。"""
        runner, _dh, _se = self._make_runner()
        runner.price_fetcher.fetch_current_price.return_value = None

        args = self._make_tick_args(self._make_strategy())
        result = runner.run_tick(args)
        assert result is True

    def test_returns_false_when_stop(self):
        """策略 keep_running=False 时返回 False。"""
        runner, dh, _se = self._make_runner()
        runner.price_fetcher.fetch_current_price.return_value = 100.0
        dh.get_last_rebalance_at.return_value = None
        dh.get_input_context_single.return_value = {
            "df": MagicMock(), "positions": [],
        }

        strat = MagicMock()
        strat.get_data_request.return_value = MagicMock()
        strat.get_signals.return_value = ([], False, False, None)

        args = self._make_tick_args(self._make_strategy(), strat)
        result = runner.run_tick(args)
        assert result is False

    def test_executes_signals_when_present(self):
        """有触发信号时应调用信号执行流程。"""
        runner, dh, se = self._make_runner()
        runner.price_fetcher.fetch_current_price.return_value = 100.0
        dh.get_last_rebalance_at.return_value = None
        dh.get_input_context_single.return_value = {
            "df": MagicMock(), "positions": [],
        }

        signals = [{"type": "open_long", "symbol": "BTC"}]
        strat = MagicMock()
        strat.get_data_request.return_value = MagicMock()
        strat.get_signals.return_value = (signals, True, False, None)

        args = self._make_tick_args(self._make_strategy(), strat)
        runner.run_tick(args)
        se.execute.assert_called()
