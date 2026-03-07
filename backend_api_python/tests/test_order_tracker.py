"""
Pure unit tests for OrderTracker FSM logic.

No mock IB or threading involved — just state transitions and result generation.
"""
import time

import pytest

from app.services.live_trading.ibkr_trading.order_tracker import (
    OrderTracker,
    HARD_TERMINAL,
    ACTIVE,
)


class TestStatusSets:
    def test_hard_terminal(self):
        assert HARD_TERMINAL == {"Filled", "Inactive", "ApiError", "ApiCancelled", "ValidationError"}

    def test_cancelled_is_active(self):
        assert "Cancelled" in ACTIVE

    def test_active_includes_all_non_terminal(self):
        assert ACTIVE == {"PendingSubmit", "PreSubmitted", "Submitted", "PendingCancel", "Cancelled"}

    def test_no_overlap(self):
        assert not (HARD_TERMINAL & ACTIVE)


class TestNormalFlows:
    def test_normal_fill(self):
        t = OrderTracker(order_id=1)
        t.on_status("Submitted", 0, 0, 10)
        assert not t.is_done()
        t.on_status("Filled", 10, 178.50, 0)
        assert t.is_done()
        r = t.to_result()
        assert r.success is True
        assert r.filled == 10.0
        assert r.avg_price == 178.50
        assert r.status == "Filled"

    def test_presubmitted_then_filled(self):
        t = OrderTracker(order_id=2)
        t.on_status("PreSubmitted", 0, 0, 10)
        assert not t.is_done()
        t.on_status("Submitted", 0, 0, 10)
        assert not t.is_done()
        t.on_status("Filled", 10, 179.0, 0)
        assert t.is_done()
        r = t.to_result()
        assert r.success is True
        assert r.status == "Filled"

    def test_partial_fill_then_complete(self):
        """Submitted → Submitted(partial) → Filled."""
        t = OrderTracker(order_id=3)
        t.on_status("Submitted", 0, 0, 10)
        t.on_status("Submitted", 3, 175.0, 7)
        assert not t.is_done()
        assert t.filled == 3.0
        t.on_status("Filled", 10, 176.5, 0)
        assert t.is_done()
        r = t.to_result()
        assert r.success is True
        assert r.filled == 10.0


class TestRejections:
    def test_immediate_inactive(self):
        t = OrderTracker(order_id=10)
        t.on_status("Inactive", 0, 0, 10, error_msgs=["Order rejected by exchange"])
        assert t.is_done()
        r = t.to_result()
        assert r.success is False
        assert r.status == "Inactive"
        assert "rejected" in r.message.lower()

    def test_api_error(self):
        t = OrderTracker(order_id=11)
        t.on_status("ApiError", 0, 0, 10, error_msgs=["Error 10243: Fractional-sized order"])
        assert t.is_done()
        r = t.to_result()
        assert r.success is False
        assert "10243" in r.message

    def test_api_cancelled(self):
        t = OrderTracker(order_id=12)
        t.on_status("ApiCancelled", 0, 0, 10)
        assert t.is_done()
        r = t.to_result()
        assert r.success is False
        assert r.status == "ApiCancelled"

    def test_validation_error(self):
        t = OrderTracker(order_id=13)
        t.on_status("ValidationError", 0, 0, 10, error_msgs=["Validation failed"])
        assert t.is_done()
        r = t.to_result()
        assert r.success is False
        assert r.status == "ValidationError"


class TestCancelledIsNotTerminal:
    def test_cancelled_zero_fill_is_not_done(self):
        """Cancelled with filled=0 is NOT done — it can still recover."""
        t = OrderTracker(order_id=20)
        t.on_status("Submitted", 0, 0, 10)
        t.on_status("Cancelled", 0, 0, 10, error_msgs=["Error 10349"])
        assert not t.is_done()

    def test_cancelled_with_fill_is_done(self):
        """Cancelled but filled > 0 is done (partial fill then cancel)."""
        t = OrderTracker(order_id=22)
        t.on_status("Submitted", 0, 0, 10)
        t.on_status("Cancelled", 3.0, 175.0, 7)
        assert t.is_done()
        r = t.to_result()
        assert r.success is True
        assert r.filled == 3.0

    def test_cancelled_zero_fill_result_is_failure(self):
        """When timeout expires while in Cancelled(filled=0), result is failure."""
        t = OrderTracker(order_id=23)
        t.on_status("Cancelled", 0, 0, 10, error_msgs=["Error 10349: TIF set to DAY"])
        r = t.to_result()
        assert r.success is False
        assert r.status == "Cancelled"
        assert "10349" in r.message


class TestCancelledRecovery:
    def test_cancelled_then_presubmitted_then_filled(self):
        """The GOOGL incident: Cancelled → PreSubmitted → Filled should succeed."""
        t = OrderTracker(order_id=30)
        t.on_status("Cancelled", 0, 0, 10, error_msgs=["Error 10349"])
        assert not t.is_done()

        t.on_status("PreSubmitted", 0, 0, 10)
        assert not t.is_done()

        t.on_status("Submitted", 0, 0, 10)
        assert not t.is_done()

        t.on_status("Filled", 1, 300.6, 0)
        assert t.is_done()
        r = t.to_result()
        assert r.success is True
        assert r.filled == 1.0
        assert r.avg_price == 300.6

    def test_cancelled_then_submitted_recovery(self):
        """Cancelled → Submitted (skip PreSubmitted) → Filled."""
        t = OrderTracker(order_id=31)
        t.on_status("Cancelled", 0, 0, 10)
        assert not t.is_done()

        t.on_status("Submitted", 0, 0, 10)
        assert not t.is_done()

        t.on_status("Filled", 10, 180.0, 0)
        assert t.is_done()
        r = t.to_result()
        assert r.success is True

    def test_cancelled_then_filled_directly(self):
        """Cancelled → Filled (rare but possible)."""
        t = OrderTracker(order_id=32)
        t.on_status("Cancelled", 0, 0, 10)
        assert not t.is_done()

        t.on_status("Filled", 10, 185.0, 0)
        assert t.is_done()
        r = t.to_result()
        assert r.success is True
        assert r.filled == 10.0


