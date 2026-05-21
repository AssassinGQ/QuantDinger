"""
截面策略指标执行：纯函数，执行指标代码并返回 scores、weights、rankings。
不依赖 Executor，数据由调用方提供。

BT-01 / Phase 22：scores 与 weights 为硬契约；框架不做 score→weight 推导或等权兜底。
"""

import traceback
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from app.utils.logger import get_logger

logger = get_logger(__name__)

CONTRACT_ERR = "CROSS_SECTIONAL_CONTRACT:"


def _tradable_symbols(data: Dict[str, pd.DataFrame], symbols: List[str]) -> List[str]:
    """参与契约校验的标的：在 data 中有非空历史。"""
    out: List[str] = []
    for sym in symbols:
        df = data.get(sym)
        if df is None or getattr(df, "empty", True):
            continue
        out.append(sym)
    return out


def _validate_scores_weights_contract(
    data: Dict[str, pd.DataFrame],
    symbols: List[str],
    scores: Any,
    weights: Any,
) -> None:
    if not isinstance(scores, dict):
        raise ValueError(f"{CONTRACT_ERR} scores must be a dict")
    if not isinstance(weights, dict):
        raise ValueError(f"{CONTRACT_ERR} weights must be a dict")
    tradable = _tradable_symbols(data, symbols)
    if not tradable:
        raise ValueError(f"{CONTRACT_ERR} no tradable symbols with OHLCV rows")
    for sym in tradable:
        if sym not in scores:
            raise ValueError(f"{CONTRACT_ERR} missing score for tradable symbol {sym!r}")
        if sym not in weights:
            raise ValueError(f"{CONTRACT_ERR} missing weight for tradable symbol {sym!r}")
        sv, wv = scores[sym], weights[sym]
        if not isinstance(sv, (int, float)) or not np.isfinite(float(sv)):
            raise ValueError(f"{CONTRACT_ERR} invalid score for {sym!r}")
        if not isinstance(wv, (int, float)) or not np.isfinite(float(wv)):
            raise ValueError(f"{CONTRACT_ERR} invalid weight for {sym!r}")


def run_cross_sectional_indicator(
    indicator_code: str,
    data: Dict[str, pd.DataFrame],
    trading_config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    执行截面策略指标代码，返回 scores、weights、rankings。
    data: {symbol: df}，由调用方提供；契约对「可交易」子集（有非空 df 的 symbol）校验 scores+weights。
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
            "weights": {},
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

        scores = exec_env.get("scores", None)
        weights = exec_env.get("weights", None)
        rankings: List[str] = list(exec_env.get("rankings", []) or [])

        _validate_scores_weights_contract(all_data, exec_env["symbols"], scores, weights)

        if not rankings and isinstance(scores, dict):
            rankings = sorted(scores.keys(), key=lambda x: float(scores.get(x, 0.0)), reverse=True)

        return {"scores": scores, "weights": weights, "rankings": rankings}
    except ValueError as exc:
        if str(exc).startswith(CONTRACT_ERR):
            logger.warning("Cross-sectional indicator contract failed: %s", exc)
            raise
        logger.error("Failed to execute cross-sectional indicator: %s", exc)
        logger.error(traceback.format_exc())
        return None
    except Exception as e:
        logger.error("Failed to execute cross-sectional indicator: %s", e)
        logger.error(traceback.format_exc())
        return None
