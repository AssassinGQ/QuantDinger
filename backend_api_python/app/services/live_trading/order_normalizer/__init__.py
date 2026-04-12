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


class MarketPreNormalizer(ABC):
    """Base class for market-layer quantity pre-normalization (before pre-check)."""

    @abstractmethod
    def pre_normalize(self, raw_qty: float, symbol: str) -> float:
        """Normalize a raw float quantity to a valid order size."""

    @abstractmethod
    def pre_check(self, qty: float, symbol: str) -> Tuple[bool, str]:
        """Validate that a quantity is acceptable for placing an order.

        Returns (ok, reason).
        """


class CryptoPreNormalizer(MarketPreNormalizer):
    """Pass-through for crypto — exchanges enforce their own precision."""

    def pre_normalize(self, raw_qty: float, symbol: str) -> float:
        return raw_qty

    def pre_check(self, qty: float, symbol: str) -> Tuple[bool, str]:
        if qty <= 0:
            return False, f"Quantity must be positive, got {qty}"
        return True, ""


def get_market_pre_normalizer(market_category: str) -> MarketPreNormalizer:
    """Factory: return the appropriate pre-normalizer for a market category."""
    from app.services.live_trading.order_normalizer.us_stock import USStockPreNormalizer
    from app.services.live_trading.order_normalizer.hk_share import HSharePreNormalizer
    from app.services.live_trading.order_normalizer.forex import ForexPreNormalizer

    cat = (market_category or "").strip()
    if cat == "HShare":
        return HSharePreNormalizer()
    if cat == "Forex":
        return ForexPreNormalizer()
    if cat == "Metals":
        # CMDTY precious metals on SMART — lot rules from IB ContractDetails (same pass-through as Forex).
        return ForexPreNormalizer()
    if cat == "Crypto":
        return CryptoPreNormalizer()
    return USStockPreNormalizer()
