---
phase: 15-normalize-pipeline-ordering
plan: 01
subsystem: infra
tags: [python, order-normalizer, MarketPreNormalizer, IBKR, pytest]

requires:
  - phase: 13-qualify-result-caching-e2e-prefix-fix
    provides: qualify cache and E2E API alignment (independent for this rename)
provides:
  - Canonical `MarketPreNormalizer` / `*PreNormalizer` with `pre_normalize` / `pre_check`
  - Factory `get_market_pre_normalizer` and shim re-exports under `ibkr_trading/order_normalizer`
  - Updated unit tests TC-15-T1 / TC-15-T5-01 / TC-15-T5-03
affects: [15-02, 15-03, 15-04, signal-executor, ibkr-client]

tech-stack:
  added: []
  patterns:
    - "INFRA-03 layer-1 naming: market pre-normalize vs later broker `align`"

key-files:
  created: []
  modified:
    - backend_api_python/app/services/live_trading/order_normalizer/__init__.py
    - backend_api_python/app/services/live_trading/order_normalizer/us_stock.py
    - backend_api_python/app/services/live_trading/order_normalizer/hk_share.py
    - backend_api_python/app/services/live_trading/order_normalizer/forex.py
    - backend_api_python/app/services/live_trading/ibkr_trading/order_normalizer/__init__.py
    - backend_api_python/app/services/live_trading/ibkr_trading/order_normalizer/us_stock.py
    - backend_api_python/app/services/live_trading/ibkr_trading/order_normalizer/hk_share.py
    - backend_api_python/app/services/live_trading/ibkr_trading/order_normalizer/forex.py
    - backend_api_python/app/services/live_trading/ibkr_trading/client.py
    - backend_api_python/app/services/signal_executor.py
    - backend_api_python/tests/test_order_normalizer.py

key-decisions:
  - "Call sites (`ibkr_trading/client.py`, `signal_executor.py`) updated in the same delivery as the rename so imports and methods stay consistent (not deferred to 15-02/03)."

patterns-established:
  - "Use `get_market_pre_normalizer` and `pre_normalize` / `pre_check` for market-layer quantity rules."

requirements-completed: []
# Plan frontmatter lists INFRA-03; full INFRA-03 (pipeline order) completes with Phase 15 plans 02–04 — not marked complete in REQUIREMENTS.md for this plan alone.

duration: 15min
completed: 2026-04-12
---

# Phase 15 Plan 01: Market pre-normalizer rename Summary

**Renamed the market-layer quantity helpers to `MarketPreNormalizer` / `*PreNormalizer` with `pre_normalize()` / `pre_check()`, factory `get_market_pre_normalizer()`, and updated pytest coverage; shim re-exports new symbols for incremental import migration.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-12T00:00:00Z (approx.)
- **Completed:** 2026-04-12T00:15:00Z (approx.)
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- Canonical package and per-market classes use `*PreNormalizer` and `pre_normalize` / `pre_check`.
- Temporary `ibkr_trading/order_normalizer` shim re-exports `MarketPreNormalizer`, `get_market_pre_normalizer`, and concrete `*PreNormalizer` types (removal in plan 15-04).
- IBKR client and signal executor call sites use the new factory and methods so runtime paths stay valid.
- `tests/test_order_normalizer.py` renamed per TC-15-T5; backward-compat test uses shim `get_market_pre_normalizer` + `pre_normalize`.

## Task Commits

1. **Task 1: Rename MarketPreNormalizer hierarchy in production modules** — `703986f` (feat)
2. **Task 2: Rename unit tests and factory test class** — `81d7b73` (test)

**Plan metadata:** Documentation commit bundles `15-01-SUMMARY.md`, `.planning/STATE.md`, and `.planning/ROADMAP.md` (see `git log` message `docs(15-01): complete MarketPreNormalizer rename plan`).

## Files Created/Modified

- `backend_api_python/app/services/live_trading/order_normalizer/__init__.py` — ABC, `CryptoPreNormalizer`, `get_market_pre_normalizer`
- `backend_api_python/app/services/live_trading/order_normalizer/us_stock.py` — `USStockPreNormalizer`
- `backend_api_python/app/services/live_trading/order_normalizer/hk_share.py` — `HSharePreNormalizer`
- `backend_api_python/app/services/live_trading/order_normalizer/forex.py` — `ForexPreNormalizer`
- `backend_api_python/app/services/live_trading/ibkr_trading/order_normalizer/*` — shim re-exports
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `pre_check` via factory
- `backend_api_python/app/services/signal_executor.py` — `pre_normalize` via factory
- `backend_api_python/tests/test_order_normalizer.py` — TC-15-T1 / TC-15-T5 coverage

## Decisions Made

- Updated `client.py` and `signal_executor.py` together with the rename so no dangling `get_normalizer` / `normalize` / `check` references remain (required for a green import graph).

## Deviations from Plan

### Scope addition (call sites)

**1. [Rule 3 - Blocking] Updated IBKR client and signal executor in Task 1**
- **Found during:** Task 1
- **Issue:** `get_normalizer` and `.check` / `.normalize` were still used outside the listed normalizer files; renaming without updating would break live trading and signal paths.
- **Fix:** Switched imports to `get_market_pre_normalizer` and method calls to `pre_check` / `pre_normalize` in `ibkr_trading/client.py` and `signal_executor.py`.
- **Files modified:** Same as above (included in Task 1 commit `703986f`)

Otherwise none — plan executed as written for listed normalizer modules and tests.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- Plan 15-02 can assume `MarketPreNormalizer` naming and shim exports.
- `INFRA-03` remains **pending** in `REQUIREMENTS.md` until plans 02–04 complete the full pipeline ordering.

## Self-Check: PASSED

- `15-01-SUMMARY.md` present at `.planning/phases/15-normalize-pipeline-ordering/15-01-SUMMARY.md`
- Task commits `703986f`, `81d7b73`; planning docs in commit matching `docs(15-01): complete MarketPreNormalizer rename plan`
- `python3 -m pytest tests/test_order_normalizer.py -v --tb=short` exit 0 (51 passed)

---
*Phase: 15-normalize-pipeline-ordering*
*Completed: 2026-04-12*
