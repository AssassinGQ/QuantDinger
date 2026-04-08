---
phase: 01-ibkr-data-source-implementation
verified: 2026-04-08T18:00:00Z
status: gaps_found
score: 6/7 must-haves verified
overrides_applied: 0
gaps:
  - truth: "trading_executor passes exchange_id to DataSourceFactory per D-14, D-15"
    status: failed
    reason: "PriceFetcher (used by trading_executor) does not accept or pass exchange_id to DataSourceFactory.get_ticker(). When strategies call get_ticker/get_kline via price_fetcher, the exchange_id is lost."
    artifacts:
      - path: "backend_api_python/app/services/price_fetcher.py"
        issue: "fetch_current_price() and DataSourceFactory.get_ticker() called without exchange_id parameter"
    missing:
      - "Add exchange_id parameter to PriceFetcher.fetch_current_price()"
      - "Pass exchange_id to DataSourceFactory.get_ticker() and get_kline()"
      - "Update trading_executor to pass exchange_id from strategy config to price_fetcher"
---

# Phase 1: IBKR Data Source Implementation — Verification Report

**Phase Goal:** 实现 IBKRDataSource 并与 trading_executor 集成，确保 exchange_id='ibkr-live' 的策略使用 IBKR 原生数据源

**Verified:** 2026-04-08
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | IBKRDataSource class exists and can be instantiated | VERIFIED | Class in backend_api_python/app/data_sources/ibkr.py, inherits from BaseDataSource, has connect/disconnect/is_connected/reconnect methods |
| 2 | get_kline() returns list of K-line data in correct format | VERIFIED | Returns [{"time": int, "open": float, "high": float, "low": float, "close": float, "volume": float}], tests pass |
| 3 | Supported timeframes: 1m, 5m, 15m, 30m, 1H, 4H, 1D | VERIFIED | Uses resolve_timeframe() from ibkr_datafetcher |
| 4 | Symbols use IBKR format (AAPL, MSFT) | VERIFIED | Uses SymbolConfig with sec_type="STK", exchange="SMART", currency="USD" |
| 5 | Uses caching per D-19 | VERIFIED | Checks kline_fetcher cache (market="USStock") before network call |
| 6 | get_ticker() returns dict with 'last' price | VERIFIED | Returns {"last": float, "symbol": str, ...}, no caching per D-20 |
| 7 | Synchronous blocking call (per D-12) | VERIFIED | Uses get_ticker_price() synchronous call pattern |
| 8 | IBKR rate limiter exists with 6 RPM (per D-21) | VERIFIED | IBKRRateLimiter in rate_limiter.py with hist_requests_per_minute=6 |
| 9 | Rate limiter protects get_ticker per D-22 | VERIFIED | _rate_limiter.acquire() called in get_ticker() |
| 10 | Rate limiter integrated with get_kline per D-23 | VERIFIED | _rate_limiter.acquire() called in get_kline() |
| 11 | DataSourceFactory.get_source() accepts optional exchange_id per D-01 | VERIFIED | Method signature includes exchange_id parameter |
| 12 | When exchange_id='ibkr-live', returns IBKRDataSource per D-02, D-03 | VERIFIED | factory.py lines 31-35 return IBKRDataSource for 'ibkr-live' |
| 13 | exchange_id takes priority over market_category per D-08 | VERIFIED | factory.py checks exchange_id first (line 31) |
| 14 | trading_executor passes exchange_id to DataSourceFactory per D-14, D-15 | FAILED | price_fetcher.fetch_current_price() does not accept exchange_id parameter; DataSourceFactory.get_ticker() called without exchange_id |

