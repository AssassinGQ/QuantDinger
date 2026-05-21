# Phase 17: Forex limit orders & automation - Research

**Researched:** 2026-04-12  
**Domain:** IBKR TWS API (`orderStatus`), `ib_insync`, QuantDinger live trading pipeline (IBKRClient, runner, worker)  
**Confidence:** HIGH (filled/remaining semantics); MEDIUM (product/TIF scope vs REQUIREMENTS wording)

## Summary

Phase 17 wires **Forex (and cross-market) limit orders** through the same paths as REST: `IBKRClient.place_limit_order`, `OrderContext` / `pending_orders`, `StatefulClientRunner`, and `PendingOrderWorker`. The codebase already has `place_limit_order`, DB columns (`order_type`, `price`), and `OrderContext.price`; the main work is **TIF policy** (limit → DAY per CONTEXT), **minTick price snap** alongside existing qty alignment, **PartiallyFilled / cumulative fill state** in `_on_order_status` and DB updates, and **enqueue/runner** branching off hardcoded `market`.

The **critical verification question** for TRADE-02: whether `EWrapper.orderStatus` passes **cumulative** totals in `filled` / `remaining` vs **incremental** deltas per callback.

**Evidence supports cumulative snapshot semantics (HIGH confidence):**

1. **Official IBKR TWS API** — `orderStatus` “Gives the **up-to-date information** of an order every time it changes.” Parameters: `filled` = “**number of filled positions**”, `remaining` = “**the remnant positions**”, and `lastFillPrice` = “price at which the **last** positions were filled” (i.e. per-fill detail is a *separate* field, not `filled`). Duplicate callbacks are explicitly called out. That combination matches **running totals + current remainder**, not per-message increments.  
   Source: [EWrapper::orderStatus](https://interactivebrokers.github.io/tws-api/interfaceIBApi_1_1EWrapper.html#a27ec36f07dff982f50968c8a8887d676) (parameter table under `orderStatus`).

2. **`ib_insync`** — `ib_insync.wrapper.Wrapper.orderStatus` **assigns** `filled` and `remaining` from the API straight into `OrderStatus` with **no summation**. If the wire protocol were incremental, this would be incorrect unless every consumer re-accumulated; the library’s design assumes API values are already authoritative totals.  
   Source: installed package `ib_insync` 0.9.86, `wrapper.py` `orderStatus` method.

3. **Related API surface** — Executions document **cumulative** quantity (`CumQty`) on executions, consistent with IB’s general “snapshot / cumulative” style for position-like fields.  
   Source: [Executions and Commissions](https://interactivebrokers.github.io/tws-api/executions_commissions.html) (sample output referencing `CumQty`).

**Planner implication:** The approach in **17-CONTEXT.md** — **overwrite** DB `filled` / `remaining` with `trade.orderStatus.filled` / `remaining` on each `PartiallyFilled` (and tolerate duplicates) — is **aligned with official semantics** and **ib_insync behavior**. Do **not** add incremental `+=` on `filled` from `orderStatus` (risk of double-counting); idempotency for **terminal** position/trade writes remains a separate concern (see pitfalls).

**Residual nuance (MEDIUM):** The official table does not use the literal word “cumulative.” If a future API revision or rare gateway bug sent non-standard values, defensive checks (`0 <= filled <= totalQuantity`, `filled + remaining ≈ totalQuantity` within float tolerance) would catch inconsistencies. **Empirical confirmation** on paper (Forex limit with multiple partials) is still valuable when the market is open.

**Primary recommendation:** Implement partial-fill handling by **treating `orderStatus.filled` / `remaining` as authoritative cumulative snapshots** from IBKR; only **terminal** transitions write trades/positions using final `filled` and `avgFillPrice`, per CONTEXT.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Market orders remain **IOC** (Phase 14); **limit orders use DAY** everywhere; **no per-signal/API TIF override** for limits.
- **`orderStatus` `filled` / `remaining` treated as cumulative**; update DB by **overwrite** on PartiallyFilled; **positions/trades only at terminal** statuses (`Filled`, `Cancelled` with `filled > 0`, `Inactive`, `ApiError`, `ApiCancelled`).
- Limit price from strategy **`execution_config`**: `order_type: "limit"`, `max_slippage_pips`; **BUY** `limit = price + slippage`, **SELL** `limit = price - slippage`; computed **at signal time**; **no commission in limit price**.
- **minTick snap**: BUY floor, SELL ceil (toward market / conservative); reuse **ContractDetails** from same path as `_align_qty_to_contract`.
- Invalid computed limit **`≤ 0`** → reject before enqueue.

### Claude's Discretion
- Refactor of `_align_qty_to_contract` vs new helper / return struct; **`execution_config` schema**; runner branching style; **source of `current_price` at signal time**; test layout; whether **PendingOrderWorker** needs migration (likely not).

### Deferred Ideas (OUT OF SCOPE)
- Frontend wizard for `max_slippage_pips` (Phase 18+); **GTC** for this pattern; TIF override; relying on **`execDetails`** as primary source; **reconnection recovery** for DAY orders (research may still mention as risk).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRADE-01 | IBKRClient Forex `LimitOrder`, **minTick** alignment, TIF **IOC/DAY/GTC** | CONTEXT locks **DAY-only** for limit orders (product); implement `_get_tif_for_signal(order_type, …)` / `place_limit_order` TIF accordingly; extend ContractDetails read for **minTick** + BUY/SELL snap; REQUIREMENTS “IOC/DAY/GTC” vs CONTEXT: **client may still accept GTC for REST** if desired later — v1.1 automation uses DAY per CONTEXT. |
| TRADE-02 | **PartiallyFilled**: correct **remaining**, no double-count fills/positions | **Cumulative `filled`/`remaining`** per IBKR + ib_insync (see Summary); overwrite DB fields; terminal-only `record_trade` / `apply_fill_to_local_position`; idempotent guards (`has_trade_for_pending_order` pattern). |
| TRADE-03 | **StatefulClientRunner** limit path; **PendingOrderWorker** passes limit **price** | `OrderContext.price` exists; `pending_order_enqueuer` must pass `order_type` + `price`; `stateful_runner.execute` branch `place_limit_order`; worker builds `OrderContext` including **price** from DB row. |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|----------------|
| `ib_insync` | **0.9.86** (current on PyPI; `requirements.txt`: `>=0.9.86`) | Async IB API wrapper, `LimitOrder`, events | Project already uses it for all IB I/O |
| Flask / app services | per `requirements.txt` | REST, worker, executor | Existing QuantDinger backend |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `math.floor` / `ceil` | stdlib | minTick grid snap | After raw limit computed |

**Installation (already in project):**

```bash
pip install "ib_insync>=0.9.86"
```

**Version verification:** `pip index versions ib_insync` → latest **0.9.86** (2026-04-12).

## Architecture Patterns

### Recommended touchpoints (align with repo)

```
backend_api_python/app/services/live_trading/ibkr_trading/
├── client.py          # _get_tif_for_signal, place_limit_order TIF, minTick snap, _on_order_status PartiallyFilled + DB
└── order_tracker.py   # OrderTracker.on_status already overwrites filled/remaining (consistent with cumulative API)

backend_api_python/app/services/live_trading/runners/
└── stateful_runner.py # branch: market vs limit using OrderContext

backend_api_python/app/services/
├── pending_order_enqueuer.py  # order_type + price on insert
├── pending_order_worker.py    # OrderContext(..., price=...)
└── signal_executor.py         # execution_config → limit price + order_type
```

### Pattern 1: Authoritative `orderStatus` snapshot

**What:** On each `orderStatus` for a tracked order, set persisted `filled` / `remaining` from `trade.orderStatus` (not `+=`).  
**When to use:** All statuses where the order is still “in flight,” especially **PartiallyFilled**.  
**Example (conceptual — actual code lives in `client._on_order_status`):**

```python
# Semantics: trade.orderStatus.filled / .remaining are totals from IBKR (see Research Summary).
filled = float(trade.orderStatus.filled or 0)
remaining = float(trade.orderStatus.remaining or 0)
# persist to DB / order row — overwrite, not increment
```

Source: IBKR [orderStatus](https://interactivebrokers.github.io/tws-api/interfaceIBApi_1_1EWrapper.html#a27ec36f07dff982f50968c8a8887d676); `ib_insync` `wrapper.py` `orderStatus`.

### Pattern 2: `Trade.filled()` vs `orderStatus.filled`

**What:** `ib_insync.Trade.filled()` sums **`execution.shares`** from **`trade.fills`** (execDetails path). **`orderStatus.filled`** comes from the **orderStatus** callback.  
**When to use:** For **DB sync of working orders**, prefer **`orderStatus`** fields for `filled`/`remaining` consistency with CONTEXT; use **`execDetails`** / `fills` for per-leg debugging or commission linkage (deferred as primary source per CONTEXT).

### Anti-patterns to avoid

- **Incrementing `filled` on each `PartiallyFilled` from `orderStatus`:** risks double-count if semantics were misunderstood (they are cumulative — increment is wrong).
- **Writing full position/trade on every PartiallyFilled:** can duplicate trades; CONTEXT says **terminal-only** for PnL/position writes.
- **Ignoring duplicate `orderStatus`:** IB states duplicates are common; **overwrite** is naturally idempotent for cumulative fields.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IB wire protocol for orders | Raw sockets | `ib_insync` + existing `TaskQueue` | Already integrated; event model matches TWS |
| Parsing minTick from scratch | Regex on symbols | `reqContractDetailsAsync` / `ContractDetails.minTick` | Same source as lot size; IB-authoritative |
| Partial-fill detection | Polling only | `orderStatus` + optional `execDetails` later | IB documents orderStatus + execDetails for executions |

**Key insight:** `OrderTracker.on_status` in this repo **already** does `self.filled = filled` (assign, not add) — same cumulative assumption.

## Common Pitfalls

### Pitfall 1: Duplicate or out-of-order `orderStatus`

**What goes wrong:** Same status repeated; brief regressions (e.g. Cancelled → active recovery per `order_tracker` docs).  
**Why it happens:** IB documents duplicate messages; gateway quirks around session boundaries.  
**How to avoid:** **Overwrite** cumulative fields; for terminal financial writes, **idempotent** checks (`has_trade_for_pending_order`, final status only).  
**Warning signs:** DB `filled` exceeding `totalQuantity`; monotonicity breaks in logs.

### Pitfall 2: `Trade.filled()` vs `orderStatus.filled` mismatch

**What goes wrong:** Discrepancy if fills list incomplete (e.g. delayed `execDetails`).  
**Why it happens:** Two parallel channels (status vs executions).  
**How to avoid:** For **persistence of working order quantity**, trust **`orderStatus`** for Phase 17; reconcile anomalies in logs.  
**Warning signs:** `sum(fills) != orderStatus.filled` over time.

### Pitfall 3: Float + Forex size increments

**What goes wrong:** Rounding `filled + remaining` vs `totalQuantity`.  
**Why it happens:** Float and venue min size.  
**How to avoid:** Compare with small epsilon; store as DECIMAL in DB if available.  
**Warning signs:** Off-by-1e-6 rejections in validation.

### Pitfall 4: REQUIREMENTS vs CONTEXT on TIF

**What goes wrong:** TRADE-01 text lists **IOC/DAY/GTC**; CONTEXT **locks automation limits to DAY**.  
**Why it happens:** Requirement written broadly; discuss-phase narrowed scope.  
**How to avoid:** **Planner follows CONTEXT** for automation; REST `/order` may still allow user-selected TIF if product wants **GTC** — clarify in PLAN if REST should expose GTC only.

## Code Examples

### IBKR `orderStatus` documentation (parameter semantics)

From the official `EWrapper::orderStatus` reference:

- Intro: *“Gives the **up-to-date information** of an order every time it changes. Often there are **duplicate** orderStatus messages.”*
- `filled` — *“number of filled positions.”*
- `remaining` — *“the remnant positions.”*
- `lastFillPrice` — *“price at which the **last** positions were filled.”*

URL: https://interactivebrokers.github.io/tws-api/interfaceIBApi_1_1EWrapper.html#a27ec36f07dff982f50968c8a8887d676

### `ib_insync` maps API values through unchanged

```python
# ib_insync/wrapper.py (abridged) — assigns filled/remaining directly
def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, ...):
    ...
    new = dict(
        status=status, filled=filled,
        remaining=remaining, avgFillPrice=avgFillPrice,
        ...
    )
    dataclassUpdate(trade.orderStatus, **new)
```

Installed path: `site-packages/ib_insync/wrapper.py` (version **0.9.86**).

### Existing `OrderTracker` overwrite semantics

```65:84:backend_api_python/app/services/live_trading/ibkr_trading/order_tracker.py
    def on_status(
        self,
        status: str,
        filled: float,
        avg_price: float,
        remaining: float,
        error_msgs: Optional[List[str]] = None,
    ) -> None:
        """Process an incoming orderStatus event according to the FSM transition table."""
        ...
        self.status_history.append((status, filled, avg_price, time.monotonic()))
        self.filled = filled
        self.avg_price = avg_price
        self.remaining = remaining
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Market-only automation | Limit + market branches in runner/enqueuer | Phase 17 | `OrderContext.price` used end-to-end |
| IOC on `place_limit_order` (Forex path today via `_get_tif_for_signal`) | Limit orders **DAY** (CONTEXT) | Phase 17 | Resting orders; PartiallyFilled handling required |

**Deprecated/outdated:** None identified for `orderStatus` semantics — stable for years across TWS API docs.

## Open Questions

1. **REST API: should `POST /order` allow GTC while automation uses DAY?**
   - What we know: REQUIREMENTS mention GTC; CONTEXT defers GTC for “slippage protection” automation.
   - What’s unclear: Single matrix for REST + automation vs split.
   - Recommendation: PLAN documents one matrix; default **DAY** for limit automation per CONTEXT.

2. **Exact `execution_config` JSON shape for `max_slippage_pips`**
   - What we know: CONTEXT points to strategy `execution_config`.
   - What’s unclear: Field names, validation, per-market pip definition.
   - Recommendation: Planner task to align with existing strategy JSON patterns.

3. **Paper empirical partial-fill run**
   - What we know: User has **paper** access; **market closed** at research time.
   - What’s unclear: Live multi-fill trace on **DUQ** / port **4004** when Forex active.
   - Recommendation: Add **manual / soak** verification step when session open (see Validation Architecture).

## Validation Architecture

`workflow.nyquist_validation` is **enabled** in `.planning/config.json` (`use-case-driven`).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | **pytest** (project standard) |
| Config file | `backend_api_python/tests/conftest.py` |
| Quick run | `cd backend_api_python && pytest tests/test_ibkr_order_callback.py -x -q` |
| Full suite | `cd backend_api_python && pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| TRADE-01 | Limit order TIF DAY + minTick snap path | unit / integration | `pytest tests/test_ibkr_client.py ...` (extend) | Partial — extend |
| TRADE-02 | PartiallyFilled overwrites cumulative filled; terminal idempotency | unit (mock `Trade`) | `pytest tests/test_ibkr_order_callback.py -x` | Extend with PartiallyFilled cases |
| TRADE-03 | Runner calls `place_limit_order` when `OrderContext` / row says limit | unit | New or extend `tests/test_stateful_runner*.py` if present | ❌ likely new tests |

### Sampling Rate

- **Per task commit:** targeted pytest for touched modules (`-x`).
- **Per wave merge:** full `pytest` for `backend_api_python`.
- **Phase gate:** full backend pytest green before `/gsd:verify-work`.

### Wave 0 Gaps

- [ ] Extend **`test_ibkr_order_callback.py`**: `PartiallyFilled` sequences with **monotonic cumulative** `filled`, duplicate callbacks, terminal `Filled`.
- [ ] **`stateful_runner` / enqueuer** tests: limit `OrderContext` passes **price** into `place_limit_order` (mock client).
- [ ] Optional **`test_ibkr_align_qty.py`** or sibling: **minTick** price alignment helper.

### Empirical / paper trading (user-noted)

- **Account / port (user-supplied):** paper Gateway **port 4004** pattern; **market was closed** during research — **cannot** confirm live multi-fill trace here.
- **Verification step for PLAN:** When **Forex session is open**, place a **DAY** limit designed to **partially fill** (or use illiquid combo if available), log sequential `orderStatus` lines and assert `filled` is **non-decreasing** and `filled + remaining ≈ totalQuantity`. **Do not commit credentials or tokens**; use env vars / local config only.

## Sources

### Primary (HIGH confidence)

- [Interactive Brokers TWS API — `EWrapper::orderStatus`](https://interactivebrokers.github.io/tws-api/interfaceIBApi_1_1EWrapper.html#a27ec36f07dff982f50968c8a8887d676) — parameter definitions; duplicate callbacks; `lastFillPrice` vs `filled`.
- [Interactive Brokers TWS API — Executions and Commissions](https://interactivebrokers.github.io/tws-api/executions_commissions.html) — partial fills trigger `execDetails`; `CumQty` in examples.
- **`ib_insync` 0.9.86** — `site-packages/ib_insync/wrapper.py` (`orderStatus` method).

### Secondary (MEDIUM confidence)

- QuantDinger **`17-CONTEXT.md`** — locked product decisions (DAY limits, overwrite semantics).
- **`order_tracker.py`** — local FSM assumes assign-from-callback totals.

### Tertiary (LOW confidence / not authoritative)

- Generic web search snippets without official text — **not** used as proof of semantics.

## Metadata

**Confidence breakdown:**

- **Standard stack:** HIGH — repo pins `ib_insync>=0.9.86`.
- **`filled`/`remaining` cumulative semantics:** HIGH — official doc wording + ib_insync pass-through + `lastFillPrice` design + Execution `CumQty` pattern.
- **Architecture / pitfalls:** HIGH — matches existing `client.py` / `OrderTracker` patterns.

**Research date:** 2026-04-12  
**Valid until:** ~30 days (stable API); re-check if upgrading `ib_insync` major or IB Gateway **API version** jumps.

---

*Phase: 17-forex-limit-orders-automation*
