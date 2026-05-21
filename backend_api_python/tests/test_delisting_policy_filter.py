"""
Tests for DelistingPolicyFilter in cross_sectional_filter_chain.

Tests STRAT-02: Delisting policy handling for NQ100 index reconstitution events.
"""

from datetime import date
from unittest.mock import MagicMock, patch, call

import pytest

from app.strategies.runners.cross_sectional_filter_chain import (
    FilterAction,
    FilterContext,
    FilterOutcome,
    SignalFilter,
)


def _make_mock_db_connection(fetchone_result=None):
    """Helper to create a properly mocked database connection context manager."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fetchone_result

    mock_conn = MagicMock()
    # conn.cursor() returns a regular cursor object (not a context manager in this code)
    mock_conn.cursor.return_value = mock_cursor

    mock_db = MagicMock()
    # db.get_db_connection() returns a context manager that yields mock_conn
    mock_context = MagicMock()
    mock_context.__enter__ = MagicMock(return_value=mock_conn)
    mock_context.__exit__ = MagicMock(return_value=False)
    mock_db.get_db_connection.return_value = mock_context

    return mock_db, mock_conn, mock_cursor


class TestFilterStructure:
    """Task 1: Test DelistingPolicyFilter structure and basic behavior."""

    def test_delisting_policy_filter_inherits_signal_filter(self):
        """Test that DelistingPolicyFilter inherits from SignalFilter."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        assert DelistingPolicyFilter.__bases__[0] == SignalFilter

    def test_filter_returns_filter_outcome(self):
        """Test that apply() returns FilterOutcome instance."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={},
            symbol="AAPL",
            side="buy",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-04",
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=None)
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            assert isinstance(result, FilterOutcome)

    def test_no_change_event_for_symbol(self):
        """Test that symbols without remove events return CONTINUE."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={},
            symbol="AAPL",
            side="buy",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-04",
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=None)
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            assert result.action == FilterAction.CONTINUE

    def test_add_event_ignored(self):
        """Test that add events do not trigger forced sell (only remove events)."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={},
            symbol="AAPL",
            side="buy",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-04",
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=None)
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            assert result.action == FilterAction.CONTINUE

    def test_missing_delisting_policy_defaults_immediate(self):
        """Test that missing delisting_policy defaults to immediate mode."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        # Signal without delisting_policy field
        ctx = FilterContext(
            signal={},
            symbol="XYZ",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-18",
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        # Return a remove event with effective_date matching execution_date
        mock_db, _, _ = _make_mock_db_connection(fetchone_result=(date(2024, 3, 18),))
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            # Default immediate mode: execution_date >= effective_date should trigger forced_sell
            assert result.action == FilterAction.ACCEPT
            assert result.signal["type"] == "forced_sell"


class TestImmediateMode:
    """Task 2: Test immediate mode forced sell logic."""

    def test_immediate_mode_forced_sell_on_effective_date(self):
        """D-12: Sell on effective_date when execution_date equals effective_date."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={"delisting_policy": {"mode": "immediate"}},
            symbol="XYZ",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-18",  # Same as effective_date
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=(date(2024, 3, 18),))
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            assert result.action == FilterAction.ACCEPT
            assert result.signal["type"] == "forced_sell"
            assert result.signal["delisting_event_date"] == "2024-03-18"
            assert result.log_status == "forced_delisting_exit_immediate"

    def test_immediate_mode_forced_sell_after_effective_date(self):
        """D-12: Sell after effective_date when execution_date > effective_date."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={"delisting_policy": {"mode": "immediate"}},
            symbol="XYZ",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-04-15",  # After effective_date
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=(date(2024, 3, 18),))
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            assert result.action == FilterAction.ACCEPT
            assert result.signal["type"] == "forced_sell"

    def test_immediate_mode_no_action_before_effective_date(self):
        """D-12: No sell before effective_date when execution_date < effective_date."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={"delisting_policy": {"mode": "immediate"}},
            symbol="XYZ",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-17",  # Before effective_date
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=(date(2024, 3, 18),))
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            assert result.action == FilterAction.CONTINUE


class TestDelayedMode:
    """Task 2: Test delayed mode forced sell logic."""

    def test_delayed_mode_forced_sell_after_months(self):
        """D-13: Sell after delay period (months after effective_date)."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={"delisting_policy": {"mode": "delayed", "months": 3}},
            symbol="XYZ",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-06-18",  # 3 months after effective_date
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=(date(2024, 3, 18),))
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            assert result.action == FilterAction.ACCEPT
            assert result.signal["type"] == "forced_sell"
            assert result.signal["delayed_months"] == 3
            assert result.log_status == "forced_delisting_exit_delayed"

    def test_delayed_mode_no_action_within_delay_period(self):
        """D-13: No sell within delay period."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={"delisting_policy": {"mode": "delayed", "months": 3}},
            symbol="XYZ",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-04-15",  # Within 3 months
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=(date(2024, 3, 18),))
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            assert result.action == FilterAction.CONTINUE

    def test_delayed_mode_6_months_delay(self):
        """D-13: Custom months value (6 months)."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={"delisting_policy": {"mode": "delayed", "months": 6}},
            symbol="XYZ",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-09-18",  # 6 months after effective_date
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=(date(2024, 3, 18),))
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            assert result.action == FilterAction.ACCEPT
            assert result.signal["delayed_months"] == 6


