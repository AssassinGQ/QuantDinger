from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

from app.services.live_trading.base import ExecutionResult, OrderContext


class PreCheckResult:
    """Result of a pre-execution check.

    ok=True  → proceed to execute()
    ok=False → skip execute(); *reason* explains why; *suppress_dedup_clear*
               tells the worker NOT to clear the dedup cache (e.g. RTH reject
               should not allow the same signal to re-enter).
    """
    __slots__ = ("ok", "reason", "suppress_dedup_clear")

    def __init__(self, ok: bool = True, reason: str = "", suppress_dedup_clear: bool = False):
        self.ok = ok
        self.reason = reason
        self.suppress_dedup_clear = suppress_dedup_clear


class OrderRunner(ABC):
    @abstractmethod
    def execute(self, *, client, order_context: OrderContext) -> ExecutionResult:
        ...

    def pre_check(self, *, client, order_context: OrderContext) -> PreCheckResult:
        """Pre-execution gate.  Default: always pass."""
        return PreCheckResult(ok=True)

    def sync_positions(
        self, *, client, exchange_config: Dict[str, Any], market_type: str = "swap"
    ) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]:
        return {}, {}
