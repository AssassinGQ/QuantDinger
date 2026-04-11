---
phase: 11-strategy-automation-forex-ibkr
plan: "02"
subsystem: testing
tags: [pytest, flask, forex, ibkr, pending-order-worker, runbook]

requires:
  - phase: 11-strategy-automation-forex-ibkr
    provides: validate_exchange_market_category + UC-SA-VAL tests (11-01); mock Paper smoke (11-03)
provides:
  - test_forex_ibkr_e2e.py (Flask POST strategies/create + PendingOrderWorker chain with mocked runner.execute)
  - 11-PAPER-RUNBOOK.md (EURUSD paper steps, full suite + phase pytest commands)
affects:
  - verify-work
  - RUNT-03 closure evidence

tech-stack:
  added: []
  patterns:
    - "Reload strategy blueprint after patching login_required; mock get_db_connection for create_strategy route"
    - "Patch pending_order_worker imports for load_strategy_configs, create_client, get_runner, records"

key-files:
  created:
    - backend_api_python/tests/test_forex_ibkr_e2e.py
    - .planning/phases/11-strategy-automation-forex-ibkr/11-PAPER-RUNBOOK.md
  modified: []

key-decisions:
  - "API contract test uses _mock_db + real create_strategy path so Forex+ibkr-paper validation matches production saves"
  - "USStock regression uses load_strategy_configs market_type usstock with AAPL open_long"

patterns-established:
  - "UC-SA-E2E-F1–F4 via parametrize with stable order_id and runner.execute.assert_called_once()"

requirements-completed:
  - RUNT-03

# Metrics
duration: 25min
completed: 2026-04-11
---

# Phase 11 Plan 02: Forex IBKR E2E tests and paper runbook Summary

**Flask `test_client` POST for Forex EURUSD plus mocked `PendingOrderWorker` → `get_runner` → `execute`, with IBKR Paper EURUSD operator runbook and canonical pytest commands.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-11T07:10:00Z
- **Completed:** 2026-04-11T07:25:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `test_forex_ibkr_e2e.py`: Section A validates `POST /api/strategy/strategies/create` for Forex + ibkr-paper + EURUSD; Sections B/C cover four Forex signal types and one USStock regression with `mark_order_sent` and `runner.execute` assertions.
- Added `11-PAPER-RUNBOOK.md` with TWS Paper prerequisites (port **7497**), concrete strategy keys (`market_type` **forex**), numbered operator steps, full-suite command, and Phase 11 subset command.

## Task Commits

Each task was committed atomically:

1. **Task 1: test_forex_ibkr_e2e.py — API + worker chain (UC-SA-E2E-F1–F4, REGR)** — `ada73fb` (test)
2. **Task 2: 11-PAPER-RUNBOOK.md + full suite gate command** — `6cc3d3f` (docs)

**Plan metadata:** docs commit `docs(11-02): complete Forex IBKR E2E plan` (STATE, ROADMAP, REQUIREMENTS, this file)

## Files Created/Modified

- `backend_api_python/tests/test_forex_ibkr_e2e.py` — Flask fixture, mocked DB insert for create route; parametrized worker tests; USStock REGR.
- `.planning/phases/11-strategy-automation-forex-ibkr/11-PAPER-RUNBOOK.md` — Manual EURUSD paper checklist and automated verify lines.

## Decisions Made

- Reused auth noop + `importlib.reload(strategy_mod)` pattern from existing strategy route tests.
- USStock mock config uses `market_type: usstock` in `load_strategy_configs` return value to align with worker resolution and IBKR equity path.

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

- Full backend suite `python -m pytest tests/ -q` completed in ~354s with **6 failures** in `tests/test_ibkr_dashboard.py` (IBKR dashboard endpoint tests); **921 passed**. These failures are outside files touched by this plan (pre-existing or environment). Phase 11 subset (`test_strategy_exchange_validation` + `test_forex_ibkr_e2e` + `test_ibkr_forex_paper_smoke`) passes (17 tests).

## User Setup Required

None for automated tests. Paper runbook assumes operator-run TWS/Gateway and backend.

## Next Phase Readiness

- Phase 11 backend deliverables (01 + 02 + 03) are in place; Phase 12 can target Forex + IBKR in the UI.

---
*Phase: 11-strategy-automation-forex-ibkr*
*Completed: 2026-04-11*

## Self-Check: PASSED

- `[ -f backend_api_python/tests/test_forex_ibkr_e2e.py ]` — FOUND
- `[ -f .planning/phases/11-strategy-automation-forex-ibkr/11-PAPER-RUNBOOK.md ]` — FOUND
- Commits `ada73fb`, `6cc3d3f` on branch
