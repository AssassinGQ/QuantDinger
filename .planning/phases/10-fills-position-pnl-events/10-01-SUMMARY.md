---
phase: 10-fills-position-pnl-events
plan: 01
subsystem: api
tags: [ibkr, forex, postgres, pytest, live-trading, records]

requires:
  - phase: 09-forex-trading-hours-liquidhours
    provides: RTH / liquidHours behavior for Forex
provides:
  - qd_ibkr_pnl_single columns sec_type, exchange, currency with migration-safe ALTER
  - ibkr_save_position / ibkr_get_positions / get_positions() contract metadata for API
  - localSymbol-or-symbol labels in _conid_to_symbol and position/portfolio saves
  - ibkr_save_pnl without dead-code NameError; UC-FP1–FP7 + UC-FP6 automated coverage
affects:
  - frontend consumers of get_positions secType/currency
  - sync_positions / PositionRecord raw payloads

tech-stack:
  added: []
  patterns:
    - "COALESCE(NULLIF(EXCLUDED.col, ''), ...) for optional contract metadata upserts"
    - "_contract_symbol_label prefers string localSymbol over symbol (MagicMock-safe)"

key-files:
  created:
    - backend_api_python/tests/test_live_trading_records_ibkr.py
  modified:
    - backend_api_python/app/services/live_trading/records.py
    - backend_api_python/app/services/live_trading/ibkr_trading/client.py
    - backend_api_python/tests/test_ibkr_client.py

key-decisions:
  - "Persist IBKR secType/exchange/currency on qd_ibkr_pnl_single rows; empty EXCLUDED values do not wipe prior metadata."
  - "Symbol label for map and DB uses localSymbol when it is a non-empty string, else symbol (Forex EUR.USD vs base EUR)."

patterns-established:
  - "get_positions reads snake_case DB fields and maps to camelCase API keys with STK/SMART/USD fallbacks when columns are blank."

requirements-completed: [RUNT-02]

duration: 30min
completed: 2026-04-11
---

# Phase 10 Plan 01: Fills, position & PnL events Summary

**IBKR portfolio snapshots use `localSymbol`-style labels (e.g. EUR.USD), persist secType/exchange/currency on `qd_ibkr_pnl_single`, expose them via `get_positions()`, and fix `ibkr_save_pnl` dead clamps — with UC-FP1–FP7 pytest coverage.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-04-11T04:17:00Z
- **Completed:** 2026-04-11T04:25:00Z
- **Tasks:** 4
- **Files modified:** 4

## Accomplishments

- Schema migration and `records.py`: `ibkr_save_position` / `ibkr_get_positions` extended; `ibkr_save_pnl` clamps only account-level PnL floats.
- `client.py`: `_on_position` / `_on_update_portfolio` use `_contract_symbol_label` + `_contract_str_field`; `get_positions()` reads DB metadata with equity defaults when empty.
- Tests: `test_live_trading_records_ibkr.py` (UC-FP6, UC-SCHEMA); `test_ibkr_client.py` UC-FP1–FP5, `TestForexPositionPnLEvents` (UC-FP3, UC-FP7).

## Task Commits

Each task was committed atomically:

1. **Task 1: Schema, records, ibkr_save_pnl bugfix** — `244a6b6` (feat)
2. **Task 2: Position/portfolio callbacks + localSymbol** — `ea715ec` (feat)
3. **Task 3: get_positions DB-backed metadata** — `55ce2dd` (feat)
4. **Task 4: Integration tests FP3/FP7** — `0db5ce4` (test)

**Plan metadata:** `f4ef841` (docs: complete plan)

## Files Created/Modified

- `backend_api_python/app/services/live_trading/records.py` — ALTER columns; `ibkr_save_*` / `ibkr_get_positions`; remove undefined-variable clamps in `ibkr_save_pnl`.
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — Label helpers; callbacks; `get_positions` fallbacks.
- `backend_api_python/tests/test_live_trading_records_ibkr.py` — UC-FP6 direct `ibkr_save_pnl`; UC-SCHEMA tuple assertions.
- `backend_api_python/tests/test_ibkr_client.py` — UC-FP1–FP7, `TestForexFillsPositionPnLCallbacks`, `TestForexPositionPnLEvents`.

## Decisions Made

- Followed phase CONTEXT: one table `qd_ibkr_pnl_single` for aggregates + contract metadata; `localSymbol or symbol` only when `localSymbol` is a real string (tests use MagicMock-safe checks).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- RUNT-02 satisfied for backend IBKR portfolio snapshot semantics; Phase 11 (strategy automation) can assume correct `get_positions` metadata for Forex.

---
*Phase: 10-fills-position-pnl-events*
*Completed: 2026-04-11*

## Self-Check: PASSED

- `10-01-SUMMARY.md` present at `.planning/phases/10-fills-position-pnl-events/10-01-SUMMARY.md`
- Commits `244a6b6`, `ea715ec`, `55ce2dd`, `0db5ce4`, `f4ef841` on branch
