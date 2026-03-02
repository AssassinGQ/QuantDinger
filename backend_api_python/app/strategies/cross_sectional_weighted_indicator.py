"""
执行 Regime 截面策略的指标代码
"""
from typing import Any, Dict

import pandas as pd

from app.strategies.base import RawIndicatorOutput
from app.utils.logger import get_logger

logger = get_logger(__name__)


def run_cross_sectional_weighted_indicator(
    symbol_indicator_codes: Dict[str, str],
    data: Dict[str, pd.DataFrame],
    trading_config: Dict[str, Any],
) -> RawIndicatorOutput:
    """
    针对不同 symbol 执行各自的指标代码，并汇总计算 weights 和 signals。
    对于 Regime 策略，每个指标返回的是：
    - weights: float
    - signals: "long", "short", "flat" 或 1, -1, 0
    然后我们将它们收集起来，组装成给到外层的 rankings, scores 等格式，或者直接构建新的格式。

    Args:
        symbol_indicator_codes: symbol 到 指标代码 的映射
        data: symbol 到 K线 df 的映射
        trading_config: 策略配置

    Returns:
        包含 weights 和 signals 字典的 RawIndicatorOutput
    """
    weights = {}
    signals = {}

    # 将 trading_config 作为参数传给每个执行的脚本环境
    global_env = {"trading_config": trading_config}

    for symbol, df in data.items():
        if df is None or len(df) == 0:
            continue

        indicator_code = symbol_indicator_codes.get(symbol)
        if not indicator_code:
            logger.warning("No indicator code found for symbol %s in cross_sectional_weighted", symbol)
            continue

        local_env = {"df": df.copy()}
        try:
            # 兼容 exec: 提供 df 作为局部变量
            # 指标需在 df 末尾或通过某种方式返回其 weight 和 signal
            # 约定：指标应在 local_env 中设置 `weight` 和 `signal` 变量
            exec(indicator_code, global_env, local_env) # pylint: disable=exec-used

            # 从局部变量中提取结果
            weight = local_env.get("weight", 0.0)
            signal = local_env.get("signal", 0) # 0=flat, 1=long, -1=short 或 'long', 'short', 'flat'

            weights[symbol] = float(weight)

            if str(signal).lower() in ("1", "1.0", "long", "buy"):
                signals[symbol] = 1
            elif str(signal).lower() in ("-1", "-1.0", "short", "sell"):
                signals[symbol] = -1
            else:
                signals[symbol] = 0

        except Exception as e: # pylint: disable=broad-exception-caught
            logger.error("Error executing indicator for %s: %s", symbol, e)
            continue

    return {"weights": weights, "signals": signals}
