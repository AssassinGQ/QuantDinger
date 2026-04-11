---
phase: 11-strategy-automation-forex-ibkr
plan: "01"
subsystem: api
tags: [forex, ibkr, strategy, validation, pytest, factory]

requires:
  - phase: 10-fills-position-pnl-events
    provides: stable IBKR client and execution context for strategy runtime
provides:
  - validate_exchange_market_category in live_trading factory (crypto + stateful brokers)
  - BaseStatefulClient.validate_market_category_static on IBKR/MT5/uSMART/EF
  - StrategyService save-time validation on create_strategy and update_strategy
  - test_strategy_exchange_validation.py (UC-SA-VAL-01–08)
affects:
  - 11-02-PLAN (E2E tests can assume configs are pre-validated at save)
  - operators saving strategies with exchange_id set

tech-stack:
  added: []
  patterns:
    - "Lazy-import client classes inside validate_exchange_market_category to avoid import cycles"
    - "Skip exchange/category check when exchange_id is absent (legacy creates without exchange)"

key-files:
  created:
    - backend_api_python/tests/test_strategy_exchange_validation.py
  modified:
    - backend_api_python/app/services/live_trading/base.py
    - backend_api_python/app/services/live_trading/factory.py
    - backend_api_python/app/services/live_trading/ibkr_trading/client.py
    - backend_api_python/app/services/live_trading/mt5_trading/client.py
    - backend_api_python/app/services/live_trading/usmart_trading/client.py
    - backend_api_python/app/services/live_trading/ef_trading/client.py
    - backend_api_python/app/services/strategy.py

key-decisions:
  - "StrategyService skips validation when exchange_id is empty so existing creates without exchange_config still succeed; impossible pairs are enforced once an exchange_id is present."

patterns-established:
  - "Per-engine static validation mirrors instance validate_market_category without connect()"

requirements-completed: []

# Metrics
duration: 25min
completed: 2026-04-11
---

# Phase 11 Plan 01: Strategy automation (Forex + IBKR) Summary

**Save-time `validate_exchange_market_category` in the factory, static validators on each stateful client, and `StrategyService` checks before DB writes — with UC-SA-VAL pytest coverage.**

## Performance

- **Duration:** 25 min (estimate)
- **Started:** 2026-04-11T00:00:00Z
- **Completed:** 2026-04-11T00:25:00Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Central factory validation aligned with `pending_order_worker` crypto rules and lazy-dispatch to IBKR/MT5/uSMART/EastMoney static validators.
- `create_strategy` and `update_strategy` call `_validate_exchange_market_for_save` before INSERT/UPDATE; `batch_create_strategies` inherits via `create_strategy`.
- Eight automated use cases (UC-SA-VAL-01–08) including batch success and failure paths.

## Task Commits

Each task was committed atomically:

1. **Task 1: BaseStatefulClient.validate_market_category_static + factory.validate_exchange_market_category** - `5fac25c` (feat)
2. **Task 2: StrategyService save-time validation + test_strategy_exchange_validation.py** - `f33a7ed` (feat)

**Plan metadata:** `6d94d01` (docs: complete plan)

## Files Created/Modified

- `backend_api_python/app/services/live_trading/base.py` — abstract `@staticmethod` `validate_market_category_static` on `BaseStatefulClient`.
- `backend_api_python/app/services/live_trading/factory.py` — `_CRYPTO_EXCHANGE_MARKET_RULES`, `validate_exchange_market_category`.
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `IBKRClient.validate_market_category_static`.
- `backend_api_python/app/services/live_trading/mt5_trading/client.py` — `MT5Client.validate_market_category_static`.
- `backend_api_python/app/services/live_trading/usmart_trading/client.py` — `USmartClient.validate_market_category_static`.
- `backend_api_python/app/services/live_trading/ef_trading/client.py` — `EFClient.validate_market_category_static`.
- `backend_api_python/app/services/strategy.py` — `_validate_exchange_market_for_save` and call sites.
- `backend_api_python/tests/test_strategy_exchange_validation.py` — UC-SA-VAL tests.

## Decisions Made

- When `exchange_id` is missing or blank after normalizing keys, validation is skipped so legacy strategy creates that omit `exchange_config` remain valid; when `exchange_id` is set, combinations are enforced.

## Deviations from Plan

### Service layer: empty `exchange_id`

- **Found during:** Task 2 (integration with existing tests)
- **Issue:** Literal always-call to `validate_exchange_market_category` with empty `exchange_id` produced `missing_exchange_id` and broke `test_strategy_display_group` and any flow that saves without an exchange.
- **Fix:** `_validate_exchange_market_for_save` returns early if `exchange_id` is absent/whitespace-only. Factory still returns `(False, "missing_exchange_id")` for direct callers that pass empty id.
- **Files modified:** `backend_api_python/app/services/strategy.py`
- **Verification:** `pytest tests/test_strategy_exchange_validation.py tests/test_strategy_display_group.py` passes.

Otherwise none — plan executed as written.

## Issues Encountered

None beyond the empty-exchange behavior above.

## User Setup Required

None.

## Next Phase Readiness

- Plan 11-02 can assume invalid exchange+category pairs are rejected at save when `exchange_id` is present.
- Full requirement **RUNT-03** in `REQUIREMENTS.md` remains open until E2E/smoke plans complete; not marked complete in this wave.

---
*Phase: 11-strategy-automation-forex-ibkr*
*Completed: 2026-04-11*

## Self-Check: PASSED

- `backend_api_python/tests/test_strategy_exchange_validation.py` exists.
- Commits `5fac25c`, `f33a7ed` present on branch (`git log --oneline -5`).
