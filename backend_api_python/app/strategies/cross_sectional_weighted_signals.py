"""
根据 Regime 截面策略的 weights 和 signals 生成调仓信号
"""
import time
from typing import Any, Dict, List

from app.strategies.base import Signal
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _should_close_position(
    side: str,
    size: float,
    expected_signal: int,
    weight: float,
) -> bool:
    if size <= 0:
        return False
    if expected_signal == 0:
        return True
    if expected_signal == 1 and side != "long":
        return True
    if expected_signal == -1 and side != "short":
        return True
    if weight <= 0:
        return True
    return False

def generate_cross_sectional_weighted_signals(
    weights: Dict[str, float],
    signals: Dict[str, int],
    current_positions: List[Dict[str, Any]],
) -> List[Signal]:
    """
    根据每个标的的 weight 和 signal，以及当前的持仓，生成换仓信号。
    """
    out_signals: List[Signal] = []
    now_ts = int(time.time())

    pos_map = {}
    for pos in current_positions:
        sym = pos.get("symbol", "")
        if sym not in pos_map:
            pos_map[sym] = {}
        pos_map[sym][pos.get("side", "long")] = float(pos.get("size", 0.0))

    # 1. 检查是否有需要平仓的现有仓位
    for sym, sides in pos_map.items():
        expected_signal = signals.get(sym, 0)
        weight = weights.get(sym, 0.0)

        for side, size in sides.items():
            if _should_close_position(side, size, expected_signal, weight):
                out_signals.append({
                    "symbol": sym,
                    "type": f"close_{side}",
                    "position_size": 1.0,
                    "timestamp": now_ts,
                })

    # 2. 生成开仓/调仓信号
    for sym, weight in weights.items():
        if weight <= 0:
            continue

        expected_signal = signals.get(sym, 0)
        if expected_signal == 0:
            continue

        target_side = "long" if expected_signal == 1 else "short"

        out_signals.append({
            "symbol": sym,
            "type": f"open_{target_side}",
            "position_size": weight,
            "target_weight": weight,
            "timestamp": now_ts,
        })

    return out_signals
