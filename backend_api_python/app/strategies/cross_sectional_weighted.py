"""
带权重的截面策略 (Regime Cross Sectional Strategy)
支持宏观数据注入，针对不同 symbol 可以配置不同的指标。

指标计算在每个 tick 都执行（与单标策略保持一致），
Rebalance（下单调仓）按配置的周期执行。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.strategies.base import DataRequest, IStrategyLoop, InputContext
from app.strategies.cross_sectional_weighted_indicator import run_cross_sectional_weighted_indicator
from app.strategies.cross_sectional_weighted_signals import generate_cross_sectional_weighted_signals
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CrossSectionalWeightedStrategy(IStrategyLoop):
    """
    带权重的截面策略：
    - 需要宏观数据 (need_macro_info() -> True)
    - 针对每个 symbol 使用各自配置的指标 (symbol_indicators)
    - 每 tick 计算指标并更新 status_info
    - 仅在 rebalance 周期到时执行下单调仓
    """

    def need_macro_info(self) -> bool:
        return True

    def should_rebalance(
        self,
        strategy: Dict[str, Any],
        last_rebalance_time: Optional[datetime],
    ) -> bool:
        """判断是否到了调仓周期，与指标计算解耦。"""
        if last_rebalance_time is None:
            return True
        trading_config = strategy.get("trading_config") or {}
        rebalance_frequency = trading_config.get("rebalance_frequency", "daily")
        delta = datetime.now() - last_rebalance_time
        if rebalance_frequency == "daily":
            return delta.days >= 1
        if rebalance_frequency == "weekly":
            return delta.days >= 7
        if rebalance_frequency == "monthly":
            return delta.days >= 30
        return True

    def get_data_request(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        current_time: float,
    ) -> DataRequest:
        trading_config = strategy.get("trading_config") or {}
        symbol_indicators = trading_config.get("symbol_indicators", {})
        symbol_list = trading_config.get("symbol_list") or []
        if not symbol_list:
            symbol = trading_config.get("symbol", "")
            if symbol:
                symbol_list = [symbol]
            else:
                symbol_list = list(symbol_indicators.keys())

        timeframe = trading_config.get("timeframe", "1H")
        rebalance_frequency = trading_config.get("rebalance_frequency", "daily")
        market_category = strategy.get("_market_category", "Crypto")

        return {
            "symbol_list": symbol_list,
            "timeframe": timeframe,
            "trading_config": trading_config,
            "need_macro": self.need_macro_info(),
            "rebalance_frequency": rebalance_frequency,
            "history_limit": 200,
            "market_category": market_category,
        }

    def get_signals(
        self,
        ctx: InputContext,
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[bool], Optional[Dict[str, Any]]]:
        strategy_id = ctx.get("strategy_id", 0)
        trading_config = ctx.get("trading_config") or {}
        symbol_indicator_codes = ctx.get("symbol_indicator_codes", {})

        data = ctx.get("data", {})
        if not data:
            logger.warning("Strategy %s failed to prepare cross-sectional weighted input", strategy_id)
            return [], True, False, None

        raw_output = run_cross_sectional_weighted_indicator(
            symbol_indicator_codes,
            data,
            trading_config,
        )
        if not raw_output:
            logger.warning("Cross-sectional weighted indicator returned no result")
            return [], True, False, None

        metadata = raw_output.get("metadata")
        weights = raw_output.get("weights", {})
        ind_signals = raw_output.get("signals", {})
        should_trade = ctx.get("should_rebalance", False)

        if not should_trade:
            logger.info(
                "Regime strategy %s: indicators done (weights=%s, signals=%s), not rebalance time",
                strategy_id, weights, ind_signals,
            )
            return [], True, False, metadata

        logger.info(
            "Regime strategy %s: rebalance — weights=%s, signals=%s",
            strategy_id, weights, ind_signals,
        )

        signals = generate_cross_sectional_weighted_signals(
            weights,
            ind_signals,
            ctx.get("positions", []),
        )

        if not signals:
            logger.info("Regime strategy %s: no rebalancing needed (all neutral or no change)", strategy_id)
            return [], True, True, metadata

        logger.info(
            "Regime strategy %s: generated %d trade signals: %s",
            strategy_id, len(signals),
            [(s.get("symbol"), s.get("type"), s.get("target_weight")) for s in signals],
        )
        return signals, True, True, metadata
