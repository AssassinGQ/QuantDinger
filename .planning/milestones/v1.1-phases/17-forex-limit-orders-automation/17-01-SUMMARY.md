---
phase: 17-forex-limit-orders-automation
plan: 01
subsystem: api
tags: [ibkr, forex, limit-order, minTick, TIF, flask]

requires:
  - phase: 14-tif-unification-usstock-hshare
    provides: IOC matrix for market orders
provides:
  - IBKRClient limit orders with DAY default TIF and ContractDetails minTick price snap
  - REST POST /api/ibkr/order optional timeInForce (IOC/DAY/GTC) for limit orders
affects:
  - 17-02-PLAN (partial fills)
  - 17-03-PLAN (runner limit path)

tech-stack:
  added: []
  patterns:
    - "Single reqContractDetailsAsync path caches sizeIncrement and minTick per conId"
    - "Limit TIF: automation default DAY; explicit REST override whitelist"

key-files:
  created: []
  modified:
    - backend_api_python/app/services/live_trading/ibkr_trading/client.py
    - backend_api_python/app/routes/ibkr.py
    - backend_api_python/tests/test_ibkr_client.py

key-decisions:
  - "Limit orders use DAY when time_in_force is omitted; market orders unchanged (IOC for Forex/USStock/HShare/Metals)"
  - "BUY limit price floors to minTick; SELL ceils; missing minTick logs warning and uses raw price"

patterns-established:
  - "place_limit_order(..., time_in_force=...) validates IOC/DAY/GTC before any IB async work"

requirements-completed: [TRADE-01]

duration: 25min
completed: 2026-04-12
---

# Phase 17 Plan 01: TRADE-01 Summary

**IBKR Forex and cross-market limit orders: DAY default TIF, minTick-aligned limit prices, and REST `timeInForce` (IOC/DAY/GTC) with fail-fast invalid TIF.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-12T07:00:00Z
- **Completed:** 2026-04-12T07:05:00Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- `_get_tif_for_signal(..., order_type)` returns DAY for `order_type=="limit"`; market path preserves Phase 14 IOC matrix.
- `place_limit_order` uses one contract-details read for lot increment and `minTick`, snaps `lmtPrice` (BUY floor / SELL ceil), rejects non-positive snapped price.
- `POST /api/ibkr/order` passes optional `timeInForce` into `place_limit_order` when the JSON key is present.

## Task Commits

1. **Task 1: TIF branching, minTick snap, and REST timeInForce** — `86a70d9` (feat)

**Plan metadata:** Bundled with `docs(17-forex-limit-orders-automation-01): complete TRADE-01 plan summary and state` (SUMMARY + STATE + ROADMAP + REQUIREMENTS).

## Files Created/Modified

- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — TIF branching, `_contract_increment_and_mintick`, limit price snap, `time_in_force` on `place_limit_order`.
- `backend_api_python/app/routes/ibkr.py` — `timeInForce` JSON pass-through for limit branch.
- `backend_api_python/tests/test_ibkr_client.py` — `TestTrade01LimitMintickTif` (UC-01a–g), TIF expectations updated for limit DAY.

## Decisions Made

- Invalid `time_in_force` returns `LiveOrderResult` with `invalid_time_in_force` before `placeOrder` (no IB side effects).
- When `minTick` is missing or non-positive, raw limit price is used and a warning is logged once per path.

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- TRADE-02 (partial fills / `remaining`) can build on this client; TRADE-03 (runner) assumes `place_limit_order` DAY default and snapped prices.

## Self-Check: PASSED

- Files listed above exist; feature commit `86a70d9` present in `git log`; planning artifacts committed with `docs(17-forex-limit-orders-automation-01): …`.

---
*Phase: 17-forex-limit-orders-automation*
*Completed: 2026-04-12*
