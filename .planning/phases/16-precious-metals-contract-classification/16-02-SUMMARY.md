---
phase: 16-precious-metals-contract-classification
plan: 02
subsystem: api
tags: [ibkr, cmdty, metals, forex, pytest, order-normalizer]

requires:
  - phase: 16-precious-metals-contract-classification
    provides: "Symbol layer: Metals, normalize_symbol SMART/CMDTY inputs (16-01)"
provides:
  - "IBKRClient CMDTY/SMART contracts for market_type Metals"
  - "get_market_pre_normalizer('Metals') → ForexPreNormalizer"
  - "IOC TIF, Forex signal map, qualify TTL shared with Forex; RTH + min-notional copy"
affects:
  - "16-03 engine/strategy validation"
  - "Phase 17 limit orders"

tech-stack:
  added: []
  patterns:
    - "Metals reuses Forex pre-normalizer and Forex signal-side map; CMDTY validated post-qualify"

key-files:
  created: []
  modified:
    - "backend_api_python/app/services/live_trading/order_normalizer/__init__.py"
    - "backend_api_python/app/services/live_trading/ibkr_trading/client.py"
    - "backend_api_python/tests/test_order_normalizer.py"
    - "backend_api_python/tests/test_ibkr_client.py"

key-decisions:
  - "Metals uses same IOC/TTL env as Forex for qualify cache; map_signal_to_side matches Forex eight-way map."
  - "Aligned-qty zero message documents troy ounce, sizeIncrement/minSize 1.0, sample XAUUSD/XAGUSD USD notionals."

patterns-established:
  - "ib_insync.Contract(secType=CMDTY) for Metals; tests use MockContract in ib_insync mock."

requirements-completed: [TRADE-04]

duration: 25min
completed: 2026-04-12
---

# Phase 16 Plan 02: Precious Metals IBKR Client Summary

**IBKRClient routes `Metals` to CMDTY/SMART contracts with IOC, Forex-equivalent signals, qualify TTL, and min-notional messaging; factory returns `ForexPreNormalizer` for pre-checks.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-12 (execution session)
- **Completed:** 2026-04-12
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- `get_market_pre_normalizer("Metals")` returns `ForexPreNormalizer` with UC-16-T2 tests.
- `_create_contract` builds `Contract(symbol, secType="CMDTY", exchange=SMART, currency=quote)` from `normalize_symbol`; `_EXPECTED_SEC_TYPES["Metals"]=="CMDTY"`; IOC TIF; `map_signal_to_side` treats Metals like Forex.
- `_qualify_ttl_seconds("Metals")` uses `IBKR_QUALIFY_TTL_FOREX_SEC`; RTH closed copy distinguishes precious metals from Forex 24/5; `aligned<=0` messages include troy ounce, increments, and sample ~3200 / ~32 notionals.
- `test_ibkr_client.py`: XAUUSD market order uses Metals; TIF matrix 8×4; `TestQualifyContractMetals`; `TestUC16T3Client` for UC-16-T3-01..08.

## Task Commits

Each task was committed atomically:

1. **Task 1: order_normalizer — Metals factory branch** — `f108788` (feat)
2. **Task 2: client.py — Metals routing, validation, messages, TIF** — `867c717` (feat)
3. **Task 3: test_ibkr_client.py — Metals tests + UC matrix** — `04ad67e` (test)

**Plan metadata:** `a54781c` (docs: SUMMARY, STATE, ROADMAP, REQUIREMENTS)

## Files Created/Modified

- `backend_api_python/app/services/live_trading/order_normalizer/__init__.py` — Metals → `ForexPreNormalizer`
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — CMDTY path, categories, TIF, validation, RTH, order messages
- `backend_api_python/tests/test_order_normalizer.py` — UC-16-T2-01..03
- `backend_api_python/tests/test_ibkr_client.py` — MockContract, TIF matrix, RTH XAGUSD Metals, qualify metals, UC-16-T3 table

## Decisions Made

- Reused `ForexPreNormalizer` for Metals (IB-driven lot sizing; same pass-through as Forex per research).
- Shared Forex qualify TTL environment variable for Metals cache lifetime.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 16-03 can add engine/strategy validation and paper/E2E paths on top of client + symbol layers.

## Self-Check: PASSED

- `16-02-SUMMARY.md` present under `.planning/phases/16-precious-metals-contract-classification/`
- Task commits verified on branch: `f108788`, `867c717`, `04ad67e`

---
*Phase: 16-precious-metals-contract-classification*
*Completed: 2026-04-12*
