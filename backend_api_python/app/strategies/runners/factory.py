"""
Strategy Runner 工厂
"""
from app.strategies.runners.base_runner import BaseStrategyRunner
from app.strategies.runners.single_symbol_runner import SingleSymbolRunner
from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner
from app.strategies.runners.regime_runner import RegimeRunner
from app.strategies.runners.single_regime_weighted_runner import SingleRegimeWeightedRunner


def create_runner(
    cs_type: str,
    data_handler,
    signal_executor
) -> BaseStrategyRunner:
    """根据策略类型创建对应的 Runner。

    支持的类型：single, single_regime_weighted, cross_sectional,
    cross_sectional_weighted。
    """
    if cs_type == "cross_sectional_weighted":
        return RegimeRunner(data_handler, signal_executor)
    if cs_type == "cross_sectional":
        return CrossSectionalRunner(data_handler, signal_executor)
    if cs_type == "single_regime_weighted":
        return SingleRegimeWeightedRunner(data_handler, signal_executor)
    return SingleSymbolRunner(data_handler, signal_executor)
