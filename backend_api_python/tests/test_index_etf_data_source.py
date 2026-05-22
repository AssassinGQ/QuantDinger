"""Unit tests for IndexETFDataSource (Phase 20-A Step A)."""
from unittest.mock import patch, MagicMock

import pytest

from app.data_sources.index_etf import (
    IndexETFDataSource,
    classify_etf_currency,
)


# ---------------------------------------------------------------------------
# classify_etf_currency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "symbol,expected",
    [
        # USD: alpha tickers
        ("QQQ", "USD"),
        ("SPY", "USD"),
        ("SQQQ", "USD"),
        ("VTI", "USD"),
        ("vti", "USD"),  # case-insensitive
        # CNY: 6-digit numeric (A-share ETF code)
        ("510300", "CNY"),
        ("510500", "CNY"),
        ("588000", "CNY"),
        ("159915", "CNY"),
        # HKD: 4-5 digit numeric (with optional leading zero)
        ("02800", "HKD"),
        ("03033", "HKD"),
        ("2800", "HKD"),
        ("700", "HKD"),
        # Edge cases
        ("", "USD"),  # empty falls through to USD by design
        ("   QQQ  ", "USD"),  # whitespace stripped
    ],
)
def test_classify_etf_currency(symbol, expected):
    assert classify_etf_currency(symbol) == expected


# ---------------------------------------------------------------------------
# get_kline routing
# ---------------------------------------------------------------------------

def test_get_kline_usd_uses_us_source():
    ds = IndexETFDataSource()
    fake_klines = [{"time": 1, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 100}]
    with patch.object(ds._us_source, "get_kline", return_value=fake_klines) as us_mock, \
         patch.object(ds._hk_source, "get_kline") as hk_mock:
        result = ds.get_kline("QQQ", "1D", 5)

    us_mock.assert_called_once_with("QQQ", "1D", 5, None)
    hk_mock.assert_not_called()
    assert result is fake_klines


def test_get_kline_hkd_uses_hk_source():
    ds = IndexETFDataSource()
    fake_klines = [{"time": 1, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 100}]
    with patch.object(ds._hk_source, "get_kline", return_value=fake_klines) as hk_mock, \
         patch.object(ds._us_source, "get_kline") as us_mock:
        result = ds.get_kline("02800", "1D", 5)

    hk_mock.assert_called_once_with("02800", "1D", 5, None)
    us_mock.assert_not_called()
    assert result is fake_klines


def test_get_kline_cny_calls_akshare_fund_etf_hist_em():
    ds = IndexETFDataSource()
    # Build a fake DataFrame-like object that supports iterrows() and emptiness check
    import pandas as pd
    df = pd.DataFrame({
        "日期": ["2026-05-20", "2026-05-21"],
        "开盘": [4.10, 4.12],
        "收盘": [4.12, 4.15],
        "最高": [4.15, 4.18],
        "最低": [4.08, 4.11],
        "成交量": [1_000_000, 1_200_000],
    })
    fake_ak = MagicMock()
    fake_ak.fund_etf_hist_em.return_value = df

    with patch("app.data_sources.index_etf.HAS_AKSHARE", True), \
         patch("app.data_sources.index_etf.ak", fake_ak):
        klines = ds.get_kline("510300", "1D", 5)

    fake_ak.fund_etf_hist_em.assert_called_once()
    call_kwargs = fake_ak.fund_etf_hist_em.call_args.kwargs
    assert call_kwargs["symbol"] == "510300"
    assert call_kwargs["period"] == "daily"
    assert call_kwargs["adjust"] == "qfq"

    assert len(klines) == 2
    assert klines[0]["close"] == 4.12
    assert klines[1]["volume"] == 1_200_000


def test_get_kline_cny_unsupported_timeframe_returns_empty():
    """A-share ETF only supports 1D / 1W via akshare (or yfinance fallback); minute-level fails soft."""
    ds = IndexETFDataSource()
    with patch("app.data_sources.index_etf.HAS_AKSHARE", True):
        assert ds.get_kline("510300", "1H", 100) == []


