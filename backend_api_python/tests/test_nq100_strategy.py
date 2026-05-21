"""
Tests for NQ100 strategy inheritance and dynamic universe binding (STRAT-01).

Phase 24 plan 01: Three-layer inheritance structure and PIT integration.
"""

import pytest
from datetime import date
from typing import List, Dict, Any
from unittest.mock import MagicMock, patch


class TestStrategyInheritance:
    """D-01: Three-layer inheritance chain tests."""

    def test_dynamic_strategy_inherits_from_cross_sectional(self):
        """Verify DynamicCrossSectionalStrategy inherits from CrossSectionalStrategy."""
        from app.strategies.dynamic_cross_sectional import DynamicCrossSectionalStrategy
        from app.strategies.cross_sectional import CrossSectionalStrategy

        assert DynamicCrossSectionalStrategy.__bases__
        # First base should be CrossSectionalStrategy
        assert CrossSectionalStrategy in DynamicCrossSectionalStrategy.__bases__

    def test_nq100_strategy_inherits_dynamic(self):
        """Verify NQ100Strategy inherits from DynamicCrossSectionalStrategy."""
        from app.strategies.nq100_strategy import NQ100Strategy
        from app.strategies.dynamic_cross_sectional import DynamicCrossSectionalStrategy

        assert NQ100Strategy.__bases__
        # First base should be DynamicCrossSectionalStrategy
        assert DynamicCrossSectionalStrategy in NQ100Strategy.__bases__


class TestDynamicUniverseBinding:
    """D-02/D-05: Dynamic universe interface contract tests."""

    def test_dynamic_strategy_requires_get_universe_list(self):
        """D-02: Verify get_universe_list() raises NotImplementedError if not implemented by subclass."""
        from app.strategies.dynamic_cross_sectional import DynamicCrossSectionalStrategy

        # Cannot instantiate abstract class directly that raises NotImplementedError
        # We create a subclass that doesn't implement get_universe_list
        class IncompleteStrategy(DynamicCrossSectionalStrategy):
            pass

        strategy = IncompleteStrategy()
        with pytest.raises(NotImplementedError) as exc_info:
            strategy.get_universe_list(date(2024, 1, 1))

        assert "Subclass must implement" in str(exc_info.value)

    def test_dynamic_strategy_get_data_request_calls_universe_list(self):
        """D-05: Verify get_data_request() calls get_universe_list() when universe field exists."""
        from app.strategies.dynamic_cross_sectional import DynamicCrossSectionalStrategy

        # Create a mock subclass that implements get_universe_list
        class MockDynamicStrategy(DynamicCrossSectionalStrategy):
            def get_universe_list(self, as_of_date: date) -> List[str]:
                return ["AAPL", "MSFT", "GOOGL"]

        strategy = MockDynamicStrategy()
        strategy_dict = {
            "trading_config": {
                "universe": "NQ100",
                "timeframe": "1D",
            },
            "_market_category": "USStock",
        }

        data_request = strategy.get_data_request(
            strategy_id=1,
            strategy=strategy_dict,
            current_time=0.0,
        )

        assert data_request["symbol_list"] == ["AAPL", "MSFT", "GOOGL"]

    def test_static_fallback_when_no_universe(self):
        """Backward compatibility: static symbol_list when no universe field."""
        from app.strategies.dynamic_cross_sectional import DynamicCrossSectionalStrategy

        class MockDynamicStrategy(DynamicCrossSectionalStrategy):
            def get_universe_list(self, as_of_date: date) -> List[str]:
                return ["DYNAMIC"]

        strategy = MockDynamicStrategy()
        strategy_dict = {
            "trading_config": {
                "symbol_list": ["AAPL", "MSFT"],
                "timeframe": "1D",
            },
            "_market_category": "USStock",
        }

        data_request = strategy.get_data_request(
            strategy_id=1,
            strategy=strategy_dict,
            current_time=0.0,
        )

        # Should use static symbol_list when no universe field
        assert data_request["symbol_list"] == ["AAPL", "MSFT"]


class TestConfigValidation:
    """D-04: Mutual exclusion validation tests."""

    def test_mutual_exclusion_symbol_list_and_universe(self):
        """D-04: Both symbol_list and universe configured should raise ValueError."""
        from app.strategies.dynamic_cross_sectional import DynamicCrossSectionalStrategy

        class MockDynamicStrategy(DynamicCrossSectionalStrategy):
            def get_universe_list(self, as_of_date: date) -> List[str]:
                return ["AAPL"]

        strategy = MockDynamicStrategy()
        strategy_dict = {
            "trading_config": {
                "symbol_list": ["AAPL", "MSFT"],
                "universe": "NQ100",
                "timeframe": "1D",
            },
            "_market_category": "USStock",
        }

        with pytest.raises(ValueError) as exc_info:
            strategy.get_data_request(
                strategy_id=1,
                strategy=strategy_dict,
                current_time=0.0,
            )

        assert "mutually exclusive" in str(exc_info.value)


