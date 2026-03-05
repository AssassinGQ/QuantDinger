"""
Order quantity normalization for different markets.

Each market has different lot size rules:
- US stocks: 1 share minimum, integer quantities
- HK stocks (HShare): board lot varies per stock (e.g. HSBC=400, JD=50)
- Forex: reserved for future MT5 integration
"""

from abc import ABC, abstractmethod
from typing import Tuple


class OrderNormalizer(ABC):
    """Base class for order quantity normalization."""

    @abstractmethod
    def normalize(self, raw_qty: float, symbol: str) -> int:
        """Normalize a raw float quantity to a valid order size.

        Called by signal_executor after calculating the order amount.
        """

    @abstractmethod
    def check(self, qty: int, symbol: str) -> Tuple[bool, str]:
        """Validate that a quantity is acceptable for placing an order.

        Called by IBKRClient right before sending the order.
        Returns (ok, reason).
        """


from app.services.ibkr_trading.order_normalizer.us_stock import USStockNormalizer
from app.services.ibkr_trading.order_normalizer.hk_share import HShareNormalizer
from app.services.ibkr_trading.order_normalizer.forex import ForexNormalizer


def get_normalizer(market_category: str) -> OrderNormalizer:
    """Factory: return the appropriate normalizer for a market category."""
    cat = (market_category or "").strip()
    if cat == "HShare":
        return HShareNormalizer()
    if cat == "Forex":
        return ForexNormalizer()
    return USStockNormalizer()
