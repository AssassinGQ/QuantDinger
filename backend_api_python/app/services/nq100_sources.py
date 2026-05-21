"""
NQ100 current membership: Nasdaq.com (primary) → Wikipedia (secondary) →
``nasdaq-100-ticker-history.tickers_as_of`` (package).

**URLs (structure must match frozen fixtures in tests; live pages may drift):**

- Primary: ``https://www.nasdaq.com/market-activity/quotes/nasdaq-100-index``
- Secondary: ``https://en.wikipedia.org/wiki/Nasdaq-100``
"""

from __future__ import annotations

import datetime as _dt
from typing import Iterable, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from app.utils.logger import get_logger
from app.utils.symbol_normalize import normalize_us_stock_symbol

logger = get_logger(__name__)

NASDAQ_NQ100_URL = "https://www.nasdaq.com/market-activity/quotes/nasdaq-100-index"
WIKIPEDIA_NQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"


def parse_nasdaq_nq100_html(html: str) -> set[str]:
    """Parse frozen Nasdaq-style listing HTML; return normalized tickers."""
    soup = BeautifulSoup(html, "lxml")
    out: set[str] = set()
    for cell in soup.select("td.symbol"):
        t = normalize_us_stock_symbol(cell.get_text())
        if t:
            out.add(t)
    return out


def parse_wikipedia_nq100_html(html: str) -> set[str]:
    """Parse frozen Wikipedia wikitable HTML; return normalized tickers."""
    soup = BeautifulSoup(html, "lxml")
    out: set[str] = set()
    for table in soup.select("table.wikitable"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            # Second column: ticker symbol (matches fixture)
            t = normalize_us_stock_symbol(cells[1].get_text())
            if t:
                out.add(t)
    return out


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_nq100_symbols_current() -> Tuple[set[str], str, str]:
    """
    Try primary scrape → secondary scrape → ``tickers_as_of`` (UTC calendar date).

    Returns ``(symbols, source_label, scraped_at_iso)``. On total failure,
    ``symbols`` is empty and ``source_label`` is ``\"none\"``.
    """
    scraped_at = _utc_now_iso()

    try:
        r = requests.get(NASDAQ_NQ100_URL, timeout=30)
        if r.ok:
            syms = parse_nasdaq_nq100_html(r.text)
            if syms:
                return syms, "nasdaq.com", scraped_at
    except requests.RequestException as e:
        logger.warning("Nasdaq NQ100 fetch failed: %s", e)

    scraped_at = _utc_now_iso()
    try:
        r = requests.get(WIKIPEDIA_NQ100_URL, timeout=30)
        if r.ok:
            syms = parse_wikipedia_nq100_html(r.text)
            if syms:
                return syms, "wikipedia.org", scraped_at
    except requests.RequestException as e:
        logger.warning("Wikipedia NQ100 fetch failed: %s", e)

    scraped_at = _utc_now_iso()
    try:
        from nasdaq_100_ticker_history import tickers_as_of

        now = _dt.datetime.now(tz=_dt.timezone.utc)
        raw = tickers_as_of(now.year, now.month, now.day)
        syms = {normalize_us_stock_symbol(s) for s in raw}
        syms.discard("")
        if syms:
            return syms, "nasdaq-100-ticker-history", scraped_at
    except Exception as e:
        logger.error("nasdaq-100-ticker-history tickers_as_of failed: %s", e)

    logger.error("All NQ100 sources failed; returning empty universe")
    return set(), "none", scraped_at


def resolve_shifted_execution_date(
    _signal_date: _dt.date,
    next_session: _dt.date,
    effective_dates: Optional[Iterable[_dt.date]] = None,
) -> _dt.date:
    """Apply D-15 rule: if T+1 hits effective_date, shift to next session (T+2)."""
    effective = set(effective_dates or [])
    if next_session in effective:
        return next_session + _dt.timedelta(days=1)
    return next_session
