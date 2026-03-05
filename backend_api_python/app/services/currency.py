"""
Currency conversion service for normalizing multi-currency portfolio values to HKD.

Uses Tiingo Forex API (same data source as the Forex market) with 5-minute caching.
Falls back to hardcoded rates if API is unavailable.
"""

import threading
import time
from typing import Dict, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

BASE_CURRENCY = "HKD"

MARKET_CATEGORY_CURRENCY = {
    "USStock": "USD",
    "Forex": "USD",
    "Crypto": "USD",
    "HShare": "HKD",
    "AShare": "CNY",
    "Futures": "CNY",
}

# Fallback: 1 unit of X = ? HKD
FALLBACK_RATES_TO_HKD = {
    "USD": 7.80,
    "CNY": 1.075,   # ~7.80/7.25
}

_rate_cache: Dict[str, tuple] = {}  # currency -> (rate_to_hkd, expiry_ts)
_rate_cache_lock = threading.Lock()
_RATE_CACHE_TTL = 300  # 5 minutes


def _fetch_rate_to_hkd(currency: str) -> Optional[float]:
    """Fetch rate: 1 unit of `currency` = ? HKD, via Tiingo Forex."""
    try:
        from app.data_sources import DataSourceFactory
        # Tiingo has USDHKD (1 USD = X HKD)
        if currency == "USD":
            ticker = DataSourceFactory.get_ticker("Forex", "USDHKD")
            if ticker:
                rate = float(ticker.get("last") or ticker.get("close") or 0)
                if rate > 0:
                    return rate  # 1 USD = rate HKD
        elif currency == "CNY":
            # CNY->HKD: get USDCNH and USDHKD, compute CNY/HKD = USDHKD / USDCNH
            ticker_hkd = DataSourceFactory.get_ticker("Forex", "USDHKD")
            ticker_cnh = DataSourceFactory.get_ticker("Forex", "USDCNH")
            if ticker_hkd and ticker_cnh:
                hkd_rate = float(ticker_hkd.get("last") or ticker_hkd.get("close") or 0)
                cnh_rate = float(ticker_cnh.get("last") or ticker_cnh.get("close") or 0)
                if hkd_rate > 0 and cnh_rate > 0:
                    return hkd_rate / cnh_rate  # 1 CNY = ? HKD
    except Exception as e:
        logger.debug("Tiingo rate fetch for %s->HKD failed: %s", currency, e)
    return None


def get_rate_to_hkd(currency: str) -> float:
    """Get conversion rate: 1 unit of currency = ? HKD. Cached for 5 minutes."""
    currency = currency.upper()
    if currency == "HKD":
        return 1.0

    now = time.time()
    with _rate_cache_lock:
        cached = _rate_cache.get(currency)
        if cached and cached[1] > now:
            return cached[0]

    rate = _fetch_rate_to_hkd(currency)
    if rate is None:
        rate = FALLBACK_RATES_TO_HKD.get(currency)
        if rate is None:
            logger.warning("No rate available for %s->HKD, treating as 1:1", currency)
            rate = 1.0

    with _rate_cache_lock:
        _rate_cache[currency] = (rate, now + _RATE_CACHE_TTL)

    return rate


def convert_to_base(amount: float, market_category: str) -> float:
    """Convert an amount from market's native currency to HKD."""
    currency = MARKET_CATEGORY_CURRENCY.get(market_category, "USD")
    return amount * get_rate_to_hkd(currency)


def get_currency_for_market(market_category: str) -> str:
    """Return the native currency code for a given market category."""
    return MARKET_CATEGORY_CURRENCY.get(market_category, "USD")
