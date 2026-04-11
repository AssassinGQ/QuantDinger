---
phase: 11-strategy-automation-forex-ibkr
plan: "03"
subsystem: testing
tags: [pytest, ibkr, forex, ib_insync, mock]

requires:
  - phase: 10-fills-position-pnl-events
    provides: IBKR callback handlers and records helpers exercised by smoke paths
provides:
  - Mock IBKR Paper smoke module for EURUSD, GBPJPY, XAGUSD (open+close per pair)
  - UC-SA-SMK-01–03 automated coverage without live TWS
affects:
  - verify-work
  - RUNT-03 evidence (supplementary; phase 11 has additional plans)

tech-stack:
  added: []
  patterns: "Reuse _make_client_with_mock_ib; wire _FakeEvent for += registration; direct handler calls in plausible Paper order"

key-files:
  created:
    - backend_api_python/tests/test_ibkr_forex_paper_smoke.py
  modified: []

key-decisions:
  - "Used market_type=\"Forex\" (not lowercase) so ForexNormalizer applies per get_normalizer"
  - "Invoked _on_order_status / _on_exec_details / _on_position / _on_pnl_single directly after each mocked fill to match client handler contracts without full ib_insync Event semantics"

patterns-established:
  - "Pair-specific qualifyContractsAsync sets conId and localSymbol (EURUSD 12087792/EUR.USD; GBPJPY 12345678/GBP.JPY; XAGUSD 87654321/XAGUSD)"

requirements-completed: []

# Metrics
duration: 12min
completed: 2026-04-11
---

# Phase 11 Plan 03: Mock IBKR Paper Forex smoke Summary

**Dedicated pytest module simulates qualify → placeOrder → fill → position → PnL handler ordering for three Forex pairs with zero live IBKR connectivity.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-04-11T00:00:00Z (approx.)
- **Completed:** 2026-04-11
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Added `test_ibkr_forex_paper_smoke.py` with three tests (UC-SA-SMK-01–03) covering EURUSD, GBPJPY, and XAGUSD open+close cycles.
- Mocked `qualifyContractsAsync` to mutate contracts per pair; asserted `placeOrder` runs twice per test and `LiveOrderResult.success` for both legs.
- Patched `ibkr_save_position` / `ibkr_save_pnl` to avoid DB; wired lightweight fake IB events so `_register_events` succeeds.

## Task Commits

1. **Task 1: test_ibkr_forex_paper_smoke.py — three pairs, open+close, mocked IB** - `047a773` (test)

**Plan metadata:** `403c443` (docs: complete plan)

## Files Created/Modified

- `backend_api_python/tests/test_ibkr_forex_paper_smoke.py` — Mock Paper smoke: `_FakeEvent`, pair-specific qualify, `_fire_callbacks_after_fill` sequence.

## Decisions Made

- Followed `test_ibkr_client` helpers for mock IB and client skeleton; duplicated event wiring in smoke file for standalone clarity.
- Did not mark requirement **RUNT-03** complete in REQUIREMENTS.md — it spans Phase 11 until **11-02** (E2E) and full verification.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Smoke proof for UC-SA-SMK-01–03 is in place; Phase 11 still needs **11-02** (E2E + runbook) for full RUNT-03 closure alongside validation already delivered in 11-01.

## Self-Check: PASSED

- `backend_api_python/tests/test_ibkr_forex_paper_smoke.py` exists.
- `047a773` (test module) is an ancestor of `HEAD`; planning updates in `04c7148` and follow-up docs commits.

---
*Phase: 11-strategy-automation-forex-ibkr*
*Completed: 2026-04-11*