**Score:** 13/14 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend_api_python/app/data_sources/ibkr.py` | IBKRDataSource class | VERIFIED | Class with connect, disconnect, is_connected, reconnect, get_kline, get_ticker |
| `backend_api_python/app/data_sources/rate_limiter.py` | IBKRRateLimiter + get_ibkr_limiter() | VERIFIED | IBKRRateLimiter class with 6 RPM, get_ibkr_limiter() singleton |
| `backend_api_python/app/data_sources/factory.py` | get_source with exchange_id | VERIFIED | exchange_id parameter added, 'ibkr-live' returns IBKRDataSource |
| `backend_api_python/app/data_sources/__init__.py` | Export IBKRDataSource | VERIFIED | IBKRDataSource in __all__ |
| `backend_api_python/tests/test_ibkr_datasource.py` | Unit tests | VERIFIED | Tests for instantiation, get_kline, get_ticker, cache, no-cache |

### Key Link Verification

| From | To | Via | Status | Details |
|------|---|---|--------|---------|
| IBKRDataSource | BaseDataSource | inheritance | VERIFIED | class IBKRDataSource(BaseDataSource) |
| IBKRDataSource | IBKRClient | import | VERIFIED | from ibkr_datafetcher.ibkr_client import IBKRClient |
| get_kline | IBKRClient.get_historical_bars | call | VERIFIED | Lines 174-178 in ibkr.py |
| get_kline | kline_fetcher | import and use | VERIFIED | import from app.services, cache check at lines 130-140 |
| get_ticker | IBKRClient | get_ticker_price call | VERIFIED | Line 242 in ibkr.py |
| IBKRDataSource | get_ibkr_limiter | import and call | VERIFIED | _rate_limiter.acquire() in get_kline and get_ticker |
| DataSourceFactory.get_source | IBKRDataSource | conditional return | VERIFIED | Returns IBKRDataSource for 'ibkr-live' |
| **PriceFetcher** | **DataSourceFactory.get_ticker** | **call** | **NOT WIRED** | **exchange_id not passed** |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| IBKRDataSource.get_kline | klines | IBKRClient.get_historical_bars | Yes | FLOWING |
| IBKRDataSource.get_ticker | ticker price | IBKRClient.get_ticker_price | Yes | FLOWING |
| DataSourceFactory.get_source | datasource | IBKRDataSource() | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| IBKRDataSource import | `python -c "from app.data_sources.ibkr import IBKRDataSource; print('OK')"` | Import OK | PASS |
| DataSourceFactory with exchange_id | `python -c "from app.data_sources.factory import DataSourceFactory; s = DataSourceFactory.get_source('Crypto', exchange_id='ibkr-live'); print(type(s).__name__)"` | IBKRDataSource | PASS |
| Rate limiter import | `python -c "from app.data_sources.rate_limiter import get_ibkr_limiter; print('OK')"` | OK | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| IBKR-01 | 01-01 | Create IBKRDataSource class | SATISFIED | Class created with connection management |
| IBKR-02 | 01-02 | get_kline() implementation | SATISFIED | Method returns correct format with cache |
| IBKR-03 | 01-03 | get_ticker() implementation | SATISFIED | Method returns real-time price, no cache |
| IBKR-04 | 01-01 | Connection management | SATISFIED | connect/disconnect/reconnect methods |
| INT-01 | 01-05 | DataSourceFactory supports exchange_id | SATISFIED | exchange_id parameter added |
| INT-02 | 01-05 | trading_executor uses exchange_id | **BLOCKED** | price_fetcher doesn't pass exchange_id |
| INT-03 | 01-05 | exchange_id='ibkr-live' uses IBKRDataSource | **BLOCKED** | INT-02 blocked this |

### Anti-Patterns Found

No significant anti-patterns detected. Code is substantive with proper error handling.

### Human Verification Required

None - all verifications can be done programmatically.

### Gaps Summary

The phase implemented IBKRDataSource with get_kline(), get_ticker(), and rate limiting. The DataSourceFactory integration is complete - when called directly with exchange_id='ibkr-live', it correctly returns IBKRDataSource.

**The critical gap:** The integration path from trading_executor to DataSourceFactory via PriceFetcher does NOT pass exchange_id. When strategies use price_fetcher.fetch_current_price() (the standard path for getting prices in trading_executor), the exchange_id is never passed to DataSourceFactory.get_ticker(). This means strategies with exchange_id='ibkr-live' will NOT automatically use IBKRDataSource - they will fall back to the default market-based data source.

**Root cause:** PriceFetcher.fetch_current_price() accepts market_category but not exchange_id. The method signature needs exchange_id added, and DataSourceFactory.get_ticker()/get_kline() need to accept and use the exchange_id parameter.

**Affected files:**
- `backend_api_python/app/services/price_fetcher.py` - needs exchange_id parameter
- `backend_api_python/app/data_sources/factory.py` - needs exchange_id in get_ticker/get_kline (currently only in get_source)

---

_Verified: 2026-04-08T18:00:00Z_
_Verifier: Claude (gsd-verifier)_
