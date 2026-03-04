"""
带权重的截面策略 (Regime Cross Sectional Strategy)
支持宏观数据注入，针对不同 symbol 可以配置不同的指标。
"""
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
    - 生成带权重的开仓信号
    """

    def need_macro_info(self) -> bool:
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

        signals = generate_cross_sectional_weighted_signals(
            raw_output.get("weights", {}),
            raw_output.get("signals", {}),
            ctx.get("positions", []),
        )

        metadata = raw_output.get("metadata")

        if not signals:
            logger.info("No rebalancing needed for weighted strategy %s", strategy_id)
            return [], True, True, metadata

        logger.info("Generated %d signals for cross-sectional weighted strategy %s", len(signals), strategy_id)
        return signals, True, True, metadata