def test_get_kline_cny_without_akshare_falls_back_to_yfinance():
    """When akshare is missing we should still try the yfinance alias (.SS/.SZ)."""
    ds = IndexETFDataSource()
    fake_klines = [{"time": 1, "open": 4.1, "high": 4.2, "low": 4.0, "close": 4.15, "volume": 1000}]
    with patch("app.data_sources.index_etf.HAS_AKSHARE", False), \
         patch.object(ds._us_source, "get_kline", return_value=fake_klines) as us_mock:
        klines = ds.get_kline("510300", "1D", 5)
    us_mock.assert_called_once_with("510300.SS", "1D", 5, None)
    assert klines == fake_klines


def test_get_kline_cny_akshare_failure_falls_back_to_yfinance():
    """akshare exception (proxy/network) should trigger yfinance fallback."""
    ds = IndexETFDataSource()
    fake_klines = [{"time": 1, "open": 4.1, "high": 4.2, "low": 4.0, "close": 4.15, "volume": 1000}]
    fake_ak = MagicMock()
    fake_ak.fund_etf_hist_em.side_effect = RuntimeError("ProxyError: Unable to connect to proxy")
    with patch("app.data_sources.index_etf.HAS_AKSHARE", True), \
         patch("app.data_sources.index_etf.ak", fake_ak), \
         patch.object(ds._us_source, "get_kline", return_value=fake_klines) as us_mock:
        klines = ds.get_kline("159915", "1D", 5)
    us_mock.assert_called_once_with("159915.SZ", "1D", 5, None)
    assert klines == fake_klines


def test_ashare_etf_to_yahoo_symbol():
    fn = IndexETFDataSource._ashare_etf_to_yahoo_symbol
    assert fn("510300") == "510300.SS"  # SSE
    assert fn("588000") == "588000.SS"  # STAR Market ETF
    assert fn("159915") == "159915.SZ"  # SZSE
    assert fn("000001") is None  # not an ETF code (regular A-share)
    assert fn("QQQ") is None
    assert fn("") is None


# ---------------------------------------------------------------------------
# get_ticker routing
# ---------------------------------------------------------------------------

def test_get_ticker_usd_uses_us_source():
    ds = IndexETFDataSource()
    with patch.object(ds._us_source, "get_ticker", return_value={"last": 714.5}) as m:
        result = ds.get_ticker("QQQ")
    m.assert_called_once_with("QQQ")
    assert result == {"last": 714.5}


def test_get_ticker_cny_parses_akshare_spot():
    ds = IndexETFDataSource()
    import pandas as pd
    spot_df = pd.DataFrame({
        "代码": ["510300", "510500", "588000"],
        "最新价": [4.15, 6.20, 1.05],
        "最高价": [4.18, 6.25, 1.06],
        "最低价": [4.10, 6.15, 1.03],
        "开盘价": [4.12, 6.18, 1.04],
        "昨收": [4.12, 6.18, 1.04],
        "涨跌额": [0.03, 0.02, 0.01],
        "涨跌幅": [0.73, 0.32, 0.96],
    })
    fake_ak = MagicMock()
    fake_ak.fund_etf_spot_em.return_value = spot_df

    with patch("app.data_sources.index_etf.HAS_AKSHARE", True), \
         patch("app.data_sources.index_etf.ak", fake_ak):
        ticker = ds.get_ticker("510300")

    assert ticker["last"] == 4.15
    assert ticker["high"] == 4.18
    assert ticker["changePercent"] == 0.73


def test_get_ticker_cny_symbol_not_found():
    ds = IndexETFDataSource()
    import pandas as pd
    spot_df = pd.DataFrame({
        "代码": ["510300"],
        "最新价": [4.15],
        "最高价": [4.18],
        "最低价": [4.10],
        "开盘价": [4.12],
        "昨收": [4.12],
        "涨跌额": [0.03],
        "涨跌幅": [0.73],
    })
    fake_ak = MagicMock()
    fake_ak.fund_etf_spot_em.return_value = spot_df

    with patch("app.data_sources.index_etf.HAS_AKSHARE", True), \
         patch("app.data_sources.index_etf.ak", fake_ak):
        ticker = ds.get_ticker("510500")

    assert ticker == {"last": 0, "symbol": "510500"}


def test_get_ticker_hkd_uses_hk_source():
    ds = IndexETFDataSource()
    with patch.object(ds._hk_source, "get_ticker", return_value={"last": 28.5}) as m:
        result = ds.get_ticker("02800")
    m.assert_called_once_with("02800")
    assert result == {"last": 28.5}
