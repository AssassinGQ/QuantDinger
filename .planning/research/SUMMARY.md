# Project Research Summary

**Project:** QuantDinger IBKR Forex (IDEALPRO) trading support  
**Domain:** Brownfield extension — add spot FX to existing `IBKRClient` (US stocks + HK shares) via `ib_insync`  
**Researched:** 2026-04-09  
**Confidence:** **MEDIUM–HIGH** (HIGH for contract/stack shape; MEDIUM for TIF/IOC-on-Forex until paper validation)

## Executive Summary

This milestone adds **IDEALPRO spot Forex** to an existing Interactive Brokers stack that already routes **US stocks** (`Stock` + `SMART`) and **HK shares** (`Stock` + `SEHK`). Experts model IBKR FX as **`secType=CASH`**, **`exchange=IDEALPRO`**, with **base currency in `symbol`** and **quote in `currency`** — implemented in `ib_insync` as `Forex(...)` with the same `qualifyContracts` → `MarketOrder` pipeline as equities. The recommended approach is **one shared `IBKRClient`**: branch `_create_contract` and `normalize_symbol` for `market_category=Forex`, add `"Forex"` to `supported_market_categories`, and reuse **`ForexNormalizer` + `_align_qty_to_contract`** so quantity follows **IBKR `ContractDetails` (`sizeIncrement` / `minSize`)** rather than hard-coded “lots.”

**Key technical decisions to lock:** **TIF** — mirror US (`DAY` open, `IOC` close) only after paper tests; if IB rejects IOC on IDEALPRO MKT, add a **Forex branch** like HShare (`DAY` for closes). **Symbol format** — normalize `EURUSD`, `EUR.USD`, etc. to a single internal base+quote representation; after qualification expect IB fields such as **`localSymbol`** (e.g. `EUR.USD`), not the pre-qual 6-letter pair string. **Quantity** — **`totalQuantity` in base currency units** on IDEALPRO; do not assume a global “25k mini-lot” — minima are **pair- and currency-specific** (rely on IB rejects + optional runbook). **Critical risks:** (1) **Stock-only paths** — `map_signal_to_side` currently rejects “short” signals; FX is two-way and must map sells/short-style signals for Forex. (2) **Defaulting unknown symbols to US stock** in `normalize_symbol` — must not mis-route FX. (3) **IOC on close** without verification — can block all exits. Mitigate with unit tests for contract/symbol, paper trading for TIF and one liquid pair, and explicit Forex branches where stock assumptions are baked in.

## Key Findings

### Recommended Stack

Use **`ib_insync.Forex`** (maps to `CASH` + default `IDEALPRO`), **`qualifyContracts` / `qualifyContractsAsync`**, and the same **`MarketOrder`** / **`LimitOrder`** classes as stocks. **Never** use `Stock` or **`exchange='SMART'`** for spot FX — wrong `secType` and routing (“invalid destination exchange”). **`Forex(pair='EURUSD')`** requires exactly **6 characters**; or **`Forex(symbol='EUR', currency='USD', exchange='IDEALPRO')`**. Same **`IB()`** session as equities; no second connection or extra SDK.

**Core technologies:**
- **`ib_insync.Forex`**: IDEALPRO cash FX contract — matches TWS API and existing client patterns.
- **`qualifyContracts`**: Resolve `conId`, `localSymbol`, `tradingClass`; validate single contract — same discipline as stocks.
- **`MarketOrder` + `totalQuantity`**: Base-currency units for IDEALPRO; optional `cashQty` is a future differentiator, not v1 default per PROJECT.md.

### Expected Features

**Must have (table stakes):**
- **CASH / IDEALPRO contract + qualification** — IB-correct routing before any order.
- **Symbol parsing** (`EURUSD`, `EUR.USD`, uppercase) — single canonical internal form → `Forex(...)`.
- **Market orders only** — aligns with PROJECT.md; defer limits/brackets.
- **Base qty + `ForexNormalizer` + `_align_qty_to_contract`** — table stakes dependency chain from FEATURES.md.
- **`supported_market_categories` includes `Forex`** — otherwise `validate_market_category` blocks live orders.
- **Callbacks / position path for Forex** — parity with USStock/HShare observability.
- **Trading hours** — reuse `liquidHours` / contract metadata (24/5), not naive equity calendars.
- **TIF policy** — resolved by testing (DAY vs GTC open question; IOC close needs Forex branch if unsupported).

