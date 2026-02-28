"""
策略工厂：根据 cs_strategy_type 创建 IStrategyLoop 实例。
支持从 DB 加载配置并创建可运行策略。
"""

from typing import Optional, Tuple

from app.strategies.base import IStrategyLoop
from app.strategies.single_symbol import SingleSymbolStrategy
from app.strategies.cross_sectional import CrossSectionalStrategy
from app.strategies.strategy_config_loader import load_strategy


def create_strategy(cs_type: str) -> IStrategyLoop:
    """
    根据策略类型创建策略实例

    Args:
        cs_type: 'single' | 'cross_sectional'

    Returns:
        IStrategyLoop 实例
    """
    if cs_type == "cross_sectional":
        return CrossSectionalStrategy()
    return SingleSymbolStrategy()


def load_and_create(
    strategy_id: int,
) -> Tuple[Optional[IStrategyLoop], Optional[dict]]:
    """
    从 DB 加载策略配置并创建策略实例。

    Returns:
        (strategy, config) 成功时；失败时 (None, None)
    """
    config = load_strategy(strategy_id)
    if not config:
        return None, None
    cs_type = (config.get("trading_config") or {}).get("cs_strategy_type", "single")
    strat = create_strategy(cs_type)
    return strat, config
