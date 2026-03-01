"""
单标的策略运行管道
"""
import os
import time
import traceback
from typing import Any, Dict

from app.strategies.runners.base_runner import BaseStrategyRunner
from app.strategies.base import IStrategyLoop
from app.services.signal_processor import process_signals
from app.utils.logger import get_logger
from app.utils.console import console_print

logger = get_logger(__name__)


class SingleSymbolRunner(BaseStrategyRunner):
    """单标的策略的运行流水线"""

    def run(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        strat_instance: IStrategyLoop,
        exchange: Any,
    ) -> None:
        try:
            tick_interval_sec = int(os.getenv("STRATEGY_TICK_INTERVAL_SEC", "10"))
        except (ValueError, TypeError):
            tick_interval_sec = 10
        tick_interval_sec = max(tick_interval_sec, 1)

        last_tick_time = 0.0

        while True:
            try:
                if not self.is_running(strategy_id):
                    logger.info("Strategy %s stopped", strategy_id)
                    break
                should_continue, current_time, last_tick_time = self._wait_for_next_tick(
                    last_tick_time, tick_interval_sec
                )
                if should_continue:
                    continue

                keep_running = self._run_single_tick(
                    strategy_id, strategy, strat_instance, exchange, current_time
                )
                if not keep_running:
                    break

            except Exception as e:
                logger.error("Strategy %s loop error: %s", strategy_id, e)
                logger.error(traceback.format_exc())
                console_print(f"[strategy:{strategy_id}] loop error: {e}")
                time.sleep(5)

        logger.info("Strategy %s loop exited", strategy_id)

    def _run_single_tick(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        strat_instance: IStrategyLoop,
        exchange: Any,
        current_time: float,
    ) -> bool:
        """运行单次 tick 逻辑。返回 False 表示策略要求停止。"""
        trading_config = strategy.get("trading_config") or {}
        symbol = trading_config.get("symbol", "")
        market_type = strategy.get("_market_type", "swap")
        market_category = strategy.get("_market_category", "Crypto")

        current_price = self.price_fetcher.fetch_current_price(
            exchange, symbol, market_type=market_type, market_category=market_category
        )
        if current_price is None:
            logger.warning(
                "Strategy %s failed to fetch current price for %s:%s",
                strategy_id, market_category, symbol,
            )
            return True

        request = strat_instance.get_data_request(strategy_id, strategy, current_time)
        ctx = self.data_handler.get_input_context_single(
            strategy_id, request, current_price=float(current_price)
        )
        if ctx is None:
            logger.warning("Strategy %s failed to get input context", strategy_id)
            return True

        ctx["strategy_id"] = strategy_id
        ctx["indicator_code"] = strategy.get("_indicator_code", "")
        ctx["current_time"] = current_time
        ctx["current_price"] = float(current_price)

        triggered_signals, keep_running, _, meta = strat_instance.get_signals(ctx)
        if not keep_running:
            logger.warning("Strategy %s get_signals returned stop", strategy_id)
            return False

        if meta and meta.get("position_updates"):
            for pu in meta["position_updates"]:
                self.data_handler.update_position(
                    strategy_id=strategy_id,
                    symbol=pu["symbol"],
                    side=pu["side"],
                    size=pu["size"],
                    entry_price=pu["entry_price"],
                    current_price=pu["current_close"],
                    highest_price=pu["highest_price"],
                )

        if triggered_signals:
            self._process_and_execute_signals(
                strategy=strategy,
                triggered_signals=triggered_signals,
                current_price=float(current_price),
                exchange=exchange,
            )

        self.data_handler.update_positions_current_price(strategy_id, symbol, current_price)

        # 获取策略内部 pending_signals 数量以供控制台输出（若存在）
        pending_count = len(getattr(strat_instance, "_state", {}).get("pending_signals", []))
        price_str = f"{float(current_price or 0.0):.8f}"
        console_print(
            f"[strategy:{strategy_id}] tick price={price_str} pending_signals={pending_count}"
        )
        return True

    def _process_and_execute_signals(
        self,
        strategy: Dict[str, Any],
        triggered_signals: list,
        current_price: float,
        exchange: Any = None,
    ) -> None:
        """
        单标的特有的流水线：信号计算、过滤、执行。
        """
        if not triggered_signals:
            return

        strategy_id = strategy.get("id")
        trading_config = strategy.get("trading_config") or {}
        symbol = trading_config.get("symbol", "")

        selected, current_positions = process_signals(
            strategy_ctx=strategy,
            symbol=symbol,
            triggered_signals=triggered_signals,
            current_price=current_price,
        )
        if not selected:
            return

        sig_type = selected.get("type")
        trigger_price = selected.get("trigger_price", current_price)
        execute_price = trigger_price if trigger_price > 0 else current_price

        ok = self.signal_executor.execute(
            strategy_ctx=strategy,
            signal=selected,
            symbol=symbol,
            current_price=execute_price,
            current_positions=current_positions,
            exchange=exchange,
        )
        if not ok:
            logger.warning(
                "Strategy %s signal rejected/failed: %s",
                strategy_id, sig_type,
            )
            return

        strategy_name = strategy.get("_strategy_name", "")
        logger.info(
            "Strategy %s signal executed: %s @ %s",
            strategy_id, sig_type, execute_price,
        )
        try:
            from app.services.portfolio_monitor import notify_strategy_signal_for_positions
            notify_strategy_signal_for_positions(
                market=strategy.get("_market_type") or "Crypto",
                symbol=symbol,
                signal_type=sig_type,
                signal_detail=f"策略: {strategy_name}\n信号: {sig_type}\n价格: {execute_price:.4f}",
            )
        except Exception as link_e:
            logger.warning(
                "Strategy signal linkage notification failed: %s",
                link_e,
            )
