"""Order state machine for EastMoney trading."""

from enum import Enum
from typing import Dict, Set, List
from dataclasses import dataclass, field
from datetime import datetime


class OrderState(Enum):
    """Order states."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIAL_FILLED = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderEvent(Enum):
    """Order events."""
    SUBMIT = "submit"
    ACCEPT = "accept"
    FILL = "fill"
    CANCEL = "cancel"
    REJECT = "reject"
    EXPIRE = "expire"
    FULL_FILL = "full_fill"


ORDER_STATE_MACHINE: Dict[OrderState, Dict[OrderEvent, OrderState]] = {
    OrderState.PENDING: {
        OrderEvent.SUBMIT: OrderState.SUBMITTED,
        OrderEvent.REJECT: OrderState.REJECTED,
        OrderEvent.EXPIRE: OrderState.EXPIRED,
    },
    OrderState.SUBMITTED: {
        OrderEvent.ACCEPT: OrderState.ACCEPTED,
        OrderEvent.REJECT: OrderState.REJECTED,
        OrderEvent.CANCEL: OrderState.CANCELLED,
        OrderEvent.EXPIRE: OrderState.EXPIRED,
    },
    OrderState.ACCEPTED: {
        OrderEvent.FILL: OrderState.PARTIAL_FILLED,
        OrderEvent.CANCEL: OrderState.CANCELLED,
        OrderEvent.REJECT: OrderState.REJECTED,
        OrderEvent.EXPIRE: OrderState.EXPIRED,
    },
    OrderState.PARTIAL_FILLED: {
        OrderEvent.FILL: OrderState.PARTIAL_FILLED,
        OrderEvent.FULL_FILL: OrderState.FILLED,
        OrderEvent.CANCEL: OrderState.CANCELLED,
        OrderEvent.REJECT: OrderState.REJECTED,
        OrderEvent.EXPIRE: OrderState.EXPIRED,
    },
    OrderState.FILLED: {},
    OrderState.CANCELLED: {},
    OrderState.REJECTED: {},
    OrderState.EXPIRED: {},
}


VALID_TRANSITIONS: Dict[OrderState, Set[OrderEvent]] = {
    state: set(events.keys())
    for state, events in ORDER_STATE_MACHINE.items()
}


TERMINAL_STATES = {
    OrderState.FILLED,
    OrderState.CANCELLED,
    OrderState.REJECTED,
    OrderState.EXPIRED,
}


@dataclass
class OrderStateMachine:
    """Order state machine for tracking order lifecycle."""

    order_id: str
    _state: OrderState = field(default=OrderState.PENDING)
    _history: List[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def state(self) -> OrderState:
        """Get current state."""
        return self._state

    @property
    def is_terminal(self) -> bool:
        """Check if state is terminal."""
        return self._state in TERMINAL_STATES

    def can_transition(self, event: OrderEvent) -> bool:
        """Check if transition is valid."""
        return event in VALID_TRANSITIONS.get(self._state, set())

    def transition(self, event: OrderEvent) -> bool:
        """Apply transition event."""
        if not self.can_transition(event):
            return False

        new_state = ORDER_STATE_MACHINE[self._state].get(event)
        if new_state is None:
            return False

        self._history.append({
            "from": self._state.value,
            "to": new_state.value,
            "event": event.value,
            "timestamp": datetime.now().isoformat()
        })

        self._state = new_state
        self.updated_at = datetime.now()
        return True

    def get_status(self) -> dict:
        """Get current status."""
        return {
            "order_id": self.order_id,
            "state": self._state.value,
            "is_terminal": self.is_terminal,
            "history": self._history,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
