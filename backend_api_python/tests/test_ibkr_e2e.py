"""
E2E tests for IBKRDataSource — full chain from DataSourceFactory through
IBKRClient to mocked ib_insync.IB.

Validates:
- DataSourceFactory -> IBKRDataSource -> IBKRClient -> ib_insync.IB
- get_kline returns correct format
- get_ticker returns correct format
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


def _make_mock_ib(connected: bool = True, bars=None, quote_price: float = 175.25):
    """
    Build a fully-configured mock ib_insync.IB instance.

    bars: list of mock bar objects (each with .date, .open, .high, .low, .close, .volume)
    quote_price: float returned as ticker.last / ticker.bid / ticker.ask
    """
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = connected
    mock_ib.managedAccounts.return_value = ["DU12345"]
    mock_ib.RequestTimeout = 10

    # connectAsync: must be AsyncMock so 'await ib_insync.IB().connectAsync(...)' works
    async def mock_connect(**kwargs):
        mock_ib.isConnected.return_value = True
    mock_ib.connectAsync = AsyncMock(side_effect=mock_connect)

    # qualifyContractsAsync: must be AsyncMock so 'await ib_insync.IB().qualifyContractsAsync(...)' works
    async def mock_qualify(*args, **kwargs):
        return [MagicMock()]  # non-empty list => contract is qualified
    mock_ib.qualifyContractsAsync = AsyncMock(side_effect=mock_qualify)

    # reqPositionsAsync: must be AsyncMock (called during connect)
    async def mock_positions(*args, **kwargs):
        return []
    mock_ib.reqPositionsAsync = AsyncMock(side_effect=mock_positions)

    # reqHistoricalBarsAsync: must be AsyncMock
    async def mock_bars(*args, **kwargs):
        if bars is None:
            # Return 5 synthetic bars
            result = []
            base_time = datetime(2024, 1, 2, 9, 30, tzinfo=timezone.utc)
            for i in range(5):
                bar = MagicMock()
                bar.date = base_time.replace(minute=30 + i)
                bar.open = 150.0 + i
                bar.high = 151.0 + i
                bar.low = 149.0 + i
                bar.close = 150.5 + i
                bar.volume = 1_000_000 + i * 1_000
                result.append(bar)
            return result
        return bars
    mock_ib.reqHistoricalBarsAsync = AsyncMock(side_effect=mock_bars)

    # reqMktData: sync method returning a mock ticker
    mock_ticker = MagicMock()
    mock_ticker.last = quote_price
    mock_ticker.bid = quote_price - 0.05
    mock_ticker.ask = quote_price + 0.05
    mock_ticker.high = quote_price + 1.0
    mock_ticker.low = quote_price - 1.0
    mock_ticker.volume = 1_000_000
    mock_ticker.close = quote_price - 0.10
    mock_ib.reqMktData = MagicMock(return_value=mock_ticker)
    mock_ib.cancelMktData = MagicMock()

    return mock_ib


def _patch_ib_insync(mock_ib):
    """
    Patch ib_insync at the module level where IBKRClient uses it.

    ib_insync.IB is a *class* — ib_insync.IB() instantiates it.
    We need to return mock_ib when IB() is called.
    Using a lambda achieves this: IB is a callable that returns mock_ib.
    """
    mock_module = MagicMock()
    mock_module.IB = lambda *args, **kwargs: mock_ib
    return patch(
        "app.services.live_trading.ibkr_trading.client.ib_insync",
        mock_module,
    )


class TestE2E_GetKline:
    """E2E: DataSourceFactory -> IBKRDataSource -> mocked ib_insync returns correct kline format."""

    def test_e2e_get_kline_returns_correct_format(self):
        """get_kline through the full chain returns list of kline dicts."""
        from app.data_sources import DataSourceFactory
        from app.services.live_trading.ibkr_trading.client import reset_ibkr_client

        mock_ib = _make_mock_ib(connected=True)
        DataSourceFactory._sources.pop('ibkr-live', None)

        with _patch_ib_insync(mock_ib):
            reset_ibkr_client()
            source = DataSourceFactory.get_source('USStock', exchange_id='ibkr-live')

            # Patch kline_fetcher cache to return empty (cache miss)
            with patch('app.data_sources.ibkr.kline_fetcher') as mock_fetcher:
                mock_fetcher.get_kline.return_value = []
                result = source.get_kline(symbol='AAPL', timeframe='1m', limit=5)

        # Verify format matches BaseDataSource contract
        assert isinstance(result, list)
        assert len(result) == 5
        for bar in result:
            assert 'time' in bar
            assert 'open' in bar
            assert 'high' in bar
            assert 'low' in bar
            assert 'close' in bar
            assert 'volume' in bar
            assert isinstance(bar['time'], int)
            assert isinstance(bar['open'], float)
            assert isinstance(bar['high'], float)
            assert isinstance(bar['low'], float)
            assert isinstance(bar['close'], float)
            assert isinstance(bar['volume'], float)

    def test_e2e_get_kline_with_empty_bars(self):
        """get_kline returns empty list when ib_insync returns no bars."""
        from app.data_sources import DataSourceFactory
        from app.services.live_trading.ibkr_trading.client import reset_ibkr_client

        mock_ib = _make_mock_ib(connected=True, bars=[])
        DataSourceFactory._sources.pop('ibkr-live', None)

        with _patch_ib_insync(mock_ib):
            reset_ibkr_client()
            source = DataSourceFactory.get_source('USStock', exchange_id='ibkr-live')

            with patch('app.data_sources.ibkr.kline_fetcher') as mock_fetcher:
                mock_fetcher.get_kline.return_value = []
                result = source.get_kline(symbol='INVALID', timeframe='1m', limit=100)

        assert isinstance(result, list)
        assert len(result) == 0


class TestE2E_GetTicker:
    """E2E: DataSourceFactory -> IBKRDataSource -> mocked ib_insync returns correct ticker format."""

    def test_e2e_get_ticker_returns_correct_format(self):
        """get_ticker through the full chain returns dict with 'last' key."""
        from app.data_sources import DataSourceFactory
        from app.services.live_trading.ibkr_trading.client import reset_ibkr_client

        mock_ib = _make_mock_ib(connected=True, quote_price=175.25)
        DataSourceFactory._sources.pop('ibkr-live', None)

        with _patch_ib_insync(mock_ib):
            reset_ibkr_client()
            source = DataSourceFactory.get_source('USStock', exchange_id='ibkr-live')
            result = source.get_ticker(symbol='AAPL')

        assert isinstance(result, dict)
        assert 'symbol' in result
        assert 'last' in result
        assert result['symbol'] == 'AAPL'
        assert isinstance(result['last'], (int, float))
        assert result['last'] == 175.25

    def test_e2e_get_ticker_with_zero_price(self):
        """get_ticker returns {'last': None} when ticker.last is 0.0.

        get_quote correctly returns None (not 0) for a zero price to distinguish
        'price unavailable' from 'price is literally zero'.
        """
        from app.data_sources import DataSourceFactory
        from app.services.live_trading.ibkr_trading.client import reset_ibkr_client

        mock_ib = _make_mock_ib(connected=True, quote_price=0.0)
        DataSourceFactory._sources.pop('ibkr-live', None)

        with _patch_ib_insync(mock_ib):
            reset_ibkr_client()
            source = DataSourceFactory.get_source('USStock', exchange_id='ibkr-live')
            result = source.get_ticker(symbol='AAPL')

        assert isinstance(result, dict)
        assert result['symbol'] == 'AAPL'
        # When ticker.last == 0, get_quote returns {"success": True, "last": None}
        assert result.get('last') is None


class TestE2E_Chain:
    """Verify the complete chain is wired correctly."""

    def test_e2e_factory_returns_ibkr_datasource(self):
        """DataSourceFactory with exchange_id='ibkr-live' returns IBKRDataSource instance."""
        from app.data_sources import DataSourceFactory
        from app.data_sources.ibkr import IBKRDataSource
        from app.services.live_trading.ibkr_trading.client import reset_ibkr_client

        DataSourceFactory._sources.pop('ibkr-live', None)

        mock_ib = _make_mock_ib(connected=True)
        with _patch_ib_insync(mock_ib):
            reset_ibkr_client()
            source = DataSourceFactory.get_source('USStock', exchange_id='ibkr-live')
            assert isinstance(source, IBKRDataSource)

    def test_e2e_kline_uses_internal_client(self):
        """get_kline calls internal IBKRClient.get_historical_bars (not direct ib_insync)."""
        from app.data_sources import DataSourceFactory
        from app.services.live_trading.ibkr_trading.client import reset_ibkr_client

        mock_ib = _make_mock_ib(connected=True)
        DataSourceFactory._sources.pop('ibkr-live', None)

        with _patch_ib_insync(mock_ib):
            reset_ibkr_client()
            source = DataSourceFactory.get_source('USStock', exchange_id='ibkr-live')

            with patch('app.data_sources.ibkr.kline_fetcher') as mock_fetcher:
                mock_fetcher.get_kline.return_value = []
                source.get_kline(symbol='AAPL', timeframe='1m', limit=5)

            # Verify ib_insync.reqHistoricalBarsAsync was called (proof of internal client usage)
            mock_ib.reqHistoricalBarsAsync.assert_called()

    def test_e2e_ticker_uses_internal_client(self):
        """get_ticker calls internal IBKRClient.get_quote (not direct ib_insync)."""
        from app.data_sources import DataSourceFactory
        from app.services.live_trading.ibkr_trading.client import reset_ibkr_client

        mock_ib = _make_mock_ib(connected=True, quote_price=200.0)
        DataSourceFactory._sources.pop('ibkr-live', None)

        with _patch_ib_insync(mock_ib):
            reset_ibkr_client()
            source = DataSourceFactory.get_source('USStock', exchange_id='ibkr-live')
            source.get_ticker(symbol='AAPL')

            # Verify ib_insync.reqMktData was called (proof of internal client usage)
            mock_ib.reqMktData.assert_called()
