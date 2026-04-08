"""
Tests for IBKRDataSource connection management.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from app.data_sources.ibkr import IBKRDataSource


class TestIBKRDataSourceInstantiation:
    """Test IBKRDataSource instantiation with default config."""

    def test_can_instantiate_with_default_config(self):
        """IBKRDataSource can be instantiated with default config."""
        ds = IBKRDataSource()
        assert ds._host == "ib-live-gateway"
        assert ds._port == 4003
        assert ds._client_id == 1
        assert ds._client is None

    def test_can_instantiate_with_custom_config(self):
        """IBKRDataSource can be instantiated with custom config."""
        ds = IBKRDataSource(host="custom-host", port=4004, client_id=5)
        assert ds._host == "custom-host"
        assert ds._port == 4004
        assert ds._client_id == 5

    def test_can_instantiate_with_env_vars(self):
        """IBKRDataSource can read config from environment variables."""
        with patch.dict("os.environ", {"IBKR_HOST": "env-host", "IBKR_PORT": "4005", "IBKR_CLIENT_ID": "10"}):
            ds = IBKRDataSource()
            assert ds._host == "env-host"
            assert ds._port == 4005
            assert ds._client_id == 10


class TestConnectionState:
    """Test connection state checks."""

    def test_is_connected_returns_false_before_connection(self):
        """is_connected() returns False before connection."""
        ds = IBKRDataSource()
        assert ds.is_connected() is False

    def test_is_connected_returns_true_when_client_connected(self):
        """is_connected() returns True when client is connected."""
        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        ds._client = mock_client
        assert ds.is_connected() is True

    def test_is_connected_returns_false_when_client_disconnected(self):
        """is_connected() returns False when client is disconnected."""
        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = False
        ds._client = mock_client
        assert ds.is_connected() is False


class TestReconnect:
    """Test reconnect behavior."""

    def test_reconnect_calls_client_reconnect(self):
        """reconnect() calls client's reconnect method."""
        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.reconnect.return_value = True
        ds._client = mock_client

        result = ds.reconnect(max_retries=5)

        mock_client.reconnect.assert_called_once_with(max_retries=5)
        assert result is True

    def test_reconnect_when_no_client(self):
        """reconnect() calls connect() when no client exists."""
        ds = IBKRDataSource()
        assert ds._client is None

        with patch.object(ds, "connect", return_value=True) as mock_connect:
            result = ds.reconnect(max_retries=3)
            mock_connect.assert_called_once()


class TestDisconnect:
    """Test disconnect behavior."""

    def test_disconnect_disconnects_client(self):
        """disconnect() calls client's disconnect method."""
        ds = IBKRDataSource()
        mock_client = MagicMock()
        ds._client = mock_client

        ds.disconnect()

        mock_client.disconnect.assert_called_once()
        assert ds._client is None

    def test_disconnect_when_no_client(self):
        """disconnect() does nothing when no client exists."""
        ds = IBKRDataSource()
        assert ds._client is None
        # Should not raise
        ds.disconnect()


class TestGetKline:
    """Test get_kline method."""

    def test_get_kline_returns_list_of_dicts(self):
        """get_kline returns list of kline dicts."""
        from unittest.mock import MagicMock, patch
        from ibkr_datafetcher.types import KlineBar, Timeframe, resolve_timeframe, SymbolConfig
        from datetime import datetime, timezone

        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.make_contract.return_value = MagicMock()

        # Use correct Timeframe enum value (M1 = 1 min)
        tf = resolve_timeframe("1m")
        mock_client.get_historical_bars.return_value = [
            KlineBar(
                symbol="AAPL",
                timeframe=tf,
                timestamp=1700000000,
                open=150.0,
                high=151.0,
                low=149.0,
                close=150.5,
                volume=1000000,
                bar_count=100,
                bar_time=datetime(2023, 11, 15, 0, 0, tzinfo=timezone.utc),
            )
        ]
        ds._client = mock_client

        result = ds.get_kline(symbol="AAPL", timeframe="1m", limit=100)

        assert isinstance(result, list)
        assert len(result) > 0
        assert "time" in result[0]
        assert "open" in result[0]
        assert "high" in result[0]
        assert "low" in result[0]
        assert "close" in result[0]
        assert "volume" in result[0]

    def test_get_kline_returns_empty_on_error(self):
        """get_kline returns empty list on error instead of raising."""
        from unittest.mock import MagicMock, patch

        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.make_contract.side_effect = Exception("Invalid contract")
        ds._client = mock_client

        result = ds.get_kline(symbol="INVALID", timeframe="1m", limit=100)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_kline_returns_empty_when_not_connected_and_connect_fails(self):
        """get_kline returns empty list when connection fails."""
        from unittest.mock import MagicMock, patch

        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = False
        mock_client.connect.return_value = False
        ds._client = mock_client

        result = ds.get_kline(symbol="AAPL", timeframe="1m", limit=100)

        assert isinstance(result, list)
        assert len(result) == 0


