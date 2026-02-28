"""
截面策略指标执行：纯函数，执行指标代码并返回 scores、rankings。
不依赖 Executor，数据由调用方（DataHandler 构建 InputContext）提供。
"""

import traceback
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from app.utils.logger import get_logger

logger = get_logger(__name__)


def run_cross_sectional_indicator(
    indicator_code: str,
    data: Dict[str, pd.DataFrame],
    trading_config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    执行截面策略指标代码，返回所有标的的评分和排序。
    data: {symbol: df}，由 DataHandler.get_input_context_cross 提供。
    """
    if not data:
        logger.error("No data available for cross-sectional indicator")
        return None
    try:
        all_data = data
        exec_env = {
            "symbols": list(all_data.keys()),
            "data": all_data,
            "scores": {},
            "rankings": [],
            "np": np,
            "pd": pd,
            "trading_config": trading_config,
            "config": trading_config,
        }
        import builtins
        safe_builtins = {
            k: getattr(builtins, k)
            for k in dir(builtins)
            if not k.startswith("_")
            and k
            not in [
                "eval",
                "exec",
                "compile",
                "open",
                "input",
                "help",
                "exit",
                "quit",
                "__import__",
            ]
        }
        exec_env["__builtins__"] = safe_builtins
        exec(indicator_code, exec_env)

        scores = exec_env.get("scores", {})
        rankings: List[str] = exec_env.get("rankings", [])

        if not rankings and scores:
            rankings = sorted(scores.keys(), key=lambda x: scores.get(x, 0), reverse=True)

        return {"scores": scores, "rankings": rankings}
    except Exception as e:
        logger.error("Failed to execute cross-sectional indicator: %s", e)
        logger.error(traceback.format_exc())
        return None
