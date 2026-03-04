"""
Regime 策略运行管道

与截面策略的区别：
1. tick 间隔与单标策略一致（默认 10 秒），而非截面策略的 5 分钟
2. 每个 tick 都计算指标并更新 status_info
3. 仅在 rebalance 周期到时才执行下单调仓
"""
import os
from typing import Any, Dict

from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner
from app.strategies.base import IStrategyLoop
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RegimeRunner(CrossSectionalRunner):
    """Regime 策略的运行流水线，继承截面策略 Runner。"""

    def _get_tick_interval(self, strategy: Dict[str, Any]) -> int:
        """与单标策略一致，默认 10 秒。"""
        try:
            interval = int(os.getenv("STRATEGY_TICK_INTERVAL_SEC", "10"))
        except (ValueError, TypeError):
            interval = 10
        return max(interval, 1)

    def _run_single_tick(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        strat_instance: IStrategyLoop,
        current_time: float,
    ) -> bool:
        """每 tick 计算指标 + 更新 status_info，仅在 rebalance 周期到时下单。"""
        self._last_current_time = current_time
        ctx = self._build_context(
            strategy_id, strategy, strat_instance, current_time
        )
        if ctx is None:
            return True

        last_rebalance = self.data_handler.get_last_rebalance_at(strategy_id)
        rebalance_now = strat_instance.should_rebalance(strategy, last_rebalance)
        ctx["should_rebalance"] = rebalance_now

        signals, keep_running, update_rebalance, metadata = strat_instance.get_signals(ctx)
        if not keep_running:
            return False

        self._dispatch_signals(
            strategy_id, strategy, signals, update_rebalance, metadata
        )
        return True
