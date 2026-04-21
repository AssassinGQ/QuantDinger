"""
提供价格获取和缓存服务，从策略执行器中解耦出来。
"""
import os
import threading
import time
from typing import Any, Optional

from app.data_sources import DataSourceFactory
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PriceFetcher:
    """价格获取器，包含简单的内存缓存机制。"""

    def __init__(self):
        # Local-only lightweight in-memory price cache (symbol -> (price, expiry_ts)).
        # This replaces the old Redis-based PriceCache for local deployments.
        self._price_cache = {}
        self._ticker_meta_cache = {}
        self._price_cache_lock = threading.Lock()
        # Default to 10s to match the unified tick cadence.
        self._price_cache_ttl_sec = int(os.getenv("PRICE_CACHE_TTL_SEC", "10"))

    def fetch_current_price(
        self,
        exchange: Any,
        symbol: str,
        market_type: Optional[str] = None,
        market_category: str = "Crypto",
    ) -> Optional[float]:
        """获取当前价格 (根据 market_category 选择正确的数据源)

        Args:
            exchange: 交易所实例（信号模式下为 None）
            symbol: 交易对/代码
            market_type: 交易类型 (swap/spot)
            market_category: 市场类型 (Crypto, USStock, Forex, Futures, AShare, HShare)
        """
        # Local in-memory cache first
        cache_key = f"{market_category}:{(symbol or '').strip().upper()}"
        if cache_key and self._price_cache_ttl_sec > 0:
            now = time.time()
            try:
                with self._price_cache_lock:
                    item = self._price_cache.get(cache_key)
                    if item:
                        price, expiry = item
                        if expiry > now:
                            return float(price)
                        # expired
                        del self._price_cache[cache_key]
            except Exception:
                pass

        try:
            # 根据 market_category 选择正确的数据源
            ticker = DataSourceFactory.get_ticker(market_category, symbol)
            if ticker:
                price = float(ticker.get("last") or ticker.get("close") or 0)
                if price > 0:
                    if cache_key and self._price_cache_ttl_sec > 0:
                        try:
                            with self._price_cache_lock:
                                exp = time.time() + self._price_cache_ttl_sec
                                self._price_cache[cache_key] = (float(price), exp)
                                self._ticker_meta_cache[cache_key] = (dict(ticker), exp)
                        except Exception:
                            pass
                    return price
        except Exception as e:
            logger.warning(
                "Failed to fetch price for %s:%s: %s",
                market_category,
                symbol,
                e,
            )

    def get_last_ticker_meta(self, symbol: str, market_category: str = "Crypto") -> dict:
        """读取最近一次 fetch_current_price 成功缓存的 ticker 元数据。"""
        cache_key = f"{market_category}:{(symbol or '').strip().upper()}"
        if not cache_key or self._price_cache_ttl_sec <= 0:
            return {}
        now = time.time()
        try:
            with self._price_cache_lock:
                item = self._ticker_meta_cache.get(cache_key)
                if not item:
                    return {}
                meta, expiry = item
                if expiry > now and isinstance(meta, dict):
                    return dict(meta)
                del self._ticker_meta_cache[cache_key]
        except Exception:
            return {}
        return {}

_price_fetcher_instance = None


def get_price_fetcher() -> PriceFetcher:
    """获取 PriceFetcher 的全局单例"""
    global _price_fetcher_instance
    if _price_fetcher_instance is None:
        _price_fetcher_instance = PriceFetcher()
    return _price_fetcher_instance