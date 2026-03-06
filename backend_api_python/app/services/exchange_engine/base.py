"""
Abstract base class for all exchange/broker engine adapters.

Every trading engine (IBKR, MT5, future engines) must implement this
interface.  The `pending_order_worker` calls only these methods and trusts
the returned `OrderResult` without back-filling or guessing values.

OrderResult contract
--------------------
- success=True  ⇒ order accepted by the engine; `filled` and `avg_price`
  MUST reflect actual execution data.  0.0 is valid when nothing has
  filled yet (e.g. order queued for next session).
- success=False ⇒ order rejected / failed / timed-out with 0 fills.
  `filled` and `avg_price` should be 0.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple


@dataclass
class OrderResult:
    """Unified order execution result returned by all exchange engines.

    Fields cover the union of IBKR and MT5 needs:
    - avg_price: execution price (IBKR avgFillPrice, MT5 result.price)
    - deal_id: MT5-specific deal identifier, 0 for engines without it
    """

    success: bool
    order_id: int = 0
    deal_id: int = 0
    filled: float = 0.0
    avg_price: float = 0.0
    status: str = ""
    message: str = ""
    exchange_id: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionRecord:
    """Normalized position snapshot returned by get_positions_normalized()."""

    symbol: str
    side: str  # "long" or "short"
    quantity: float  # always positive
    entry_price: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)


class ExchangeEngine(ABC):
    """Abstract adapter that every trading engine must implement."""

    engine_id: str = ""
    supported_market_categories: FrozenSet[str] = frozenset()

    def validate_market_category(self, market_category: str) -> Tuple[bool, str]:
        """Check if this engine supports the given market category.

        Returns (ok, error_message).
        """
        if not self.supported_market_categories:
            return True, ""
        if market_category in self.supported_market_categories:
            return True, ""
        return False, (
            f"{self.engine_id} only supports "
            f"{', '.join(sorted(self.supported_market_categories))}, "
            f"got {market_category}"
        )

    # ── connection ──────────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection. Return True on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Gracefully disconnect."""

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether the engine is currently connected."""

    # ── order execution ─────────────────────────────────────────────

    @abstractmethod
    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        market_type: str = "",
        **kwargs,
    ) -> OrderResult:
        """Place a market order.

        Args:
            symbol: Instrument symbol (raw, e.g. "00005", "GOOGL", "EURUSD").
            side: "buy" or "sell".
            quantity: Positive number of units.
            market_type: Engine-specific hint (e.g. "USStock", "HShare", "Forex").
        """

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        market_type: str = "",
        **kwargs,
    ) -> OrderResult:
        """Place a limit order.  Optional — not all engines need this."""
        return OrderResult(
            success=False,
            message=f"{self.engine_id} does not support limit orders",
        )

    def cancel_order(self, order_id: int) -> bool:
        """Cancel an open order.  Optional."""
        return False

    # ── signal mapping ──────────────────────────────────────────────

    @abstractmethod
    def map_signal_to_side(self, signal_type: str) -> str:
        """Convert a strategy signal to an engine-native side string.

        Args:
            signal_type: e.g. "open_long", "close_long", "open_short", ...

        Returns:
            "buy" or "sell".

        Raises:
            ValueError if the engine does not support the signal.
        """

    # ── query (optional) ────────────────────────────────────────────

    def get_positions(self) -> List[Dict[str, Any]]:
        return []

    def get_positions_normalized(self) -> List[PositionRecord]:
        """Return positions in a standardized format.

        Each engine overrides this to convert its native format into
        ``PositionRecord`` so the worker can consume positions without
        knowing engine-specific field names.
        """
        return []

    def get_open_orders(self) -> List[Dict[str, Any]]:
        return []

    def get_account_summary(self) -> Dict[str, Any]:
        return {"success": False, "error": "not implemented"}

    def get_connection_status(self) -> Dict[str, Any]:
        return {"connected": self.connected, "engine_id": self.engine_id}

    # ── lifecycle ───────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Release resources.  Default calls disconnect."""
        self.disconnect()
