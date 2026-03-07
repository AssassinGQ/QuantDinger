import pytest
from app.services.live_trading.usmart_trading.fsm import (
    OrderState,
    OrderEvent,
    OrderStateMachine,
    ORDER_STATE_MACHINE,
    VALID_TRANSITIONS,
    TERMINAL_STATES,
)


class TestOrderState:
    def test_order_state_values(self):
        assert OrderState.PENDING.value == "pending"
        assert OrderState.SUBMITTED.value == "submitted"
        assert OrderState.ACCEPTED.value == "accepted"
        assert OrderState.PARTIAL_FILLED.value == "partial"
        assert OrderState.FILLED.value == "filled"
        assert OrderState.CANCELLED.value == "cancelled"
        assert OrderState.REJECTED.value == "rejected"
        assert OrderState.EXPIRED.value == "expired"


class TestOrderEvent:
    def test_order_event_values(self):
        assert OrderEvent.SUBMIT.value == "submit"
        assert OrderEvent.ACCEPT.value == "accept"
        assert OrderEvent.FILL.value == "fill"
        assert OrderEvent.CANCEL.value == "cancel"
        assert OrderEvent.REJECT.value == "reject"
        assert OrderEvent.EXPIRE.value == "expire"
        assert OrderEvent.FULL_FILL.value == "full_fill"


class TestOrderStateMachine:
    def test_initial_state(self):
        fsm = OrderStateMachine("order_123")
        assert fsm.state == OrderState.PENDING
        assert fsm.is_terminal is False

    def test_terminal_states(self):
        assert OrderState.FILLED in TERMINAL_STATES
        assert OrderState.CANCELLED in TERMINAL_STATES
        assert OrderState.REJECTED in TERMINAL_STATES
        assert OrderState.EXPIRED in TERMINAL_STATES
        assert OrderState.PENDING not in TERMINAL_STATES


class TestValidTransitions:
    def test_pending_transitions(self):
        events = VALID_TRANSITIONS[OrderState.PENDING]
        assert OrderEvent.SUBMIT in events
        assert OrderEvent.REJECT in events
        assert OrderEvent.EXPIRE in events

    def test_submitted_transitions(self):
        events = VALID_TRANSITIONS[OrderState.SUBMITTED]
        assert OrderEvent.ACCEPT in events
        assert OrderEvent.REJECT in events
        assert OrderEvent.CANCEL in events
        assert OrderEvent.EXPIRE in events

    def test_accepted_transitions(self):
        events = VALID_TRANSITIONS[OrderState.ACCEPTED]
        assert OrderEvent.FILL in events
        assert OrderEvent.CANCEL in events
        assert OrderEvent.REJECT in events
        assert OrderEvent.EXPIRE in events

    def test_partial_filled_transitions(self):
        events = VALID_TRANSITIONS[OrderState.PARTIAL_FILLED]
        assert OrderEvent.FILL in events
        assert OrderEvent.FULL_FILL in events
        assert OrderEvent.CANCEL in events
        assert OrderEvent.REJECT in events

    def test_terminal_no_transitions(self):
        assert len(VALID_TRANSITIONS[OrderState.FILLED]) == 0
        assert len(VALID_TRANSITIONS[OrderState.CANCELLED]) == 0
        assert len(VALID_TRANSITIONS[OrderState.REJECTED]) == 0
        assert len(VALID_TRANSITIONS[OrderState.EXPIRED]) == 0


class TestStateTransitions:
    def test_normal_flow_pending_to_submitted(self):
        fsm = OrderStateMachine("order_1")
        result = fsm.transition(OrderEvent.SUBMIT)
        assert result is True
        assert fsm.state == OrderState.SUBMITTED

    def test_normal_flow_submitted_to_accepted(self):
        fsm = OrderStateMachine("order_2")
        fsm.transition(OrderEvent.SUBMIT)
        result = fsm.transition(OrderEvent.ACCEPT)
        assert result is True
        assert fsm.state == OrderState.ACCEPTED

    def test_normal_flow_accepted_to_partial_filled(self):
        fsm = OrderStateMachine("order_3")
        fsm.transition(OrderEvent.SUBMIT)
        fsm.transition(OrderEvent.ACCEPT)
        result = fsm.transition(OrderEvent.FILL)
        assert result is True
        assert fsm.state == OrderState.PARTIAL_FILLED

    def test_normal_flow_to_filled(self):
        fsm = OrderStateMachine("order_4")
        fsm.transition(OrderEvent.SUBMIT)
        fsm.transition(OrderEvent.ACCEPT)
        fsm.transition(OrderEvent.FILL)
        result = fsm.transition(OrderEvent.FULL_FILL)
        assert result is True
        assert fsm.state == OrderState.FILLED
        assert fsm.is_terminal is True

    def test_cancel_flow(self):
        fsm = OrderStateMachine("order_5")
        fsm.transition(OrderEvent.SUBMIT)
        result = fsm.transition(OrderEvent.CANCEL)
        assert result is True
        assert fsm.state == OrderState.CANCELLED
        assert fsm.is_terminal is True

    def test_reject_flow(self):
        fsm = OrderStateMachine("order_6")
        result = fsm.transition(OrderEvent.REJECT)
        assert result is True
        assert fsm.state == OrderState.REJECTED
        assert fsm.is_terminal is True

    def test_expire_flow(self):
        fsm = OrderStateMachine("order_7")
        result = fsm.transition(OrderEvent.EXPIRE)
        assert result is True
        assert fsm.state == OrderState.EXPIRED
        assert fsm.is_terminal is True


