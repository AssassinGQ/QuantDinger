"""
Dynamic cross-sectional strategy: intermediate layer providing dynamic universe binding.

D-01: Three-layer inheritance structure:
    CrossSectionalStrategy -> DynamicCrossSectionalStrategy -> NQ100Strategy (or other universe subclasses)

D-02: Interface contract:
    Subclass must implement get_universe_list(as_of_date: date) -> List[str]
    to return constituents as of the given date.

D-04: Mutual exclusion:
    symbol_list and universe in trading_config are mutually exclusive.

D-05: Dynamic binding:
    get_data_request() calls get_universe_list() when universe field exists,
    fallback to static symbol_list when universe field not present.
"""

from datetime import date
from typing import Any, Dict, List

from app.strategies.cross_sectional import CrossSectionalStrategy
from app.utils.logger import get_logger

logger = get_logger(__name__)

__all__ = ["DynamicCrossSectionalStrategy"]


class DynamicCrossSectionalStrategy(CrossSectionalStrategy):
    """
    Intermediate strategy layer providing dynamic universe binding interface.

    D-01: Inherits from CrossSectionalStrategy, provides get_universe_list()
    interface that subclasses must implement.

    D-02: Subclasses (e.g., NQ100Strategy, SP100Strategy) must implement
    get_universe_list() to return the universe constituents as of a given date.

    D-04/D-05: Override get_data_request() to:
    - Validate mutual exclusion of symbol_list and universe
    - Call get_universe_list() when universe field is present
    - Fallback to static symbol_list for backward compatibility
    """

    def get_universe_list(self, as_of_date: date) -> List[str]:
        """
        D-02: Return the universe constituent list as of the given date.

        Subclass must implement this method to provide dynamic universe binding.
        For example, NQ100Strategy calls get_constituents_as_of(as_of_date)
        from Phase 19 PIT API.

        Args:
            as_of_date: The date to query constituents for.

        Returns:
            Sorted list of symbols that were constituents on as_of_date.

        Raises:
            NotImplementedError: Always, until subclass implements this method.
        """
        raise NotImplementedError("Subclass must implement get_universe_list()")

    def get_data_request(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        current_time: float,
    ) -> Dict[str, Any]:
        """
        D-05: Override to use dynamic universe binding when configured.

        Behavior:
        1. D-04: Check mutual exclusion - both symbol_list AND universe configured
           raises ValueError.
        2. If trading_config has "universe" field -> call self.get_universe_list()
           to get dynamic symbol list.
        3. Else -> use static trading_config.get("symbol_list", []) for backward
           compatibility with non-dynamic subclasses.

        Args:
            strategy_id: Strategy ID.
            strategy: Strategy dict containing trading_config.
            current_time: Current timestamp.

        Returns:
            DataRequest dict with symbol_list, timeframe, trading_config, etc.

        Raises:
            ValueError: If both symbol_list and universe are configured (D-04).
        """
        trading_config = strategy.get("trading_config") or {}

        # D-04: Mutual exclusion check
        has_symbol_list = trading_config.get("symbol_list") is not None and len(trading_config.get("symbol_list", [])) > 0
        has_universe = trading_config.get("universe") is not None

        if has_symbol_list and has_universe:
            raise ValueError("symbol_list and universe are mutually exclusive")

        # D-05: Dynamic universe binding or static fallback
        if has_universe:
            # Call subclass implementation
            symbol_list = self.get_universe_list(date.today())
        else:
            # Backward compatibility: use static symbol_list
            symbol_list = trading_config.get("symbol_list", [])

        timeframe = trading_config.get("timeframe", "1H")
        rebalance_frequency = trading_config.get("rebalance_frequency", "daily")
        market_category = strategy.get("_market_category", "Crypto")

        return {
            "symbol_list": symbol_list,
            "timeframe": timeframe,
            "trading_config": trading_config,
            "need_macro": self.need_macro_info(),
            "rebalance_frequency": rebalance_frequency,
            "history_limit": 200,
            "market_category": market_category,
        }