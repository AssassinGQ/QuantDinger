---
phase: 16-precious-metals-contract-classification
plan: 03
subsystem: testing
tags: [pytest, IBKR, Metals, CMDTY, TRADE-04]

requires:
  - phase: 16-02
    provides: IBKRClient Metals CMDTY/SMART, symbol Metals routing, ForexPreNormalizer for Metals
provides:
  - Engine + strategy API tests asserting Metals in supported set and ibkr-paper + XAUUSD create
  - Paper smoke XAGUSD path with CMDTY qualify and Metals market_category
  - E2E worker chain with market_category Metals and CMDTY contract assertions on placeOrder
affects: [phase-17-forex-limit-orders, phase-18-e2e]

tech-stack:
  added: []
  patterns:
    - "Qualify mocks pass sec_type=CASH vs CMDTY; CMDTY sets exchange SMART on contract"
    - "Integration tests thread market_category Metals through smoke and E2E like Forex"

key-files:
  created: []
  modified:
    - backend_api_python/tests/test_exchange_engine.py
    - backend_api_python/tests/test_strategy_exchange_validation.py
    - backend_api_python/tests/test_ibkr_forex_paper_smoke.py
    - backend_api_python/tests/test_forex_ibkr_e2e.py

key-decisions:
  - "XAGUSD research conId 77124483 used in smoke/E2E mocks (replacing placeholder 87654321)."
  - "_run_open_close_cycle returns place_calls list for assertions without breaking EURUSD/GBPJPY defaults."

patterns-established:
  - "UC-16-T5/T6/T7 tables map to named pytest tests for TRADE-04 traceability."

requirements-completed: [TRADE-04]

duration: 18min
completed: 2026-04-12
---

# Phase 16 Plan 03: Integration tests for Metals (TRADE-04) Summary

**Engine and strategy validation plus paper smoke and full worker E2E assert `Metals` + CMDTY/SMART for XAGUSD alongside unchanged Forex EURUSD paths.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-04-12T04:40:00Z
- **Completed:** 2026-04-12T04:47:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- `test_exchange_engine`: frozenset includes `Metals`; `test_uc_16_t5_01` / `test_uc_16_t5_02` for supported set and `validate_market_category_static`.
- `test_strategy_exchange_validation`: `_metals_payload` + `test_uc_16_t5_03` for `ibkr-paper` + XAUUSD.
- `test_ibkr_forex_paper_smoke`: `_make_qualify_for_pair(..., sec_type=)`; XAGUSD uses Metals + CMDTY; `place_calls[0].contract.secType == "CMDTY"`.
- `test_forex_ibkr_e2e`: XAGUSD chain uses `market_category: "Metals"`, qualify CMDTY, asserts symbol/exchange on open and close legs.

## Task Commits

Each task was committed atomically:

1. **Task 1: test_exchange_engine + test_strategy_exchange_validation — Metals supported** — `8ac6cd7` (test)
2. **Task 2: test_ibkr_forex_paper_smoke — XAGUSD Metals + CMDTY qualify** — `fa84c1e` (test)
3. **Task 3: test_forex_ibkr_e2e — XAGUSD E2E Metals + CMDTY** — `7c693de` (test)

**Plan metadata:** docs commit on `main` after task commits (SUMMARY, STATE, ROADMAP).

## Files Created/Modified

- `backend_api_python/tests/test_exchange_engine.py` — UC-16-T5 engine assertions for Metals
- `backend_api_python/tests/test_strategy_exchange_validation.py` — `_metals_payload`, UC-16-T5-03 API path
- `backend_api_python/tests/test_ibkr_forex_paper_smoke.py` — qualify sec_type, `_run_open_close_cycle` kwargs + place_calls
- `backend_api_python/tests/test_forex_ibkr_e2e.py` — Metals config + CMDTY qualify + contract field asserts

## Decisions Made

- Followed 16-RESEARCH conId **77124483** for XAGUSD in mocks (was inconsistent placeholder).
- Returned `(r_open, r_close, place_calls)` from `_run_open_close_cycle` so smoke tests can assert `secType` without duplicating placeOrder wiring.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 16 all three plans complete; TRADE-04 covered at client (16-02) and integration (16-03) layers.
- Ready to proceed with Phase 17 (Forex limit orders) per roadmap dependencies.

## Self-Check: PASSED

- `16-03-SUMMARY.md` exists at `.planning/phases/16-precious-metals-contract-classification/16-03-SUMMARY.md`
- Commits `8ac6cd7`, `fa84c1e`, `7c693de` present in `git log`
- Four-module pytest: 60 passed; full backend: 992 passed, 11 skipped

---
*Phase: 16-precious-metals-contract-classification*
*Completed: 2026-04-12*
