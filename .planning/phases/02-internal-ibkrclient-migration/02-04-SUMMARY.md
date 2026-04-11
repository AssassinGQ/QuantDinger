---
phase: "02"
plan: "04"
subsystem: data_sources
tags: [ibkr, e2e, migration, test]
dependency_graph:
  requires:
    - 02-01
    - 02-02
    - 02-03
  provides:
    - IBKRDataSource fully migrated to internal IBKRClient
    - Zero ibkr_datafetcher references in codebase
    - E2E test suite with mocked ib_insync
  affects:
    - backend_api_python/tests/test_ibkr_datasource.py
    - backend_api_python/tests/test_ibkr_e2e.py
tech_stack:
  added:
    - unittest.mock.AsyncMock (for async ib_insync method mocks)
  patterns:
    - E2E chain testing: DataSourceFactory -> IBKRDataSource -> IBKRClient -> ib_insync.IB
    - Mock ib_insync at module level using lambda factory
key_files:
  created:
    - backend_api_python/tests/test_ibkr_e2e.py
  modified:
    - backend_api_python/tests/test_ibkr_datasource.py
decisions:
  - Removed unused `from ibkr_datafetcher.types import KlineBar, resolve_timeframe` import from test_ibkr_datasource.py (line 174) — these names were never used in the test body
  - E2E tests mock ib_insync.IB using a lambda factory pattern so `IB()` returns the fully-configured mock instance
  - `qualifyContractsAsync` (plural) must be mocked as AsyncMock — the internal client calls this method (not `qualifyContractAsync`)
  - `ticker.last = 0.0` maps to `get_quote` returning `{"success": True, "last": None}` to distinguish zero-price from unknown-price
metrics:
  duration: ~3 min (full test suite)
  completed_date: 2026-04-11
---

# Phase 2 Plan 4: IBKRClient Migration Cleanup and Verification Summary

## One-liner

Removed the last ibkr_datafetcher import and added a 7-test E2E suite verifying the complete DataSourceFactory-to-ib_insync chain with mocked async methods.

## Context

The source code migration to internal IBKRClient was completed in prior plans (02-01, 02-02, 02-03). This plan performs the final cleanup: removing the last external dependency reference and adding comprehensive E2E tests to verify the chain is wired correctly.

## What Was Built

### Task 1: Audit for remaining ibkr_datafetcher imports
- Confirmed only one reference remained: `test_ibkr_datasource.py:174`
- No source files referenced ibkr_datafetcher (migration was already complete)

### Task 2: Remove ibkr_datafetcher import
- Deleted `from ibkr_datafetcher.types import KlineBar, resolve_timeframe` from `test_ibkr_datasource.py`
- Neither `KlineBar` nor `resolve_timeframe` was used anywhere in the test body (plain dicts used instead)
- Result: zero ibkr_datafetcher references in the entire codebase

### Task 3: E2E test suite (test_ibkr_e2e.py)
Created `backend_api_python/tests/test_ibkr_e2e.py` with 7 tests:

| Test | What it verifies |
|------|-----------------|
| `test_e2e_get_kline_returns_correct_format` | Full chain returns list of kline dicts with correct keys/types |
| `test_e2e_get_kline_with_empty_bars` | Returns empty list when ib_insync returns no bars |
| `test_e2e_get_ticker_returns_correct_format` | Full chain returns dict with 'last' key |
| `test_e2e_get_ticker_with_zero_price` | Returns `{'last': None}` when ticker.last is 0.0 |
| `test_e2e_factory_returns_ibkr_datasource` | `exchange_id='ibkr-live'` returns IBKRDataSource instance |
| `test_e2e_kline_uses_internal_client` | `reqHistoricalBarsAsync` called on mock (proof of internal client usage) |
| `test_e2e_ticker_uses_internal_client` | `reqMktData` called on mock (proof of internal client usage) |

**Mock setup key decisions:**
- `ib_insync.IB` patched at `app.services.live_trading.ibkr_trading.client.ib_insync` using a lambda factory so `IB()` returns the configured mock instance
- `qualifyContractsAsync` (plural, not singular) — must be `AsyncMock` since it's awaited internally
- `reqPositionsAsync` — also awaited during connect; added to prevent "object MagicMock can't be used in 'await'" errors
- `reqHistoricalBarsAsync` and `connectAsync` also `AsyncMock`

### Task 4: Pre-existing test fix (Rule 1 - auto-fix bug)
- `test_get_kline_returns_empty_when_not_connected_and_connect_fails` was hitting the real database cache (returning 100 items)
- Fixed by wrapping the call in `patch('app.data_sources.ibkr.kline_fetcher')` with a cache-miss return value

## Deviations from Plan

### Rule 1 (Bug) - Pre-existing test isolation fix
- **Found during:** Task 4
- **Issue:** `test_get_kline_returns_empty_when_not_connected_and_connect_fails` did not mock `kline_fetcher.get_kline`, causing it to hit the real database cache and return 100 items instead of 0
- **Fix:** Added `with patch('app.data_sources.ibkr.kline_fetcher') as mock_fetcher: mock_fetcher.get_kline.return_value = []`
- **Files modified:** `backend_api_python/tests/test_ibkr_datasource.py`
- **Commit:** Same as Task 2 commit (8ae381f)

## Test Results

```
25 passed in 141.35s (0:02:21)
```

All tests pass including:
- 18 original tests in `test_ibkr_datasource.py`
- 7 new E2E tests in `test_ibkr_e2e.py`

## Final Verification

```bash
$ grep -rn "ibkr_datafetcher" backend_api_python/ --include="*.py"
# (no output — PASS)

$ grep -n "get_ibkr_client" backend_api_python/app/data_sources/ibkr.py
11:from app.services.live_trading.ibkr_trading.client import get_ibkr_client, IBKRConfig
56:            self._client = get_ibkr_client(cfg, mode=self._mode)
```

## Requirements Satisfied

| Requirement | Status |
|-------------|--------|
| INT-04: IBKRDataSource uses internal IBKRClient | Complete (confirmed in ibkr.py) |
| INT-05: Remove ibkr_datafetcher dependency | Complete (zero references remain) |

## Self-Check

- `backend_api_python/tests/test_ibkr_e2e.py` exists: YES
- `backend_api_python/tests/test_ibkr_datasource.py` has no ibkr_datafetcher import: YES
- Commit 8ae381f exists: YES
- 25 tests pass: YES
