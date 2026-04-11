# Pitfalls Research

**Domain:** v1.1 — Tech debt cleanup, limit orders, qualify caching, precious metals, TIF unification, normalize/align ordering, E2E hardening on an existing `ib_insync` / IBKR Forex + equity stack (~928 tests)  
**Researched:** 2026-04-11  
**Confidence:** **HIGH** for integration risks tied to this repo’s `IBKRClient` (`client.py` event path, caches, `_get_tif_for_signal`, `_create_contract`); **MEDIUM** for venue-specific metal contract details (verify in TWS / paper per symbol).

---

## Critical Pitfalls

### Pitfall 1: Treating limit orders like market orders in `_on_order_status` (partial fills and terminal states)

**What goes wrong:** Limit orders can remain **Submitted** / **PreSubmitted** for a long time, transition through **`PartiallyFilled`** (IBKR order status string per TWS API), then **Filled**, or end **Cancelled** / **Inactive** with a **non-zero** cumulative fill. Logic that assumes “first terminal event == full story” or that only **`Filled`** matters will mishandle PnL, pending rows, and notifications. Worse: calling **`_handle_fill`** on **every** status update with **cumulative** `filled` without deduplication **double-applies** position/trade rows.

**Why it happens:** Market-order-centric code paths fire **`_handle_fill`** only on **`Filled`** (and cancelled-with-fill). That matches fast fills. Limit orders stress **multiple** updates with increasing `filled`; developers often add “handle partial” without incremental-vs-cumulative discipline.

**How to avoid:**

- Keep **`PartiallyFilled`** out of **`_handle_fill`** unless you implement **delta fills** (compare to last seen `filled`, or drive from **`execDetails`** / per-fill commission path only).
- Align with existing **`OrderTracker`** FSM semantics: **`Cancelled` is not hard-terminal** in tracker (recovery paths exist); do not fork divergent meanings between sync waiters and fire-and-forget callbacks.
- Add tests that simulate **`PartiallyFilled` → `PartiallyFilled` → `Filled`** and **`PartiallyFilled` → `Cancelled`** (partial) with asserted single apply to ledger.

**Warning signs:** Duplicate trades for one `orderId`; position size 2× expected; logs showing **`_handle_fill`** more than once per order; **`has_trade_for_pending_order`** spam.

**Phase to address:** **Limit order lifecycle + fill accounting** (backend execution / Phase that owns `client.py` callbacks).

---

### Pitfall 2: Cache invalidation for `qualifyContractsAsync` results (`conId`, `secType`, `localSymbol`)

**What goes wrong:** **`qualifyContractsAsync`** mutates the contract **in place** (tests already mock this). A **qualify cache** keyed by `(symbol, market_type)` or raw user string can return a **stale** `Contract` after: symbol dictionary changes, **TIF/venue** changes, IB **re-listing** / **conId** churn, or switching **paper ↔ live**. Wrong **`conId`** → wrong **`reqContractDetailsAsync`** increment, wrong RTH details, or orders sent on **stale** instrument.

**Why it happens:** Caching is added to cut latency; invalidation rules are easy to under-specify. **`ib_insync`** async calls run on the IB thread; sharing mutable **`Contract`** objects across tasks without a clear ownership model increases stale reads.

**How to avoid:**

- Key caches with **normalized canonical keys** (same as **`normalize_symbol`** output), include **`market_type`**, and version or TTL if IB data can change session-over-session.
- Invalidate on **disconnect / reconnect** (IB session reset), and when **`_create_contract`** branch changes (new `elif` for metals).
- Prefer storing **immutable snapshots** (`conId`, `secType`, `exchange`, `localSymbol`) rather than reusing live **`Contract`** instances across unrelated orders unless the codebase standardizes one object per order.
- Run concurrency tests: two coroutines qualifying the same symbol should not leave **`_lot_size_cache`** or qualify cache in an inconsistent state (`conId` race).

**Warning signs:** Intermittent “wrong increment” alignment; RTH open/closed flipping for same symbol; first order after reconnect behaves differently from subsequent.