class TestInvalidTransitions:
    def test_invalid_transition_pending_to_filled(self):
        fsm = OrderStateMachine("order_8")
        result = fsm.transition(OrderEvent.FILL)
        assert result is False
        assert fsm.state == OrderState.PENDING

    def test_invalid_transition_pending_to_cancel(self):
        fsm = OrderStateMachine("order_9")
        result = fsm.transition(OrderEvent.CANCEL)
        assert result is False
        assert fsm.state == OrderState.PENDING

    def test_invalid_transition_after_filled(self):
        fsm = OrderStateMachine("order_10")
        fsm.transition(OrderEvent.SUBMIT)
        fsm.transition(OrderEvent.ACCEPT)
        fsm.transition(OrderEvent.FILL)
        fsm.transition(OrderEvent.FULL_FILL)
        assert fsm.is_terminal is True
        result = fsm.transition(OrderEvent.CANCEL)
        assert result is False

    def test_cannot_transition_from_terminal(self):
        fsm = OrderStateMachine("order_11")
        fsm.transition(OrderEvent.REJECT)
        assert fsm.is_terminal is True
        result = fsm.transition(OrderEvent.SUBMIT)
        assert result is False


class TestHistoryTracking:
    def test_history_records_transitions(self):
        fsm = OrderStateMachine("order_12")
        fsm.transition(OrderEvent.SUBMIT)
        fsm.transition(OrderEvent.ACCEPT)
        
        history = fsm._history
        assert len(history) == 2
        assert history[0]["from"] == "pending"
        assert history[0]["to"] == "submitted"
        assert history[0]["event"] == "submit"
        assert history[1]["from"] == "submitted"
        assert history[1]["to"] == "accepted"
        assert history[1]["event"] == "accept"

    def test_get_status(self):
        fsm = OrderStateMachine("order_13")
        fsm.transition(OrderEvent.SUBMIT)
        
        status = fsm.get_status()
        assert status["order_id"] == "order_13"
        assert status["state"] == "submitted"
        assert status["is_terminal"] is False
        assert len(status["history"]) == 1
        assert "created_at" in status
        assert "updated_at" in status


class TestCanTransition:
    def test_can_transition_returns_true_for_valid(self):
        fsm = OrderStateMachine("order_14")
        assert fsm.can_transition(OrderEvent.SUBMIT) is True

    def test_can_transition_returns_false_for_invalid(self):
        fsm = OrderStateMachine("order_15")
        assert fsm.can_transition(OrderEvent.FILL) is False
        assert fsm.can_transition(OrderEvent.CANCEL) is False


class TestPartialFilledTransitions:
    def test_partial_to_partial(self):
        fsm = OrderStateMachine("order_16")
        fsm.transition(OrderEvent.SUBMIT)
        fsm.transition(OrderEvent.ACCEPT)
        fsm.transition(OrderEvent.FILL)
        
        result = fsm.transition(OrderEvent.FILL)
        assert result is True
        assert fsm.state == OrderState.PARTIAL_FILLED

    def test_partial_to_filled(self):
        fsm = OrderStateMachine("order_17")
        fsm.transition(OrderEvent.SUBMIT)
        fsm.transition(OrderEvent.ACCEPT)
        fsm.transition(OrderEvent.FILL)
        
        result = fsm.transition(OrderEvent.FULL_FILL)
        assert result is True
        assert fsm.state == OrderState.FILLED

    def test_partial_to_cancelled(self):
        fsm = OrderStateMachine("order_18")
        fsm.transition(OrderEvent.SUBMIT)
        fsm.transition(OrderEvent.ACCEPT)
        fsm.transition(OrderEvent.FILL)
        
        result = fsm.transition(OrderEvent.CANCEL)
        assert result is True
        assert fsm.state == OrderState.CANCELLED
