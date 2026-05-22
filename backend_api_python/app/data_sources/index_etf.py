"""
IndexETF data source.

Routes by inferred currency of the symbol:
- USD ETFs (QQQ/SPY/DIA/IWM/VTI/SQQQ/...) -> reuse USStockDataSource (yfinance)
- A-share ETFs (510300/159915/...)        -> akshare.fund_etf_hist_em / fund_etf_spot_em
- HK ETFs (02800/03033)                   -> reuse HShareDataSource (Tencent/Eastmoney/yfinance)

Symbols are passed through as-is — the same string the user sees in the UI
and stores in qd_market_symbols (e.g. "QQQ", "510300", "02800").
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from app.data_sources.base import BaseDataSource
from app.data_sources.us_stock import USStockDataSource
from app.data_sources.cn_stock import HShareDataSource
from app.utils.logger import get_logger

logger = get_logger(__name__)

try:
    import akshare as ak  # type: ignore
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    logger.debug("akshare not installed; A-share ETF will be unavailable")


def classify_etf_currency(symbol: str) -> str:
    """
    Infer currency bucket from the raw symbol code.

    Returns one of: 'USD' | 'CNY' | 'HKD'.

    Rules:
    - 6-digit numeric code starting with 1/5  -> CNY (A-share fund / ETF code)
    - 4-5 digit numeric code                  -> HKD (HK code, with or without leading 0)
    - Otherwise (alpha tickers like QQQ/SPY)  -> USD
    """
    s = (symbol or "").strip().upper()
    if s.isdigit():
        # A-share ETF codes are always 6 digits, typically 5xxxxx (SSE) or 1xxxxx (SZSE).
        if len(s) == 6:
            return "CNY"
        # HK codes are <=5 digits (often padded with leading zeros).
        if 1 <= len(s) <= 5:
            return "HKD"
    return "USD"


class IndexETFDataSource(BaseDataSource):
    """Index ETF data source. Multi-region; routes by currency."""

    name = "IndexETF"

    AKSHARE_PERIOD_MAP = {"1D": "daily", "1W": "weekly"}

    # akshare.fund_etf_spot_em column names are Chinese; this is the canonical mapping.
    _ASHARE_TICKER_FIELDS = {
        "code": "代码",
        "last": "最新价",
        "high": "最高价",
        "low": "最低价",
        "open": "开盘价",
        "previousClose": "昨收",
        "change": "涨跌额",
        "changePercent": "涨跌幅",
    }

    def __init__(self):
        self._us_source = USStockDataSource()
        self._hk_source = HShareDataSource()

    # -------------------------------------------------------------------------
    # Public BaseDataSource interface
    # -------------------------------------------------------------------------

    def get_kline(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        before_time: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        currency = classify_etf_currency(symbol)
        if currency == "USD":
            return self._us_source.get_kline(symbol, timeframe, limit, before_time)
        if currency == "CNY":
            return self._fetch_ashare_etf_kline(symbol, timeframe, limit, before_time)
        if currency == "HKD":
            return self._hk_source.get_kline(symbol, timeframe, limit, before_time)
        logger.warning("IndexETF: cannot classify currency for %s", symbol)
        return []

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        currency = classify_etf_currency(symbol)
        if currency == "USD":
            return self._us_source.get_ticker(symbol)
        if currency == "CNY":
            return self._fetch_ashare_etf_ticker(symbol)
        if currency == "HKD":
            return self._hk_source.get_ticker(symbol)
        return {"last": 0, "symbol": symbol}

    # -------------------------------------------------------------------------
    # A-share ETF (akshare)
    # -------------------------------------------------------------------------

    @staticmethod
    def _ashare_etf_to_yahoo_symbol(symbol: str) -> Optional[str]:
        """A-share ETF code → yfinance ticker.

        SSE ETFs use codes 510xxx/511xxx/512xxx/513xxx/515xxx/518xxx/588xxx → .SS.
        SZSE ETFs use 159xxx → .SZ. Anything else returns None.
        """
        s = (symbol or "").strip()
        if not s.isdigit() or len(s) != 6:
            return None
        if s.startswith("5"):
            return f"{s}.SS"
        if s.startswith("1"):
            return f"{s}.SZ"
        return None

    def _fetch_ashare_etf_kline(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        before_time: Optional[int],
    ) -> List[Dict[str, Any]]:
        """Fetch A-share ETF K-line with akshare primary + yfinance fallback.

        akshare calls eastmoney behind the scenes and can fail when the
        container is forced through a proxy that blocks eastmoney; yfinance
        (via the SSE/SZSE Yahoo aliases) is a reliable fallback for daily/
        weekly bars.
        """
        if not HAS_AKSHARE:
            logger.warning("akshare not installed; falling back to yfinance for %s", symbol)
            return self._fetch_ashare_etf_kline_yfinance(symbol, timeframe, limit, before_time)

        period = self.AKSHARE_PERIOD_MAP.get(timeframe)
        if not period:
            logger.warning("A-share ETF unsupported timeframe: %s", timeframe)
            return []

        try:
            end_dt = datetime.fromtimestamp(before_time) if before_time else datetime.now()
            end_date = end_dt.strftime("%Y%m%d")
            # daily ETFs: ask for ~limit*2 calendar days to cover non-trading days; weekly: *10
            days = limit * 2 if timeframe == "1D" else max(limit * 10, 60)
            start_date = (end_dt - timedelta(days=days)).strftime("%Y%m%d")

            df = ak.fund_etf_hist_em(
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            )
            if df is not None and not df.empty:
                klines: List[Dict[str, Any]] = []
                for _, row in df.iterrows():
                    date_str = str(row["日期"])
                    try:
                        ts = int(datetime.strptime(date_str, "%Y-%m-%d").timestamp())
                    except ValueError:
                        continue
                    klines.append(
                        self.format_kline(
                            timestamp=ts,
                            open_price=float(row["开盘"]),
                            high=float(row["最高"]),
                            low=float(row["最低"]),
                            close=float(row["收盘"]),
                            volume=float(row["成交量"]),
                        )
                    )
                if klines:
                    klines = self.filter_and_limit(klines, limit, before_time)
                    self.log_result(symbol, klines, timeframe)
                    return klines
                logger.warning("A-share ETF %s: akshare returned rows but parsed empty", symbol)
            else:
                logger.warning("A-share ETF %s: akshare returned empty", symbol)

        except Exception as e:  # noqa: BLE001 — third-party API can raise anything
            logger.warning("A-share ETF %s akshare failed (will try yfinance): %s", symbol, e)

        return self._fetch_ashare_etf_kline_yfinance(symbol, timeframe, limit, before_time)

    def _fetch_ashare_etf_kline_yfinance(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        before_time: Optional[int],
    ) -> List[Dict[str, Any]]:
        """yfinance fallback for A-share ETFs (daily/weekly only)."""
        if timeframe not in ("1D", "1W"):
            return []
        yahoo_symbol = self._ashare_etf_to_yahoo_symbol(symbol)
        if not yahoo_symbol:
            logger.warning("A-share ETF %s: cannot derive yahoo symbol", symbol)
            return []
        klines = self._us_source.get_kline(yahoo_symbol, timeframe, limit, before_time)
        if klines:
            self.log_result(symbol, klines, timeframe)
        return klines

    def _fetch_ashare_etf_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        akshare has no per-symbol ETF realtime endpoint; fund_etf_spot_em returns
        the full A-share ETF universe in one call (~1-3s). For Step A we accept
        the cost; a future patch can add a 60s memory cache here.
        """
        if not HAS_AKSHARE:
            return {"last": 0, "symbol": symbol}

        try:
            df = ak.fund_etf_spot_em()
            if df is None or df.empty:
                return {"last": 0, "symbol": symbol}

            code_col = self._ASHARE_TICKER_FIELDS["code"]
            row_match = df[df[code_col] == symbol]
            if row_match.empty:
                return {"last": 0, "symbol": symbol}

            row = row_match.iloc[0]

            def _f(field: str) -> float:
                col = self._ASHARE_TICKER_FIELDS[field]
                try:
                    return float(row[col])
                except (TypeError, ValueError):
                    return 0.0

            return {
                "last": _f("last"),
                "high": _f("high"),
                "low": _f("low"),
                "open": _f("open"),
                "previousClose": _f("previousClose"),
                "change": _f("change"),
                "changePercent": _f("changePercent"),
            }

        except Exception as e:  # noqa: BLE001
            logger.debug("A-share ETF ticker %s failed: %s", symbol, e)
            return {"last": 0, "symbol": symbol}