**Phase to address:** **Qualify cache** milestone phase (often early backend).

---

### Pitfall 3: Wrong `secType` / contract class for precious metals (spot vs futures)

**What goes wrong:** **Spot FX metals** (e.g. some **`XAUUSD` / `XAGUSD`** style pairs on **IDEALPRO**) use **`CASH`** like other FX; **exchange-traded** metals may be **`FUT`**, **`CMDTY`**, or other **`secType`** with different **exchange**, **multiplier**, and **min size**. Building **`Forex(...)`** for a symbol that IB exposes only as **futures**, or the reverse, yields qualification failure, silent wrong instrument, or fills with **different margin and PnL** semantics.

**Why it happens:** **`_create_contract`** uses **`elif` chains** and **`_EXPECTED_SEC_TYPES`** (`Forex` → **`CASH`**, equities → **`STK`**). New **`market_type`** or “metal” branch added without paper validation often copies the **Forex** path or **Stock** path incorrectly.

**How to avoid:**

- For each supported symbol class: **paper qualify + `reqContractDetailsAsync`**, record **`secType`**, **`exchange`**, **`currency`**, **`localSymbol`**, then encode that in **`_create_contract`** and **`_validate_qualified_contract`** (extend **`_EXPECTED_SEC_TYPES`** or per-branch validators).
- Do not assume **precious metal == Forex** without IB confirmation for **your** account and routing.

**Warning signs:** Error 200 / empty qualify; **`secType`** mismatch vs **`_EXPECTED_SEC_TYPES`**; position shows in unexpected **asset class** in TWS.

**Phase to address:** **Contract / symbol** phase (same phase that touches **`_create_contract`** and normalization).

---

### Pitfall 4: TIF unification breaking existing US stock / HShare strategies

**What goes wrong:** Today **`_get_tif_for_signal`** uses **`IOC`** for **all Forex** signals; **USStock** uses **`DAY`** for opens and **`IOC`** for closes; **HShare** uses **`DAY`** even for closes (IOC not supported). **Unifying** TIF (one policy per asset class, or global enum) without preserving these **documented behaviors** changes **fill timing**: e.g. close orders filling **outside** intended session, or **immediate** IOC failures where **DAY** would rest.

**Why it happens:** Refactors favor “one function, one matrix”; easy to drop **`HShare`** exception or invert **open vs close** rules.

**How to avoid:**

- Lock behavior with **REGR** tests: parametrize **`signal_type` × `market_type`** against expected TIF string (existing pattern in **`test_ibkr_client.py`**).
- Any change to **close** TIF for **USStock** / **HShare** requires **explicit** migration note for deployed strategies and paper re-validation.

**Warning signs:** Spike in **Inactive** / **Cancelled** on close signals; orders not filling in extended hours when they used to.

**Phase to address:** **TIF policy** phase (small, test-heavy; must run before or with execution changes).

---

### Pitfall 5: Flaky frontend E2E (timing, selectors, IB mocks)

**What goes wrong:** E2E tests that **assert** on **async** IBKR mock callbacks (**orderStatus** → **execDetails** → position) or **Vue** next-tick timing fail intermittently in CI. **Network** or **Gateway**-dependent tests without mocks are inherently flaky.

**Why it happens:** **`ib_insync`** is **async**; UI updates follow **websocket/poll** delays; strict **timeouts** without **condition waits**; **race** between **strategy create** and **worker** pick-up.

**How to avoid:**

- Prefer **deterministic mocks** at the same boundaries v1.0 used (**pending_order_worker** patches, etc. per **`STATE.md`**).
- Use **wait-for** assertions (text/element stable) rather than fixed **`sleep`**.
- Isolate **E2E** from real IB; keep **one** optional smoke job for paper if needed, not gating CI.

**Warning signs:** CI pass rate below 100% on unchanged code; failures at **screenshot** / **timeout** only.

**Phase to address:** **E2E / frontend** phase; **CI** config review.

---