**Should have (competitive / later):**
- `cashQty` sizing, margin monitoring, algos, multi-leg FX — documented as differentiators, not v1.

**Defer (v2+):**
- Limit/stop/bracket, Forex-specific UI, parallel min-size policy in normalizer beyond IB alignment, MT5 changes.

### Architecture Approach

Forex extends the **same** **contract → qualify → RTH (`liquidHours`) → normalizer → `_align_qty_to_contract` → `MarketOrder`** pipeline inside **`BaseStatefulClient` → `StatefulClientRunner` → `PendingOrderWorker`**. Structural fork: **`IBKRClient._create_contract`** returns **`Forex`** when execution category is Forex; **`ibkr_trading/symbols.py`** gains a **Forex branch** so unknown types never default to US `Stock`. **`ForexNormalizer`** is already wired — **no factory change**. **`StatefulClientRunner`** / **`PendingOrderWorker`** need **no logic change** once the client accepts `Forex`; strategy config should set **`market_category=Forex`** (runner prefers `market_category` over generic payload fields).

**Major components:**
1. **`IBKRClient`** — `supported_market_categories`, `_create_contract`, `_get_tif_for_signal` (Forex), **`map_signal_to_side` (Forex two-way)** — primary edit surface.
2. **`symbols.py`** — `normalize_symbol` (+ optional `parse_symbol`) for FX pairs vs equity tickers.
3. **`_align_qty_to_contract` + `ForexNormalizer`** — reuse; document base units and IB min/reject handling.

**Files called out in research:** `ibkr_trading/client.py`, `ibkr_trading/symbols.py`, tests `test_exchange_engine.py`, `test_ibkr_client.py`; `factory.py` at most docstring.

### Critical Pitfalls

1. **`Stock` / SMART for FX or defaulting Forex symbols to US stock** — Use explicit `market_type == "Forex"` → `Forex(...)`, hard-fail or branch when Forex is explicit; never SMART for IDEALPRO spot.
2. **Inconsistent pair encoding (`EUR.USD` vs `EURUSD`)** — Single parser; verify post-qual `localSymbol` vs intent.
3. **`map_signal_to_side` rejects shorts** — Blocks FX sells / short-style signals; extend for `market_category=Forex`.
4. **IOC on close without Forex branch** — Can reject every exit; paper-test; fallback to DAY like HShare if needed.
5. **Uniform “25k lot” mental model** — Minima vary by pair/currency; use `ContractDetails` + IB table + reject messages, not one global rule.
6. **IDEALPRO vs currency conversion (FXCONV)** — Keep strategy trades on **`CASH` + IDEALPRO**; avoid conversion order confusion.

## Implications for Roadmap

Suggested phase structure follows **dependency order** (symbols → contract → gates → execution → validation) and matches ARCHITECTURE “Suggested Build Order,” extended with **signal mapping** early because it blocks E2E.

### Phase 1: Symbol parsing + contract creation
**Rationale:** Pure functions first; wrong contract is the highest-risk bug (PITFALLS 1–2, 8).  
**Delivers:** `normalize_symbol` Forex branch; `_create_contract` → `Forex(IDEALPRO)`; `supported_market_categories` += `Forex`.  
**Addresses:** Table stakes — IDEALPRO contract, symbol formats, category validation.  
**Avoids:** Stock pseudo-symbols, SMART routing, ambiguous defaults to US stock.

### Phase 2: Signal mapping + order policy (TIF)
**Rationale:** **`map_signal_to_side`** blocks two-way FX before orders reach IB (PITFALLS 5); TIF must be validated before relying on automation (PITFALLS 4).  
**Delivers:** Forex branch in `map_signal_to_side`; `_get_tif_for_signal` Forex branch; paper/paper-api checks for DAY vs IOC on open/close.  
**Addresses:** Executable BUY/SELL for long/short-style signals; exit reliability.  
**Avoids:** Equity-only long assumption; blind copy of US IOC close rules.

