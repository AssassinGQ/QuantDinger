# Phase 17: Forex limit orders & automation - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Full limit-order execution: REST/automation parity, minTick prices, partial fills, and runner/worker support. Limit orders serve as **slippage protection** — capping the maximum price deviation from the signal-time market price. Covers TRADE-01, TRADE-02, TRADE-03.

</domain>

<decisions>
## Implementation Decisions

### TIF Policy for Limit Orders
- Market orders remain **IOC** (Phase 14 decision, unchanged)
- **Automation path** (signal → enqueue → worker → runner): limit orders always use **DAY** — resting until end of trading session or fill, whichever comes first. No per-signal override; `_get_tif_for_signal` returns `"DAY"` when `order_type == "limit"` regardless of `market_type`
- **REST API path** (`POST /api/ibkr/order`): manual limit orders accept optional `timeInForce` from `IOC`/`DAY`/`GTC` whitelist per TRADE-01; default is `DAY` when omitted
- Applies to **all market types** including Forex, Metals, USStock, HShare — same rule

### Partial Fill Handling
- IBKR `orderStatus` callback reports **cumulative** `filled` and `remaining` (not incremental)
- IBKR does **not guarantee** a callback for every status change — duplicate messages are common
- **PartiallyFilled**: update DB `filled` / `remaining` fields by **overwriting with cumulative values** (no increment arithmetic — eliminates double-counting risk)
- **Positions/PnL written only at terminal status**: `Filled`, `Cancelled` (with `filled > 0`), `Inactive`, `ApiError`, `ApiCancelled`
- Terminal status uses final `filled` + `avgFillPrice` for position entry
- `Cancelled` with `filled == 0` → mark order failed, no position
- `Cancelled` with `filled > 0` → write position for the filled portion (DAY limit partial fill then session close)

### Limit Order Signal Flow (Automation)
- Limit orders are **slippage protection** — limit price is set slightly worse than market to cap maximum slippage
- **Offset source**: strategy `trading_config.live_order` contains `order_type: "limit"` and `max_slippage_pips` (user sets in frontend when creating strategy)
- **Price calculation at signal time** (not at worker execution time):
  - BUY: `limit_price = current_price + max_slippage_in_price_units`
  - SELL: `limit_price = current_price - max_slippage_in_price_units`
- **Commission NOT embedded** in limit price — IBKR charges commission separately from execution price (0.20 bps or $2 min per order)
- **Enqueue stores**: `order_type='limit'` + computed `limit_price` in `pending_orders` table
- Worker/runner reads `order_type` and `price` from `OrderContext`, branches to `place_limit_order`
- **Invalid price guard**: if computed `limit_price ≤ 0` (extreme offset or zero market price), reject order with error — do not enqueue

### Price Tick Alignment (minTick snap)
- Limit price must snap to `ContractDetails.minTick` grid
- **Snap direction**: toward market side (more conservative, reduces slippage)
  - BUY: `floor(raw_limit / minTick) * minTick` (snap down — lower max buy price)
  - SELL: `ceil(raw_limit / minTick) * minTick` (snap up — higher min sell price)
- **Reuse existing ContractDetails call** — `_align_qty_to_contract` already fetches `reqContractDetailsAsync`; extend to also extract `minTick` and apply price alignment in the same call
- Invalid price after snap (≤ 0) → reject order

### Claude's Discretion
- How to refactor `_align_qty_to_contract` to also return/apply minTick (rename? new helper? combined struct?)
- Exact `execution_config` schema for limit order fields
- How `StatefulClientRunner.execute` branches on order_type (if/elif vs strategy pattern)
- How to acquire `current_price` at signal time (from indicator payload? IBKR snapshot? cached last price?)
- Test organization and naming for new limit-order tests
- Whether `PendingOrderWorker` needs schema migration or if existing `order_type` + `price` columns suffice (they should)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Limit order placement (existing implementation)
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` lines 1262–1349 — `place_limit_order` (already constructs `ib_insync.LimitOrder` with `lmtPrice`, calls qualify + align; TIF currently IOC for Forex)
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` lines 1159–1260 — `place_market_order` (reference for parallel structure)

