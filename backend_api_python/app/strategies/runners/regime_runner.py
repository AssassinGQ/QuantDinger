"""
Regime 策略运行管道

与截面策略的区别：
1. tick 间隔与单标策略一致（默认 10 秒），而非截面策略的 5 分钟
2. 每个 tick 都计算指标并更新 status_info
3. 仅在 rebalance 周期到时才执行下单调仓
"""
import os
from typing import Any, Dict, Optional

from app.data_sources.base import TIMEFRAME_SECONDS
from app.services.server_side_risk import (
    check_stop_loss_signal,
    check_take_profit_or_trailing_signal,
)
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

        if rebalance_now:
            logger.info(
                "Strategy %s rebalance triggered (last_rebalance=%s)",
                strategy_id, last_rebalance,
            )

        signals, keep_running, update_rebalance, metadata = strat_instance.get_signals(ctx)
        if not keep_running:
            return False

        if signals:
            logger.debug(
                "Strategy %s generated %d signals: %s",
                strategy_id, len(signals),
                [(s.get("symbol"), s.get("type"), s.get("target_weight")) for s in signals],
            )

        self._dispatch_signals(
            strategy_id, strategy, signals, update_rebalance, metadata
        )

        self._check_risk_signals(strategy_id, strategy)
        return True

    def _get_current_price(
        self, strategy_id: int, symbol: str, strategy: Dict[str, Any]
    ) -> Optional[float]:
        market_type = strategy.get("_market_type", "swap")
        market_category = strategy.get("_market_category", "Crypto")
        price = self.price_fetcher.fetch_current_price(
            exchange=None,
            symbol=symbol,
            market_type=market_type,
            market_category=market_category,
        )
        if price is None:
            logger.debug(
                "Strategy %s: no price for %s:%s, skip risk check",
                strategy_id, market_category, symbol,
            )
        return price

    def _check_risk_signals(self, strategy_id: int, strategy: Dict[str, Any]):
        trading_config = strategy.get("trading_config") or {}

        # For regime strategies, symbol_indicators keys are style names (aggressive/balanced/etc),
        # NOT actual symbols. Use the strategy's main symbol for risk checks instead.
        main_symbol = trading_config.get("symbol") or strategy.get("symbol") or ""
        if not main_symbol:
            return
        symbols_to_check = [main_symbol]

        leverage = float(strategy.get("_leverage", 1.0))
        market_type = strategy.get("_market_type", "swap")
        tf_str = trading_config.get("timeframe", "1H")
        timeframe_seconds = TIMEFRAME_SECONDS.get(tf_str, 3600)

        for symbol in symbols_to_check:
            current_price = self._get_current_price(strategy_id, symbol, strategy)
            if not current_price:
                continue

            risk_signals = []
            sl = check_stop_loss_signal(
                self.data_handler, strategy_id, symbol,
                current_price, market_type, leverage,
                trading_config, timeframe_seconds,
            )
            if sl:
                risk_signals.append(sl)
            tp = check_take_profit_or_trailing_signal(
                self.data_handler, strategy_id, symbol,
                current_price, market_type, leverage,
                trading_config, timeframe_seconds,
            )
            if tp:
                risk_signals.append(tp)

            for sig in risk_signals:
                positions = self.data_handler.get_current_positions(
                    strategy_id, symbol
                )
                logger.info(
                    "Strategy %s risk signal for %s: %s",
                    strategy_id, symbol, sig.get("reason"),
                )
                self.signal_executor.execute(
                    strategy_ctx=strategy,
                    signal=sig,
                    symbol=symbol,
                    current_price=current_price,
                    current_positions=positions,
                )
