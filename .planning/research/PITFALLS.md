# Domain Pitfalls

**Domain:** IBKR Forex integration (IDEALPRO spot FX) added to an existing stock-focused IBKR client (`ib_insync`, QuantDinger)  
**Researched:** 2026-04-09  
**Overall confidence:** **MEDIUM–HIGH** for contract/min-size/TIF (official IB + TWS contract docs); **MEDIUM** for IOC-on-Forex and some venue edge cases (verify in paper with target pairs).

## Critical Pitfalls

### Pitfall 1: Treating Forex like `Stock` in `_create_contract` / `normalize_symbol`

**What goes wrong:** Orders fail qualification, wrong instrument, or silent mis-routing (e.g. interpreting `EURUSD` as a US equity symbol). IBKR spot FX uses **secType `CASH`**, **base in `symbol`**, **quote in `currency`**, **exchange `IDEALPRO`** (TWS API basic contract example). `ib_insync.Stock(...)` is never valid for FX.

**Why it happens:** Existing code path always builds `Stock` from `normalize_symbol` and defaults unknown `market_type` to US SMART/USD (`symbols.py` else branch).

**Consequences:** `qualifyContracts` fails; or worse, rare ambiguous cases if future code ever mixed defaults.

**Prevention:**

- Branch `market_type == "Forex"`: build `ib_insync.Forex(...)` (or explicit `Contract(secType="CASH", exchange="IDEALPRO", ...)`) after parsing pair into base/quote.
- Remove or hard-fail the “default to US stock” branch when `market_type` is explicit but unsupported.

**Warning signs:** Error 200 / “No security definition”; qualification returns 0 contracts; `conId` stays 0.

**Detection:** Unit tests: `Forex("EURUSD")` + `qualifyContracts` in paper; log qualified `secType` and `exchange`.

**Phase:** **Contract & symbol milestone** (first implementation phase).

---

### Pitfall 2: Wrong symbol / pair encoding (EUR.USD vs EURUSD vs `symbol`/`currency` split)

**What goes wrong:** IB expects **base currency** as `symbol` and **quote currency** as `currency` for `CASH` (official TWS API FX example). User-facing formats (`EUR/USD`, `EUR.USD`, `EURUSD`) must be parsed **once**, consistently, before building the contract.

**Why it happens:** Stock code habits (ticker + exchange) do not transfer; a single concatenated string is easy to split incorrectly (e.g. assuming 3+3 letters only).

**Consequences:** Wrong pair (e.g. USD/EUR inverted logic), qualification failure, or fills on an unintended pair.

**Prevention:**

- Define a single canonical internal representation (e.g. base+quote ISO codes) and map all display formats to it.
- After `qualifyContracts`, assert `contract.localSymbol` / `symbol`+`currency` match intent (spot-check in logs).

**Warning signs:** Qualification succeeds but bid/quote or historical data don’t match expectations; PnL sign wrong.

**Phase:** **Symbol parsing** (same phase as contract creation).

---

### Pitfall 3: Assuming uniform “25,000 lot” minimum (base currency minima are pair- and currency-specific)

**What goes wrong:** Rejecting valid orders or accepting sizes IBKR will reject. Official **Spot Currency Minimum/Maximum Order Sizes** list **minimums in base currency units that vary by currency** (examples from IBKR table, 2026 snapshot): USD **25,000**; EUR **20,000**; JPY **2,500,000**; some crosses use **USD-notional** minima (`USD 25,000` footnote for certain currencies). This is **not** a single global 25k rule.

**Why it happens:** Community shorthand “25k min” is outdated or USD-centric; `ForexNormalizer` in-repo only floors to integer and does not encode IB minima (by design per `PROJECT.md`).

**Consequences:** Repeated API rejects; `_align_qty_to_contract` may align to `sizeIncrement` but still violate **min trade size** if increment < min.

**Prevention:**

- Treat **`reqContractDetails` / `minSize` / `sizeIncrement`** as authoritative for alignment, but **also** enforce (or surface) **broker min notional** from IBKR tables or error messages on reject.
- Log and handle reject reason codes explicitly when size is below minimum.

**Warning signs:** Error messages referencing minimum order size; paper works only above certain qty.

**Phase:** **Order sizing** (implementation); **hardening** if relying on IBKR rejects only.

---

### Pitfall 4: IOC on close signals (`_get_tif_for_signal`) without a Forex branch

