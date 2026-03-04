"""
截面策略运行管道
"""
import time
import traceback
from typing import Any, Dict

from app.strategies.runners.base_runner import BaseStrategyRunner
from app.strategies.base import IStrategyLoop
from app.utils.logger import get_logger
from app.utils.console import console_print

logger = get_logger(__name__)


class CrossSectionalRunner(BaseStrategyRunner):
    """截面策略的运行流水线"""

    def run(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        strat_instance: IStrategyLoop,
        exchange: Any,
    ) -> None:
        trading_config = strategy.get("trading_config") or {}
        tick_interval_sec = int(trading_config.get("decide_interval", 300))
        if tick_interval_sec < 1:
            tick_interval_sec = 300
        last_tick_time = 0.0

        while True:
            try:
                if not self.is_running(strategy_id):
                    logger.info("Cross-sectional strategy %s stopped", strategy_id)
                    break
                should_continue, current_time, last_tick_time = self._wait_for_next_tick(
                    last_tick_time, tick_interval_sec
                )
                if should_continue:
                    continue

                keep_running = self._run_single_tick(
                    strategy_id, strategy, strat_instance, current_time
                )
                if not keep_running:
                    break

            except Exception as e:
                logger.error("Cross-sectional strategy %s loop error: %s", strategy_id, e)
                logger.error(traceback.format_exc())
                console_print(f"[strategy:{strategy_id}] loop error: {e}")
                time.sleep(5)

        logger.info("Cross-sectional strategy %s loop exited", strategy_id)

    def _build_context(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        strat_instance: IStrategyLoop,
        current_time: float,
    ):
        """构建上下文，返回 None 表示跳过本次 tick。"""
        last_rebalance = self.data_handler.get_last_rebalance_at(strategy_id)
        if not strat_instance.should_execute(strategy_id, strategy, last_rebalance):
            return None

        request = strat_instance.get_data_request(strategy_id, strategy, current_time)
        ctx = self.data_handler.get_input_context_cross(strategy_id, request)
        if ctx is None:
            logger.warning(
                "Strategy %s failed to get cross input context", strategy_id
            )
            return None

        ctx["strategy_id"] = strategy_id
        ctx["indicator_code"] = strategy.get("_indicator_code", "")
        ctx["symbol_indicator_codes"] = strategy.get("_symbol_indicator_codes", {})
        ctx["current_time"] = current_time
        return ctx

    def _dispatch_signals(
        self, strategy_id, strategy, signals, update_rebalance, metadata
    ):
        """执行信号、更新 rebalance 时间戳和 status_info。"""
        if signals:
            positions = self.data_handler.get_all_positions(strategy_id)
            self.signal_executor.execute_batch(
                strategy_ctx=strategy,
                signals=signals,
                all_positions=positions,
                current_time=int(self._last_current_time),
            )
        if update_rebalance:
            self.data_handler.update_last_rebalance(strategy_id)
        if metadata:
            self.data_handler.update_strategy_status_info(strategy_id, metadata)

    def _run_single_tick(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        strat_instance: IStrategyLoop,
        current_time: float,
    ) -> bool:
        """截面策略的 tick 逻辑：受 rebalance 周期控制。"""
        self._last_current_time = current_time
        ctx = self._build_context(
            strategy_id, strategy, strat_instance, current_time
        )
        if ctx is None:
            return True

        signals, keep_running, update_rebalance, metadata = strat_instance.get_signals(ctx)
        if not keep_running:
            return False

        self._dispatch_signals(
            strategy_id, strategy, signals, update_rebalance, metadata
        )
        return True