class TestGetKlineCache:
    """Test get_kline cache integration per D-19."""

    def test_get_kline_uses_kline_fetcher_cache(self):
        """get_kline should check kline_fetcher cache before network call."""
        from unittest.mock import MagicMock, patch
        from ibkr_datafetcher.types import KlineBar, resolve_timeframe
        from datetime import datetime, timezone

        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.make_contract.return_value = MagicMock()

        # Mock kline_fetcher.get_kline to return cached data (>= limit to pass cache check)
        cached_klines = [
            {'time': 1700000000 + i*60, 'open': 150.0, 'high': 151.0, 'low': 149.0, 'close': 150.5, 'volume': 1000000}
            for i in range(100)  # 100 items = limit
        ]

        with patch('app.data_sources.ibkr.kline_fetcher') as mock_fetcher:
            mock_fetcher.get_kline.return_value = cached_klines
            result = ds.get_kline(symbol="AAPL", timeframe="1m", limit=100)

            # kline_fetcher should be called with market="USStock"
            mock_fetcher.get_kline.assert_called_once()
            # Should return cached data (limit=100 satisfied)
            assert len(result) == 100

    def test_get_kline_network_call_on_cache_miss(self):
        """get_kline falls back to network when cache is empty."""
        from unittest.mock import MagicMock, patch
        from ibkr_datafetcher.types import KlineBar, resolve_timeframe
        from datetime import datetime, timezone

        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.make_contract.return_value = MagicMock()

        tf = resolve_timeframe("1m")
        mock_client.get_historical_bars.return_value = [
            KlineBar(
                symbol="AAPL",
                timeframe=tf,
                timestamp=1700000000,
                open=150.0,
                high=151.0,
                low=149.0,
                close=150.5,
                volume=1000000,
                bar_count=100,
                bar_time=datetime(2023, 11, 15, 0, 0, tzinfo=timezone.utc),
            )
        ]
        ds._client = mock_client

        # Simulate cache miss (empty cache)
        with patch('app.data_sources.ibkr.kline_fetcher') as mock_fetcher:
            mock_fetcher.get_kline.return_value = []
            result = ds.get_kline(symbol="AAPL", timeframe="1m", limit=100)

            # Network call should be made since cache was empty
            assert len(result) > 0
            mock_client.get_historical_bars.assert_called_once()


class TestGetTicker:
    """Test get_ticker method per D-20 (no caching)."""

    def test_get_ticker_returns_dict_with_last_key(self):
        """get_ticker returns dict with 'last' key."""
        from unittest.mock import MagicMock, patch
        from ibkr_datafetcher.types import SymbolConfig

        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.make_contract.return_value = MagicMock()
        mock_client.qualify_contract.return_value = 123456
        # Mock get_ticker_price to return actual price
        mock_client.get_ticker_price.return_value = 150.25
        ds._client = mock_client

        result = ds.get_ticker(symbol="AAPL")

        assert isinstance(result, dict)
        assert "last" in result
        assert "symbol" in result

    def test_get_ticker_returns_fallback_on_error(self):
        """get_ticker returns {'last': 0} on error (consistent with factory)."""
        from unittest.mock import MagicMock, patch

        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.make_contract.side_effect = Exception("Invalid symbol")
        ds._client = mock_client

        result = ds.get_ticker(symbol="INVALID")

        # Should return fallback per plan behavior
        assert isinstance(result, dict)
        assert result.get("last") == 0 or result.get("last") is None

    def test_get_ticker_no_cache(self):
        """get_ticker does NOT use cache per D-20 (verifies no cache lookup)."""
        from unittest.mock import MagicMock, patch

        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.make_contract.return_value = MagicMock()
        mock_client.qualify_contract.return_value = 123456
        mock_client.get_ticker_price.return_value = 150.00
        ds._client = mock_client

        # Call get_ticker twice
        result1 = ds.get_ticker(symbol="AAPL")
        result2 = ds.get_ticker(symbol="AAPL")

        # Verify no cache is involved - client method should be called twice
        assert mock_client.get_ticker_price.call_count == 2