class TestHoldUntilSignalExit:
    """Task 2: Test hold_until_signal_exit mode."""

    def test_hold_until_signal_exit_no_forced_sell(self):
        """D-09: No forced sell from filter in hold_until_signal_exit mode."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={"delisting_policy": {"mode": "hold_until_signal_exit"}},
            symbol="XYZ",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-06-18",  # Long after effective_date
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=(date(2024, 3, 18),))
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            # hold_until_signal_exit should NOT trigger forced_sell
            assert result.action == FilterAction.CONTINUE


class TestMonthBoundaryCalculation:
    """Test month boundary handling for delayed mode."""

    def test_calculate_delayed_date_jan_to_apr(self):
        """Test Jan 31 + 3 months = Apr 30 (not Apr 31)."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        result = filt._calculate_delayed_date(date(2024, 1, 31), 3)
        assert result == date(2024, 4, 30)

    def test_calculate_delayed_date_mar_to_may(self):
        """Test Mar 31 + 2 months = May 31."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        result = filt._calculate_delayed_date(date(2024, 3, 31), 2)
        assert result == date(2024, 5, 31)

    def test_calculate_delayed_date_year_rollover(self):
        """Test month addition with year rollover."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        result = filt._calculate_delayed_date(date(2024, 11, 15), 3)
        assert result == date(2025, 2, 15)

    def test_calculate_delayed_date_feb_boundary(self):
        """Test Jan 31 + 1 month = Feb 28/29 depending on year."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        # 2024 is a leap year
        result_2024 = filt._calculate_delayed_date(date(2024, 1, 31), 1)
        assert result_2024 == date(2024, 2, 29)

        # 2023 is not a leap year
        result_2023 = filt._calculate_delayed_date(date(2023, 1, 31), 1)
        assert result_2023 == date(2023, 2, 28)


class TestForceExitSymbols:
    """Task 1 (Plan 04): Test force_exit_symbols override logic (D-14/D-16)."""

    def test_force_exit_symbols_immediate_sell(self):
        """D-14/D-16: Symbol in force_exit_symbols triggers immediate forced_sell."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={"force_exit_symbols": ["ENRN"], "delisting_policy": {"mode": "immediate"}},
            symbol="ENRN",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-18",
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=None)
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            # force_exit_symbols override should trigger immediate forced_sell
            assert result.action == FilterAction.ACCEPT
            assert result.signal["type"] == "forced_sell"
            assert result.signal["force_exit_reason"] == "manual_force_exit"
            assert result.log_status == "forced_exit_override"

    def test_force_exit_symbols_override_delisting_policy_mode(self):
        """D-14/D-16: force_exit_symbols overrides all delisting_policy timing."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        # hold_until_signal_exit normally would NOT trigger forced_sell
        # but force_exit_symbols override should bypass that
        ctx = FilterContext(
            signal={"force_exit_symbols": ["ENRN"], "delisting_policy": {"mode": "hold_until_signal_exit"}},
            symbol="ENRN",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-18",
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=(date(2024, 3, 18),))
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            # force_exit_symbols override bypasses hold_until_signal_exit mode
            assert result.action == FilterAction.ACCEPT
            assert result.signal["type"] == "forced_sell"
            assert result.signal["force_exit_reason"] == "manual_force_exit"

    def test_force_exit_symbols_empty_list_normal_logic(self):
        """Empty force_exit_symbols list falls through to normal delisting_policy logic."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={"force_exit_symbols": [], "delisting_policy": {"mode": "immediate"}},
            symbol="XYZ",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-17",  # Before effective_date
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=(date(2024, 3, 18),))
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            # Empty list means normal delisting_policy logic applies
            assert result.action == FilterAction.CONTINUE

    def test_force_exit_symbols_symbol_not_in_list(self):
        """Symbol not in force_exit_symbols falls through to normal delisting_policy logic."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={"force_exit_symbols": ["ENRN"], "delisting_policy": {"mode": "immediate"}},
            symbol="AAPL",  # Not in force_exit_symbols list
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-17",
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=(date(2024, 3, 18),))
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            # AAPL not in force_exit_symbols, normal delisting_policy applies
            assert result.action == FilterAction.CONTINUE

    def test_force_exit_symbols_from_signal_metadata(self):
        """force_exit_symbols comes from signal metadata (passed by Runner)."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={"force_exit_symbols": ["ENRN", "WXYZ"]},  # Multiple symbols in metadata
            symbol="ENRN",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-18",
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=None)
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            assert result.action == FilterAction.ACCEPT
            assert result.signal["type"] == "forced_sell"

    def test_force_exit_symbols_case_insensitive(self):
        """D-14/D-16: Case-insensitive symbol matching."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={"force_exit_symbols": ["ENRN"]},  # uppercase
            symbol="enrn",  # lowercase
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-18",
            market_row={},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=None)
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            # Case-insensitive match
            assert result.action == FilterAction.ACCEPT
            assert result.signal["type"] == "forced_sell"


class TestBacktestTotalLoss:
    """Task 2 (Plan 04): Test backtest total loss assumption (D-15)."""

    def test_backtest_force_exit_total_loss(self):
        """D-15: Backtest + force_exit -> execution_price=0.0 (total loss)."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={
                "force_exit_symbols": ["ENRN"],
                "execution_mode": "backtest",
                "delisting_policy": {"mode": "immediate"},
            },
            symbol="ENRN",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-18",
            market_row={"next_open": 50.0},  # Has market price
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=None)
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            # D-15: Backtest total loss for force_exit_symbols
            assert result.action == FilterAction.ACCEPT
            assert result.signal["type"] == "forced_sell"
            assert result.signal["execution_price"] == 0.0
            assert result.signal["price_source"] == "total_loss_assumption"

    def test_live_force_exit_actual_price(self):
        """D-14: Live + force_exit -> execution_price NOT set (ExecutionPriceFilter handles)."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={
                "force_exit_symbols": ["ENRN"],
                "execution_mode": "live",
                "delisting_policy": {"mode": "immediate"},
            },
            symbol="ENRN",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-18",
            market_row={"next_open": 50.0},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=None)
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            # D-14: Live trading uses actual price (ExecutionPriceFilter will set)
            assert result.action == FilterAction.ACCEPT
            assert result.signal["type"] == "forced_sell"
            # execution_price should NOT be set by DelistingPolicyFilter for live mode
            assert "execution_price" not in result.signal

    def test_backtest_normal_delisting_market_price(self):
        """Normal delisting events (from change_events) use market_row price regardless of execution_mode."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={
                "execution_mode": "backtest",
                "delisting_policy": {"mode": "immediate"},
            },
            symbol="XYZ",  # Not in force_exit_symbols
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-18",
            market_row={"next_open": 50.0},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=(date(2024, 3, 18),))
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            # Normal delisting uses market price (ExecutionPriceFilter handles)
            assert result.action == FilterAction.ACCEPT
            assert result.signal["type"] == "forced_sell"
            # execution_price should NOT be set here - ExecutionPriceFilter handles it
            assert "execution_price" not in result.signal

    def test_execution_mode_default_live(self):
        """execution_mode defaults to 'live' when not specified."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={
                "force_exit_symbols": ["ENRN"],
                # No execution_mode field - should default to live
                "delisting_policy": {"mode": "immediate"},
            },
            symbol="ENRN",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-18",
            market_row={"next_open": 50.0},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=None)
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            # Default to live mode - execution_price NOT set
            assert result.action == FilterAction.ACCEPT
            assert "execution_price" not in result.signal

    def test_backtest_total_loss_log_status(self):
        """Log status includes 'backtest_total_loss' indicator for total loss scenario."""
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        filt = DelistingPolicyFilter()
        ctx = FilterContext(
            signal={
                "force_exit_symbols": ["ENRN"],
                "execution_mode": "backtest",
                "delisting_policy": {"mode": "immediate"},
            },
            symbol="ENRN",
            side="sell",
            signal_date_iso="2024-03-01",
            execution_date_iso="2024-03-18",
            market_row={"next_open": 50.0},
            tradability={},
            cash_mna_events={},
            min_liquidity_usd=1000000.0,
            fallback_mode="strict",
        )

        mock_db, _, _ = _make_mock_db_connection(fetchone_result=None)
        with patch("app.strategies.runners.cross_sectional_filter_chain.db", mock_db):
            result = filt.apply(ctx)
            assert "backtest_total_loss" in result.log_status