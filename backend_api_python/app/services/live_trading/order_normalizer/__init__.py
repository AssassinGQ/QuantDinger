"""
Order quantity normalization for different markets.

Each market has different lot size rules:
- US stocks: 1 share minimum, integer quantities
- HK stocks (HShare): board lot varies per stock (e.g. HSBC=400, JD=50)
- Forex: integer quantities (oz for metals, units for pairs)
- Crypto: pass-through (exchange handles precision)
"""

from abc import ABC, abstractmethod
from typing import Tuple


class OrderNormalizer(ABC):
    """Base class for order quantity normalization."""

    @abstractmethod
    def normalize(self, raw_qty: float, symbol: str) -> float:
        """Normalize a raw float quantity to a valid order size."""

    @abstractmethod
    def check(self, qty: float, symbol: str) -> Tuple[bool, str]:
        """Validate that a quantity is acceptable for placing an order.

        Returns (ok, reason).
        """


class CryptoNormalizer(OrderNormalizer):
    """Pass-through for crypto — exchanges enforce their own precision."""

    def normalize(self, raw_qty: float, symbol: str) -> float:
        return raw_qty

    def check(self, qty: float, symbol: str) -> Tuple[bool, str]:
        if qty <= 0:
            return False, f"Quantity must be positive, got {qty}"
        return True, ""


def get_normalizer(market_category: str) -> OrderNormalizer:
    """Factory: return the appropriate normalizer for a market category."""
    from app.services.live_trading.order_normalizer.us_stock import USStockNormalizer
    from app.services.live_trading.order_normalizer.hk_share import HShareNormalizer
    from app.services.live_trading.order_normalizer.forex import ForexNormalizer

    cat = (market_category or "").strip()
    if cat == "HShare":
        return HShareNormalizer()
    if cat == "Forex":
        return ForexNormalizer()
    if cat == "Crypto":
        return CryptoNormalizer()
    return USStockNormalizer()
