"""
NQ100 strategy: specific implementation with PIT universe binding.

D-03: Implements get_universe_list() by calling Phase 19's
get_constituents_as_of(as_of_date) to return NQ100 constituents
as of a given date.

D-01: Inherits from DynamicCrossSectionalStrategy, following
three-layer inheritance structure:
    CrossSectionalStrategy -> DynamicCrossSectionalStrategy -> NQ100Strategy

D-07/D-09: STRAT-02 hold_until_signal_exit mode:
- Removed stocks with positions remain in ranking pool
- Signals for removed stocks marked with excluded_from_universe=True
- After sell signal executed, stock permanently excluded from universe
"""

from datetime import date
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.universe_nq100_service import get_constituents_as_of
from app.strategies.dynamic_cross_sectional import DynamicCrossSectionalStrategy
from app.utils import db
from app.utils.logger import get_logger

logger = get_logger(__name__)

__all__ = ["NQ100Strategy"]


class NQ100Strategy(DynamicCrossSectionalStrategy):
    """
    NQ100-specific strategy with PIT universe binding.

    D-01: Inherits from DynamicCrossSectionalStrategy (intermediate layer).

    D-03: Implements get_universe_list() to call Phase 19 PIT API
    get_constituents_as_of(as_of_date) which returns the NQ100
    constituents as of the given date from qd_nq100_membership table.

    D-07/D-09: STRAT-02 hold_until_signal_exit mode:
    - Removed stocks with positions remain in ranking pool (Strategy adjusts universe)
    - Signals for removed stocks marked with excluded_from_universe=True
    - Runner updates status_info after sell execution to permanently exclude

    Error handling: Returns empty list on database errors or empty
    results to avoid crashing strategy execution.
    """

    def _get_removed_symbols(self, as_of_date: date) -> Set[str]:
        """
        D-07: Query qd_nq100_change_events for symbols removed with effective_date <= as_of_date.

        Used for hold_until_signal_exit mode to determine which stocks have been
        removed from the universe and should be tracked for exclusion.

        Args:
            as_of_date: The date to query removed symbols for.

        Returns:
            Set of uppercase symbols that have been removed from NQ100 index
            with effective_date <= as_of_date.
        """
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT symbol
                FROM qd_nq100_change_events
                WHERE event_type = 'remove' AND effective_date <= %s
                """,
                (as_of_date,)
            )
            rows = cursor.fetchall()
        return {str(row[0]).upper() for row in rows}

    def get_universe_list(self, as_of_date: date) -> List[str]:
        """
        D-03: Return NQ100 constituents as of the given date.

        Calls Phase 19's get_constituents_as_of(as_of_date) to retrieve
        the point-in-time NQ100 constituent list from qd_nq100_membership.

        Args:
            as_of_date: The date to query NQ100 constituents for.

        Returns:
            Sorted list of NQ100 constituent symbols on as_of_date.
            Empty list if database query fails or returns no results.

        Note:
            Exceptions are caught and logged; returns empty list to
            avoid crashing strategy execution. This is intentional
            graceful degradation for production resilience.
        """
        try:
            constituents = get_constituents_as_of(as_of_date)
            # PIT API already returns sorted unique symbols
            return constituents
        except Exception as exc:
            logger.warning(
                "NQ100Strategy.get_universe_list failed for date %s: %s",
                as_of_date,
                exc,
            )
            # Return empty list gracefully - don't crash strategy
            return []

    def get_data_request(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        current_time: float,
    ) -> Dict[str, Any]:
        """
        D-07: Override get_data_request for hold_until_signal_exit mode.

        For immediate/delayed modes: Returns current universe constituents.
        For hold_until_signal_exit mode:
        - Includes removed stocks that still have positions in ranking pool
        - Excludes stocks that have been marked as excluded_from_universe

        Args:
            strategy_id: Strategy ID.
            strategy: Strategy dict containing trading_config.
            current_time: Current timestamp.

        Returns:
            DataRequest dict with symbol_list adjusted for delisting mode.
        """
        trading_config = strategy.get("trading_config") or {}
        delisting_policy = trading_config.get("delisting_policy", {"mode": "immediate"})
        mode = delisting_policy.get("mode", "immediate")

        # Get current universe from PIT API (base symbol_list)
        symbol_list = self.get_universe_list(date.today())

        if mode == "hold_until_signal_exit":
            # D-07: Include removed stocks that still have positions
            removed_symbols = self._get_removed_symbols(date.today())

            # Get existing positions from trading_config (passed by Runner)
            existing_positions = trading_config.get("_existing_positions", [])
            position_symbols = {p.get("symbol") for p in existing_positions if p.get("symbol")}
            position_symbols = {s.upper() for s in position_symbols}

            # Add removed stocks with positions to ranking pool
            symbols_to_add = removed_symbols & position_symbols
            if symbols_to_add:
                symbol_list = list(set(symbol_list) | symbols_to_add)
                symbol_list = sorted(symbol_list)

            # D-09: Exclude symbols already marked as excluded (after sell execution)
            excluded_symbols = set(trading_config.get("_excluded_from_universe", []))
            if excluded_symbols:
                symbol_list = [s for s in symbol_list if s.upper() not in excluded_symbols]

        # Build request dict (reusing parent class logic for other fields)
        timeframe = trading_config.get("timeframe", "1H")
        rebalance_frequency = trading_config.get("rebalance_frequency", "daily")
        market_category = strategy.get("_market_category", "USStock")

        return {
            "symbol_list": symbol_list,
            "timeframe": timeframe,
            "trading_config": trading_config,
            "need_macro": self.need_macro_info(),
            "rebalance_frequency": rebalance_frequency,
            "history_limit": 200,
            "market_category": market_category,
        }

    def get_signals(
        self,
        ctx: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[bool], Optional[Dict[str, Any]]]:
        """
        D-09: Override get_signals to mark excluded_from_universe for removed stocks.

        For hold_until_signal_exit mode, signals for removed stocks are marked
        with excluded_from_universe=True so Runner can track them after sell execution.

        Args:
            ctx: Input context from data_handler.

        Returns:
            Tuple of (signals, keep_running, update_rebalance, metadata).
        """
        trading_config = ctx.get("trading_config", {})
        delisting_policy = trading_config.get("delisting_policy", {"mode": "immediate"})
        mode = delisting_policy.get("mode", "immediate")

        # Call parent class to generate signals
        signals, keep_running, update_rebalance, metadata = super().get_signals(ctx)

        if mode == "hold_until_signal_exit":
            # D-09: Mark signals for removed stocks as excluded_from_universe
            removed_symbols = self._get_removed_symbols(date.today())
            for signal in signals:
                sym = signal.get("symbol", "").upper()
                if sym in removed_symbols:
                    signal["excluded_from_universe"] = True

        return signals, keep_running, update_rebalance, metadata