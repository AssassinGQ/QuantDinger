# Project Research Summary

**Project:** QuantDinger v1.1 — Tech Debt Cleanup + Limit Orders  
**Domain:** IBKR TWS / `ib_insync` — Forex IDEALPRO, precious metals (CMDTY), contract qualification, automated execution, E2E testing  
**Researched:** 2026-04-11  
**Confidence:** MEDIUM–HIGH (HIGH for stack/API shapes; MEDIUM for venue-specific IB product rules and HShare IOC constraints)

## Executive Summary

QuantDinger v1.1 extends an existing brownfield stack (Flask, `ib_insync` 0.9.86, Vue 2, pytest) with **Forex limit orders**, **qualify-result caching**, **TIF policy unification** (USStock/HShare open → IOC where supported), **precious-metal contract routing** (notably whether `XAUUSD` is `CMDTY` vs `CASH`), **`normalize()` timing alignment** with the IB order pipeline, and **E2E hardening** (API prefix fixes, optional frontend HTTP E2E via Playwright). Experts ship this by keeping **one IBKR order pipeline** (`place_market_order` / `place_limit_order`), rounding limit prices with **`Decimal` + `ContractDetails.minTick`**, and using **mock-first CI** with paper smoke optional.

The recommended approach: pin **`ib_insync==0.9.86`**, add **`cachetools.TTLCache`** (or a careful stdlib TTL dict) **inside `_qualify_contract_async`**, extend **`StatefulClientRunner`** and **`PendingOrderWorker`** so automated trading can pass limit price and order type—not only REST, validate **metals on paper** per symbol before encoding `Forex` vs `Commodity`/generic `Contract`, and lock **TIF** behavior with **parametrized regression tests** so HShare DAY-only exceptions are not lost. **Limit orders** stress **partial fills** and **`PartiallyFilled`**; ledger logic must avoid **double-applying** cumulative fills in `_handle_fill`.

Key risks: **stale qualify cache** after reconnect or IB listing changes (mitigate: TTL, reconnect flush, canonical keys, prefer `conId` snapshots); **wrong `secType` for metals** (mitigate: paper `qualifyContractsAsync` + `_validate_qualified_contract`); **TIF changes** altering US stock fill behavior (mitigate: explicit matrix tests + migration notes); **flaky E2E** (mitigate: deterministic mocks, wait-for assertions, no merge-blocking live IB).

**Milestone scope alignment (v1.1):** (1) qualify result caching — (2) USStock/HShare open → IOC (TIF unification) — (3) Forex limit orders (`LimitOrder`) — (4) precious metal contract classification (`XAUUSD` as CMDTY per IB Basic Contracts doc; verify `XAGUSD`) — (5) `normalize()` call timing fix — (6) E2E test API prefix fix — (7) frontend HTTP E2E test (Playwright recommended).

## Key Findings

### Recommended Stack

See [STACK.md](./STACK.md). No second IB API layer: **`ib_insync`** remains the single gateway wrapper. **Limit orders** use `LimitOrder(action, totalQuantity, lmtPrice, **kwargs)` with TIF from existing `_get_tif_for_signal` / unification work. **Price precision:** stdlib **`decimal.Decimal`** plus **`ContractDetails.minTick`** / `priceMagnifier` after qualify—no extra PyPI dependency for rounding. **Qualify cache:** **`cachetools>=7.0.5`** (`TTLCache`; Python ≥3.10) or stdlib-only TTL dict. **E2E:** Flask **`test_client()`** for backend; optional **`pytest-flask`**; browser/HTTP E2E via **`@playwright/test`** + **`playwright`** (e.g. 1.59.1)—keep Jest + Vue Test Utils for unit/component tests.

**Core technologies:**
- **ib_insync 0.9.86:** `LimitOrder`, `MarketOrder`, `Forex`, `Commodity`, qualify/details APIs — matches project lower bound; pin for reproducibility.
- **cachetools (TTLCache):** Bounded qualify cache with TTL — avoids unbounded dict growth; align access with existing IB executor / threading model.
- **Playwright (dev):** Frontend HTTP E2E against real stack — complements Flask in-process tests; one framework, no Cypress duplication.

### Expected Features

See [FEATURES.md](./FEATURES.md).

