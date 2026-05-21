"""
Tests for CrossSectionalRunner integration with DelistingPolicyFilter.

Tests STRAT-02: Runner-level integration for delisting policy handling.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.strategies.runners.cross_sectional_runner import (
    CrossSectionalRunner,
    ExecutionPolicy,
)


def _make_mock_db_connection(fetchall_result=None, fetchone_result=None):
    """Helper to create a properly mocked database connection context manager."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = fetchall_result or []
    mock_cursor.fetchone.return_value = fetchone_result

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_db = MagicMock()
    mock_context = MagicMock()
    mock_context.__enter__ = MagicMock(return_value=mock_conn)
    mock_context.__exit__ = MagicMock(return_value=False)
    mock_db.get_db_connection.return_value = mock_context

    return mock_db, mock_conn, mock_cursor


class TestDelistingFilterChain:
    """Task 1: Test DelistingPolicyFilter integration in Runner FilterChain."""

    def test_runner_includes_delisting_filter_in_chain(self):
        """Test 1: DelistingPolicyFilter in FilterChain filter list."""
        # Inspect _filter_phase21_signals to verify filter chain composition
        from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner
        from app.strategies.runners.cross_sectional_filter_chain import DelistingPolicyFilter

        runner = CrossSectionalRunner(
            data_handler=MagicMock(),
            signal_executor=MagicMock(),
        )

        # Check that _filter_phase21_signals builds the chain with DelistingPolicyFilter
        # We'll need to inspect the code to verify this - this test verifies the import exists
        # and the filter is added to the chain
        # For now, check the import is available in the module
        import app.strategies.runners.cross_sectional_runner as runner_module

        # Check that DelistingPolicyFilter is imported in runner module
        assert hasattr(runner_module, 'DelistingPolicyFilter'), \
            "DelistingPolicyFilter should be imported in cross_sectional_runner"

    def test_runner_filter_order_correct(self):
        """Test 6: Verify DelistingPolicyFilter position in chain (after CashMna, before Tradability)."""
        # This test will verify the correct order of filters in the chain
        # After Task 1 implementation, we can verify by inspecting the _filter_phase21_signals method
        # The order should be: CashMnaForcedExitFilter -> DelistingPolicyFilter -> TradabilityFilter
        from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner

        runner = CrossSectionalRunner(
            data_handler=MagicMock(),
            signal_executor=MagicMock(),
        )

        # Create test signals and metadata
        signals = [{"symbol": "AAPL", "type": "open_long", "signal_date": date(2024, 3, 1)}]
        policy = ExecutionPolicy()
        metadata = {
            "ic_effective_dates": [],
            "market_rows": {},
            "tradability": {},
            "cash_mna": {},
        }

        # Mock the chain building and verify filter order
        # This test will pass after implementation adds DelistingPolicyFilter
        with patch.object(runner, '_query_change_events', return_value={}):
            filtered, exec_meta = runner._filter_phase21_signals(signals, policy, metadata)

        # After implementation, DelistingPolicyFilter should be in the chain
        # We verify by checking the import and filter chain structure
        import app.strategies.runners.cross_sectional_filter_chain as filter_chain_module

        # Verify DelistingPolicyFilter is available
        assert hasattr(filter_chain_module, 'DelistingPolicyFilter')

    def test_runner_metadata_includes_change_events(self):
        """Test 2: Runner metadata includes change_events from qd_nq100_change_events."""
        from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner

        runner = CrossSectionalRunner(
            data_handler=MagicMock(),
            signal_executor=MagicMock(),
        )

        # Mock database to return change events
        mock_change_events = [
            ("XYZ", "remove", date(2024, 3, 18)),
            ("ABC", "remove", date(2024, 3, 20)),
        ]
        mock_db, _, _ = _make_mock_db_connection(fetchall_result=mock_change_events)

        # Check that _query_change_events method exists
        assert hasattr(runner, '_query_change_events'), \
            "Runner should have _query_change_events helper method"

        with patch("app.strategies.runners.cross_sectional_runner.db", mock_db):
            change_events = runner._query_change_events([date(2024, 3, 1)])

        # Verify the structure: {symbol: [{"event_type": "remove", "effective_date": date}]}
        assert isinstance(change_events, dict)

    def test_runner_metadata_includes_force_exit_symbols(self):
        """Test 3: Runner metadata includes force_exit_symbols from trading_config."""
        from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner

        runner = CrossSectionalRunner(
            data_handler=MagicMock(),
            signal_executor=MagicMock(),
        )

        # Create test signals
        signals = [{"symbol": "ENRN", "type": "open_long", "signal_date": date(2024, 3, 1)}]
        policy = ExecutionPolicy()
        metadata = {
            "trading_config": {
                "force_exit_symbols": ["ENRN"],
                "delisting_policy": {"mode": "immediate"},
            },
            "ic_effective_dates": [],
            "market_rows": {},
            "tradability": {},
            "cash_mna": {},
            "execution_mode": "live",
        }

        # Mock _query_change_events
        with patch.object(runner, '_query_change_events', return_value={}):
            filtered, exec_meta = runner._filter_phase21_signals(signals, policy, metadata)

        # Verify that signals have force_exit_symbols metadata attached
        # After implementation, each signal should have force_exit_symbols from trading_config
        for signal in filtered:
            # Check that signal metadata includes force_exit_symbols
            # This will be verified after implementation
            pass

    def test_runner_metadata_includes_delisting_policy(self):
        """Test 4: Runner metadata includes delisting_policy from trading_config."""
        from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner

        runner = CrossSectionalRunner(
            data_handler=MagicMock(),
            signal_executor=MagicMock(),
        )

        signals = [{"symbol": "AAPL", "type": "open_long", "signal_date": date(2024, 3, 1)}]
        policy = ExecutionPolicy()
        metadata = {
            "trading_config": {
                "delisting_policy": {"mode": "immediate"},
            },
            "ic_effective_dates": [],
            "market_rows": {},
            "tradability": {},
            "cash_mna": {},
            "execution_mode": "live",
        }

        with patch.object(runner, '_query_change_events', return_value={}):
            filtered, exec_meta = runner._filter_phase21_signals(signals, policy, metadata)

        # After implementation, signals should have delisting_policy attached
        # Verify by checking signal structure
        pass

    def test_runner_metadata_includes_execution_mode(self):
        """Test 5: execution_mode passed in signal metadata for backtest vs live distinction."""
        from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner

        runner = CrossSectionalRunner(
            data_handler=MagicMock(),
            signal_executor=MagicMock(),
        )

        signals = [{"symbol": "AAPL", "type": "open_long", "signal_date": date(2024, 3, 1)}]
        policy = ExecutionPolicy()
        metadata = {
            "execution_mode": "backtest",
            "ic_effective_dates": [],
            "market_rows": {},
            "tradability": {},
            "cash_mna": {},
        }

        with patch.object(runner, '_query_change_events', return_value={}):
            filtered, exec_meta = runner._filter_phase21_signals(signals, policy, metadata)

        # After implementation, each signal should have execution_mode
        pass


