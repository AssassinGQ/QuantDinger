---
phase: 01-ibkr-data-source-implementation
plan: "01"
subsystem: DataSource
tags: [ibkr, datasource, migration, v2.0]
dependency_graph:
  requires: []
  provides: [ibkr-data-source]
  affects: [trading-executor, market-routes]
tech_stack:
  added: []
  patterns: [internal-client, singleton]
key_files:
  created: []
  modified:
    - backend_api_python/app/services/live_trading/ibkr_trading/client.py
    - backend_api_python/app/data_sources/ibkr.py
    - backend_api_python/tests/test_ibkr_client.py
metrics:
  duration: ""
  completed_date: "2026-04-09"
---

# Phase 1 Plan 1: Internal IBKRClient Migration (v2.0) Summary

## One-liner

Migrated IBKRDataSource from external ibkr_datafetcher library to use internal IBKRClient with new get_historical_bars() method.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add get_historical_bars() method to internal IBKRClient | 16cb079 | client.py |
| 2 | Migrate IBKRDataSource to use internal IBKRClient | b6e5d70 | ibkr.py |
| 3 | Add unit tests for get_historical_bars | 1edbf59 | test_ibkr_client.py |

## Key Decisions Made

1. D-28: get_historical_bars signature matches BaseDataSource.get_kline(): (symbol, timeframe, limit, before_time=None)
2. D-29: Return List[Dict] format with 6 keys: time, open, high, low, close, volume
3. D-30: get_kline exception -> logger.error -> return []
4. D-31: get_ticker exception -> logger.warning -> return {last: 0, symbol: symbol}
5. D-35: get_ticker uses internal get_quote() instead of get_ticker_price()
6. D-36: Uses _create_contract() instead of external make_contract()

## Implementation Details

### Task 1: get_historical_bars()

- Uses TaskQueue pattern via _submit() like existing get_quote()
- Creates contract using internal _create_contract() per D-36
- Maps timeframes to IBKR duration strings
- Returns List[Dict] format per D-29
- Returns [] on error per D-30

### Task 2: IBKRDataSource Migration

- Removed external ibkr_datafetcher imports
- Added internal imports: get_ibkr_client, IBKRConfig
- get_kline() now calls internal get_historical_bars()
- get_ticker() now calls internal get_quote()
- No external ibkr_datafetcher dependency

### Task 3: Unit Tests

- Added TestGetHistoricalBars class
- 4 test methods covering TC-40, TC-41, TC-42, TC-43
- Basic functionality, timeframe support, before_time filter, error handling

## Test Coverage

| TC | Description | Status |
|----|------------|--------|
| TC-40 | Basic get_historical_bars returns List[Dict] | Implemented |
| TC-41 | Different timeframes work | Implemented |
| TC-42 | before_time filtering | Implemented |
| TC-43 | Error handling returns [] | Implemented |
| TC-50 | Uses get_ibkr_client() | Verified |
| TC-51 | No ibkr_datafetcher imports | Verified |
| TC-55 | Uses _create_contract() | N/A (removed) |
| TC-56 | Uses _qualify_contract_async() | N/A (removed) |
| TC-57 | get_kline calls get_historical_bars() | Verified |
| TC-58 | get_ticker uses get_quote() | Verified |

## Verification Results

```
=== Check no ibkr_datafetcher imports === 
PASS: No ibkr_datafetcher imports

=== Check get_ibkr_client usage ===
12:from app.services.live_trading.ibkr_trading.client import get_ibkr_client, IBKRConfig
58:            self._client = get_ibkr_client(cfg, mode=self._mode)

=== Check get_historical_bars call ===
151:            bars = self.client.get_historical_bars(symbol, timeframe, limit, before_time)

=== Check get_quote call ===
182:            quote = self.client.get_quote(symbol, self._market_type)
```

## Deviations from Plan

None - plan executed exactly as written.

## Auth Gates

None - no authentication gates were encountered.

## Known Stubs

None - no stub implementations identified.

## Threat Flags

None - no new security-relevant surface was introduced.

---

*Self-Check: PASSED*