# Feature Landscape — v1.1 (Tech Debt + Limit Orders + Metals + Caching + TIF + E2E)

**Domain:** IBKR TWS API / `ib_insync` — Forex (`CASH` / IDEALPRO), precious metals (`CMDTY`), contract qualification, automated execution  
**Researched:** 2026-04-11  
**Scope:** **NEW work in v1.1 only** — limit orders on IDEALPRO, precious-metal contracts (XAU/XAG-style), qualify-result caching, TIF policy unification (opens → IOC across markets where supported), timing-normalization fixes, E2E test improvements. Assumes v1.0 already ships **Forex market orders**, eight-signal mapping, Forex `IOC` TIF, qualify + post-qualify validation, `ForexNormalizer` + `_align_qty_to_contract`, and frontend/strategy automation for Forex + IBKR.

## Table Stakes (v1.1 — users expect these for “production-grade” limits + metals)

| Feature | Why expected | Complexity | Notes / expected behavior |
|--------|----------------|------------|---------------------------|
| **Forex limit orders (`LMT`) on IDEALPRO** | Limit is the standard way to control price vs MKT; IB supports `LimitOrder` with `lmtPrice`, `totalQuantity`, `tif`. | Med | **Price grid:** use **`ContractDetails.minTick`** (and related fields) after qualify — IB rejects or rounds off-grid prices; pair-dependent (e.g. many majors use **0.00005** increments; JPY quotes differ). **Partials:** IB emits **`orderStatus` / `openOrder`** updates with **`filled`**, **`remaining`**; **IOC** limits behave like IOC MKT — **immediate match + cancel rest** → terminal **`Cancelled` with `filled > 0`** is normal for under-filled IOC (this repo already treats that as a fill path). **Lifecycle (typical):** non-terminal states include **`PreSubmitted`**, **`Submitted`**; may pass through **`PartiallyFilled`** before **`Filled`** or **`Cancelled`**; terminal set should match **`IBKRClient._TERMINAL_STATUSES`** in code. |
| **Limit price validation before submit** | Avoid predictable rejects and noisy logs. | Low–Med | Round or reject when `lmtPrice` not on **`minTick`**; optional spread sanity (bid/ask) is **differentiator**, not table stakes. |
| **Partial-fill handling in strategy semantics** | IOC/DAY limits may not complete size. | Med | Table stakes = **correct accounting** (`filled` vs requested) and **clear completion reason** (filled vs cancelled-incomplete); **auto-resubmit** is a **differentiator** / later milestone. |
| **GTC vs DAY for Forex limits** | Operators need orders that survive the day or not. | Med | **DAY** = rest until day/session rules; **GTC** = persists until filled/cancelled (subject to IB product rules). For v1.1, pick **one default** per product + document; **supporting both** as config is table stakes if you expose limit automation to end users. |
| **Precious metals: correct `secType` + routing** | Wrong type breaks qualify and orders. | Med | **Official TWS API example:** spot gold **`XAUUSD`** uses **`SecType = CMDTY`**, **`Exchange = SMART`**, **`Currency = USD`** ([TWS API — Basic Contracts — Commodities](https://interactivebrokers.github.io/tws-api/basic_contracts.html)). **Not** IDEALPRO **`CASH`** like `EUR.USD`. **XAGUSD:** treat as **same pattern (CMDTY + SMART + USD)** at **MEDIUM confidence** until verified via **`reqContractDetails` / qualify** on your account — do not assume parity with EURUSD construction. |
| **Qualify caching (TTL + invalidation)** | Repeated `qualifyContracts` on hot paths wastes API and latency. | Med | **Not an IB API feature** — app responsibility. **Typical patterns:** TTL **5–60 minutes** per `(symbol, market_type)` or **`conId`**; **invalidate** on qualify error, session reconnect, explicit symbol change, or **stale** flag after N failures. **Depends on:** non-zero **`conId`** and validated **`secType`** (existing `_validate_qualified_contract`). |
| **TIF unification: “open → IOC” across markets** | Single policy reduces surprise vs per-asset special cases. | Med–High | **Expected broker behavior:** **IOC** = work immediately and **do not leave a resting order** (remainder cancelled). **Stocks:** venue/exchange may **reject IOC** on some order types or sessions — **must be validated** per exchange (HK already forced **DAY** in v1.0 for close; **HShare may stay DAY-only**). **Forex** already **IOC** for all signals. **Unification** = product decision: if **USStock open** moves from **DAY → IOC**, resting day orders disappear; **GTC limits** are orthogonal (persistence ≠ DAY open MKT). |
| **Timing normalization fix** | Correct ordering of time-based gates vs IB server time. | Low–Med | Table stakes for **correct RTH / session** behavior when mixed with **cached** contract details — exact fix belongs in implementation phase; dependency: **`reqCurrentTimeAsync`** and existing **`_rth_details_cache`**. |
| **E2E / integration confidence** | Regressions on order path are costly. | Med | **Table stakes:** repeatable **mocked** event chains (**`orderStatus` → `execDetails` → position → PnL**) matching production callbacks; **optional** paper smoke **non-deterministic** — mark **manual / nightly**, not CI gate. |

## Differentiators (nice-to-have; not required to ship v1.1)

| Feature | Value | Complexity | Notes |
|--------|-------|------------|--------|
| **Bracket / OCO / stop-loss on IBKR FX/metals** | Risk overlays | High | Multi-order state machines; defer if v1.1 is “plain LMT” only. |
| **Auto-retry or re-price on IOC partial** | Better fill rate | Med–High | Policy-heavy; easy to fight the market. |
| **Rich pre-trade risk (margin, notional caps)** | Safer automation | Med–High | Portfolio-dependent on IB. |
| **Deterministic E2E with recorded FIX/API replay** | CI-grade live parity | High | Most teams use **mocks + selective paper** instead. |
| **Bid/ask spread check before limit submit** | Fewer “impossible” limits | Low–Med | Needs quote subscription path live. |

## Anti-Features (explicitly avoid for v1.1 unless requirements change)

| Anti-feature | Why avoid | Instead |
|--------------|-----------|--------|
| **Treating XAUUSD/XAGUSD as `CASH` / IDEALPRO Forex** | Breaks contract match; contradicts IB **CMDTY** example for XAUUSD. | Build **`CMDTY` + SMART** (or IB-returned exchange after qualify) branch; **qualify** always. |
| **Hard-coded tick sizes** | Drifts from IB, breaks minor pairs. | Read **`minTick`** from qualified **ContractDetails**. |
| **Infinite qualify cache without invalidation** | Wrong `conId` after corporate/contract changes (rarer for spot metals/FX, still brittle). | TTL + invalidate on errors/reconnect. |
| **Assuming paper fills == live** | IB documents simulated execution on paper. | Separate **mock unit tests** from **paper smoke** expectations. |
| **One giant E2E that requires live IB for CI** | Flaky, slow, environment-dependent. | **CI = mocked**; paper = optional job. |

## Feature Dependencies

```
v1.0: Forex MKT + ForexNormalizer + qualify + _validate_qualified_contract + _get_tif_for_signal (Forex→IOC)
  → v1.1 LMT: same qualify + minTick alignment for lmtPrice + LimitOrder + same order-status handlers
  → v1.1 CMDTY metals: _create_contract branch + _validate_qualified_contract(secType=CMDTY) + normalizer alignment rules
  → v1.1 qualify cache: must store post-qualify contract snapshot or conId + details; invalidate when connection resets
  → v1.1 TIF unification: touches _get_tif_for_signal + per-market compatibility matrix (HShare/HK constraints)
  → v1.1 E2E: depends on stable callback contract in IBKRClient (_on_order_status, _handle_fill, terminal statuses)
```

**Specific dependency notes**

- **Limit orders** depend on **existing** partial-fill handling (`Cancelled` + `filled > 0`) and **terminal status** classification — extend tests for **`PartiallyFilled`** → **`Filled`** sequences if not already covered.
- **Metals** depend on **new** `market_category` / `market_type` routing (e.g. `PreciousMetal` or extend `Forex` policy deliberately — **product choice**) and **secType validation** in `_validate_qualified_contract`.
- **Qualify cache** depends on **not** bypassing post-qualify validation when serving cached rows.
- **TIF unification** may **conflict** with **HShare DAY-only** constraint — dependency: **requirements matrix** (Forex IOC, USStock IOC open?, HShare DAY).

## MVP Recommendation (v1.1 minimal shippable slices)

1. **IBKR Forex limits:** `LimitOrder` + **`lmtPrice` rounded to `minTick`** + **`tif`** from unified policy + reuse **order status / fill** pipeline; **IOC + partial** explicitly tested.
2. **Metals:** **`XAUUSD` as `CMDTY` / SMART / USD** per IB doc; **`XAGUSD`** verified via **one** qualify on target account; **not** shoehorned into `Forex` `CASH` unless IB returns that (unlikely for XAUUSD example).
3. **Qualify cache:** in-process TTL cache with **reconnect/session invalidation**; metrics/logging on hit rate.
4. **TIF:** document **exceptions** (e.g. HShare) before coding; add **matrix test** in unit tests.
5. **E2E:** expand **mocked** event simulations; keep **live paper** as **manual / scheduled**, not CI blocker.

**Defer:** Brackets/OCO, auto-reprice, margin-aware sizing, full golden replay harness.

## Sub-feature checklist — **Forex limit orders**

| Sub-feature | Essential for v1.1? | Rationale |
|-------------|----------------------|-----------|
| **minTick / price quantization** | **Yes** | IB rejection avoidance; standard integration. |
| **Partial fill handling (accounting + status)** | **Yes** | IOC and liquidity; already partly handled for MKT/IOC. |
| **GTC** | **Product call** | Essential if strategies need multi-day resting limits; else **DAY** may suffice for IOC-heavy automation. |
| **DAY** | **Likely yes** | Default for many limit workflows; pair with open **IOC** policy carefully (IOC ≠ resting). |
| **Price validation (bounds)** | **Recommended** | minTick + **optional** min/max distance from NBBO — latter is **nice-to-have**. |

## Sub-feature checklist — **Precious metals (IBKR)**

| Question | Recommendation | Confidence |
|----------|----------------|------------|
| **CMDTY vs CASH for XAUUSD / XAGUSD?** | **CMDTY** for **`XAUUSD`** per official **Basic Contracts** commodity sample; **XAGUSD** almost certainly **CMDTY** OTC spot — **confirm with qualify**. | **HIGH** (XAUUSD doc); **MEDIUM** (XAGUSD by analogy) |
| **Exchange IDEALPRO vs SMART?** | Doc shows **`SMART`** for **`XAUUSD`**; after qualify, prefer **IB-returned** `primaryExchange` / `exchange`. | **HIGH** |

## Sub-feature checklist — **Qualify caching**

| Mechanism | Expected behavior |
|-----------|-------------------|
| **TTL** | Bounded freshness (e.g. 15–60 min) or session-scoped. |
| **Invalidation** | New symbol, failed order/qualify, reconnect, optional manual bust. |
| **What to cache** | Qualified **contract** (or **`conId` + ContractDetails** needed for minTick/sizeIncrement). |

## Sub-feature checklist — **TIF unification (opens → IOC)**

| Expected behavior | Caveat |
|-------------------|--------|
| **Forex** | Already **IOC** — unchanged. |
| **USStock open → IOC** | Resting **DAY** liquidity-taking behavior changes; **verify** exchange accepts IOC for intended order types. |
| **HShare** | **May not support IOC** — **exception row** in policy, not forced IOC. |

## Sub-feature checklist — **E2E testing (trading systems)**

| Pattern | Expected role |
|---------|-----------------|
| **Unit + callback mocks** | **Primary CI** — deterministic, fast (`test_ibkr_client`, `test_ibkr_forex_paper_smoke`-style). |
| **Integration with mock IB** | Full path without network — **recommended** for every release. |
| **Paper / live smoke** | **Optional** — validates connectivity and **rough** behavior; not bit-reproducible. |
| **Golden replay** | **Differentiator** — only if team invests in harness. |

## Sources

| Source | Used for | Confidence |
|--------|----------|------------|
| [TWS API — Basic Contracts (Commodities: XAUUSD)](https://interactivebrokers.github.io/tws-api/basic_contracts.html) | **`CMDTY` + `SMART` + `USD`** for spot gold | **HIGH** |
| [TWS API — Placing Orders / order callbacks](https://interactivebrokers.github.io/tws-api/order_submission.html) | Order events via **`openOrder` / `orderStatus`** | **HIGH** |
| Phase 06 research (`.planning/milestones/v1.0-phases/06-tif-policy-for-forex/06-RESEARCH.md`) | **IOC** + **`Cancelled`+`filled>0`** semantics | **HIGH** (project) |
| Phase 03 research (`.planning/milestones/v1.0-phases/03-contract-qualification/03-RESEARCH.md`) | Qualify + **`XAUUSD` ≠ Forex/CASH** note | **HIGH** (project) |
| `backend_api_python/.../client.py` — `_TERMINAL_STATUSES`, `_get_tif_for_signal`, `_on_order_status` | Terminal states + Forex IOC | **HIGH** (code) |
| Web / industry patterns for qualify caching & E2E layering | TTL, invalidation, mock-first CI | **MEDIUM** (pattern, not IB-specific) |

## Confidence

| Area | Level | Notes |
|------|-------|--------|
| XAUUSD = **CMDTY** (IB official sample) | **HIGH** | Basic Contracts doc |
| XAGUSD = **CMDTY** | **MEDIUM** | Verify via `qualify` / Contract Information Center |
| Forex limit **tick** / partial lifecycle | **MEDIUM–HIGH** | Align with **ContractDetails** + ib_insync **Trade.orderStatus** |
| TIF unification across **all** markets | **MEDIUM** | Exchange constraints (esp. HK) need **matrix** validation |
| Qualify cache design | **MEDIUM** | Standard app pattern; not IB-specified |
| E2E patterns | **MEDIUM** | Consensus: mock-first; paper secondary |