**What goes wrong:** For **USStock**, close signals use **`IOC`** (comment: pre/post-market). **HShare** overrides to **`DAY`** because IOC is not supported. **Forex** TIF support must be verified: if IOC is rejected for IDEALPRO MKT, orders fail on every `close_long` / `close_short`.

**Why it happens:** Copying stock TIF rules to FX without testing.

**Consequences:** Systematic reject on exits; strategies stuck in positions.

**Prevention:**

- In paper, submit MKT with `DAY` vs `IOC` for representative pairs; align code with observed behavior.
- Add `Forex` branch: if IOC unsupported, use `DAY` (mirroring HShare workaround) or `GTC` only if product allows (confirm; do not assume GTC for all FX).

**Warning signs:** Order error immediately on submit; TWS message about TIF.

**Phase:** **Order execution** (same milestone as `place_market_order`).

---

### Pitfall 5: `map_signal_to_side` / signal model assumes long-only equities

**What goes wrong:** `IBKRClient.map_signal_to_side` **rejects any signal containing `"short"`** with “IBKR stock trading does not support short signals.” Spot FX is inherently **two-way**: selling EUR.USD is normal and **not** equity shorting.

**Why it happens:** Equity-only product decision baked into the client.

**Consequences:** Any strategy emitting `open_short` / `close_short` for Forex will fail before `place_market_order`, even after Forex contracts work.

**Prevention:**

- For `market_category == "Forex"` (or `market_type`), map `open_short`→`sell`, `close_short`→`buy` (and validate with product intent), **or** use a dedicated FX signal vocabulary and map to BUY/SELL.
- Document whether **crypto/margin stock shorting** stays out of scope vs **FX sell**.

**Warning signs:** `unsupported_signal` in `StatefulClientRunner.execute` logs; no order reaches IBKR.

**Phase:** **Runner + client signal mapping** (early; blocks end-to-end Forex).

---

### Pitfall 6: Confusing **spot IDEALPRO** with **currency conversion (FXCONV / cash FX)**

**What goes wrong:** IBKR exposes **currency conversion** workflows (often discussed under “FXCONV” / conversion orders) that differ from **speculative spot FX** on IDEALPRO. Wrong contract or order type → unexpected fills or account cash movements vs position screen.

**Why it happens:** “FX” in UIs and docs refers to both conversion and trading.

**Prevention:** Stick to **`CASH` + `IDEALPRO`** for strategy trades; use conversion APIs only when intentionally converting account balances.

**Warning signs:** Fill posts to cash ledger differently; position line missing or labeled as conversion.

**Phase:** **Architecture / contract** (initial); **ops validation** in paper.

---

### Pitfall 7: RTH / “market open” semantics for 24/5 Forex

**What goes wrong:** Forex is **not** equity RTH. Weekend gaps, daily maintenance breaks, and holiday calendars differ. Reusing `is_rth_check` + `liquidHours` is correct **if** `ContractDetails` returns meaningful hours; **wrong** if code still assumes “stock session” mentally (e.g. fuse logic tuned for 30-minute post-close delays).

**Why it happens:** `is_market_open` is fail-closed on qualification failure — good — but Forex may show **long multi-day sessions**; edge cases: **Friday close / Sunday open** (broker time vs UTC).

**Consequences:** Blocked trades while market is tradeable, or allowed trades into illiquid windows if hours parsing fails.

**Prevention:** Test `liquidHours` strings for major pairs across a weekend boundary; ensure server time uses `reqCurrentTimeAsync` (already in client) and timezone handling in `trading_hours.py` remains valid for FX hour strings.

**Warning signs:** Systematic “outside RTH” on Sundays; false opens on Friday evening.

**Phase:** **RTH / scheduling** (parallel with first Forex orders).

---

## Moderate Pitfalls

### Pitfall 8: `qualifyContracts` ambiguity or stale `Forex` helper

**What goes wrong:** `qualifyContracts` can return multiple matches or require explicit `exchange` (`IDEALPRO`). Community reports (ib_insync issues) include qualification edge cases with FX.

**Prevention:** Always set **`exchange='IDEALPRO'`** for spot; after qualification, use returned `contract` with `conId` for orders.

**Phase:** Contract milestone.

---

### Pitfall 9: Position / PnL / commission currency mix-ups

**What goes wrong:** Executions report commission in one currency; position size is in **base**; PnL may be tracked in account currency. Downstream `records.apply_fill_to_local_position` may assume “price × qty” like stocks without FX-specific **quote currency** and **pip** semantics.