### Pitfall 6: `normalize_symbol` vs `qualify` vs `_align_qty_to_contract` ordering bugs (“normalize timing fix”)

**What goes wrong:** **Quantity** must be validated **after** **`normalize_symbol`** produces the IB-facing symbol, **after** **qualify** establishes **`conId`**, and **after** **`reqContractDetailsAsync`** supplies **increment** — the production order in **`place_market_order` / `place_limit_order`** is intentional. Reordering (e.g. aligning qty **before** qualify, or caching **increment** by **pre-qualify** key) can **floor qty to 0** or use **wrong increment**. A **“normalize timing fix”** that runs normalization twice with different **market_type** can split behavior between **check** and **submit**.

**Why it happens:** Refactors extract “helpers” and accidentally call them in different order in **`place_limit_order`** vs **`place_market_order`** or **`is_market_open`**.

**How to avoid:**

- Single **pipeline** helper or shared **internal** function for **contract build → qualify → validate → align → order**, used by market and limit paths.
- Unit tests: **same inputs** → **same** `conId` path and **same** aligned qty for both order types.

**Warning signs:** Limit and market **disagree** on rejected qty for same inputs; **`_lot_size_cache`** hit with **`conId=0`** paths.

**Phase to address:** **Execution refactor / tech debt** phase (normalize + align consolidation).

---

## Moderate Pitfalls

### Pitfall 7: Thread-pool / event-loop mismatch on cache writes

**What goes wrong:** **`_submit`** runs coroutines on the IB loop; **`_fire_submit`** uses thread pool for **`_handle_fill`**. A **non-thread-safe** `dict` for qualify cache if ever read from **event** callbacks and written from **pool** without synchronization → rare **lost updates** or **exceptions**.

**Why it happens:** Most cache access today is on the IB side; expanding cache use without auditing **call sites** risks crossing threads.

**How to avoid:** Keep **all** cache read/write on **one** executor (IB loop), or use **`threading.Lock`** / immutable replacements. Document **ownership** in the phase that adds caching.

**Warning signs:** Heisenbugs only under load; `RuntimeError: dictionary changed size during iteration`.

**Phase to address:** Same as **qualify cache** phase.

---

### Pitfall 8: `OrderTracker` vs `IBKRClient._TERMINAL_STATUSES` drift

**What goes wrong:** **`order_tracker.HARD_TERMINAL`** and **`IBKRClient._TERMINAL_STATUSES`** are **not identical** (e.g. **`Cancelled`** handling differs). Unification work can **merge** concepts incorrectly and break **wait-for-order** vs **callback** paths.

**How to avoid:** Single source of truth or explicit mapping table; test both paths for **limit** order outcomes.

**Phase to address:** Limit order / tracker alignment phase.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Global qualify cache with no TTL | Fewer IB round trips | Stale `conId`, wrong instrument after IB changes | Only with explicit invalidation rules + reconnect flush |
| “Metals use Forex branch” without paper proof | Faster ship | Wrong secType, margin surprises | Never without qualification proof per symbol |
| E2E `sleep(3000)` | Quick test pass | Flaky CI | Never in merge-blocking E2E |
| Duplicate normalize/align in market vs limit | Copy-paste speed | Drift bugs | Short-term if tracked for merge into one pipeline in same milestone |

---

## Integration Gotchas (ib_insync / IBKR)