**Must have (table stakes):**
- **Forex limit orders (`LMT`) on IDEALPRO** — `lmtPrice` on minTick grid; partial fills and IOC semantics; terminal status handling consistent with `_TERMINAL_STATUSES`.
- **Limit price validation** — round/reject off-grid prices before submit.
- **Precious metals routing** — IB doc: **XAUUSD** as **CMDTY**, **SMART**, **USD**; **XAGUSD** verify via qualify (MEDIUM confidence by analogy).
- **Qualify caching** — TTL + invalidation (reconnect, errors, symbol change); cache qualified snapshot or `conId` + details; do not skip post-qualify validation.
- **TIF unification** — open → IOC for USStock where valid; **HShare may remain DAY-only** — document exception matrix before coding.
- **`normalize()` timing** — explicit pipeline: `check` → `normalize` → contract/qualify/validate → `_align_qty_to_contract` (supersedes prior “not on purpose” decision for main chain).
- **E2E confidence** — mocked callback chains in CI; API prefix fixes in tests; optional Playwright for wizard HTTP flows.

**Should have (competitive):**
- Bid/ask spread sanity before limit submit — nice-to-have; needs quote path.
- Metrics/logging on qualify cache hit rate — operational visibility.

**Defer (v2+):**
- Bracket/OCO/stop overlays; auto-reprice on IOC partial; golden FIX replay harness.

### Architecture Approach

See [ARCHITECTURE.md](./ARCHITECTURE.md).

**Major components:**
1. **`IBKRClient` (`ibkr_trading/client.py`)** — Qualify cache in `_qualify_contract_async`; `_create_contract` / `_validate_qualified_contract` for metals; TIF in `_get_tif_for_signal`; shared preamble for market and limit orders.
2. **`StatefulClientRunner` + `PendingOrderWorker`** — Today runner calls **`place_market_order` only**; v1.1 must branch for limit orders and plumb limit price + order type from `OrderContext` / payload so REST and automation stay consistent.
3. **`app/routes/ibkr.py`** — Already routes limit to `place_limit_order`; worker/runner gap is the main automation gap.
4. **Tests** — Extend `test_forex_ibkr_e2e.py` pattern; fix API prefix in E2E; add Playwright suite under `quantdinger_vue` for frontend HTTP E2E.

### Critical Pitfalls

See [PITFALLS.md](./PITFALLS.md).

1. **Limit vs market in `_on_order_status`** — Multiple updates with increasing `filled`; avoid calling `_handle_fill` in ways that double-apply cumulative fills; handle **`PartiallyFilled`** with delta discipline or execDetails-only application.
2. **Qualify cache invalidation** — Stale `conId`/secType after reconnect or IB changes; use canonical keys, TTL, reconnect flush; avoid sharing mutable `Contract` across unrelated orders without a clear model.
3. **Metals `secType`** — Assuming all XAU/XAG are IDEALPRO `Forex`/`CASH` can break qualification; validate per symbol on paper and extend `_EXPECTED_SEC_TYPES` / branches accordingly.
4. **TIF unification** — Regressions on HShare (IOC unsupported) or unintended change to close-day behavior; lock with **`signal_type` × `market_type`** golden tests.
5. **Normalize / align ordering** — Drift between `place_market_order` and `place_limit_order` or wrong order vs qualify causes wrong qty increment; prefer one internal pipeline helper.
6. **Flaky frontend E2E** — Fixed sleeps, real IB latency — use mocks at same boundaries as v1.0 and condition-based waits.

## Implications for Roadmap

Suggested phase structure for v1.1 (continues project numbering in `ROADMAP.md`):

### Phase A: Qualify result caching
**Rationale:** Isolated to `IBKRClient`, benefits all callers (`place_*`, `get_quote`, `is_market_open`).  
**Delivers:** TTL cache wrapping `_qualify_contract_async`, invalidation on reconnect, logging/metrics hooks.  
**Addresses:** Milestone item (1); FEATURES qualify caching; STACK cachetools.  
**Avoids:** Pitfall 2 (stale cache), Pitfall 7 (thread safety on cache writes).

### Phase B: TIF unification (USStock/HShare open → IOC)
**Rationale:** Single policy surface (`_get_tif_for_signal`) before broad execution changes.  
**Delivers:** Documented matrix (Forex IOC unchanged, USStock open IOC where accepted, HShare DAY exception), parametrized REGR tests.  
**Addresses:** Milestone item (2); FEATURES TIF checklist.  
**Avoids:** Pitfall 4 (TIF regression).

### Phase C: `normalize()` call timing fix
**Rationale:** Small, testable; reduces drift before limit-order plumbing.  
**Delivers:** `check` → `normalize` → qualify chain → `_align_qty_to_contract` in both order paths; unit tests in `test_order_normalizer.py`.  
**Addresses:** Milestone item (5).  
**Avoids:** Pitfall 6 (ordering bugs).