### Phase 3: Integration tests + quantity/RTH hardening
**Rationale:** Lock behavior with mocks before live; align min size / increment vs broker table (PITFALLS 3).  
**Delivers:** `test_ibkr_client` / `test_exchange_engine` updates; optional logging for `localSymbol`; weekend/Fri–Sun checks for `liquidHours` (PITFALLS 7).  
**Addresses:** `ForexNormalizer` + `_align_qty_to_contract` path; RTH consistency.  
**Avoids:** Assuming single global minimum; stock-only PnL assumptions (flag moderate pitfall 9 for follow-up).

### Phase 4: E2E paper trading
**Rationale:** Validate IOC/TIF, min size rejects, fills, and position keys for one liquid pair (e.g. EURUSD).  
**Delivers:** Open + close, fill/position reconciliation, runbook for rejects.  
**Addresses:** TIF confidence gap; operational reality of mixed portfolio.

### Phase Ordering Rationale

- **Symbols + contract before** orders — qualification and routing fail fast if wrong.  
- **Signal mapping in parallel or immediately after contract** — otherwise green builds still fail at runner.  
- **TIF after first contract path** — quick iteration once `place_market_order` can submit Forex.  
- **Tests then paper** — reduces wasted manual cycles; ARCHITECTURE lists integration tests before E2E paper.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (TIF / IOC):** Account- and product-specific behavior; sparse single canonical doc — **paper validation required**.
- **Phase 3–4 (sizing / margin):** IB min-notional vs `sizeIncrement` — **verify rejects and optional explicit checks**.

Phases with standard patterns (lighter research):
- **Phase 1:** `ib_insync` `Forex` + TWS basic contracts — **well documented**.
- **Phase 3:** Existing test patterns in `test_ibkr_client.py` — **extend mocks**.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | **HIGH** | `Forex` / CASH / IDEALPRO verified against ib_insync + TWS basic contracts. |
| Features | **HIGH–MEDIUM** | Aligns with PROJECT.md and standard IBKR integration; TIF defaults MEDIUM until tested. |
| Architecture | **HIGH** | File touch points and control flow read from repo (`client.py`, `symbols.py`, runners). |
| Pitfalls | **MEDIUM–HIGH** | Contract/symbol/short-signal pitfalls HIGH confidence; IOC-on-Forex MEDIUM until paper. |

**Overall confidence:** **MEDIUM–HIGH**

### Gaps to Address

- **IOC (and optionally GTC) for IDEALPRO MKT** on target account — confirm in paper; drives `_get_tif_for_signal`.
- **DAY vs GTC for persistent signals** — product decision + IB behavior (FEATURES / PROJECT open points).
- **Position/PnL quote currency and analytics** — ensure fill/ledger keys don’t assume equity “shares” (moderate pitfall 9).
- **Frontend / trading assistant** — may route Forex to MT5 today; backend-only milestone but product may want config/UI later (PITFALLS codebase table).

## Sources

### Primary (HIGH confidence)

- [ib_insync `contract.py` — `Forex`](https://github.com/erdewit/ib_insync/blob/master/ib_insync/contract.py) — pair length, IDEALPRO default, CASH.
- [TWS API — Basic Contracts (FX Pairs)](https://interactivebrokers.github.io/tws-api/basic_contracts.html) — base/quote, CASH, IDEALPRO.
- [Interactive Brokers — Spot Currency Minimum/Maximum Order Sizes](https://www.interactivebrokers.com/en/trading/forexOrderSize.php) — pair-specific minima (verify current revision).
- `.planning/PROJECT.md` — scope, quantity mechanism, out-of-scope items.

### Secondary (MEDIUM confidence)

- [IBKR Campus — Contracts / order types](https://www.interactivebrokers.com/campus/ibkr-api-page/contracts/) — supplemental wording; validate against TWS build.
- ib_insync docs / community reports — qualification edge cases; use for test ideas.

### Tertiary (LOW confidence)

- GitHub `ib_insync` issues (Forex qualification) — anecdotal; confirm in tests.

### Research artifacts (this initiative)

- `.planning/research/STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md` — synthesized 2026-04-09.

---
*Research completed: 2026-04-09*  
*Ready for roadmap: yes*