| Integration | Common mistake | Correct approach |
|-------------|----------------|------------------|
| **`qualifyContractsAsync`** | Assuming return value replaces contract; ignoring in-place mutation | Use the **same** contract object after await; assert **`conId`** / **`secType`** in **`_validate_qualified_contract`** |
| **Limit order status** | Treating **`PartiallyFilled`** like **`Filled`** for ledger | Only finalize ledger on **terminal** cumulative policy you define; avoid double **`_handle_fill`** |
| **`reqContractDetailsAsync`** | Caching increment by symbol string instead of **`conId`** | Cache by **`conId`** after qualify (current **`_lot_size_cache`** pattern); invalidate if contract class changes |
| **TIF** | Applying **Forex IOC** to equities or vice versa | Keep **`market_type`** branching tests as **golden** outputs |
| **Reconnect** | Reusing pre-disconnect **Contract** / cache entries | Flush qualify + RTH + increment caches on session loss |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Unbounded qualify cache | Memory growth over days | TTL, max entries, reconnect flush | Long-running Gateway process |
| Per-tick qualify in hot path | CPU + IB rate limits | Cache after first success; invalidate on symbol change | New automation calling qualify repeatedly |
| RTH cache keyed by `(conId, date)` only | Wrong hours if contract details change intraday | Rare; document assumption | IB contract update mid-session (low probability) |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging full **Contract** / keys in client logs in production | Information leakage | Log **`symbol` / `conId`** at INFO; redact account fields if ever added |

*(Domain-specific; not the main v1.1 risk.)*

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Limit order shown “Submitted” while partially filled | Confusion about working size | Surface **filled / remaining** from **`trade.orderStatus`** in API responses when milestone exposes them |
| Metal routed to wrong product | Unexpected margin / fill | Clear **market_type** and validation errors from **`_validate_qualified_contract`** |

---

## “Looks Done But Isn’t” Checklist

- [ ] **Limit partials:** Ledger updated **once** per logical fill strategy; no double **`apply_fill_to_local_position`** for same order.
- [ ] **Qualify cache:** Invalidation on **reconnect** and **symbol/market_type** change verified.
- [ ] **Metals:** Each new symbol has **paper** qualify + **`secType`** assertion.
- [ ] **TIF:** **`test_ibkr_client`** (or successor) locks **USStock / HShare / Forex** matrix.
- [ ] **Normalize pipeline:** Market and limit orders share **identical** pre-submit steps.
- [ ] **E2E:** No merge-blocking test depends on real IB latency or fixed **sleep** without wait condition.

---

## Recovery Strategies

| Pitfall | Recovery cost | Recovery steps |
|---------|---------------|----------------|
| Stale qualify cache | MEDIUM | Disable cache flag / deploy flush; reconnect Gateway; verify `conId` in logs |
| Double ledger on partials | HIGH | Reconcile DB from IB executions; add idempotency key on `orderId`+`cumQty` |
| TIF regression | MEDIUM | Revert TIF commit; rerun golden tests; paper validate closes |

---

## Pitfall-to-Phase Mapping (v1.1)

Suggested mapping — adjust to final **`ROADMAP.md`** phase numbers.

| Pitfall | Prevention phase | Verification |
|---------|------------------|--------------|
| Partial fill / status handling | Limit orders + callback work | Simulated **`PartiallyFilled`** sequences; DB counts |
| Cache invalidation | Qualify cache phase | Reconnect test; cache miss after invalidate |
| Metals **secType** | Contract / symbol extension | Paper qualify + **`_EXPECTED_SEC_TYPES`** (or equivalent) |
| TIF regression | TIF unification / policy | Parametrize **`_get_tif_for_signal`** REGR |
| Flaky E2E | Frontend E2E phase | CI stability over N runs |
| Normalize/align order | Tech debt / execution refactor | Parity tests market vs limit |

---

## Sources

- **This repo:** `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — **`_on_order_status`**, **`_create_contract`**, **`_get_tif_for_signal`**, **`_lot_size_cache`**, **`_rth_details_cache`**
- **This repo:** `backend_api_python/app/services/live_trading/ibkr_trading/order_tracker.py` — **`HARD_TERMINAL`**, **`ACTIVE`**, **`Cancelled`** recovery notes
- **Interactive Brokers:** [TWS API — Order statuses](https://interactivebrokers.github.io/tws-api/order_submission.html) (confirm **`PartiallyFilled`** and lifecycle) — verify current page revision
- **ib_insync:** Trade / `orderStatus` updates on **`Trade`** objects — see library docs for event ordering with **`execDetails`**

---

*Pitfalls research for: v1.1 IBKR integration (limit orders, caching, metals, TIF, E2E)*  
*Researched: 2026-04-11*