class TestNQ100PITIntegration:
    """D-03: NQ100 PIT API integration tests."""

    def test_nq100_get_universe_list_calls_pit_api(self):
        """D-03: Verify NQ100Strategy.get_universe_list() calls get_constituents_as_of()."""
        from app.strategies.nq100_strategy import NQ100Strategy

        strategy = NQ100Strategy()
        test_date = date(2024, 3, 15)

        with patch(
            "app.strategies.nq100_strategy.get_constituents_as_of",
            return_value=["AAPL", "GOOGL", "MSFT"],  # already sorted from PIT API
        ) as mock_pit:
            result = strategy.get_universe_list(test_date)

            mock_pit.assert_called_once_with(test_date)
            assert result == ["AAPL", "GOOGL", "MSFT"]  # sorted from PIT API

    def test_nq100_get_universe_list_empty_result(self):
        """Handle empty PIT result gracefully."""
        from app.strategies.nq100_strategy import NQ100Strategy

        strategy = NQ100Strategy()
        test_date = date(2024, 1, 1)

        with patch(
            "app.strategies.nq100_strategy.get_constituents_as_of",
            return_value=[],
        ):
            result = strategy.get_universe_list(test_date)

            assert result == []

    def test_nq100_get_universe_list_db_error_handling(self):
        """Handle database errors gracefully - returns empty list."""
        from app.strategies.nq100_strategy import NQ100Strategy

        strategy = NQ100Strategy()
        test_date = date(2024, 1, 1)

        with patch(
            "app.strategies.nq100_strategy.get_constituents_as_of",
            side_effect=Exception("DB connection failed"),
        ):
            result = strategy.get_universe_list(test_date)

            # Should handle error gracefully, return empty list
            assert result == []


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


