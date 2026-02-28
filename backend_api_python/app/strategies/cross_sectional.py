"""
截面策略：仅负责生成信号，不依赖 Executor。

- get_data_request(): 返回本 tick 的数据请求，供 Executor 传给 DataHandler
- get_signals(ctx): 基于 InputContext 生成调仓信号，纯计算
"""

from typing import Any, Dict, List, Optional, Tuple

from app.strategies.base import DataRequest, IStrategyLoop, InputContext
from app.strategies.cross_sectional_indicator import run_cross_sectional_indicator
from app.strategies.cross_sectional_signals import generate_cross_sectional_signals
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CrossSectionalStrategy(IStrategyLoop):
    """
    截面策略：只生成信号。
    Executor 通过 DataHandler 构建 InputContext，调用 get_signals(ctx) 获取信号。
    """

    def need_macro_info(self) -> bool:
        return False

    def get_data_request(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        current_time: float,
    ) -> DataRequest:
        """返回本 tick 的数据请求"""
        trading_config = strategy.get("trading_config") or {}
        symbol_list = trading_config.get("symbol_list", [])
        timeframe = trading_config.get("timeframe", "1H")
        need_macro = bool(trading_config.get("include_macro", False))
        rebalance_frequency = trading_config.get("rebalance_frequency", "daily")
        market_category = strategy.get("_market_category", "Crypto")

        return {
            "symbol_list": symbol_list,
            "timeframe": timeframe,
            "trading_config": trading_config,
            "need_macro": need_macro,
            "rebalance_frequency": rebalance_frequency,
            "history_limit": 200,
            "market_category": market_category,
        }

    def get_signals(
        self,
        ctx: InputContext,
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[bool], Optional[Dict[str, Any]]]:
        """基于 InputContext 生成调仓信号"""
        strategy_id = ctx.get("strategy_id", 0)
        indicator_code = ctx.get("indicator_code", "")
        trading_config = ctx.get("trading_config") or {}
        symbol_list = trading_config.get("symbol_list", [])

        if not symbol_list:
            logger.error(
                "Strategy %s has no symbol_list for cross-sectional strategy",
                strategy_id,
            )
            return [], False, False, None

        data = ctx.get("data", {})
        if not data:
            logger.warning("Strategy %s failed to prepare cross-sectional input", strategy_id)
            return [], True, False, None

        raw_output = run_cross_sectional_indicator(
            indicator_code,
            data,
            trading_config,
        )
        if not raw_output:
            logger.warning("Cross-sectional indicator returned no result")
            return [], True, False, None

        signals = generate_cross_sectional_signals(
            raw_output.get("rankings", []),
            raw_output.get("scores", {}),
            trading_config,
            ctx.get("positions", []),
        )

        if not signals:
            logger.info("No rebalancing needed for strategy %s", strategy_id)
            return [], True, True, None

        logger.info("Generated %d signals for cross-sectional strategy %s", len(signals), strategy_id)
        return signals, True, True, None