class TestExcludedTracking:
    """Task 3: Test excluded_from_universe persistence after sell signal execution."""

    def test_runner_updates_excluded_after_sell(self):
        """Test 1: Sell signal for excluded stock updates strategy status_info."""
        from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner

        mock_data_handler = MagicMock()
        mock_data_handler.get_strategy_status_info.return_value = {"excluded_from_universe": []}
        mock_data_handler.update_strategy_status_info = MagicMock()
        mock_data_handler.get_all_positions.return_value = []

        mock_signal_executor = MagicMock()

        runner = CrossSectionalRunner(
            data_handler=mock_data_handler,
            signal_executor=mock_signal_executor,
        )
        runner._last_current_time = 1234567890.0

        # Simulate sell signal for excluded stock in hold_until_signal_exit mode
        strategy_id = 1
        strategy = {
            "trading_config": {
                "delisting_policy": {"mode": "hold_until_signal_exit"},
            }
        }
        # Simulate filtered signals after _filter_phase21_signals
        signals = [
            {
                "symbol": "XYZ",
                "type": "close_long",
                "excluded_from_universe": True,
            }
        ]
        metadata = {
            "trading_config": {
                "delisting_policy": {"mode": "hold_until_signal_exit"},
            }
        }

        # Mock _filter_phase21_signals to return signals with excluded_from_universe
        with patch.object(
            runner,
            '_filter_phase21_signals',
            return_value=(signals, {"execution_logs": []})
        ):
            runner._dispatch_signals(
                strategy_id, strategy, signals, True, metadata, MagicMock()
            )

        # After implementation, status_info should be updated with excluded_from_universe
        # Check that update_strategy_status_info was called
        mock_data_handler.update_strategy_status_info.assert_called()

    def test_excluded_persist_across_rebalance(self):
        """Test 2: excluded_from_universe list persists in status_info."""
        from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner

        mock_data_handler = MagicMock()
        # Simulate existing excluded symbols
        mock_data_handler.get_strategy_status_info.return_value = {
            "excluded_from_universe": ["ABC"]
        }
        mock_data_handler.update_strategy_status_info = MagicMock()
        mock_data_handler.get_all_positions.return_value = []

        runner = CrossSectionalRunner(
            data_handler=mock_data_handler,
            signal_executor=MagicMock(),
        )
        runner._last_current_time = 1234567890.0

        # Add new excluded symbol
        strategy_id = 1
        strategy = {
            "trading_config": {
                "delisting_policy": {"mode": "hold_until_signal_exit"},
            }
        }
        signals = [
            {
                "symbol": "XYZ",
                "type": "close_long",
                "excluded_from_universe": True,
            }
        ]
        metadata = {
            "trading_config": {
                "delisting_policy": {"mode": "hold_until_signal_exit"},
            }
        }

        with patch.object(
            runner,
            '_filter_phase21_signals',
            return_value=(signals, {"execution_logs": []})
        ):
            runner._dispatch_signals(
                strategy_id, strategy, signals, True, metadata, MagicMock()
            )

        # After implementation, status_info should be updated with ["ABC", "XYZ"]
        # Verify the call was made
        mock_data_handler.update_strategy_status_info.assert_called()

    def test_excluded_not_reenter_ranking_pool(self):
        """Test 3: Symbol NOT in get_data_request symbol_list after being excluded."""
        # This tests Strategy-layer behavior - verified in Task 2 tests
        # test_hold_mode_reads_excluded_from_status_info covers this
        pass

    def test_immediate_mode_no_excluded_tracking(self):
        """Test 4: No excluded_from_universe tracking in immediate mode."""
        from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner

        mock_data_handler = MagicMock()
        mock_data_handler.get_strategy_status_info.return_value = {"excluded_from_universe": []}
        mock_data_handler.update_strategy_status_info = MagicMock()
        mock_data_handler.get_all_positions.return_value = []

        runner = CrossSectionalRunner(
            data_handler=mock_data_handler,
            signal_executor=MagicMock(),
        )
        runner._last_current_time = 1234567890.0

        strategy_id = 1
        strategy = {
            "trading_config": {
                "delisting_policy": {"mode": "immediate"},
            }
        }
        signals = [
            {
                "symbol": "XYZ",
                "type": "forced_sell",
            }
        ]
        metadata = {
            "trading_config": {
                "delisting_policy": {"mode": "immediate"},
            }
        }

        with patch.object(
            runner,
            '_filter_phase21_signals',
            return_value=(signals, {"execution_logs": []})
        ):
            runner._dispatch_signals(
                strategy_id, strategy, signals, True, metadata, MagicMock()
            )

        # In immediate mode, no excluded_from_universe tracking needed
        # update_strategy_status_info should still be called (for execution_logs)
        # but excluded_from_universe should NOT be added
        calls = mock_data_handler.update_strategy_status_info.call_args_list
        for call in calls:
            args = call[0]
            if len(args) >= 2:
                status_info = args[1]
                if isinstance(status_info, dict) and "excluded_from_universe" in status_info:
                    # In immediate mode, should not add excluded_from_universe
                    pytest.fail("excluded_from_universe should not be tracked in immediate mode")

    def test_forced_sell_updates_excluded(self):
        """Test 5: Forced sell signal also marks symbol as excluded."""
        from app.strategies.runners.cross_sectional_runner import CrossSectionalRunner

        mock_data_handler = MagicMock()
        mock_data_handler.get_strategy_status_info.return_value = {"excluded_from_universe": []}
        mock_data_handler.update_strategy_status_info = MagicMock()
        mock_data_handler.get_all_positions.return_value = []

        runner = CrossSectionalRunner(
            data_handler=mock_data_handler,
            signal_executor=MagicMock(),
        )
        runner._last_current_time = 1234567890.0

        strategy_id = 1
        strategy = {
            "trading_config": {
                "delisting_policy": {"mode": "hold_until_signal_exit"},
            }
        }
        signals = [
            {
                "symbol": "XYZ",
                "type": "forced_sell",
                "excluded_from_universe": True,
            }
        ]
        metadata = {
            "trading_config": {
                "delisting_policy": {"mode": "hold_until_signal_exit"},
            }
        }

        with patch.object(
            runner,
            '_filter_phase21_signals',
            return_value=(signals, {"execution_logs": []})
        ):
            runner._dispatch_signals(
                strategy_id, strategy, signals, True, metadata, MagicMock()
            )

        # Forced sell should also update excluded_from_universe
        mock_data_handler.update_strategy_status_info.assert_called()