class TestExecDetails:
    def test_exec_details_updates_fill(self):
        t = OrderTracker(order_id=40)
        t.on_exec_details(filled=5.0, avg_price=200.0, exec_id="exec-001")
        assert t.filled == 5.0
        assert t.avg_price == 200.0

    def test_exec_details_does_not_set_done(self):
        t = OrderTracker(order_id=41)
        t.on_exec_details(filled=10.0, avg_price=200.0, exec_id="exec-001")
        assert not t.is_done()

    def test_exec_details_only_increases_fill(self):
        t = OrderTracker(order_id=42)
        t.on_exec_details(filled=5.0, avg_price=200.0, exec_id="exec-001")
        t.on_exec_details(filled=3.0, avg_price=195.0, exec_id="exec-002")
        assert t.filled == 5.0

    def test_multiple_exec_details_accumulate(self):
        t = OrderTracker(order_id=43)
        t.on_exec_details(filled=3.0, avg_price=175.0, exec_id="exec-001")
        t.on_exec_details(filled=7.0, avg_price=176.0, exec_id="exec-002")
        t.on_exec_details(filled=10.0, avg_price=176.5, exec_id="exec-003")
        assert t.filled == 10.0
        assert t.avg_price == 176.5


class TestCommission:
    def test_single_commission(self):
        t = OrderTracker(order_id=50)
        t.add_commission(commission=1.25, currency="USD")
        assert t.commission == pytest.approx(1.25)
        assert t.commission_ccy == "USD"

    def test_multiple_commissions_accumulate(self):
        t = OrderTracker(order_id=51)
        t.add_commission(0.40, "USD")
        t.add_commission(0.50, "USD")
        t.add_commission(0.35, "USD")
        assert t.commission == pytest.approx(1.25)

    def test_commission_in_result(self):
        t = OrderTracker(order_id=52)
        t.on_status("Filled", 10, 178.50, 0)
        t.add_commission(1.25, "USD")
        r = t.to_result()
        assert r.fee == pytest.approx(1.25)
        assert r.fee_ccy == "USD"


class TestStatusHistory:
    def test_history_recorded(self):
        t = OrderTracker(order_id=60)
        t.on_status("Submitted", 0, 0, 10)
        t.on_status("Filled", 10, 180.0, 0)
        assert len(t.status_history) == 2
        assert t.status_history[0][0] == "Submitted"
        assert t.status_history[1][0] == "Filled"

    def test_history_includes_cancelled_recovery(self):
        t = OrderTracker(order_id=61)
        t.on_status("Cancelled", 0, 0, 10)
        t.on_status("PreSubmitted", 0, 0, 10)
        t.on_status("Submitted", 0, 0, 10)
        t.on_status("Filled", 10, 300.0, 0)
        assert len(t.status_history) == 4
        statuses = [h[0] for h in t.status_history]
        assert statuses == ["Cancelled", "PreSubmitted", "Submitted", "Filled"]


class TestHardTerminalIgnoresSubsequent:
    def test_filled_ignores_subsequent_cancelled(self):
        t = OrderTracker(order_id=70)
        t.on_status("Filled", 10, 180.0, 0)
        t.on_status("Cancelled", 0, 0, 10)
        assert t.current_status == "Filled"
        r = t.to_result()
        assert r.success is True

    def test_inactive_ignores_subsequent_filled(self):
        t = OrderTracker(order_id=71)
        t.on_status("Inactive", 0, 0, 10)
        t.on_status("Filled", 10, 180.0, 0)
        assert t.current_status == "Inactive"
        r = t.to_result()
        assert r.success is False


class TestToResult:
    def test_timeout_with_fills(self):
        """If tracker times out but has fills, result should be success."""
        t = OrderTracker(order_id=80)
        t.on_status("Submitted", 5, 150.0, 5)
        r = t.to_result()
        assert r.success is True
        assert r.filled == 5.0
        assert "timeout" in r.message.lower()

    def test_timeout_no_fills(self):
        t = OrderTracker(order_id=81)
        t.on_status("Submitted", 0, 0, 10)
        r = t.to_result()
        assert r.success is False
        assert "timed out" in r.message.lower()

    def test_result_raw_fields(self):
        t = OrderTracker(order_id=82)
        t.on_status("Filled", 10, 180.0, 0)
        r = t.to_result()
        assert r.raw["orderId"] == 82
        assert r.raw["status"] == "Filled"
        assert r.raw["filled"] == 10.0
        assert r.raw["remaining"] == 0.0

    def test_result_exchange_id(self):
        t = OrderTracker(order_id=83, engine_id="ibkr")
        t.on_status("Filled", 10, 180.0, 0)
        r = t.to_result()
        assert r.exchange_id == "ibkr"

    def test_cancelled_no_fill_error_message(self):
        t = OrderTracker(order_id=84)
        t.on_status("Cancelled", 0, 0, 10, error_msgs=["Error 10349: TIF set to DAY"])
        r = t.to_result()
        assert r.success is False
        assert "10349" in r.message

    def test_cancelled_no_fill_no_error(self):
        t = OrderTracker(order_id=85)
        t.on_status("Cancelled", 0, 0, 10)
        r = t.to_result()
        assert r.success is False
        assert "rejected by IBKR" in r.message