### Phase D: Precious metal contract classification (XAUUSD / XAGUSD)
**Rationale:** Product-dependent; may touch `symbols.py`, `_create_contract`, `_validate_qualified_contract`.  
**Delivers:** CMDTY/SMART path per IB doc for XAUUSD; paper validation for XAGUSD; tests.  
**Addresses:** Milestone item (4).  
**Avoids:** Pitfall 3, FEATURES anti-feature “treat metals as CASH Forex”.

### Phase E: Forex limit orders in live pipeline
**Rationale:** Depends on stable TIF, normalize pipeline, and qualify cache; extends runner/worker.  
**Delivers:** `LimitOrder` + minTick rounding, `StatefulClientRunner` + worker support for limits, extended order-status tests (`PartiallyFilled` sequences).  
**Addresses:** Milestone item (3); REST already calls `place_limit_order`.  
**Avoids:** Pitfall 1, Pitfall 8 (tracker vs terminal status drift).

### Phase F: E2E hardening — API prefix + frontend HTTP E2E
**Rationale:** After API surface stable; fixes test drift and adds browser coverage.  
**Delivers:** E2E test API prefix fix; Playwright config + smoke flows for `trading-assistant` HTTP paths; CI job optional/separate from unit tests.  
**Addresses:** Milestone items (6)(7).  
**Avoids:** Pitfall 5 (flaky E2E).

### Phase Ordering Rationale

- **Cache + TIF + normalize** early: low coupling, high leverage, fewer regressions when limits and metals land.  
- **Metals** before or in parallel with **limit** work if `minTick` and validation share contract details.  
- **Runner limit support** after contract/TIF/normalize foundations to avoid duplicate behavior between REST-only limits and automation.  
- **E2E** last: depends on stable routes and callbacks.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase D (metals):** Account-specific `secType`/exchange for XAGUSD and any new symbols — paper `qualify` is source of truth.
- **Phase B (TIF):** Exchange acceptance of IOC for US stock opens — confirm against IB/product rules if any ambiguity remains.

Phases with standard patterns (lighter research):
- **Phase A (cache):** TTL + invalidate is well-trodden; align with existing `_lot_size_cache` patterns.
- **Phase C (normalize):** Local code change with clear unit test surface.
- **Phase F (Playwright):** Established tooling; focus on deterministic selectors and mock boundaries.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | PyPI versions, `ib_insync` API shapes, Decimal/minTick pattern |
| Features | MEDIUM–HIGH | HIGH for XAUUSD CMDTY doc; MEDIUM for XAGUSD and full TIF matrix |
| Architecture | HIGH | File/method locations verified from repo |
| Pitfalls | HIGH | Grounded in `client.py` callbacks, caches, and tracker semantics |

**Overall confidence:** **MEDIUM–HIGH** — implementation path is clear; IB venue/account specifics for metals and HShare TIF need validation in paper/testing.

### Gaps to Address

- **XAGUSD and other metals:** Confirm `secType`/exchange via `qualifyContractsAsync` on target accounts — do not rely on EURUSD-style `Forex` alone.
- **USStock IOC on open:** Confirm venue rules for intended order types and sessions if any rejection appears in paper.
- **OrderTracker vs `_TERMINAL_STATUSES`:** Explicit mapping tests when limit partials are added — avoid semantic drift.

## Sources

### Primary (HIGH confidence)
- [STACK.md](./STACK.md), [FEATURES.md](./FEATURES.md), [ARCHITECTURE.md](./ARCHITECTURE.md), [PITFALLS.md](./PITFALLS.md) — v1.1 research set (2026-04-11)
- [IB TWS API — Basic Contracts (Commodities)](https://interactivebrokers.github.io/tws-api/basic_contracts.html) — XAUUSD CMDTY sample
- [IB ContractDetails](https://interactivebrokers.github.io/tws-api/classIBApi_1_1ContractDetails.html) — minTick / priceMagnifier
- PyPI: `ib-insync`, `cachetools`, `pytest-flask`; npm: `@playwright/test` — versions per STACK.md

### Secondary (MEDIUM confidence)
- v1.0 phase research (TIF, contract qualification) referenced in FEATURES.md
- Industry pattern: mock-first E2E for trading systems

### Tertiary (LOW confidence)
- Long-term IB listing changes for spot metals — mitigate with TTL + invalidate

---
*Research completed: 2026-04-11*  
*Ready for roadmap: yes*
