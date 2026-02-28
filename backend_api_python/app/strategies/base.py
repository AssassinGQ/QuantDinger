"""
策略基类与类型定义

- InputContext: 输入上下文（df/data, positions, initial_* 等）
- RawIndicatorOutput: 指标原始输出（pending_signals 或 scores/rankings）
- Signal: 交易信号
- IStrategyLoop: 策略接口

## 数据流（已解耦）

- DataHandler：集中 K 线、持仓等数据拉取与 InputContext 构造
- Executor：get_data_request → DataHandler.get_input_context → strategy.get_signals(ctx) → 执行信号
- 策略：仅消费 InputContext，纯计算，不依赖 Executor
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypedDict

import pandas as pd


# ── 类型定义 ────────────────────────────────────────────────────────────────

class DataRequest(TypedDict, total=False):
    """策略返回的数据请求，供 Executor 传给 DataHandler 拉取数据"""
    symbol: str
    symbol_list: List[str]
    timeframe: str
    trading_config: Dict[str, Any]
    need_macro: bool
    rebalance_frequency: str
    refresh_klines: bool
    df_override: Optional[pd.DataFrame]
    history_limit: int
    market_category: str


class InputContext(TypedDict, total=False):
    """单标或截面策略的输入上下文，由 DataHandler 构建、Executor 传入 get_signals"""
    df: pd.DataFrame
    data: Dict[str, pd.DataFrame]
    positions: List[Dict[str, Any]]
    symbol: str
    initial_highest_price: float
    initial_position: int
    initial_avg_entry_price: float
    initial_position_count: int
    initial_last_add_price: float
    trading_config: Dict[str, Any]
    current_time: float
    current_price: Optional[float]
    strategy_id: int
    indicator_code: str
    market_category: str


class RawIndicatorOutput(TypedDict, total=False):
    """指标原始输出"""
    pending_signals: List[Dict[str, Any]]
    last_kline_time: int
    new_highest_price: float
    scores: Dict[str, float]
    rankings: List[str]


class Signal(TypedDict, total=False):
    """交易信号"""
    symbol: str
    type: str
    score: float
    position_size: Optional[float]
    trigger_price: Optional[float]
    timestamp: Optional[int]


# ── 公共逻辑（单标/截面复用） ────────────────────────────────────────────────


def sleep_until_next_tick(
    current_time: float, last_tick_time: float, tick_interval_sec: int
) -> tuple[bool, float]:
    """
    统一 tick 节奏：若未到下一 tick 则 sleep 并返回应 continue。
    Returns (should_continue, new_last_tick_time).
    """
    if last_tick_time <= 0:
        return False, current_time
    sleep_sec = (last_tick_time + tick_interval_sec) - current_time
    if sleep_sec > 0:
        time.sleep(min(sleep_sec, 1.0))
        return True, last_tick_time
    return False, current_time


# ── 策略接口 ────────────────────────────────────────────────────────────────


class IStrategyLoop(ABC):
    """
    策略接口：仅负责生成信号，不依赖 Executor。

    - need_macro_info(): 是否需要在 prepare 时拉取 macro
    - get_data_request(): 返回本 tick 所需数据的请求，供 Executor 传给 DataHandler
    - get_signals(): 接收 InputContext，返回信号。策略只消费 context，纯计算。
    """

    @abstractmethod
    def need_macro_info(self) -> bool:
        """是否需要在 prepare 时拉取宏观数据"""
        pass

    @abstractmethod
    def get_data_request(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        current_time: float,
    ) -> DataRequest:
        """
        返回本 tick 的数据请求，Executor 传给 DataHandler 拉取数据。

        策略可基于内部状态（如 last_kline_update_time）决定 refresh_klines 等。
        """
        pass

    @abstractmethod
    def get_signals(
        self,
        ctx: "InputContext",
    ) -> tuple[List[Dict[str, Any]], bool, Optional[bool], Optional[Dict[str, Any]]]:
        """
        基于 InputContext 生成本 tick 的信号。纯函数，不依赖 executor。

        Returns:
            (signals, should_continue, update_rebalance, meta)
            - signals: 本 tick 触发的交易信号列表
            - should_continue: False 表示初始化失败，Executor 应退出循环
            - update_rebalance: 截面策略专用；单标返回 None
            - meta: 可选，如 position_updates 供 Executor 持久化持仓
        """
        pass
