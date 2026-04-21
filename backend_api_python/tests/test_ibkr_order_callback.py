"""
Tests for IBKR fire-and-forget order callback flow.

Verifies that event callbacks (_on_order_status) correctly dispatch
_handle_fill / _handle_reject to the IO executor via TaskQueue, and that
the DB update logic in those handlers is correct.
"""
import threading
from unittest.mock import MagicMock, patch, call

import pytest

from app.services.live_trading.ibkr_trading.client import (
    IBKRClient,
    IBKRConfig,
    IBKROrderContext,
)


def _make_client():
    """Create a minimal IBKRClient for callback testing."""
    client = IBKRClient.__new__(IBKRClient)
    client.config = IBKRConfig()
    client.mode = "paper"
    client._ib = MagicMock()
    client._account = "DU999"
    client._order_contexts = {}
    client._commission_contexts = {}
    client._events_registered = False
    client._event_map = []
    client._reconnect_thread = None
    client._reconnect_stop = threading.Event()
    client._conid_to_symbol = {}
    client._subscribed_conids = set()
    client._qualify_cache = {}
    client._acct_summary_req_id = None
    client._acct_summary_cache = {}
    client._tq = MagicMock()
    client._ib_executor = MagicMock()
    client._io_executor = MagicMock()
    client._tq.submit.return_value = MagicMock()
    client._fire_submit = lambda fn, is_blocking=False: fn()

    import asyncio

    def _sync_ib(fn, timeout=60.0):
        if asyncio.iscoroutine(fn):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(fn)
            finally:
                loop.close()
        return fn()
    client._submit = _sync_ib

    async def _noop_ensure(*_a, **_kw):
        pass
    client._ensure_connected_async = _noop_ensure

    return client


def _make_ctx(order_id=100, **overrides):
    defaults = dict(
        order_id=order_id,
        pending_order_id=50,
        strategy_id=7,
        symbol="AAPL",
        signal_type="open_long",
        amount=10.0,
        market_type="USStock",
    )
    defaults.update(overrides)
    return IBKROrderContext(**defaults)


def _make_trade(
    order_id,
    status,
    filled=0.0,
    avg_price=0.0,
    log_messages=None,
    remaining=0.0,
    total_qty=None,
):
    trade = MagicMock()
    trade.order.orderId = order_id
    trade.order.totalQuantity = 0.0 if total_qty is None else float(total_qty)
    trade.orderStatus.status = status
    trade.orderStatus.filled = filled
    trade.orderStatus.avgFillPrice = avg_price
    trade.orderStatus.remaining = remaining
    if log_messages:
        trade.log = [MagicMock(message=m) for m in log_messages]
    else:
        trade.log = []
    return trade


# ===========================================================================
# Dispatch routing
# ===========================================================================

class TestCallbackDispatchRouting:
    """Verify _on_order_status routes to the correct handler."""

    def test_filled_dispatches_handle_fill(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=1)
        client._order_contexts[1] = ctx

        client._on_order_status(_make_trade(1, "Filled", 10.0, 155.0))

        assert 1 not in client._order_contexts  # popped for fill idempotency
        assert 1 in client._commission_contexts  # lingers for commissionReport
        assert len(fire_calls) == 1
        assert callable(fire_calls[0])

    def test_cancelled_with_fill_dispatches_handle_fill(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=2)
        client._order_contexts[2] = ctx

        client._on_order_status(_make_trade(2, "Cancelled", 5.0, 300.0))

        assert 2 not in client._order_contexts  # popped for fill idempotency
        assert 2 in client._commission_contexts  # lingers for commissionReport
        assert len(fire_calls) == 1

    def test_inactive_dispatches_handle_reject(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=3)
        client._order_contexts[3] = ctx

        client._on_order_status(_make_trade(3, "Inactive", 0, 0, ["Order rejected"]))

        assert 3 not in client._order_contexts
        assert len(fire_calls) == 1

    def test_api_error_dispatches_handle_reject(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=4)
        client._order_contexts[4] = ctx

        client._on_order_status(_make_trade(4, "ApiError", 0, 0, ["Error 10243"]))

        assert 4 not in client._order_contexts
        assert len(fire_calls) == 1

    def test_api_cancelled_dispatches_handle_reject(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=5)
        client._order_contexts[5] = ctx

        client._on_order_status(_make_trade(5, "ApiCancelled", 0, 0))

        assert 5 not in client._order_contexts
        assert len(fire_calls) == 1

    def test_validation_error_dispatches_handle_reject(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=6)
        client._order_contexts[6] = ctx

        client._on_order_status(_make_trade(6, "ValidationError", 0, 0))

        assert 6 not in client._order_contexts
        assert len(fire_calls) == 1

    def test_submitted_does_not_dispatch(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=7)
        client._order_contexts[7] = ctx

        client._on_order_status(_make_trade(7, "Submitted", 0, 0))

        assert 7 in client._order_contexts
        assert len(fire_calls) == 0

    def test_presubmitted_does_not_dispatch(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=8)
        client._order_contexts[8] = ctx

        client._on_order_status(_make_trade(8, "PreSubmitted", 0, 0))

        assert 8 in client._order_contexts
        assert len(fire_calls) == 0

    def test_cancelled_zero_fills_dispatches_reject(self):
        """Cancelled(filled=0) is treated as a rejection (e.g. lot-size error)."""
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=9)
        client._order_contexts[9] = ctx

        client._on_order_status(_make_trade(9, "Cancelled", 0, 0))

        assert 9 not in client._order_contexts
        assert len(fire_calls) == 1

    def test_untracked_order_ignored(self):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        client._on_order_status(_make_trade(999, "Filled", 10.0, 155.0))
        assert len(fire_calls) == 0


