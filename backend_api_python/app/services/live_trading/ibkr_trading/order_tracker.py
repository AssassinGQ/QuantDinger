"""
OrderTracker: explicit FSM for IBKR order lifecycle.

Handles the non-obvious Cancelled → PreSubmitted → Filled recovery path
that can occur in IB Gateway (especially Paper Trading and around market
open/close boundaries).

Cancelled is NOT a terminal state — IBKR can recover from it.
Only HARD_TERMINAL states are truly irreversible.
The overall timeout in _wait_for_order is what ultimately ends tracking.
"""

import time
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.services.live_trading.base import LiveOrderResult
from app.utils.logger import get_logger

logger = get_logger(__name__)

HARD_TERMINAL = frozenset({
    "Filled", "Inactive", "ApiError", "ApiCancelled", "ValidationError",
})

ACTIVE = frozenset({
    "PendingSubmit", "PreSubmitted", "Submitted", "PendingCancel",
    "Cancelled",
})


@dataclass
class OrderTracker:
    order_id: int
    engine_id: str = "ibkr"
    created_at: float = field(default_factory=time.monotonic)

    # FSM state
    status_history: List[Tuple[str, float, float, float]] = field(default_factory=list)
    current_status: str = "PendingSubmit"
    filled: float = 0.0
    avg_price: float = 0.0
    remaining: float = 0.0

    # Commission accumulator
    commission: float = 0.0
    commission_ccy: str = ""

    # Error info
    error_messages: List[str] = field(default_factory=list)

    # Completion signal
    done_event: threading.Event = field(default_factory=threading.Event)

    def add_error_message(self, error_msg: str) -> None:
        """Add an error message from IBKR error event."""
        if error_msg and error_msg not in self.error_messages:
            self.error_messages.append(error_msg)
            logger.info(
                "[OrderTracker] order=%s added error: %s",
                self.order_id, error_msg,
            )

    def on_status(
        self,
        status: str,
        filled: float,
        avg_price: float,
        remaining: float,
        error_msgs: Optional[List[str]] = None,
    ) -> None:
        """Process an incoming orderStatus event according to the FSM transition table."""
        if self.current_status in HARD_TERMINAL:
            logger.debug(
                "[OrderTracker] order=%s ignoring status=%s (already in HARD_TERMINAL %s)",
                self.order_id, status, self.current_status,
            )
            return

        self.status_history.append((status, filled, avg_price, time.monotonic()))
        self.filled = filled
        self.avg_price = avg_price
        self.remaining = remaining
        if error_msgs:
            self.error_messages.extend(error_msgs)

        prev = self.current_status
        self.current_status = status

        logger.info(
            "[OrderTracker] order=%s transition %s→%s filled=%.2f avg=%.4f remaining=%.2f",
            self.order_id, prev, status, filled, avg_price, remaining,
        )

        if status in HARD_TERMINAL:
            self.done_event.set()
            return

        if status == "Cancelled" and filled > 0:
            self.done_event.set()
            return

        if prev == "Cancelled" and status in ACTIVE:
            logger.info(
                "[OrderTracker] order=%s RECOVERED from Cancelled → %s",
                self.order_id, status,
            )

    def on_exec_details(self, filled: float, avg_price: float, exec_id: str = "") -> None:
        """Update fill data from execDetailsEvent. Does NOT drive state transitions."""
        if filled > self.filled:
            self.filled = filled
        if avg_price > 0:
            self.avg_price = avg_price
        logger.info(
            "[OrderTracker] order=%s execDetails: execId=%s filled=%.2f avg=%.4f",
            self.order_id, exec_id, filled, avg_price,
        )

    def add_commission(self, commission: float, currency: str = "") -> None:
        """Accumulate commission from commissionReportEvent."""
        self.commission += commission
        if currency:
            self.commission_ccy = currency

    def is_done(self) -> bool:
        return self.done_event.is_set()

    def to_result(self) -> LiveOrderResult:
        """Convert current tracker state to a LiveOrderResult."""
        status = self.current_status
        filled = self.filled
        avg_price = self.avg_price

        if status == "Filled":
            success = True
            message = "Order filled"
        elif status in HARD_TERMINAL:
            success = False
            error_str = "; ".join(self.error_messages) if self.error_messages else "rejected by IBKR"
            message = f"Order {status}: {error_str}"
        elif status == "Cancelled":
            if filled > 0:
                success = True
                message = f"Order Cancelled (filled={filled})"
            else:
                success = False
                error_str = "; ".join(self.error_messages) if self.error_messages else "rejected by IBKR"
                message = f"Order Cancelled: {error_str}"
        elif filled > 0:
            success = True
            message = f"Order {status} (timeout, filled={filled})"
        else:
            success = False
            message = f"Order timed out in '{status}' with 0 fills"

        return LiveOrderResult(
            success=success,
            order_id=self.order_id,
            filled=filled,
            avg_price=avg_price,
            status=status,
            exchange_id=self.engine_id,
            message=message,
            raw={
                "orderId": self.order_id,
                "status": status,
                "filled": filled,
                "remaining": self.remaining,
            },
            fee=self.commission,
            fee_ccy=self.commission_ccy,
        )
