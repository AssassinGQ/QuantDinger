"""
Position guard tests for StatefulClientRunner.pre_check.

Tests the close/reduce position guard that prevents sending sell orders
when the local strategy position is zero or insufficient.
"""
from unittest.mock import MagicMock, patch

from app.services.live_trading.base import (
    BaseStatefulClient,
    OrderContext,
)
from app.services.live_trading.runners.base import PreCheckResult
from app.services.live_trading.runners.stateful_runner import (
    StatefulClientRunner,
    _is_close_or_reduce_signal,
)
from app.services.live_trading import records as live_records


def _make_ctx(
    strategy_id=525,
    symbol="09618",
    signal_type="close_long",
    amount=200.0,
) -> OrderContext:
    return OrderContext(
        order_id=1,
        strategy_id=strategy_id,
        symbol=symbol,
        signal_type=signal_type,
        amount=amount,
        market_type="USStock",
        market_category="HShare",
        exchange_config={},
        payload={},
        order_row={},
        notification_config={},
        strategy_name="test",
        direction="long",
        price=112.0,
    )


# ── _is_close_or_reduce_signal ────────────────────────────────

def test_is_close_or_reduce_signal_true():
    assert _is_close_or_reduce_signal("close_long") is True
    assert _is_close_or_reduce_signal("close_short") is True
    assert _is_close_or_reduce_signal("reduce_long") is True
    assert _is_close_or_reduce_signal("reduce_short") is True


def test_is_close_or_reduce_signal_false():
    assert _is_close_or_reduce_signal("open_long") is False
    assert _is_close_or_reduce_signal("open_short") is False
    assert _is_close_or_reduce_signal("add_long") is False
    assert _is_close_or_reduce_signal("add_short") is False


# ── Position guard: close/reduce with no position ─────────────

def test_close_long_no_position_rejected():
    """close_long when local_size=0 → rejected."""
    with patch.object(live_records, "_fetch_position", return_value={}):
        runner = StatefulClientRunner()
        client = MagicMock(spec=BaseStatefulClient)
        ctx = _make_ctx(signal_type="close_long", amount=200.0)
        result = runner.pre_check(client=client, order_context=ctx)
        assert result.ok is False
        assert "position_guard:no_position" in result.reason


def test_close_short_no_position_rejected():
    """close_short when local_size=0 → rejected."""
    with patch.object(live_records, "_fetch_position", return_value={}):
        runner = StatefulClientRunner()
        client = MagicMock(spec=BaseStatefulClient)
        ctx = _make_ctx(signal_type="close_short", amount=100.0)
        result = runner.pre_check(client=client, order_context=ctx)
        assert result.ok is False
        assert "position_guard:no_position" in result.reason


def test_reduce_long_no_position_rejected():
    """reduce_long when local_size=0 → rejected."""
    with patch.object(live_records, "_fetch_position", return_value={}):
        runner = StatefulClientRunner()
        client = MagicMock(spec=BaseStatefulClient)
        ctx = _make_ctx(signal_type="reduce_long", amount=50.0)
        result = runner.pre_check(client=client, order_context=ctx)
        assert result.ok is False
        assert "position_guard:no_position" in result.reason


def test_close_long_zero_size_rejected():
    """close_long when local_size=0 (position row exists but size=0) → rejected."""
    with patch.object(live_records, "_fetch_position", return_value={"size": 0.0}):
        runner = StatefulClientRunner()
        client = MagicMock(spec=BaseStatefulClient)
        ctx = _make_ctx(signal_type="close_long", amount=200.0)
        result = runner.pre_check(client=client, order_context=ctx)
        assert result.ok is False
        assert "position_guard:no_position" in result.reason


# ── Position guard: amount exceeds position ────────────────────

def test_close_long_amount_exceeds_position_rejected():
    """close_long when amount > local_size → rejected (would create short)."""
    with patch.object(live_records, "_fetch_position", return_value={"size": 100.0}):
        runner = StatefulClientRunner()
        client = MagicMock(spec=BaseStatefulClient)
        ctx = _make_ctx(signal_type="close_long", amount=200.0)
        result = runner.pre_check(client=client, order_context=ctx)
        assert result.ok is False
        assert "position_guard:amount" in result.reason
        assert "exceeds_position" in result.reason


def test_reduce_long_amount_exceeds_position_rejected():
    """reduce_long when amount > local_size → rejected."""
    with patch.object(live_records, "_fetch_position", return_value={"size": 50.0}):
        runner = StatefulClientRunner()
        client = MagicMock(spec=BaseStatefulClient)
        ctx = _make_ctx(signal_type="reduce_long", amount=80.0)
        result = runner.pre_check(client=client, order_context=ctx)
        assert result.ok is False
        assert "position_guard:amount" in result.reason


# ── Position guard: valid close/reduce ──────────────────────────

