# Feature Landscape — IBKR Forex Trading Integration

**Domain:** IBKR IDEALPRO spot FX via TWS API / `ib_insync` (QuantDinger backend)  
**Researched:** 2026-04-09  
**Scope:** Extending an existing IBKR client that already handles US stocks and HK shares; **market orders only**; strategy-driven automation; **all IBKR-supported FX pairs**; quantity handling via existing **ForexNormalizer + `_align_qty_to_contract`**.

## Table Stakes

Features integrators and this milestone need so Forex behaves like a first-class asset class on IB—not a generic “FX app,” but **IBKR-correct contracts, orders, and state**.

| Feature | Why it is expected | Complexity | IBKR-specific notes |
|--------|---------------------|------------|----------------------|
| **Forex contract creation (IDEALPRO, `SecType=CASH`)** | IB models spot FX as **cash** on **IDEALPRO**; wrong `secType`/exchange breaks matching. | Low | Official pattern: `Symbol` = base CCY, `Currency` = quote CCY, `Exchange` = `IDEALPRO` ([TWS API basic contracts — FX Pairs](https://interactivebrokers.github.io/tws-api/basic_contracts.html)). `ib_insync.Forex(...)` should map to this; still **qualify** before trading. |
| **Contract qualification / ambiguity handling** | IB returns errors if the description matches multiple contracts; production paths must **resolve a single conId** (same as equities). | Low–Med | Same `reqContractDetails` / `qualifyContracts` discipline as stocks; FX usually simpler than SMART stocks but still mandatory. |
| **Symbol parsing (canonical ↔ IB)** | Strategies and configs will emit `EUR.USD`, `EURUSD`, etc.; the client must normalize to one internal form and build the contract consistently. | Low–Med | Not MT5 symbol maps—**IB’s** base/quote split drives the contract object. |
| **Market orders on IDEALPRO** | Table stakes for automated execution when the product owner chose **MKT-only** for v1. | Low | `MarketOrder` + `totalQuantity` in **base currency units** is the standard API path; aligns with PROJECT.md (not “mini-lot” abstraction at IB layer). |
| **Quantity: base-currency units + size increment** | IB enforces minimum increment / precision via **ContractDetails**; integrators must align quantity before submit. | Low (already implemented) | **Depends on:** `ForexNormalizer` → `_align_qty_to_contract` (PROJECT.md). This is the **correct** IBKR integration pattern vs hard-coding “0.01 lot.” |
| **Position tracking (FX cash positions)** | After fills, account **FX exposure** must reconcile (per pair / base qty), same operational need as equities. | Med | IB reports FX as **cash** positions; existing IB event-driven position logic should extend **category=Forex** without a parallel ledger. |
| **Order / execution / error callbacks** | Operational visibility: accepted, filled, rejected, partials—**required** for unattended strategies. | Low | Same as current IBKR path; **depends on** wiring `market_type=Forex` through context keys already used for USStock/HShare. |
| **Trading hours / “RTH” for FX** | FX is ~24/5; strategies still need a **consistent gate** aligned with IB’s session metadata. | Med | PROJECT.md: reuse **IBKR contract trading hours** (e.g. `liquidHours`) like existing logic—**not** a naive “weekday 9–5” stock calendar. |
| **`supported_market_categories` includes `Forex`** | Without this, orchestration and validation never route signals to the IBKR Forex path. | Low | Pure plumbing; **depends on** strategy config (`market_category=Forex`) and runner dispatch. |
| **TIF appropriate to FX + automation** | IB orders require `tif`; FX may use `DAY` vs `GTC` differently than equities. | Low–Med | **Open point** in PROJECT.md (DAY vs GTC); must be resolved against IB’s behavior for **CASH/IDEALPRO** and your signal cadence (daily vs persistent). Confidence: **MEDIUM** until confirmed in paper/live tests. |

**Dependency chain (table stakes):**

```
Symbol parse → Forex contract (CASH/IDEALPRO) → qualifyContract
    → ForexNormalizer.check → _align_qty_to_contract → MarketOrder(MKT) → IB placeOrder
    → callbacks → position / PnL updates (Forex as market category)
```

## Differentiators

Features that **some** integrations add later; not required for QuantDinger’s stated v1, but useful to label for roadmap hygiene.

| Feature | Value proposition | Complexity | IBKR-specific notes |
|--------|-------------------|------------|----------------------|
| **`cashQty` (quote-currency or “cash notional” style sizing)** | Lets operators size in **quote currency** or cash amounts instead of base units—common in PM workflows. | Med | IB documents **fractional/cash-style** quantity for **Forex** in API order models ([Order types / IBKR API Campus](https://www.interactivebrokers.com/campus/ibkr-api-page/order-types/) — verify current fields in your API version). **Overlaps** with PROJECT’s “base units + alignment” approach—treat as **alternative sizing mode**, not v1 default. |
| **Margin / buying-power monitoring for FX** | Pre-trade or periodic checks vs **margin cushion**, currency-specific haircuts—reduces surprise liquidations. | Med–High | IB margin rules are **product- and portfolio-dependent**; useful differentiator vs “fire order and handle reject.” |
| **Cross-currency / treasury-style hedging workflows** | Auto-hedge an exposure into account **base currency** or a risk bucket (overlay to spot speculation). | High | Often crosses into **currency conversion** order semantics vs pure IDEALPRO spot—needs explicit product design ([IBKR Campus: currency conversion vs FX orders](https://www.interactivebrokers.com/campus/ibkr-quant-news/how-to-code-a-currency-conversion-order-in-the-web-api/) — conceptually related; validate for **TWS API** parity). |
| **Multi-leg / spread FX (e.g. FX baskets, spreads)** | Express relative value between pairs in one order object. | High | IB **spread contracts** / combined orders are a distinct integration surface ([spreads in TWS API](https://interactivebrokers.github.io/tws-api/spread_contracts.html)); not needed for single-pair v1. |
| **Algorithmic / duration-based execution (TWAP/VWAP-style on FX)** | Lower market impact for large clips—**differentiator** for execution quality. | Med–High | Separate order types and controls; out of scope for **MKT-only** v1. |
| **Deep book / microstructure analytics** | Better slippage modeling—**differentiator** for research-heavy shops. | Med | Market data subscriptions and storage—not required if strategies consume external signals and only **execute** on IB. |

## Anti-Features (deliberately NOT for Forex v1)

Things that are **out of scope** or **actively harmful** to build now, given PROJECT.md and the “simple automated MKT” goal.

| Anti-feature | Why avoid for v1 | What to do instead |
|--------------|------------------|---------------------|
| **Limit / stop / bracket / OCO for IBKR Forex** | PROJECT **Out of Scope**: limit orders; expands QA and state machines. | Stay **MKT-only**; add other types in a later milestone with full test matrix. |
| **Second sizing pipeline: `cashQty` + base-qty in parallel** | Duplicates validation, splits strategy semantics, doubles failure modes. | **One** sizing story: existing **ForexNormalizer + `_align_qty_to_contract`** unless a future milestone **replaces** base-qty with `cashQty` by design. |
| **Forex-specific UI / new strategy type** | PROJECT: no frontend; reuse existing strategy framework. | Configure `market_category=Forex` and symbols only. |
| **ForexNormalizer “minimum size” hard checks beyond IB** | PROJECT: explicit non-goal; IB rejects impossible sizes. | Rely on **IBKR rejection messages** + alignment rounding to zero guard (already in client pattern). |
| **MT5 Forex changes** | PROJECT: MT5 Forex untouched; separate stack. | Keep IB path isolated in `IBKRClient`. |
| **Full cross-asset portfolio risk engine** | Large scope; not required to **route and fill** FX MKT orders. | Optional later: integrate account summary / margin endpoints if product asks for **risk differentiators**. |
| **Custom execution / internalizer** | You are **not** building a broker—IB is the venue. | Delegate execution quality to **MKT** + IB’s IDEALPRO handling. |

## Feature Dependencies (summary)

| Dependency | Consumer |
|------------|----------|
| Symbol → **CASH/IDEALPRO** contract | qualify, align qty, place order |
| **ContractDetails** (`sizeIncrement`, etc.) | `_align_qty_to_contract` |
| **ForexNormalizer** | pre-check before async IB calls |
| **market_type / category = Forex** | normalizer selection, TIF policy, logging |
| IB **session hours** metadata | RTH / tradability gating consistent with stocks path |
| Existing **order context + callbacks** | parity of observability with USStock/HShare |

## MVP Recommendation (this milestone)

**Must ship (table stakes):** IDEALPRO **CASH** contract + qualification; **symbol parsing**; **MKT** with **base-qty** after **ForexNormalizer + `_align_qty_to_contract`**; **`Forex` in `supported_market_categories`**; **callbacks + position path** for Forex; **trading-hours** behavior aligned with IB contract metadata; **TIF** decision locked by testing.

**Defer (differentiators):** `cashQty` sizing, margin dashboards, multi-leg FX, algos, currency-conversion-style workflows, L2 book.

**Explicitly not building (anti-features):** limit/stop/bracket, Forex UI, parallel min-size policy in normalizer, MT5 work.

## Sources

| Source | Used for |
|--------|----------|
| [TWS API — Basic Contracts (FX Pairs)](https://interactivebrokers.github.io/tws-api/basic_contracts.html) | **HIGH** confidence: `CASH`, `IDEALPRO`, base/quote fields |
| [TWS API — Contracts overview / ambiguity](https://interactivebrokers.github.io/tws-api/contracts.html) | **HIGH** confidence: contract matching discipline |
| IBKR Campus — order types / Forex `cashQty` discussions (web search synthesis) | **MEDIUM** confidence: validate against your **TWS API build** and Python `Order` fields |
| PROJECT.md (`.planning/PROJECT.md`) | Scope, out-of-scope, quantity mechanism |
| QuantDinger codebase — `IBKRClient.place_market_order` pattern | Alignment with existing **MKT + qualify + align** flow |

## Confidence

| Area | Level | Notes |
|------|-------|--------|
| IBKR FX contract shape (`CASH` / `IDEALPRO`) | **HIGH** | Official basic contracts doc |
| Table stakes for “typical IBKR integration” | **HIGH–MEDIUM** | Matches standard API patterns + this repo’s stock flow |
| TIF defaults for FX automation | **MEDIUM** | Must be validated in paper trading |
| `cashQty` semantics vs `totalQuantity` | **MEDIUM** | Confirm in `ib_insync` + IBKR version you run |
