---
phase: 15-normalize-pipeline-ordering
plan: 02
subsystem: infra
tags: [ibkr, order-normalizer, pytest, live-trading]

requires:
  - phase: 15-01
    provides: MarketPreNormalizer, get_market_pre_normalizer
provides:
  - IBKRClient place_market_order / place_limit_order sync preamble pre_normalize → pre_check
  - Single qty closure into _align_qty_to_contract and totalQuantity
  - HShare pre_normalize preserves sub-lot positive qty for board-lot pre_check messages
affects:
  - Phase 15 plan 04 (shim removal)
  - downstream Forex/USStock order flows

tech-stack:
  added: []
  patterns:
    - "Canonical import: app.services.live_trading.order_normalizer.get_market_pre_normalizer"
    - "Align-zero messages use post-align quantity (aligned), not raw input"

key-files:
  created: []
  modified:
    - backend_api_python/app/services/live_trading/ibkr_trading/client.py
    - backend_api_python/app/services/live_trading/order_normalizer/hk_share.py
    - backend_api_python/tests/test_ibkr_client.py
    - backend_api_python/tests/test_order_normalizer.py

key-decisions:
  - "HShare pre_normalize returns whole-share floor when snapped lot is 0 but raw > 0, so pre_check can surface multiples-of-N messaging (e.g. 400) instead of only 'got 0'."

patterns-established:
  - "IBKRClient: n = get_market_pre_normalizer(market_type); qty = n.pre_normalize(...); pre_check(qty); async path uses qty into align."

requirements-completed: [INFRA-03]

duration: 25min
completed: 2026-04-12
---

# Phase 15 Plan 02: IBKRClient normalize pipeline Summary

**IBKRClient wires `pre_normalize` → `pre_check` before async qualify/align; USStock fractional inputs floor to whole shares; tests cover TC-15-T2/T6 and call order.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-12T00:00:00Z (approx.)
- **Completed:** 2026-04-12
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- `place_market_order` and `place_limit_order` import `get_market_pre_normalizer` from the canonical `order_normalizer` package and run `pre_normalize` then `pre_check` on the sync path before `_submit`.
- Inner `_do()` passes the pre-normalized `qty` into `_align_qty_to_contract`; `MarketOrder`/`LimitOrder` and `IBKROrderContext.amount` use the aligned quantity; zero-align errors reference the aligned value.
- Pytest: `TestQuantityGuard` fractional USStock cases expect success with floored `totalQuantity`; `TestIBKRPreNormalizePipeline` proves pipeline order (TC-15-T2-05) and align input (TC-15-T2-06).

## Task Commits

1. **Task 1: IBKRClient place_market_order and place_limit_order pipeline** — `20e9fbf` (feat)
2. **Task 2: test_ibkr_client — TestQuantityGuard + TestIBKRPreNormalizePipeline** — `067e9e6` (test)

**Plan metadata:** `3270315` (docs: complete plan)

## Files Created/Modified

- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — Pipeline preamble and `qty` threading into align and orders.
- `backend_api_python/app/services/live_trading/order_normalizer/hk_share.py` — Sub-lot positive quantities preserved for board-lot `pre_check` messaging.
- `backend_api_python/tests/test_ibkr_client.py` — TC-15-T2/T6 tests; UC-E2 assertion for aligned-qty error text.
- `backend_api_python/tests/test_order_normalizer.py` — HShare under-lot `pre_normalize` expectation.

## Deviations from Plan

### Auto-fixed / scope extensions

**1. [Rule 2 — Critical] HShare `pre_normalize` for sub-lot positive quantity**
- **Found during:** Task 1 / Task 2 acceptance (TC-15-T2-04 requires `"400"` in message).
- **Issue:** Snapping `3` shares to lot multiple yielded `0`, so `pre_check` only reported non-positive quantity.
- **Fix:** When lot-snapped value is `0` but raw quantity is positive, return `float(int(raw_qty))` so `pre_check` can reject with board-lot text.
- **Files modified:** `order_normalizer/hk_share.py`, `tests/test_order_normalizer.py`

**2. [Rule 1 — Test] UC-E2 Forex align-zero message**
- **Found during:** Full `test_ibkr_client` run after message used aligned qty.
- **Fix:** Assertion updated to match `rounds to 0 after lot-size alignment for EURUSD` wording.
- **Files modified:** `tests/test_ibkr_client.py`

Otherwise — plan executed as written.

## Self-Check: PASSED

- `15-02-SUMMARY.md` exists at `.planning/phases/15-normalize-pipeline-ordering/15-02-SUMMARY.md`.
- Commits `20e9fbf`, `067e9e6`, and `3270315` present on branch.
