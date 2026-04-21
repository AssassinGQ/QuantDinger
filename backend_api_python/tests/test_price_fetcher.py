import time
import pytest
from unittest.mock import patch, MagicMock

from app.services.price_fetcher import PriceFetcher, get_price_fetcher


class TestPriceFetcher:
    def test_fetch_current_price_success(self):
        fetcher = PriceFetcher()
        
        with patch("app.services.price_fetcher.DataSourceFactory.get_ticker") as mock_ticker:
            mock_ticker.return_value = {"last": 100.0}
            
            price = fetcher.fetch_current_price(None, "BTC/USDT", market_category="Crypto")
            
            assert price == 100.0
            mock_ticker.assert_called_once_with("Crypto", "BTC/USDT")
            
            # Check if it was cached
            assert "Crypto:BTC/USDT" in fetcher._price_cache

    def test_fetch_current_price_uses_cache(self):
        fetcher = PriceFetcher()
        fetcher._price_cache_ttl_sec = 10
        
        # Pre-populate cache
        cache_key = "Crypto:ETH/USDT"
        fetcher._price_cache[cache_key] = (2000.0, time.time() + 10)
        
        with patch("app.services.price_fetcher.DataSourceFactory.get_ticker") as mock_ticker:
            price = fetcher.fetch_current_price(None, "ETH/USDT", market_category="Crypto")
            
            # Should return cached price without calling get_ticker
            assert price == 2000.0
            mock_ticker.assert_not_called()

    def test_fetch_current_price_cache_expired(self):
        fetcher = PriceFetcher()
        fetcher._price_cache_ttl_sec = 10
        
        # Pre-populate expired cache
        cache_key = "Crypto:BNB/USDT"
        fetcher._price_cache[cache_key] = (300.0, time.time() - 10)  # Expired
        
        with patch("app.services.price_fetcher.DataSourceFactory.get_ticker") as mock_ticker:
            mock_ticker.return_value = {"last": 310.0}
            
            price = fetcher.fetch_current_price(None, "BNB/USDT", market_category="Crypto")
            
            # Should fetch new price and update cache
            assert price == 310.0
            mock_ticker.assert_called_once()
            
            cached_val, expiry = fetcher._price_cache[cache_key]
            assert cached_val == 310.0
            assert expiry > time.time()

    def test_fetch_current_price_handles_exception(self):
        fetcher = PriceFetcher()
        
        with patch("app.services.price_fetcher.DataSourceFactory.get_ticker", side_effect=Exception("API Error")):
            price = fetcher.fetch_current_price(None, "FAIL/USDT")
            
            assert price is None

    def test_fetch_current_price_cache_read_exception(self):
        fetcher = PriceFetcher()
        fetcher._price_cache_ttl_sec = 10
        cache_key = "Crypto:ERR/USDT"
        
        # Replace the lock object with a MagicMock
        mock_lock = MagicMock()
        mock_lock.__enter__.side_effect = Exception("Lock Error")
        fetcher._price_cache_lock = mock_lock
        
        with patch("app.services.price_fetcher.DataSourceFactory.get_ticker") as mock_ticker:
            mock_ticker.return_value = {"last": 100.0}
            price = fetcher.fetch_current_price(None, "ERR/USDT")
            assert price == 100.0
            mock_ticker.assert_called_once()

    def test_fetch_current_price_cache_write_exception(self):
        fetcher = PriceFetcher()
        fetcher._price_cache_ttl_sec = 10
        
        mock_lock = MagicMock()
        lock_calls = 0
        def mock_enter(*args, **kwargs):
            nonlocal lock_calls
            lock_calls += 1
            if lock_calls == 2:
                raise Exception("Write Lock Error")
            return mock_lock
            
        mock_lock.__enter__.side_effect = mock_enter
        fetcher._price_cache_lock = mock_lock
        
        with patch("app.services.price_fetcher.DataSourceFactory.get_ticker") as mock_ticker:
            mock_ticker.return_value = {"last": 100.0}
            price = fetcher.fetch_current_price(None, "ERR2/USDT")
            assert price == 100.0
            mock_ticker.assert_called_once()

    def test_get_last_ticker_meta_from_cache(self):
        fetcher = PriceFetcher()
        fetcher._price_cache_ttl_sec = 10

        with patch("app.services.price_fetcher.DataSourceFactory.get_ticker") as mock_ticker:
            mock_ticker.return_value = {
                "last": 31.5,
                "previousClose": 31.3,
                "previousCloseAgeDays": 1.2,
                "previousCloseFresh": False,
            }
            price = fetcher.fetch_current_price(None, "XAGUSD", market_category="Forex")
            assert price == 31.5

        meta = fetcher.get_last_ticker_meta("XAGUSD", market_category="Forex")
        assert meta.get("previousClose") == 31.3
        assert meta.get("previousCloseAgeDays") == 1.2
        assert meta.get("previousCloseFresh") is False

    def test_get_last_ticker_meta_expired_returns_empty(self):
        fetcher = PriceFetcher()
        fetcher._price_cache_ttl_sec = 10
        cache_key = "Forex:XAGUSD"
        fetcher._ticker_meta_cache[cache_key] = ({"last": 31.5}, time.time() - 1)

        meta = fetcher.get_last_ticker_meta("XAGUSD", market_category="Forex")
        assert meta == {}


class TestPriceFetcherSingleton:
    def test_get_price_fetcher_returns_singleton(self):
        fetcher1 = get_price_fetcher()
        fetcher2 = get_price_fetcher()
        
        assert fetcher1 is fetcher2
        assert isinstance(fetcher1, PriceFetcher)