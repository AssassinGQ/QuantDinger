"""
定义策略运行管道基类
"""
from abc import ABC, abstractmethod
from typing import Any, Dict

from app.strategies.base import IStrategyLoop
from app.services.data_handler import DataHandler
from app.services.price_fetcher import get_price_fetcher
from app.services.signal_executor import SignalExecutor


class BaseStrategyRunner(ABC):
    """
    策略运行管道基类 (Strategy Runner)
    负责解耦 TradingExecutor，为其提供一致的运行接口。
    主要职责：按自身周期找 DataHandler 取数据 -> 喂给 Strategy -> 取出信号给 SignalExecutor。
    """

    def __init__(
        self,
        data_handler: DataHandler,
        signal_executor: SignalExecutor,
    ):
        self.data_handler = data_handler
        self.signal_executor = signal_executor
        self.price_fetcher = get_price_fetcher()

    def is_running(self, strategy_id: int) -> bool:
        """检查策略是否在运行"""
        status = self.data_handler.get_strategy_status(strategy_id)
        return status == "running"

    def _wait_for_next_tick(self, last_tick_time: float, tick_interval_sec: int) -> tuple[bool, float, float]:
        """等待下一个 tick，返回 (should_continue, current_time, new_last_tick_time)"""
        import time
        from app.strategies.base import sleep_until_next_tick
        current_time = time.time()
        should_continue, new_last_tick_time = sleep_until_next_tick(
            current_time, last_tick_time, tick_interval_sec
        )
        return should_continue, current_time, new_last_tick_time

    @abstractmethod
    def run(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        strat_instance: IStrategyLoop,
        exchange: Any,
    ) -> None:
        """
        开始策略循环。当 self.is_running(strategy_id) 为 False 时应退出循环。
        """
