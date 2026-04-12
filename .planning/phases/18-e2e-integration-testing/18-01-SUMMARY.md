---
phase: 18-e2e-integration-testing
plan: "01"
subsystem: testing
tags: [pytest, flask, ibkr, mock, helpers]

requires:
  - phase: 17-forex-limit-orders-automation
    provides: limit-order E2E paths and client behavior exercised by existing tests
provides:
  - Shared `tests/helpers/ibkr_mocks.py` (events, qualify stubs, `_make_ibkr_client_for_e2e`, `patched_records`)
  - `tests/helpers/flask_strategy_app.py` (`make_strategy_test_app` with `/api` + `g.user_id=1`)
  - `conftest.py` fixtures `strategy_client` and registered `patched_records`
affects:
  - 18-02 through 18-06 E2E modules (import helpers instead of copy-paste)

tech-stack:
  added: []
  patterns:
    - "Central IBKR test doubles under `backend_api_python/tests/helpers/`"
    - "Flask strategy E2E: noop `login_required` + `importlib.reload(strategy)` before blueprint register"

key-files:
  created:
    - backend_api_python/tests/helpers/__init__.py
    - backend_api_python/tests/helpers/ibkr_mocks.py
    - backend_api_python/tests/helpers/flask_strategy_app.py
  modified:
    - backend_api_python/tests/conftest.py
    - backend_api_python/tests/test_ibkr_forex_paper_smoke.py
    - backend_api_python/tests/test_forex_ibkr_e2e.py

key-decisions:
  - "Re-export `_make_mock_ib_insync` / `_make_client_with_mock_ib` / `_make_trade_mock` from `tests.test_ibkr_client` inside `ibkr_mocks` so consumers have one import path."
  - "`patched_records` lives on `ibkr_mocks` and is imported in `conftest` so smoke and E2E share one fixture definition."
  - "Removed module-level Flask auth patch from `test_forex_ibkr_e2e.py`; HTTP test uses `strategy_client` built via `flask_strategy_app` (same behavior as legacy inline fixture)."

patterns-established:
  - "Phase 18 E2E tests should import mocks from `tests.helpers.ibkr_mocks` and HTTP clients from `strategy_client`."

requirements-completed: []

duration: 8min
completed: 2026-04-12
---

# Phase 18 Plan 01: Shared IBKR mocks + Flask strategy fixture Summary

**Centralized IBKR paper/E2E mocks under `tests/helpers/`, a reusable Flask `strategy_bp` factory at `/api`, and `conftest` `strategy_client` — refactors smoke and legacy forex E2E imports without changing assertions.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-04-12T08:17:00Z
- **Completed:** 2026-04-12T08:28:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added `tests/helpers/ibkr_mocks.py` with shared `_FakeEvent`, wire/fill/callback helpers, `_make_ibkr_client_for_e2e`, and `patched_records`.
- Added `flask_strategy_app.make_strategy_test_app()` matching legacy E2E setup (noop login, reload strategy, `register_blueprint(..., url_prefix="/api")`, `g.user_id=1`).
- Exposed `strategy_client` and shared `patched_records` via `conftest.py`; refactored `test_ibkr_forex_paper_smoke.py` and `test_forex_ibkr_e2e.py` to use helpers only (no assertion drift).

## Task Commits

1. **Task 1: Add tests/helpers/ibkr_mocks.py and switch paper smoke imports** — `73d701d` (feat)
2. **Task 2: flask_strategy_app factory, conftest fixture, refactor test_forex_ibkr_e2e imports** — `3f3540e` (feat)

**Plan metadata:** docs commit bundles SUMMARY + STATE + ROADMAP (see `git log -1 --oneline` on completion).

## Files Created/Modified

- `backend_api_python/tests/helpers/__init__.py` — package marker
- `backend_api_python/tests/helpers/ibkr_mocks.py` — IBKR mocks + `patched_records` fixture
- `backend_api_python/tests/helpers/flask_strategy_app.py` — Flask app factory for strategy routes
- `backend_api_python/tests/conftest.py` — `patched_records` re-export, `strategy_client` fixture
- `backend_api_python/tests/test_ibkr_forex_paper_smoke.py` — imports from helpers; shared `patched_records` via conftest
- `backend_api_python/tests/test_forex_ibkr_e2e.py` — imports from helpers; API test uses `strategy_client`

## Decisions Made

- Followed 18-CONTEXT: helpers under `backend_api_python/tests/helpers/`; E2E logic unchanged aside from imports and fixture wiring.
- Phase-level requirement IDs TRADE-05, TRADE-06, TEST-02 in plan frontmatter map to the whole Phase 18 outcome; they remain **pending** until later 18-0x plans ship (not marked complete in REQUIREMENTS.md for this plan alone).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- Foundation for new Phase 18 E2E modules: import `tests.helpers.ibkr_mocks` and `strategy_client` instead of duplicating setup.

## Self-Check: PASSED

- `backend_api_python/tests/helpers/ibkr_mocks.py` exists (245 lines).
- `backend_api_python/tests/helpers/flask_strategy_app.py` exists.
- Commits `73d701d` and `3f3540e` (task work) and docs commit with SUMMARY/STATE/ROADMAP present on branch.

---
*Phase: 18-e2e-integration-testing · Plan 01 · Completed: 2026-04-12*
