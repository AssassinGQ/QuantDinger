from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple

from app.services.live_trading.base import ExecutionResult, OrderContext


class OrderRunner(ABC):
    @abstractmethod
    def execute(self, *, client, order_context: OrderContext) -> ExecutionResult:
        ...

    def sync_positions(
        self, *, client, exchange_config: Dict[str, Any], market_type: str = "swap"
    ) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]:
        return {}, {}