# ===========================================================================
# PartiallyFilled cumulative snapshot (TRADE-02)
# ===========================================================================

CLIENT_PY = __import__(
    "app.services.live_trading.ibkr_trading.client", fromlist=["*"]
).__file__


class TestPartiallyFilledSnapshot:
    """UC-02c–UC-02g: PartiallyFilled overwrites DB; no trade on partial; invariants."""

    @patch("app.services.live_trading.ibkr_trading.client.records.update_pending_order_fill_snapshot")
    def test_partially_filled_calls_snapshot_not_handle_fill(self, mock_snap):
        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        ctx = _make_ctx(order_id=11, pending_order_id=99)
        client._order_contexts[11] = ctx

        client._on_order_status(
            _make_trade(
                11,
                "PartiallyFilled",
                filled=4.0,
                avg_price=1.25,
                remaining=6.0,
                total_qty=10.0,
            )
        )

        mock_snap.assert_called_once_with(99, filled=4.0, remaining=6.0, avg_price=1.25)
        assert len(fire_calls) == 0
        assert 11 in client._order_contexts
        assert client._order_contexts[11].last_reported_filled == 4.0

    @patch("app.services.live_trading.ibkr_trading.client.records.update_pending_order_fill_snapshot")
    def test_partially_filled_duplicate_overwrites_same(self, mock_snap):
        client = _make_client()
        ctx = _make_ctx(order_id=12, pending_order_id=88)
        client._order_contexts[12] = ctx

        tr = _make_trade(
            12, "PartiallyFilled", filled=4.0, avg_price=1.0, remaining=6.0, total_qty=10.0
        )
        client._on_order_status(tr)
        client._on_order_status(tr)

        assert mock_snap.call_count == 2
        mock_snap.assert_called_with(88, filled=4.0, remaining=6.0, avg_price=1.0)

    @patch("app.services.live_trading.ibkr_trading.client.logger")
    @patch("app.services.live_trading.ibkr_trading.client.records.update_pending_order_fill_snapshot")
    def test_non_monotonic_filled_logs_warning(self, _mock_snap, mock_logger):
        client = _make_client()
        ctx = _make_ctx(order_id=13, pending_order_id=77)
        client._order_contexts[13] = ctx

        client._on_order_status(
            _make_trade(
                13,
                "PartiallyFilled",
                filled=5.0,
                avg_price=1.0,
                remaining=5.0,
                total_qty=10.0,
            )
        )
        client._on_order_status(
            _make_trade(
                13,
                "PartiallyFilled",
                filled=4.0,
                avg_price=1.0,
                remaining=6.0,
                total_qty=10.0,
            )
        )

        warn_msgs = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("non_monotonic_filled" in m for m in warn_msgs)

    @patch("app.services.live_trading.ibkr_trading.client.logger")
    @patch("app.services.live_trading.ibkr_trading.client.records.update_pending_order_fill_snapshot")
    def test_sum_invariant_bad_total_logs_warning(self, _mock_snap, mock_logger):
        client = _make_client()
        ctx = _make_ctx(order_id=14, pending_order_id=66)
        client._order_contexts[14] = ctx

        client._on_order_status(
            _make_trade(
                14,
                "PartiallyFilled",
                filled=3.0,
                avg_price=1.0,
                remaining=10.0,
                total_qty=10.0,
            )
        )

        warn_msgs = [str(c) for c in mock_logger.warning.call_args_list]
        joined = " ".join(warn_msgs)
        assert "filled_plus_remaining" in joined and "ORDER_QTY_EPS" in joined

    @patch("app.services.live_trading.records.record_trade")
    @patch("app.services.live_trading.records.apply_fill_to_local_position", return_value=(0.0, {}))
    @patch("app.services.live_trading.records.mark_order_sent")
    @patch("app.services.live_trading.ibkr_trading.client.records.update_pending_order_fill_snapshot")
    def test_partially_filled_then_filled_records_trade_once(
        self, _snap, mock_sent, mock_apply, mock_record,
    ):
        client = _make_client()
        ctx = _make_ctx(order_id=15, pending_order_id=55, strategy_id=3)
        client._order_contexts[15] = ctx

        client._on_order_status(
            _make_trade(
                15,
                "PartiallyFilled",
                filled=5.0,
                avg_price=2.0,
                remaining=5.0,
                total_qty=10.0,
            )
        )
        assert 15 in client._order_contexts

        client._on_order_status(
            _make_trade(15, "Filled", filled=10.0, avg_price=2.0, remaining=0.0, total_qty=10.0)
        )

        mock_record.assert_called_once()

    def test_chinese_comment_uc02g_present_in_client_source(self):
        from pathlib import Path

        text = Path(CLIENT_PY).read_text(encoding="utf-8")
        needle = "PartiallyFilled → 累计值覆盖 DB 的 filled/remaining（不做增量计算）"
        assert needle in text


