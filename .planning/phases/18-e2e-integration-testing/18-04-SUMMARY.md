---
phase: 18-e2e-integration-testing
plan: "04"
subsystem: testing
tags: [pytest, ibkr, USStock, HShare, e2e, pending_order_worker]

requires:
  - phase: 18-e2e-integration-testing
    provides: shared `tests/helpers/ibkr_mocks.py` and `patched_records` from 18-01
provides:
  - `test_e2e_cross_market_usstock_hshare_ibkr.py` with USStock/HShare market chains and USStock limit path
affects:
  - regression gate for IBKR cross-market worker routing

tech-stack:
  added: []
  patterns:
    - "Cross-market E2E mirrors `test_forex_ibkr_e2e` patch stack: `load_strategy_configs`, `create_client`, `mark_order_*`, `_notify_live_best_effort`, `_make_mock_ib_insync`"

key-files:
  created:
    - backend_api_python/tests/test_e2e_cross_market_usstock_hshare_ibkr.py
  modified: []

key-decisions:
  - "HShare uses symbol `0700.HK` with STK qualify stub and asserts `exchange == SEHK` on the placed contract."
  - "USStock limit E2E uses `_make_ibkr_client_for_e2e(..., sec_type=\"STK\", min_tick=0.01)` and asserts BUY floor snap + DAY TIF like Forex limit tests."

patterns-established:
  - "Cross-market full-chain tests call `PendingOrderWorker._execute_live_order` with `market_category`/`market_type` from `load_strategy_configs` matching production casing (`usstock`/`hshare`)."

requirements-completed: [TRADE-05, TRADE-06]

duration: 10min
completed: 2026-04-12
---

# Phase 18 Plan 04: USStock/HShare cross-market IBKR E2E Summary

**Mock IBKR full-chain tests for USStock (AAPL) and HShare (`0700.HK`) market orders plus a USStock limit order with minTick snap — extending TRADE-05/TRADE-06 beyond Forex/Metals.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-12T12:00:00Z
- **Completed:** 2026-04-12T12:10:00Z
- **Tasks:** 2
- **Files modified:** 1 (new test module)

## Accomplishments

- Added `test_cross_market_usstock_open_long_full_chain` and `test_cross_market_hshare_open_long_full_chain` exercising Worker → `StatefulClientRunner` → `IBKRClient.place_market_order` with STK contracts (SMART vs SEHK).
- Added `test_cross_market_usstock_limit_order_submitted` for `place_limit_order` with `min_tick=0.01`, DAY TIF, and BUY-side price snap (TRADE-06 docstring).

## Task Commits

1. **Task 1: USStock + HShare market-order full chain** — `07f8bfa` (feat)
2. **Task 2: USStock limit-order cross-market E2E (TRADE-06)** — `a0ac21b` (feat)

**Plan metadata:** final `docs(18-04)` commit records SUMMARY + STATE + ROADMAP.

## Files Created/Modified

- `backend_api_python/tests/test_e2e_cross_market_usstock_hshare_ibkr.py` — three E2E tests with shared IBKR mock helpers

## Decisions Made

- Followed `test_forex_ibkr_e2e.py` and `test_uc_sa_e2e_regr_usstock_full_chain` for `order_row`/`payload` shape and `load_strategy_configs` return dict.
- Implemented USStock limit coverage (no `pytest.skip`) because `StatefulClientRunner` and `place_limit_order` already support USStock with automation DAY TIF.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Cross-market E2E file is in place; continue Phase 18 plans 18-02/03/06 as roadmap dictates (ordering may differ from filename sequence).

## Self-Check: PASSED

- `backend_api_python/tests/test_e2e_cross_market_usstock_hshare_ibkr.py` exists (100+ lines).
- Commits `07f8bfa`, `a0ac21b` present on branch.

---
*Phase: 18-e2e-integration-testing*
*Completed: 2026-04-12*
