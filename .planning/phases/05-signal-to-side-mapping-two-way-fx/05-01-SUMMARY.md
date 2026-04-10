---
phase: 05-signal-to-side-mapping-two-way-fx
plan: 01
subsystem: live-trading
tags: [ibkr, forex, map_signal_to_side, stateful-runner, pytest]

requires:
  - phase: 04-market-category-worker-gate
    provides: Forex accepted in supported_market_categories and worker path
provides:
  - Keyword-only market_category on BaseStatefulClient.map_signal_to_side
  - IBKR _FOREX_SIGNAL_MAP (eight signals) and non-Forex short rejection with localized message
  - StatefulClientRunner passes OrderContext.market_category into mapping
  - Unit tests UC-F1–F6, UC-E1–E3, UC-R1; full backend suite green
affects:
  - phase-06-tif-policy-forex
  - phase-07-forex-market-orders

tech-stack:
  added: []
  patterns:
    - "Keyword-only market_category for optional routing without breaking positional callers"
    - "Forex branch uses explicit eight-key map matching MT5 semantics"

key-files:
  created:
    - backend_api_python/tests/test_stateful_runner_execute.py
  modified:
    - backend_api_python/app/services/live_trading/base.py
    - backend_api_python/app/services/live_trading/ibkr_trading/client.py
    - backend_api_python/app/services/live_trading/mt5_trading/client.py
    - backend_api_python/app/services/live_trading/ef_trading/client.py
    - backend_api_python/app/services/live_trading/usmart_trading/client.py
    - backend_api_python/app/services/live_trading/runners/stateful_runner.py
    - backend_api_python/tests/test_exchange_engine.py

key-decisions:
  - "When market_category is Forex, IBKR maps all eight long/short-style signals via _FOREX_SIGNAL_MAP (aligned with MT5)."
  - "When not Forex, IBKR rejects any signal containing short with ValueError IBKR 美股/港股不支持 short 信号 — preserving equity assumptions."

patterns-established:
  - "Runner forwards ctx.market_category stripped into map_signal_to_side for engine-specific routing."

requirements-completed: [EXEC-02]

duration: 10min
completed: 2026-04-10
---

# Phase 5 Plan 01: Signal-to-side mapping (two-way FX) Summary

**IBKR Forex uses an eight-signal `_FOREX_SIGNAL_MAP` and `StatefulClientRunner` passes `OrderContext.market_category` into `map_signal_to_side`; equity paths still reject short-style signals with an explicit Chinese error.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-10T02:33:00Z
- **Completed:** 2026-04-10T02:37:00Z
- **Tasks:** 1
- **Files modified:** 8

## Accomplishments

- Extended `BaseStatefulClient.map_signal_to_side` with keyword-only `market_category=""` across IBKR, MT5, EF, and uSMART clients (latter three ignore the flag).
- IBKR: Forex branch uses `_FOREX_SIGNAL_MAP`; non-Forex keeps `_SIGNAL_MAP` for long-only equity signals and rejects `short` in the signal name before lookup.
- `StatefulClientRunner.execute` calls `map_signal_to_side(signal, market_category=(ctx.market_category or \"\").strip())`.
- Tests cover Forex two-way mapping, equity rejection paths, runner wiring, and full `pytest tests/` regression (856 passed, 11 skipped).

## Task Commits

Each task was committed atomically:

1. **Task 1: Production + tests — UC-F1–F6, UC-E1–E3, UC-R1, REGR-01** - `234af30` (feat)

**Plan metadata:** `4e6c8fb` (docs: complete signal-to-side mapping plan)

## Files Created/Modified

- `backend_api_python/app/services/live_trading/base.py` — Abstract `map_signal_to_side(..., *, market_category=\"\")`.
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_FOREX_SIGNAL_MAP` + Forex vs equity branching.
- `backend_api_python/app/services/live_trading/mt5_trading/client.py`, `ef_trading/client.py`, `usmart_trading/client.py` — Signature-only `market_category` kwarg.
- `backend_api_python/app/services/live_trading/runners/stateful_runner.py` — Pass `market_category` from `OrderContext`.
- `backend_api_python/tests/test_exchange_engine.py` — `TestIBKRSignalMapping` Forex and error-path tests.
- `backend_api_python/tests/test_stateful_runner_execute.py` — UC-R1 mock assertion.

## Decisions Made

- Forex mapping table matches the eight MT5 keys so strategy semantics stay consistent across engines.
- Non-Forex IBKR continues to forbid short-style signals with a clear operator-facing Chinese message instead of a generic English string.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- EXEC-02 complete; ready for Phase 6 TIF policy work (`EXEC-03`) with signal mapping and runner context in place.

---
*Phase: 05-signal-to-side-mapping-two-way-fx*
*Completed: 2026-04-10*

## Self-Check: PASSED

- `05-01-SUMMARY.md` exists at `.planning/phases/05-signal-to-side-mapping-two-way-fx/05-01-SUMMARY.md`
- Commit `234af30` present in history for feat(05-01)
- Commit `4e6c8fb` present in history for docs(05-01)