# ===========================================================================
# _handle_fill DB integration
# ===========================================================================

class TestHandleFillDB:

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    @patch("app.services.live_trading.records.record_trade")
    @patch("app.services.live_trading.records.apply_fill_to_local_position", return_value=(25.0, {}))
    @patch("app.services.live_trading.records.mark_order_sent")
    def test_full_fill_flow(self, mock_sent, mock_apply, mock_record, mock_notify):
        client = _make_client()
        ctx = _make_ctx(order_id=100, pending_order_id=50, strategy_id=7)

        client._handle_fill(ctx, filled=10.0, avg_price=155.0)

        mock_sent.assert_called_once()
        assert mock_sent.call_args[1]["order_id"] == 50
        assert mock_sent.call_args[1]["filled"] == 10.0
        assert mock_sent.call_args[1]["avg_price"] == 155.0

        mock_apply.assert_called_once_with(
            strategy_id=7, symbol="AAPL", signal_type="open_long",
            filled=10.0, avg_price=155.0,
        )

        mock_record.assert_called_once()
        assert mock_record.call_args[1]["strategy_id"] == 7
        assert mock_record.call_args[1]["price"] == 155.0
        assert mock_record.call_args[1]["amount"] == 10.0
        assert mock_record.call_args[1]["profit"] == 25.0

        mock_notify.assert_called_once_with(
            ctx, "filled", filled=10.0, avg_price=155.0,
        )

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    @patch("app.services.live_trading.records.mark_order_sent")
    def test_fill_without_strategy_skips_position_update(self, mock_sent, mock_notify):
        """If strategy_id=0, skip apply_fill and record_trade."""
        client = _make_client()
        ctx = _make_ctx(order_id=101, pending_order_id=51, strategy_id=0)

        client._handle_fill(ctx, filled=5.0, avg_price=200.0)

        mock_sent.assert_called_once()
        mock_notify.assert_called_once()

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    def test_fill_without_pending_id_skips_mark_sent(self, mock_notify):
        """If pending_order_id=0, skip mark_order_sent."""
        client = _make_client()
        ctx = _make_ctx(order_id=102, pending_order_id=0, strategy_id=0)

        client._handle_fill(ctx, filled=5.0, avg_price=200.0)
        mock_notify.assert_called_once()

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    @patch("app.services.live_trading.records.mark_order_sent", side_effect=Exception("DB error"))
    def test_fill_db_error_does_not_crash(self, mock_sent, mock_notify):
        """DB errors are caught and logged, not re-raised."""
        client = _make_client()
        ctx = _make_ctx(order_id=103, pending_order_id=52)

        client._handle_fill(ctx, filled=10.0, avg_price=155.0)
        mock_notify.assert_called_once()