**Prevention:** Store **pair**, **base qty**, **quote currency**, and **fill price** explicitly; avoid mixing with stock “shares” semantics in analytics.

**Phase:** **Post-fill / ledger** (after execution works).

---

### Pitfall 10: Margin and leverage differ from US/HK stocks

**What goes wrong:** Users expect stock margin rules; FX has **different margin tiers** and **close-out** behavior.

**Prevention:** Surface IBKR margin requirements in runbooks; do not reuse stock buying-power checks for FX without validation.

**Phase:** **Risk / ops** (documentation + optional pre-trade checks).

---

### Pitfall 11: Connection / session over weekend

**What goes wrong:** IB Gateway may disconnect or reset around FX week rollover; strategies assuming continuous sessions may submit blindly.

**Prevention:** Rely on existing reconnect path; add explicit handling for “market closed” from `is_market_open` after reconnect.

**Phase:** **Stability** (hardening).

---

## Minor Pitfalls

### Pitfall 12: Logging assumes `contract.symbol` is a stock ticker

**What goes wrong:** Logs remain readable, but dashboards keyed only on ticker may collide or confuse (e.g. `EUR` without quote).

**Prevention:** Log `localSymbol` or `pair` string for FX.

**Phase:** Observability polish.

---

### Pitfall 13: Caching `_lot_size_cache` / `_rth_details_cache` by `conId` after contract type change

**What goes wrong:** If contract objects are reused incorrectly, stale increments or hours could apply.

**Prevention:** Invalidate caches when Forex branch ships or on contract mismatch.

**Phase:** Implementation review.

---

## Codebase-specific: Stock-only assumptions that will break or block Forex

| Location / behavior | Risk |
|---------------------|------|
| `IBKRClient.supported_market_categories` — only `USStock`, `HShare` | `validate_market_category` fails for Forex until extended (`pending_order_worker` path). |
| `_create_contract` — always `Stock` | Wrong instrument for Forex. |
| `normalize_symbol` — unknown → US SMART/USD | Mis-resolves symbols if `market_type` missing or wrong. |
| `map_signal_to_side` — rejects “short” | Blocks FX sell-side / short-style signals. |
| `_get_tif_for_signal` — IOC on close for non-HShare | May break Forex exits if IOC unsupported. |
| `quantdinger_vue` trading assistant — Forex → MT5, US/HK → IBKR | Users may not route Forex to IBKR until UI/config updated (product decision; noted even if backend-only milestone). |
| `ForexNormalizer.check` — only `qty > 0` | Does not enforce IB min size (intentional per project; increases reliance on IB rejects). |

---

## Phase-specific warnings

| Phase / topic | Likely pitfall | Mitigation |
|---------------|----------------|------------|
| Contract + symbol | Stock contract, wrong pair parsing | `CASH` + IDEALPRO; single parser; qualify in paper |
| Orders | IOC / TIF rejects | Paper test close signals; add Forex branch |
| Signals | Long-only map | Extend `map_signal_to_side` for Forex |
| Sizing | Min-notional vs increment | Table + API rejects; optional explicit min check |
| RTH | Stock mental model | Validate `liquidHours` across Fri–Sun |
| Ledger / PnL | Stock PnL math | Explicit FX fields and quote currency |

---

## Sources

- [TWS API Basic Contracts — FX Pairs (CASH, IDEALPRO)](https://interactivebrokers.github.io/tws-api/basic_contracts.html#forex) — **HIGH** (official structure)
- [Interactive Brokers — Spot Currency Minimum/Maximum Order Sizes](https://www.interactivebrokers.com/en/trading/forexOrderSize.php) — **HIGH** (official min/max table; verify current revision periodically)
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_create_contract`, `_get_tif_for_signal`, `map_signal_to_side`, `supported_market_categories`
- `backend_api_python/app/services/live_trading/ibkr_trading/symbols.py` — `normalize_symbol` defaults
- GitHub `ib_insync` issues on `qualifyContracts` + Forex — **LOW–MEDIUM** (anecdotal; use for test ideas, not as law)

---

## Gaps / verify in paper

- Exact **IOC** support for IDEALPRO **MKT** on your account type and target pairs (official table vs runtime can differ).
- Whether **GTC** is desired/allowed for Forex market orders in this product (project already flags DAY vs GTC as open).
- **IBKRATEWAY** vs **IDEALPRO**: default retail/API spot is **IDEALPRO**; only deviate with explicit IB documentation for your use case.