def test_close_long_with_position_allowed():
    """close_long when local_size >= amount → allowed, RTH skipped."""
    with patch.object(live_records, "_fetch_position", return_value={"size": 200.0}):
        runner = StatefulClientRunner()
        client = MagicMock(spec=BaseStatefulClient)
        ctx = _make_ctx(signal_type="close_long", amount=200.0)
        result = runner.pre_check(client=client, order_context=ctx)
        assert result.ok is True
        # RTH check should NOT be called for close signals
        client.is_market_open.assert_not_called()


def test_close_long_amount_less_than_size_allowed():
    """close_long when amount < local_size → allowed."""
    with patch.object(live_records, "_fetch_position", return_value={"size": 400.0}):
        runner = StatefulClientRunner()
        client = MagicMock(spec=BaseStatefulClient)
        ctx = _make_ctx(signal_type="close_long", amount=200.0)
        result = runner.pre_check(client=client, order_context=ctx)
        assert result.ok is True


def test_reduce_long_with_position_allowed():
    """reduce_long when local_size >= amount → allowed."""
    with patch.object(live_records, "_fetch_position", return_value={"size": 100.0}):
        runner = StatefulClientRunner()
        client = MagicMock(spec=BaseStatefulClient)
        ctx = _make_ctx(signal_type="reduce_long", amount=30.0)
        result = runner.pre_check(client=client, order_context=ctx)
        assert result.ok is True
        client.is_market_open.assert_not_called()


# ── Position guard does NOT affect open/add signals ─────────────

def test_open_long_skips_position_guard_and_checks_rth():
    """open_long should not trigger position guard; should check RTH."""
    runner = StatefulClientRunner()
    client = MagicMock(spec=BaseStatefulClient)
    client.engine_id = "ibkr-paper"
    client.is_market_open.return_value = (True, "")
    ctx = _make_ctx(signal_type="open_long", amount=200.0)
    result = runner.pre_check(client=client, order_context=ctx)
    assert result.ok is True
    client.is_market_open.assert_called_once()


def test_open_long_rth_blocked():
    """open_long blocked by RTH → position guard not involved."""
    runner = StatefulClientRunner()
    client = MagicMock(spec=BaseStatefulClient)
    client.engine_id = "ibkr-paper"
    client.is_market_open.return_value = (False, "market closed")
    ctx = _make_ctx(signal_type="open_long", amount=200.0)
    result = runner.pre_check(client=client, order_context=ctx)
    assert result.ok is False
    assert "market_closed" in result.reason


# ── Position drift detection in apply_fill_to_local_position ────

@patch("app.services.live_trading.records._delete_position")
@patch("app.services.live_trading.records._fetch_position")
def test_apply_fill_oversold_logs_drift_warning(mock_fetch, mock_delete):
    """When fill exceeds local position (oversold), log a PositionDrift warning."""
    # Local position: size=100, entry_price=110
    mock_fetch.return_value = {"size": 100.0, "entry_price": 110.0, "highest_price": 115.0, "lowest_price": 105.0}
    # After deletion, fetch returns empty
    mock_delete.return_value = None

    with patch.object(live_records.logger, "warning") as mock_warn:
        profit, pos = live_records.apply_fill_to_local_position(
            strategy_id=525,
            symbol="09618",
            signal_type="close_long",
            filled=200.0,  # oversold: local=100, fill=200
            avg_price=112.0,
        )

        # Profit should use close_qty = min(100, 200) = 100
        assert profit is not None
        expected_profit = (112.0 - 110.0) * 100.0  # close_qty=100
        assert profit == expected_profit

        # Position deleted (new_size = 100 - 200 = -100 ≤ 0)
        mock_delete.assert_called_once_with(525, "09618", "long")

        # Drift warning logged
        drift_warnings = [c for c in mock_warn.call_args_list if "PositionDrift" in str(c)]
        assert len(drift_warnings) == 1


@patch("app.services.live_trading.records._delete_position")
@patch("app.services.live_trading.records._fetch_position")
def test_apply_fill_normal_close_no_drift_warning(mock_fetch, mock_delete):
    """Normal close (fill <= local_size) should NOT log PositionDrift warning."""
    mock_fetch.return_value = {"size": 200.0, "entry_price": 110.0, "highest_price": 115.0, "lowest_price": 105.0}
    mock_delete.return_value = None

    with patch.object(live_records.logger, "warning") as mock_warn:
        profit, pos = live_records.apply_fill_to_local_position(
            strategy_id=525,
            symbol="09618",
            signal_type="close_long",
            filled=200.0,  # exact match: local=200, fill=200
            avg_price=112.0,
        )

        # No drift warning
        drift_warnings = [c for c in mock_warn.call_args_list if "PositionDrift" in str(c)]
        assert len(drift_warnings) == 0