# ===========================================================================
# _handle_reject DB integration
# ===========================================================================

class TestHandleRejectDB:

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    @patch("app.services.live_trading.records.mark_order_failed")
    def test_reject_marks_failed(self, mock_failed, mock_notify):
        client = _make_client()
        ctx = _make_ctx(order_id=200, pending_order_id=60)

        client._handle_reject(ctx, "Inactive", ["Order rejected by exchange"])

        mock_failed.assert_called_once()
        assert mock_failed.call_args[1]["order_id"] == 60
        assert "Inactive" in mock_failed.call_args[1]["error"]
        assert "Order rejected by exchange" in mock_failed.call_args[1]["error"]

        mock_notify.assert_called_once_with(
            ctx, "failed",
            error="Order rejected by exchange",
        )

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    @patch("app.services.live_trading.records.mark_order_failed")
    def test_reject_empty_error_msgs(self, mock_failed, mock_notify):
        client = _make_client()
        ctx = _make_ctx(order_id=201, pending_order_id=61)

        client._handle_reject(ctx, "ApiError", [])

        mock_failed.assert_called_once()
        assert "ApiError" in mock_failed.call_args[1]["error"]

    @patch("app.services.live_trading.ibkr_trading.client.IBKRClient._notify_order_event")
    def test_reject_no_pending_id_skips_mark(self, mock_notify):
        client = _make_client()
        ctx = _make_ctx(order_id=202, pending_order_id=0)

        client._handle_reject(ctx, "ApiError", ["Some error"])
        mock_notify.assert_called_once()


# ===========================================================================
# Scenario: full lifecycle
# ===========================================================================

class TestFullOrderLifecycle:
    """End-to-end: place order → event callback → DB update."""

    @patch("app.services.live_trading.ibkr_trading.client.ib_insync")
    def test_place_then_fill(self, mock_ib_mod):
        mock_ib_mod.MarketOrder = MagicMock(return_value=MagicMock(orderId=0))
        mock_ib_mod.Stock = MagicMock()

        client = _make_client()
        fire_calls = []
        client._fire_submit = lambda fn, is_blocking=True: fire_calls.append(fn)

        trade_mock = MagicMock()
        trade_mock.order.orderId = 777
        trade_mock.orderStatus.status = "Submitted"
        client._ib.placeOrder.return_value = trade_mock
        client._ib.qualifyContracts.return_value = [MagicMock()]

        import asyncio as _aio
        async def _mock_qualify_async(*contracts):
            for c in contracts:
                con_id = getattr(c, 'conId', None)
                if not isinstance(con_id, int) or con_id == 0:
                    c.conId = 1
                sec = getattr(c, 'secType', None)
                if not isinstance(sec, str):
                    c.secType = 'STK'
            return list(contracts)
        client._ib.qualifyContractsAsync = _mock_qualify_async
        client._ib.isConnected.return_value = True

        result = client.place_market_order(
            "AAPL", "buy", 10, "USStock",
            pending_order_id=88, strategy_id=12, signal_type="open_long",
        )

        assert result.success is True
        assert result.status == "Submitted"
        assert result.order_id == 777
        assert 777 in client._order_contexts

        # Simulate fill event
        fill_trade = MagicMock()
        fill_trade.order.orderId = 777
        fill_trade.orderStatus.status = "Filled"
        fill_trade.orderStatus.filled = 10.0
        fill_trade.orderStatus.avgFillPrice = 155.0
        fill_trade.log = []
        client._on_order_status(fill_trade)

        assert 777 not in client._order_contexts  # popped for fill idempotency
        assert 777 in client._commission_contexts  # lingers for commissionReport
        assert len(fire_calls) == 1
