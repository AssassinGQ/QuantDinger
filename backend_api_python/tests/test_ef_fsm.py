"""
Tests for Order state machine in ef_trading.
"""

from app.services.live_trading.ef_trading.fsm import (
    OrderState,
    OrderEvent,
    OrderStateMachine,
    TERMINAL_STATES,
)


class TestOrderState:
    """Test cases for OrderState enum."""

    def test_order_state_values(self):
        """Test OrderState enum values."""
        assert OrderState.PENDING.value == "pending"
        assert OrderState.SUBMITTED.value == "submitted"
        assert OrderState.ACCEPTED.value == "accepted"
        assert OrderState.PARTIAL_FILLED.value == "partial"
        assert OrderState.FILLED.value == "filled"
        assert OrderState.CANCELLED.value == "cancelled"
        assert OrderState.REJECTED.value == "rejected"
        assert OrderState.EXPIRED.value == "expired"


class TestOrderEvent:
    """Test cases for OrderEvent enum."""

    def test_order_event_values(self):
        """Test OrderEvent enum values."""
        assert OrderEvent.SUBMIT.value == "submit"
        assert OrderEvent.ACCEPT.value == "accept"
        assert OrderEvent.FILL.value == "fill"
        assert OrderEvent.CANCEL.value == "cancel"
        assert OrderEvent.REJECT.value == "reject"
        assert OrderEvent.EXPIRE.value == "expire"
        assert OrderEvent.FULL_FILL.value == "full_fill"


class TestOrderStateMachine:
    """Test cases for OrderStateMachine."""

    def test_init(self):
        """Test state machine initialization."""
        fsm = OrderStateMachine("order_123")
        assert fsm.order_id == "order_123"
        assert fsm.state == OrderState.PENDING
        assert fsm.is_terminal is False

    def test_pending_to_submitted(self):
        """Test transition from PENDING to SUBMITTED."""
        fsm = OrderStateMachine("order_123")
        result = fsm.transition(OrderEvent.SUBMIT)
        assert result is True
        assert fsm.state == OrderState.SUBMITTED

    def test_pending_to_rejected(self):
        """Test transition from PENDING to REJECTED."""
        fsm = OrderStateMachine("order_123")
        result = fsm.transition(OrderEvent.REJECT)
        assert result is True
        assert fsm.state == OrderState.REJECTED
        assert fsm.is_terminal is True

    def test_submitted_to_accepted(self):
        """Test transition from SUBMITTED to ACCEPTED."""
        fsm = OrderStateMachine("order_123")
        fsm.transition(OrderEvent.SUBMIT)
        result = fsm.transition(OrderEvent.ACCEPT)
        assert result is True
        assert fsm.state == OrderState.ACCEPTED

    def test_submitted_to_cancelled(self):
        """Test transition from SUBMITTED to CANCELLED."""
        fsm = OrderStateMachine("order_123")
        fsm.transition(OrderEvent.SUBMIT)
        result = fsm.transition(OrderEvent.CANCEL)
        assert result is True
        assert fsm.state == OrderState.CANCELLED

    def test_accepted_to_partial_filled(self):
        """Test transition from ACCEPTED to PARTIAL_FILLED."""
        fsm = OrderStateMachine("order_123")
        fsm.transition(OrderEvent.SUBMIT)
        fsm.transition(OrderEvent.ACCEPT)
        result = fsm.transition(OrderEvent.FILL)
        assert result is True
        assert fsm.state == OrderState.PARTIAL_FILLED

    def test_partial_filled_to_filled(self):
        """Test transition from PARTIAL_FILLED to FILLED."""
        fsm = OrderStateMachine("order_123")
        fsm.transition(OrderEvent.SUBMIT)
        fsm.transition(OrderEvent.ACCEPT)
        fsm.transition(OrderEvent.FILL)
        result = fsm.transition(OrderEvent.FULL_FILL)
        assert result is True
        assert fsm.state == OrderState.FILLED
        assert fsm.is_terminal is True

    def test_invalid_transition(self):
        """Test invalid transition."""
        fsm = OrderStateMachine("order_123")
        result = fsm.transition(OrderEvent.CANCEL)
        assert result is False
        assert fsm.state == OrderState.PENDING

    def test_can_transition(self):
        """Test can_transition method."""
        fsm = OrderStateMachine("order_123")
        assert fsm.can_transition(OrderEvent.SUBMIT) is True
        assert fsm.can_transition(OrderEvent.CANCEL) is False

    def test_history_tracking(self):
        """Test state transition history."""
        fsm = OrderStateMachine("order_123")
        fsm.transition(OrderEvent.SUBMIT)
        fsm.transition(OrderEvent.ACCEPT)

        assert len(fsm.history) == 2
        assert fsm.history[0]["from"] == "pending"
        assert fsm.history[0]["to"] == "submitted"
        assert fsm.history[1]["from"] == "submitted"
        assert fsm.history[1]["to"] == "accepted"

    def test_get_status(self):
        """Test get_status method."""
        fsm = OrderStateMachine("order_123")
        status = fsm.get_status()

        assert status["order_id"] == "order_123"
        assert status["state"] == "pending"
        assert status["is_terminal"] is False
        assert "created_at" in status
        assert "updated_at" in status
        assert status["history"] == []

    def test_terminal_states(self):
        """Test terminal states."""
        assert OrderState.FILLED in TERMINAL_STATES
        assert OrderState.CANCELLED in TERMINAL_STATES
        assert OrderState.REJECTED in TERMINAL_STATES
        assert OrderState.EXPIRED in TERMINAL_STATES
        assert OrderState.PENDING not in TERMINAL_STATES

    def test_filled_state_is_terminal(self):
        """Test FILLED is terminal state."""
        fsm = OrderStateMachine("order_123")
        fsm.transition(OrderEvent.SUBMIT)
        fsm.transition(OrderEvent.ACCEPT)
        fsm.transition(OrderEvent.FILL)
        fsm.transition(OrderEvent.FULL_FILL)

        assert fsm.is_terminal is True
        assert fsm.can_transition(OrderEvent.CANCEL) is False
