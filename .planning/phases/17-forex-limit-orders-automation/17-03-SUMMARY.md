---
phase: 17-forex-limit-orders-automation
plan: 03
subsystem: api
tags: [forex, limit-order, pip, signal-executor, pending-order, stateful-runner, worker]

requires:
  - phase: 17-01
    provides: IBKRClient.place_limit_order with DAY TIF and minTick snap
  - phase: 17-02
    provides: pending_orders.remaining for partial fill tracking
provides:
  - forex_pip.py helper for JPY/non-JPY pip size calculation
  - SignalExecutor limit price computation from trading_config.live_order
  - PendingOrderEnqueuer order_type + limit_price pass-through
  - StatefulClientRunner limit branch routing to place_limit_order
  - PendingOrderWorker OrderContext price/notification_config parity
affects: []

tech-stack:
  added: []
  patterns:
    - "trading_config.live_order.order_type=limit + max_slippage_pips drives limit price calculation"
    - "Runner branches on payload order_type: limit → place_limit_order, else → place_market_order"

key-files:
  created:
    - backend_api_python/app/services/live_trading/forex_pip.py
  modified:
    - backend_api_python/app/services/signal_executor.py
    - backend_api_python/app/services/pending_order_enqueuer.py
    - backend_api_python/app/services/live_trading/runners/stateful_runner.py
    - backend_api_python/app/services/pending_order_worker.py
    - backend_api_python/tests/test_pending_order_enqueuer.py
    - backend_api_python/tests/test_stateful_runner_execute.py
    - backend_api_python/tests/test_pending_order_worker.py

key-decisions:
  - "JPY pairs use 0.01 pip; all others 0.0001 — detected via 'JPY' substring in symbol"
  - "BUY limit = current_price + slippage_pips * pip_size; SELL = current_price - slippage_pips * pip_size"
  - "Non-positive computed limit_price aborts enqueue with return False"
  - "Runner returns ibkr_limit_price_required error for limit order with price <= 0"

patterns-established:
  - "Worker builds OrderContext with price=lim_px from payload/order_row cascade"
  - "Enqueuer passes order_type and price through to insert_pending_order"

requirements-completed: [TRADE-03]

duration: 15min
completed: 2026-04-12
---

# Phase 17 Plan 03: TRADE-03 Summary

**Strategy automation limit pipeline: pip helper, SignalExecutor slippage-cap pricing, enqueuer/runner/worker pass-through to place_limit_order.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-04-12
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- `forex_pip.py` with `pip_size_for_forex_symbol` — JPY pairs return 0.01, others 0.0001
- `SignalExecutor.execute` reads `trading_config.live_order`, computes limit price from `max_slippage_pips * pip_size`, rejects non-positive prices
- `PendingOrderEnqueuer.enqueue_pending_order` accepts `order_type` parameter, passes to `insert_pending_order`
- `StatefulClientRunner.execute` branches: `order_type==limit` → `place_limit_order`, else → `place_market_order`
- `PendingOrderWorker._execute_live_order` builds `OrderContext(price=lim_px)` with notification_config/strategy_name parity

## Task Commits

1. **Task 1: forex pip helper + limit enqueue from SignalExecutor** — `e199995` (feat)
2. **Task 2: StatefulClientRunner limit branch** — `9a4b31a` (feat)
3. **Task 3: PendingOrderWorker OrderContext parity** — code included in prior commits (worker already updated)

## Files Created/Modified

- `backend_api_python/app/services/live_trading/forex_pip.py` — pip size helper
- `backend_api_python/app/services/signal_executor.py` — live_order config, limit price calc, enqueue with order_type
- `backend_api_python/app/services/pending_order_enqueuer.py` — order_type parameter + pass-through
- `backend_api_python/app/services/live_trading/runners/stateful_runner.py` — limit/market branch in execute()
- `backend_api_python/app/services/pending_order_worker.py` — OrderContext with lim_px, notification_config, strategy_name
- `backend_api_python/tests/test_pending_order_enqueuer.py` — limit enqueue tests
- `backend_api_python/tests/test_stateful_runner_execute.py` — UC-03e/UC-03f limit and missing price tests
- `backend_api_python/tests/test_pending_order_worker.py` — UC-03g/UC-03h OrderContext price and notification tests

## Decisions Made

- Worker resolves `lim_px` from cascade: `payload.limit_price` → `payload.price` → `order_row.price` → 0.0
- `payload["order_type"]` injected if missing, ensuring runner always sees it
- notification_config loaded from DB if empty in payload, matching `_dispatch_one` signal path

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- Full automation pipeline operational: strategy signal → limit price calc → enqueue → worker → runner → IBKR place_limit_order
- Combined with 17-01 (minTick snap + TIF) and 17-02 (partial fills), the complete forex limit order lifecycle is implemented

## Self-Check: PASSED

- `forex_pip.py` exists; `live_order` grep in signal_executor; `place_limit_order` in runner; `price=lim_px` in worker
- Commits `e199995` and `9a4b31a` present in git log
- 226 tests pass (0 failures)

---
*Phase: 17-forex-limit-orders-automation*
*Completed: 2026-04-12*
