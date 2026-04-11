---
phase: 09-forex-trading-hours-liquidhours
plan: 01
subsystem: testing
tags: [pytest, forex, liquidHours, is_rth_check, IBKR, RUNT-01]

requires:
  - phase: 08-quantity-normalization-ib-alignment
    provides: Qualified Forex contracts and sizing path used unchanged by RTH checks
provides:
  - UC-FX-L01–L09 unit tests on parse_liquid_hours / is_rth_check
  - Forex-specific is_market_open closed reason (24/5, weekend/maintenance)
  - UC-FX-I01–I05 TestForexRTHGate integration with real is_rth_check
affects:
  - phase-10-fills-pnl
  - operators diagnosing Forex vs equity RTH messages

tech-stack:
  added: []
  patterns:
    - "pytest autouse `wraps=` on trading_hours.is_rth_check to override module autouse mock"
    - "Clear IBKRClient._rth_details_cache + trading_hours fuse between Forex integration tests"

key-files:
  created: []
  modified:
    - backend_api_python/tests/test_trading_hours.py
    - backend_api_python/tests/conftest.py
    - backend_api_python/app/services/live_trading/ibkr_trading/client.py
    - backend_api_python/tests/test_ibkr_client.py

key-decisions:
  - "Forex closed reason appends one English sentence mentioning Forex 24/5 and weekend or daily maintenance (non-Forex paths unchanged)"

patterns-established:
  - "TestForexLiquidHours + @pytest.mark.Forex; TestForexRTHGate + @pytest.mark.ForexRTH"

requirements-completed: [RUNT-01]

duration: 25min
completed: 2026-04-11
---

# Phase 9 Plan 1: Forex liquidHours & messaging summary

**Forex `is_market_open` locked to IBKR `liquidHours` via `is_rth_check`, with UC-FX-L/I tests and operator-facing 24/5 closed messaging distinct from equity RTH.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-11T03:33:00Z (approx.)
- **Completed:** 2026-04-11T03:42:00Z (approx.)
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Nine pure-logic Forex schedule cases (cross-day, Fri/Sun, maintenance gap, CLOSED, JST, XAGUSD) in `TestForexLiquidHours`.
- Production tweak: when `market_type == "Forex"` and outside liquid hours, the returned reason adds Forex 24/5 weekend/maintenance context.
- Five integration tests exercise `is_market_open` end-to-end with real `is_rth_check` (autouse mock overridden via `wraps`).

## Task Commits

1. **Task 1: UC-FX-L01–L09 pure logic tests** — `dd77e35` (test)
2. **Task 2: Forex closed message in client.py** — `f60e3d9` (feat)
3. **Task 3: UC-FX-I01–I05 TestForexRTHGate** — `5c114e1` (test)

**Plan metadata:** docs commit includes SUMMARY + STATE + ROADMAP + REQUIREMENTS (see repo `git log`)

## Files Created/Modified

- `backend_api_python/tests/test_trading_hours.py` — `TestForexLiquidHours` (UC-FX-L01–L09)
- `backend_api_python/tests/conftest.py` — register `Forex` / `ForexRTH` pytest marks
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — Forex branch on closed `reason` in `is_market_open`
- `backend_api_python/tests/test_ibkr_client.py` — `_make_forex_rth_client`, `TestForexRTHGate`, `_REAL_IS_RTH_CHECK_FN`

## Decisions Made

- Extended closed message uses a single appended phrase: **Forex 24/5: closed outside liquid hours (weekend or daily maintenance window).** — keeps base `"outside RTH (market closed)"` for all types; Forex-only suffix for operators.

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- RUNT-01 satisfied for mocked `liquidHours`; Phase 10 can assume stable RTH messaging for Forex diagnostics.

## Self-Check: PASSED

- `09-01-SUMMARY.md` present under `.planning/phases/09-forex-trading-hours-liquidhours/`
- Task commits `dd77e35`, `f60e3d9`, `5c114e1` verified on branch; planning docs committed after tasks

---
*Phase: 09-forex-trading-hours-liquidhours*
*Completed: 2026-04-11*