### TIF policy
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` lines 164–179 — `_get_tif_for_signal` (current: IOC for Forex/USStock/HShare/Metals, DAY otherwise)
- `.planning/phases/14-tif-unification-usstock-hshare/14-CONTEXT.md` — Phase 14 TIF decisions (IOC unified for market orders)

### Order status handling
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` lines 443–470 — `_on_order_status` (current: Filled → _handle_fill, Cancelled+filled → _handle_fill, else → re-register context)
- `backend_api_python/app/services/live_trading/ibkr_trading/order_tracker.py` lines 23–30 — `HARD_TERMINAL` and `ACTIVE` status sets
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` lines 964–1045 — `_handle_fill`, `_handle_reject`

### Quantity and price alignment
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` lines 933–960 — `_align_qty_to_contract` (qty only; no minTick price snap yet)

### Automation pipeline
- `backend_api_python/app/services/live_trading/runners/stateful_runner.py` lines 55–110 — `StatefulClientRunner.execute` (market-only; no limit branch)
- `backend_api_python/app/services/pending_order_worker.py` lines 387–412 — worker → runner execution (builds `OrderContext` from DB)
- `backend_api_python/app/services/signal_executor.py` lines 378–386 — signal → enqueue path
- `backend_api_python/app/services/pending_order_enqueuer.py` lines 119–135 — enqueue insert (hardcodes `order_type="market"`)
- `backend_api_python/app/services/live_trading/base.py` lines 57–72 — `OrderContext` (has `price` field, unused for IBKR)

### REST API (manual limit orders)
- `backend_api_python/app/routes/ibkr.py` lines 193–256 — `POST /order` (already supports `orderType: "limit"` with `price`)

### DB schema
- `backend_api_python/migrations/init.sql` lines 232–261 — `pending_orders` table (has `order_type VARCHAR(20) DEFAULT 'market'` and `price` columns)

### Requirements
- `.planning/REQUIREMENTS.md` — TRADE-01 (limit order + minTick + TIF), TRADE-02 (partial fills), TRADE-03 (runner/worker automation)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `place_limit_order` in `client.py` — already fully functional for REST API; needs TIF change (IOC → DAY) and minTick snap
- `OrderContext.price` field — exists in `base.py`, ready for runner to use
- `pending_orders.order_type` + `pending_orders.price` DB columns — schema already supports limit orders
- `_align_qty_to_contract` — already calls `reqContractDetailsAsync`; extend to extract `minTick`
- `POST /order` REST endpoint — already branches on `orderType: "limit"` vs `"market"`

### Established Patterns
- Market-type dispatch in `_get_tif_for_signal` — add order_type dimension
- `_on_order_status` event-driven callback — extend with `PartiallyFilled` branch
- `StatefulClientRunner.execute` → `client.place_market_order` — add limit branch
- `PendingOrderEnqueuer.execute_exchange_order` → `enqueue_pending_order` — parameterize order_type

### Integration Points
- `signal_executor.py` → `PendingOrderEnqueuer`: must pass order_type + limit_price from strategy config
- `pending_order_worker.py` → `StatefulClientRunner`: must read order_type from DB and call correct placement method
- `stateful_runner.py` → `IBKRClient`: must branch on order_type to call `place_limit_order` with price
- `_on_order_status` → DB: must handle `PartiallyFilled` status for in-flight limit orders
- Frontend strategy creation wizard → `execution_config`: must allow setting order_type + max_slippage_pips (Phase 18 or separate)

</code_context>

<specifics>
## Specific Ideas

- Limit orders as **slippage protection** (not "better price" seeking) — limits are set slightly worse than market, most orders execute immediately but with a price ceiling/floor
- DAY TIF means orders can live up to ~24h for Forex (17:00 ET session close) — system must handle long-lived orders
- Cumulative value overwrite (not increment) for partial fill tracking — eliminates double-counting risk from duplicate IBKR callbacks
- IBKR `orderStatus` docs warn: "There are not guaranteed to be orderStatus callbacks for every change in order status" — defensive design needed

</specifics>

<deferred>
## Deferred Ideas

- Frontend UI for setting `max_slippage_pips` in strategy creation wizard — Phase 18 or separate
- GTC TIF for **automation** — not needed for slippage protection pattern (DAY is sufficient); REST API does expose GTC per TRADE-01
- TIF override per **automation signal** — complexity not justified for v1.1 (REST path already accepts TIF whitelist)
- `execDetails` monitoring (IBKR recommends alongside `orderStatus`) — nice-to-have, not blocking
- Reconnection recovery for in-flight DAY limit orders — technical concern for research/planning to address

</deferred>

---

*Phase: 17-forex-limit-orders-automation*
*Context gathered: 2026-04-12*
