"""
策略抽象与实现

- IStrategyLoop: 策略循环接口
- SingleSymbolStrategy: 单标策略
- CrossSectionalStrategy: 截面策略
"""

from app.strategies.base import (
    IStrategyLoop,
    InputContext,
    RawIndicatorOutput,
    Signal,
    sleep_until_next_tick,
)
from app.strategies.factory import create_strategy

__all__ = [
    "IStrategyLoop",
    "InputContext",
    "RawIndicatorOutput",
    "Signal",
    "create_strategy",
]
