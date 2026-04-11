# Technology Stack (Additions for v1.1)

**Project:** QuantDinger — IBKR Forex + milestone (limit orders, metals routing, qualify cache, E2E)
**Researched:** 2026-04-11
**Scope:** NEW capabilities only; existing Flask + ib_insync + Vue 2 + Jest + pytest baseline is assumed frozen.

## Recommended Stack

### Core (unchanged — pin / verify)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **ib_insync** | **0.9.86** (PyPI latest as of research) | `LimitOrder`, `MarketOrder`, `Forex`, `Commodity`, `qualifyContractsAsync`, `reqContractDetailsAsync` | Single supported async wrapper around IB Gateway/TWS; already wired through `IBExecutor` / `TaskQueue`. No additional IB API layer needed. |
| **Flask** | 2.3.3 (project) | HTTP API under test | `app.test_client()` for in-process API E2E; no new server stack. |
| **pytest** | (project pin) | Backend tests | Existing 928-test suite; new cases follow same patterns. |

**Version note:** `ib_insync` latest on PyPI is **0.9.86** — matches `requirements.txt` lower bound `>=0.9.86`. Prefer pinning `ib_insync==0.9.86` for reproducibility while this milestone ships.

---

### 1) Limit orders (ib_insync + price precision)

| Item | Version / mechanism | Purpose | Why |
|------|------------------------|---------|-----|
| **ib_insync.LimitOrder** | same package as above | `placeOrder(contract, order)` with `orderType='LMT'` | Constructor: `LimitOrder(action, totalQuantity, lmtPrice, **kwargs)` — passes `lmtPrice` into base `Order` (see upstream `ib_insync/order.py`). Same object model as existing `MarketOrder`. |
| **Order fields** | built-in | TIF, account, etc. | Reuse existing `_get_tif_for_signal` / unification work; `tif` is a standard `Order` field (e.g. `DAY`, `IOC`, `GTD`). |
| **Limit price precision** | **stdlib `decimal.Decimal` + `ContractDetails`** | Round `lmtPrice` to exchange-valid increments | **No new PyPI dependency.** After qualify, use `reqContractDetailsAsync` (already used for lot size) and apply `ContractDetails.minTick` and `priceMagnifier` per [IB contract details](https://interactivebrokers.github.io/tws-api/classIBApi_1_1ContractDetails.html). Float-only math is a common source of “price does not conform to minimum price variation” errors; Decimal + explicit rounding to minTick avoids that. |
| **Integration point** | `IBKRClient.place_limit_order` | Already constructs `ib_insync.LimitOrder(..., lmtPrice=price, tif=tif)` | Extend with a small normalizer step: fetch/cache details → round price → then build `LimitOrder`. |

**Confidence:** **HIGH** for API shape (verified against `erdewit/ib_insync` `order.py` on GitHub). **HIGH** for minTick/magnifier (IB API + existing `ContractDetails` in same library).

---

### 2) Precious metals — CMDTY vs CASH (IDEALPRO)

| Item | Version | Purpose | Why |
|------|---------|---------|-----|
| **ib_insync.Forex** | ib_insync | `secType='CASH'`, 6-char pair | `Forex(pair='XAUUSD')` expands to symbol `XAU`, currency `USD`, exchange default `IDEALPRO`. Used today in `_create_contract` for `market_type == "Forex"`. |
| **ib_insync.Commodity** | ib_insync | `secType='CMDTY'` | `Commodity(symbol=..., exchange=..., currency=...)` maps to CMDTY in `contract.py`. Use when IB’s qualified contract for a “metal” symbol is **CMDTY** (spot metals / OTC-style listing) rather than CASH. |
| **Generic Contract** | ib_insync `Contract` | Escape hatch | `Contract(secType='...', symbol=..., exchange=..., currency=..., localSymbol=...)` if a symbol does not fit `Forex`’s strict 6-char `pair` constructor. |
| **Routing logic** | Application code (no extra lib) | Choose factory per symbol / product line | **No new dependency.** Decision is by **qualification result** and/or curated symbol table: e.g. if `qualifyContractsAsync` returns `CMDTY`, validate with `_EXPECTED_SEC_TYPES`-style rules for a new `market_type` or sub-flag; if `CASH`, keep `Forex` path. IB may list spot gold/silver differently over time — contract search / paper validation is the source of truth. |

**Confidence:** **HIGH** for class mapping (`Forex` → CASH, `Commodity` → CMDTY) from ib_insync source. **MEDIUM** for which symbol uses which secType on your account — must be validated in **paper** with live `qualifyContractsAsync` / Contract Search.

---

### 3) Qualify result caching (in-process TTL)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **cachetools** | **>=7.0.5** (PyPI latest; requires **Python ≥3.10**) | `TTLCache` for `(symbol, market_type, exchange?) → qualified Contract or conId` | Bounded size + TTL eviction; avoids unbounded `dict` growth. Thread-safe enough for typical single-event-loop + executor patterns if **one cache writer** or use behind existing `IBExecutor` serialization. |
| **Alternative: stdlib only** | — | `dict` + monotonic TTL check | Zero dependency; more boilerplate and easier to get eviction wrong. Acceptable for a tiny cache. |

**Integration points:**

- Cache **after** successful `qualifyContractsAsync` (and optionally store `conId` + secType for validation).
- **Invalidate** on reconnect to IB or on qualify errors (optional policy).
- **Do not** cache mutable `Contract` objects shared across coroutines without copying if safety becomes an issue — prefer caching **conId** + minimal fields and rebuilding `Contract(conId=...)` when needed.

**Confidence:** **HIGH** for cachetools version (PyPI API). **MEDIUM** for concurrency semantics — align with your existing `IBClient` threading model in code review.

---

### 4) E2E testing — Flask + HTTP / browser

| Layer | Tool | Version | Purpose | Why |
|-------|------|---------|---------|-----|
| **Backend API** | **Flask `test_client()`** | (Flask built-in) | UC-style full chain tests (already in `tests/test_forex_ibkr_e2e.py`) | No new dependency; same process, deterministic mocks for `ib_insync` / DB. |
| **pytest fixtures (optional)** | **pytest-flask** | **1.3.0** (PyPI) | `client` fixture, `app` lifecycle helpers | Optional convenience only; not required if you keep manual `Flask(__name__)` + blueprint registration. |
| **Browser / real HTTP** | **@playwright/test** + **playwright** | **1.59.1** (npm, as of research) | True E2E: Vue app + API, cross-origin, cookies, redirects | Microsoft-maintained; fits “HTTP frontend testing” beyond Jest unit tests. Install browser binaries via `npx playwright install` in CI. |
| **Already present** | **axios** (frontend), **requests** (backend deps) | — | Manual black-box HTTP | Useful for smoke scripts; not a substitute for Playwright when you need DOM + network assertions. |

**Vue 2 + Vue CLI 5 note:** Keep **Jest + `@vue/test-utils`** for component/unit tests. Add Playwright **only** for the subset of flows that need a real browser or full-stack HTTP.

**What NOT to add (unless requirements expand)**

| Avoid | Why |
|-------|-----|
| **ibapi** (official Java/Python sync API) | Duplicates `ib_insync`; two stacks for one gateway. |
| **Redis / external cache** for qualify | In-process `TTLCache` matches single-gateway, single-process trading engine; add Redis only for multi-instance deployments. |
| **Cypress** (in addition to Playwright) | One browser E2E framework is enough; team already has Playwright skill in `webapp-testing` tooling ecosystem. |
| **Supertest** | Node-centric; backend is Python — use Flask client or `requests` against test server. |
| **Heavy new API frameworks** | No benefit for “Flask test client + HTTP E2E” milestone. |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Qualify cache | `cachetools.TTLCache` | Manual TTL dict | OK for minimal scope; cachetools reduces bugs at small cost. |
| | `cachetools` | `cacheout` / `diskcache` | cachetools is tiny, widely used, no disk complexity. |
| Browser E2E | Playwright | Cypress | Either works; Playwright tends to fit CI + multi-browser with one runner. |
| Limit price math | `Decimal` + `minTick` | float only | IB rejects invalid increments; Decimal is stdlib. |
| Metals contract | `Forex` vs `Commodity` | Futures (`Future`) | Milestone scope is spot/IDEALPRO-style metals, not dated futures. |

---

## Installation (incremental)

```bash
# Backend — qualify cache (optional but recommended)
pip install "cachetools>=7.0.5"

# Optional pytest helpers
pip install "pytest-flask>=1.3.0"

# Frontend — browser E2E (dev)
cd quantdinger_vue && npm install -D @playwright/test@1.59.1 playwright@1.59.1
npx playwright install
```

Pin exact versions in `requirements.txt` / `package.json` when the milestone locks dependencies.

---

## Sources

- PyPI JSON API: `https://pypi.org/pypi/ib-insync/json` — latest **0.9.86**
- PyPI: **cachetools** **7.0.5**, **pytest-flask** **1.3.0**
- `npm view @playwright/test version` — **1.59.1**
- `erdewit/ib_insync` — `ib_insync/order.py` (`LimitOrder`), `ib_insync/contract.py` (`Forex`, `Commodity`, `ContractDetails.minTick` / `priceMagnifier`)
- IB TWS API: ContractDetails / minimum price variation (official docs)

**Overall confidence:** **HIGH** for versions and library roles; **MEDIUM** for IB-specific secType per symbol without account-specific paper validation.
