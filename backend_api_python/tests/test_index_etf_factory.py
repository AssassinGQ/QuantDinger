"""DataSourceFactory recognises IndexETF (Phase 20-A Step A)."""
from app.data_sources.factory import DataSourceFactory
from app.data_sources.index_etf import IndexETFDataSource


def test_factory_returns_index_etf_data_source():
    src = DataSourceFactory.get_source("IndexETF")
    assert isinstance(src, IndexETFDataSource)


def test_factory_caches_index_etf_singleton():
    """Factory caches sources per-market — same instance on repeat calls."""
    s1 = DataSourceFactory.get_source("IndexETF")
    s2 = DataSourceFactory.get_source("IndexETF")
    assert s1 is s2


def test_factory_market_types_still_include_existing():
    """Smoke check: adding IndexETF does not break existing markets."""
    for market in ("USStock", "AShare", "HShare", "Crypto", "Forex", "Futures"):
        src = DataSourceFactory.get_source(market)
        assert src is not None, f"{market} data source must still resolve"
