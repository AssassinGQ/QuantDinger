---
phase: 07-forex-market-orders
plan: "01"
subsystem: testing
tags: [ibkr, forex, idealpro, pytest, mock, place_market_order]

requires:
  - phase: 06-tif-policy-for-forex
    provides: Forex IOC TIF policy and TestTifForexPolicy patterns
provides:
  - Forex-specific user message when aligned quantity is zero (market + limit)
  - TestPlaceMarketOrderForex mock-IB coverage for UC-M1–M3, UC-E1–E3, UC-R1–R2
affects:
  - phase-08-quantity-normalization
  - EXEC-01 verification in REQUIREMENTS.md

tech-stack:
  added: []
  patterns:
    - "Forex qty<=0: shared prefix + IDEALPRO minimum-size hint only when market_type == Forex"
    - "Lot-size cache cleared after UC-E2 to avoid conId collision across tests"

key-files:
  created: []
  modified:
    - backend_api_python/app/services/live_trading/ibkr_trading/client.py
    - backend_api_python/tests/test_ibkr_client.py

key-decisions:
  - "Appended exact substring `For Forex (IDEALPRO), the amount may be below the minimum tradable size for this pair.` after the existing non-Forex alignment message for Forex only."

patterns-established:
  - "TestPlaceMarketOrderForex: one method per UC; @patch ib_insync; _make_client_with_mock_ib; assert placeOrder args for CASH/IOC"

requirements-completed: [EXEC-01]

duration: 12min
completed: 2026-04-10
---

# Phase 7 Plan 01: Forex market orders Summary

**Mock-IB integration tests lock Forex `place_market_order` (EURUSD, GBPJPY, XAUUSD) with IOC and CASH contracts; Forex-only IDEALPRO hint when lot alignment yields zero quantity; USStock/HShare DAY TIF regressions.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-04-10T07:10:00Z
- **Completed:** 2026-04-10T07:22:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Forex `place_market_order` and `place_limit_order` return an extended message when `qty <= 0` after alignment and `market_type == "Forex"`, without changing non-Forex text.
- `TestPlaceMarketOrderForex` encodes UC-M1–M3 (happy paths), UC-E1–E3 (qualify fail, alignment zero, normalizer zero), and UC-R1–R2 (equity TIF unchanged).
- Full `pytest tests/` suite green (REGR-01).

## Task Commits

Each task was committed atomically:

1. **Task 1: Forex qty<=0 message after alignment (place_market_order + place_limit_order)** — `3d38941` (feat)
2. **Task 2: TestPlaceMarketOrderForex — UC-M1–M3, UC-E1–E3, UC-R1–R2, REGR-01** — `f327dcb` (test)

## Files Created/Modified

- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — Forex branch for zero aligned quantity in market and limit orders.
- `backend_api_python/tests/test_ibkr_client.py` — `TestPlaceMarketOrderForex` plus `types` import; UC-E2 clears `IBKRClient._lot_size_cache` in `finally` to avoid cross-test pollution.

## Decisions Made

- Followed plan’s exact IDEALPRO hint string and kept the original non-Forex message unchanged for USStock/HShare.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Class-level `_lot_size_cache` leaked UC-E2 increment to later tests sharing `conId`**

- **Found during:** Task 2 (UC-R1 failed: `placeOrder` never called)
- **Issue:** After UC-E2, `con_id` 1 cached `sizeIncrement=25000`, so USStock AAPL with qty 100 aligned to 0 and skipped `placeOrder`.
- **Fix:** Wrapped UC-E2 in `try`/`finally` and call `IBKRClient._lot_size_cache.clear()` in `finally`.
- **Files modified:** `backend_api_python/tests/test_ibkr_client.py`
- **Verification:** `pytest tests/test_ibkr_client.py -k PlaceMarketOrderForex` and full `pytest tests/` pass.
- **Committed in:** `f327dcb`

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug)

## Issues Encountered

None beyond the cache isolation issue above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- EXEC-01 satisfied; Phase 8 can build on `_align_qty_to_contract` + normalizer with the same mock patterns.

## Self-Check: PASSED

- `07-01-SUMMARY.md` present at `.planning/phases/07-forex-market-orders/07-01-SUMMARY.md`
- Commits `3d38941`, `f327dcb` on branch

---
*Phase: 07-forex-market-orders*
*Completed: 2026-04-10*