class TestExcludedFromUniverse:
    """Task 2: Test Strategy-layer excluded_from_universe tracking (STRAT-02)."""

    def test_get_removed_symbols_helper_exists(self):
        """Test that NQ100Strategy has _get_removed_symbols helper method."""
        from app.strategies.nq100_strategy import NQ100Strategy

        strategy = NQ100Strategy()
        assert hasattr(strategy, '_get_removed_symbols'), \
            "NQ100Strategy should have _get_removed_symbols helper method"

    def test_removed_symbols_query_correct(self):
        """Test 6: _get_removed_symbols returns correct set."""
        from app.strategies.nq100_strategy import NQ100Strategy

        strategy = NQ100Strategy()

        # Mock database to return removed symbols
        mock_removed = [("XYZ",), ("ABC",)]
        mock_db, _, _ = _make_mock_db_connection(fetchall_result=mock_removed)

        with patch("app.strategies.nq100_strategy.db", mock_db):
            result = strategy._get_removed_symbols(date(2024, 3, 18))

        # Should return uppercase set
        assert isinstance(result, set)
        assert "XYZ" in result
        assert "ABC" in result

    def test_no_removed_symbols_empty_result(self):
        """Test 5: Query returns empty set when no removed symbols."""
        from app.strategies.nq100_strategy import NQ100Strategy

        strategy = NQ100Strategy()

        mock_db, _, _ = _make_mock_db_connection(fetchall_result=[])

        with patch("app.strategies.nq100_strategy.db", mock_db):
            result = strategy._get_removed_symbols(date(2024, 3, 18))

        assert result == set()

    def test_strategy_excluded_from_universe_tracking(self):
        """Test 1: Removed stock with position appears in ranking pool for hold_until_signal_exit."""
        from app.strategies.nq100_strategy import NQ100Strategy

        strategy = NQ100Strategy()

        # Mock get_constituents_as_of to return current universe (excludes XYZ)
        with patch("app.strategies.nq100_strategy.get_constituents_as_of", return_value=["AAPL", "ABC"]):
            # Mock _get_removed_symbols to return XYZ (removed)
            with patch.object(strategy, '_get_removed_symbols', return_value={"XYZ"}):
                # Mock get_data_request context
                strategy_obj = {
                    "trading_config": {
                        "universe": "NQ100",
                        "delisting_policy": {"mode": "hold_until_signal_exit"},
                        "_existing_positions": [{"symbol": "XYZ"}],
                    }
                }

                request = strategy.get_data_request(1, strategy_obj, 1234567890.0)

                # XYZ should appear in symbol_list because it has position and is removed
                assert "XYZ" in request["symbol_list"]

    def test_strategy_marks_excluded_in_metadata(self):
        """Test 2: get_signals marks removed stock with excluded_from_universe=True."""
        from app.strategies.nq100_strategy import NQ100Strategy
        from app.strategies.dynamic_cross_sectional import DynamicCrossSectionalStrategy

        strategy = NQ100Strategy()

        # Mock _get_removed_symbols
        with patch.object(strategy, '_get_removed_symbols', return_value={"XYZ"}):
            # Mock parent get_signals to return signals including XYZ
            mock_signals = [
                {"symbol": "AAPL", "type": "open_long"},
                {"symbol": "XYZ", "type": "close_long"},
            ]

            # Patch the parent class's get_signals method
            original_get_signals = DynamicCrossSectionalStrategy.get_signals
            DynamicCrossSectionalStrategy.get_signals = lambda self, ctx: (mock_signals, True, True, {})

            try:
                ctx = {
                    "trading_config": {
                        "delisting_policy": {"mode": "hold_until_signal_exit"},
                    }
                }

                signals, keep_running, update_rebalance, metadata = strategy.get_signals(ctx)

                # XYZ should have excluded_from_universe=True
                xyz_signal = next((s for s in signals if s["symbol"] == "XYZ"), None)
                assert xyz_signal is not None
                assert xyz_signal.get("excluded_from_universe") == True

                # AAPL should NOT have excluded_from_universe
                aapl_signal = next((s for s in signals if s["symbol"] == "AAPL"), None)
                assert aapl_signal is not None
                assert aapl_signal.get("excluded_from_universe", False) == False
            finally:
                DynamicCrossSectionalStrategy.get_signals = original_get_signals

    def test_immediate_mode_excludes_from_ranking(self):
        """Test 3: immediate mode excludes removed stock from ranking pool."""
        from app.strategies.nq100_strategy import NQ100Strategy

        strategy = NQ100Strategy()

        with patch("app.strategies.nq100_strategy.get_constituents_as_of", return_value=["AAPL"]):
            strategy_obj = {
                "trading_config": {
                    "universe": "NQ100",
                    "delisting_policy": {"mode": "immediate"},
                }
            }

            request = strategy.get_data_request(1, strategy_obj, 1234567890.0)

            # In immediate mode, only current universe constituents
            assert request["symbol_list"] == ["AAPL"]

    def test_delayed_mode_excludes_from_ranking(self):
        """Test 4: delayed mode excludes removed stock from ranking pool (Runner handles forced_sell)."""
        from app.strategies.nq100_strategy import NQ100Strategy

        strategy = NQ100Strategy()

        with patch("app.strategies.nq100_strategy.get_constituents_as_of", return_value=["AAPL"]):
            strategy_obj = {
                "trading_config": {
                    "universe": "NQ100",
                    "delisting_policy": {"mode": "delayed", "months": 3},
                }
            }

            request = strategy.get_data_request(1, strategy_obj, 1234567890.0)

            # In delayed mode, only current universe constituents (Runner handles timing)
            assert request["symbol_list"] == ["AAPL"]

    def test_hold_mode_without_position_excludes(self):
        """Removed stock without position does NOT appear in ranking pool."""
        from app.strategies.nq100_strategy import NQ100Strategy

        strategy = NQ100Strategy()

        with patch("app.strategies.nq100_strategy.get_constituents_as_of", return_value=["AAPL"]):
            with patch.object(strategy, '_get_removed_symbols', return_value={"XYZ"}):
                # No position for XYZ
                strategy_obj = {
                    "trading_config": {
                        "universe": "NQ100",
                        "delisting_policy": {"mode": "hold_until_signal_exit"},
                        "_existing_positions": [],  # No XYZ position
                    }
                }

                request = strategy.get_data_request(1, strategy_obj, 1234567890.0)

                # XYZ should NOT appear in symbol_list because it has no position
                assert "XYZ" not in request["symbol_list"]

    def test_hold_mode_reads_excluded_from_status_info(self):
        """Strategy reads _excluded_from_universe from trading_config to filter ranking pool."""
        from app.strategies.nq100_strategy import NQ100Strategy

        strategy = NQ100Strategy()

        # Mock get_constituents_as_of and _get_removed_symbols
        with patch("app.strategies.nq100_strategy.get_constituents_as_of", return_value=["AAPL", "XYZ"]):
            with patch.object(strategy, '_get_removed_symbols', return_value=set()):
                strategy_obj = {
                    "trading_config": {
                        "universe": "NQ100",
                        "delisting_policy": {"mode": "hold_until_signal_exit"},
                        "_excluded_from_universe": ["XYZ"],  # XYZ already sold and excluded
                    }
                }

                request = strategy.get_data_request(1, strategy_obj, 1234567890.0)

                # XYZ should NOT appear in symbol_list because it's already excluded
                assert "XYZ" not in request["symbol_list"]