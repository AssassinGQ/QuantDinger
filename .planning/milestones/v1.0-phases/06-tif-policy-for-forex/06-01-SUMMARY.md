---
phase: 06-tif-policy-for-forex
plan: 01
subsystem: api
tags: [ibkr, forex, tif, ioc, idealpro, pytest]

requires:
  - phase: 05-signal-to-side-mapping-two-way-fx
    provides: Forex signal-to-side mapping (EXEC-02)
provides:
  - Forex-only `_get_tif_for_signal` branch returning IOC for all eight signal types
  - Documented TIF policy vs USStock/HShare in client docstring
  - Locked use-case tests UC-T1–T8, UC-E1–E3, and Forex order-path IOC assertions
affects:
  - Phase 7 (Forex market orders) and any execution path that relies on TIF for IDEALPRO

tech-stack:
  added: []
  patterns:
    - "Forex TIF: early return IOC before equity open/close logic"

key-files:
  created: []
  modified:
    - backend_api_python/app/services/live_trading/ibkr_trading/client.py
    - backend_api_python/tests/test_ibkr_client.py

key-decisions:
  - "Forex uses IOC for every signal type (open/add/close/reduce × long/short); equity rules unchanged."

patterns-established:
  - "TestTifForexPolicy parametrize ids uc_t1–uc_t8 for grep-friendly UC traceability"

requirements-completed: [EXEC-03]

duration: 5min
completed: 2026-04-10
---

# Phase 6 Plan 1: TIF policy for Forex Summary

**Forex `_get_tif_for_signal` early-returns IOC for all signals; USStock/HShare behavior unchanged; tests lock UC-T1–T8, UC-E1–E3, and mocked order `tif` for market/limit Forex paths.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-10T03:55:00Z
- **Completed:** 2026-04-10T04:00:00Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Production: `market_type == "Forex"` branch returns `"IOC"` before equity TIF logic; docstring documents Forex vs non-Forex rules.
- Tests: `TestTifForexPolicy` covers eight Forex signals, three equity regressions, and two integration tests asserting `placeOrder` receives IOC on market and limit Forex orders.
- REGR-01: full `backend_api_python/tests/` suite passed (869 passed, 11 skipped).

## Task Commits

Each task was committed atomically:

1. **Task 1: Production + tests — UC-T1–T8, UC-E1–E3, REGR-01** — `08f2151` (feat)

**Plan metadata:** Same docs commit as STATE/ROADMAP/REQUIREMENTS (`docs(06-01): complete TIF policy for Forex plan`).

## Files Created/Modified

- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — Forex IOC early return; updated `_get_tif_for_signal` docstring.
- `backend_api_python/tests/test_ibkr_client.py` — `TestTifForexPolicy`; TIF section header and `TestTifDay` docstring clarified for USStock scope.

## Decisions Made

- Followed locked research/context: Forex → IOC everywhere on IDEALPRO automation (no DAY rest on open paths for FX).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- EXEC-03 satisfied; Phase 7 can assume Forex orders receive IOC TIF from `_get_tif_for_signal`.
- Paper trading may still inform fine-tuning; policy is encoded in code and tests.

---
*Phase: 06-tif-policy-for-forex*
*Completed: 2026-04-10*

## Self-Check: PASSED

- `06-01-SUMMARY.md` exists at `.planning/phases/06-tif-policy-for-forex/06-01-SUMMARY.md`
- Commit `08f2151` present in history for feat(06-01)
- Full suite REGR-01: 869 passed, 11 skipped (2026-04-10 run)
