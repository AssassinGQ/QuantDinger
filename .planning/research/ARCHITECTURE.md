# Architecture Patterns — v1.1 Integration (Tech Debt + Limit Orders)

**Domain:** IBKR Forex live trading (brownfield extension)  
**Researched:** 2026-04-11  
**Scope:** NEW work only — limit orders, precious metals, qualify caching, TIF unification, normalize timing, E2E tests  
**Overall confidence:** **HIGH** for file/method locations (read from repo); **MEDIUM** for IBKR product rules on metals (verify against IB contract specs before shipping)

## Recommended Architecture (v1.1 Touchpoints)

```
[Flask ibkr.py POST /order] ──► IBKRClient.place_market_order | place_limit_order
                                        │
[PendingOrderWorker._execute_live_order] ──► get_runner → StatefulClientRunner
                                        │         └── execute() → place_market_order ONLY (today)
                                        │
                                        └── records / callbacks (unchanged pattern)
```

### Component Boundaries (what changes vs stays)

| Component | Responsibility today | v1.1 delta |
|-----------|------------------------|------------|
| `IBKRClient` (`ibkr_trading/client.py`) | Contract, qualify, qty align, market/limit `placeOrder` | Caching inside qualify path; optional `normalize()` in order pipeline; TIF policy in `_get_tif_for_signal`; metals = extend `_create_contract` / `normalize_symbol` if not IDEALPRO CASH |
| `normalize_symbol` (`ibkr_trading/symbols.py`) | Forex → 6-char pair, IDEALPRO, quote ccy | Metals already listed in `KNOWN_FOREX_PAIR`; non–Forex-style contracts need new branches |
| `StatefulClientRunner` (`runners/stateful_runner.py`) | RTH `pre_check`; `execute` → **`place_market_order` only** | **New:** branch or sibling path for limit orders (needs price + order kind on `OrderContext` / payload) |
| `PendingOrderWorker` (`pending_order_worker.py`) | Build `OrderContext`, `create_client`, `get_runner`, `pre_check`, `execute` | Pass through limit fields from `payload` once runner supports limits |
| `app/routes/ibkr.py` | Dispatches market vs limit to client | Already calls `place_limit_order` when `orderType == 'limit'` |
| Vue `trading-assistant` | Wizard UX | E2E improvements are mostly **backend** in this repo; frontend hooks via HTTP API, not Flask `test_client` |

## Integration Answers (numbered)

### (1) Where `place_limit_order` fits alongside `place_market_order`

**Location:** `backend_api_python/app/services/live_trading/ibkr_trading/client.py`

Both methods are parallel implementations:

- **Shared preamble (sync):** `get_normalizer(market_type).check(quantity, symbol)` via `app.services.live_trading.ibkr_trading.order_normalizer` (re-exports `live_trading/order_normalizer`), then `_get_tif_for_signal(signal_type, market_type)`.
- **Shared async body:** `_ensure_connected_async` → `_create_contract` → `_qualify_contract_async` → `_validate_qualified_contract` → `_align_qty_to_contract` → build order → `self._ib.placeOrder` → `_order_contexts[oid] = IBKROrderContext(...)`.

**Difference:** `place_market_order` uses `ib_insync.MarketOrder(...)`; `place_limit_order` uses `ib_insync.LimitOrder(..., lmtPrice=price, ...)`.

**API:** `backend_api_python/app/routes/ibkr.py` (`place_order`) already routes `orderType == 'limit'` to `client.place_limit_order(...)`.

**Gap for automated live trading:** `StatefulClientRunner.execute` only invokes `place_market_order` (see `stateful_runner.py` ~lines 76–90). Any **strategy-driven** limit flow must extend the runner (or add a dedicated runner) and plumb **limit price + order type** through `OrderContext` and `PendingOrderWorker._execute_live_order`’s `ctx` construction.

### (2) Where qualify caching hooks into `_qualify_contract_async`

**Primary hook:** `IBKRClient._qualify_contract_async` in `client.py` (~851–856), the single async entry that calls `self._ib.qualifyContractsAsync(contract)`.

**Related caches (not qualify today):**

- `_lot_size_cache` on `conId` — used in `_align_qty_to_contract` after qualification populates `conId`.
- `is_market_open` uses `_rth_details_cache` keyed by `(conId, date_str)` for **RTH** contract details, not for qualify itself.

**Recommendation:** Implement a **contract-qualify cache** (e.g. keyed by stable hash of `(secType, symbol, currency, exchange, localSymbol)` or normalized `(market_type, display_symbol)` → qualified contract snapshot / `conId`) **inside or immediately wrapping** `_qualify_contract_async`, so all callers (`place_market_order`, `place_limit_order`, `get_quote`, `is_market_open`) benefit without duplicating logic.

**Confidence:** HIGH for hook point; MEDIUM for optimal cache key and invalidation policy (TTL vs session).

### (3) How `_create_contract` must change for precious metals

**Current behavior** (`client.py` ~841–849):

- `normalize_symbol(symbol, market_type)` in `symbols.py` returns `(ib_symbol, exchange, currency)`.
- For `market_type == "Forex"`, `_create_contract` returns `ib_insync.Forex(pair=ib_symbol)` (IDEALPRO CASH).

**Precious metals in repo today:** `KNOWN_FOREX_PAIRS` in `symbols.py` includes `XAUUSD`, `XAGUSD`, `XAUEUR` — treated as **six-letter Forex pairs** like fiat pairs.

**Implication:** If v1.1 “precious metal contracts” means **continuing IDEALPRO spot CASH pairs**, `_create_contract` may need **no new branch**; work may concentrate on validation (`_validate_qualified_contract`), docs, and tests.

**If** product requires **non-CASH** instruments (e.g. futures, CFDs, or a different exchange):

- Extend `normalize_symbol` with a distinct `market_type` (or detection rules).
- Add a branch in `_create_contract` (e.g. `ib_insync.Future(...)`, `Contract(secType=...)`) per IBKR contract definitions.
- Extend `_EXPECTED_SEC_TYPES` and any Forex-specific assumptions (`_get_tif_for_signal` currently treats all `"Forex"` as IOC).

**Confidence:** HIGH for current code path; **verify on paper** for each metal symbol’s actual IB `secType`/exchange.

### (4) Where `normalize()` should be called in the order flow

**Current behavior:** `place_market_order` and `place_limit_order` call only `get_normalizer(market_type).check(quantity, symbol)`. They do **not** call `OrderNormalizer.normalize()`.

**Forex:** `ForexNormalizer.normalize` in `order_normalizer/forex.py` is identity (`return raw_qty`) — used to satisfy the abstract API; `_align_qty_to_contract` performs IB-driven rounding.

**Recommended pipeline (if v1.1 explicitly wires `normalize`):**

1. `check(raw_qty, symbol)` — reject invalid inputs early.
2. `normalized_qty = normalize(raw_qty, symbol)` — identity for Forex today; future-proof for other categories.
3. `_create_contract` / qualify / validate.
4. `await _align_qty_to_contract(contract, normalized_qty, symbol)` — final increment alignment.

**Single file change surface:** the sync section at the start of `place_market_order` / `place_limit_order`, or the first line inside `_do()` before align — **after** `check` and **before** `_align_qty_to_contract`. Avoid calling `normalize` only after qualify if the intent is consistent qty semantics through the whole IB path.

**Note:** Phase 8 planning docs in-repo stated “normalize() not called on purpose”; v1.1 “normalize timing fix” supersedes that product decision — document the new invariant in code comments when implemented.

### (5) How E2E tests hook into Flask `test_client` and the frontend

**Backend E2E (this repository):**

- **`backend_api_python/tests/test_forex_ibkr_e2e.py`:** Documents chain: minimal Flask app → `register_blueprint(strategy_bp)` → `app.test_client()`; mocks JWT/psycopg2; patches `get_db_connection`; uses **real** `PendingOrderWorker`, `StatefulClientRunner`, `IBKRClient` with mocked `ib_insync`. This is the pattern to extend for limit-order or caching scenarios.
- **`backend_api_python/tests/test_ibkr_dashboard.py`:** Registers `ibkr_bp` at `/api/ibkr`, uses `test_client` for dashboard API tests.

**Frontend:** There is **no** Flask `test_client` bridge to Vue in this repo’s tests. The wizard (`quantdinger_vue/src/views/trading-assistant/index.vue`) talks to the backend over HTTP; improving E2E there implies **browser automation** (e.g. Playwright in `webapp-testing` skill) or separate Vue test stack — **out of scope** for pure Flask `test_client` tests.

## Patterns to Follow

### Pattern: One IBKR order pipeline

Keep `place_market_order` and `place_limit_order` structurally identical except order type and limit price — any caching, TIF, or normalize behavior should apply to **both** unless product explicitly diverges.

### Pattern: Runner as single execution policy

`factory.get_runner(client)` returns `StatefulClientRunner` for IBKR (`factory.py`). Execution policy (market vs limit) should stay centralized here once limit orders are supported for live pending orders.

## Anti-Patterns to Avoid

- **Duplicating qualify** outside `_qualify_contract_async` for caching — risks inconsistent cache keys and missed callers (`get_quote`, `is_market_open`).
- **Calling `place_limit_order` only from REST** while the worker still only knows market orders — splits behavior between manual API and automated trading unintentionally.

## Suggested Build Order (dependencies)

1. **Qualify caching** — isolated to `IBKRClient`, low coupling; unblocks latency for all paths.
2. **TIF unification (`_get_tif_for_signal`)** — single method; affects both order types equally.
3. **`normalize()` timing** — small, testable change in `place_market_order` / `place_limit_order` + unit tests in `test_order_normalizer.py`.
4. **Precious metals contract rules** — depends on product decision (CASH vs futures); may be docs/tests only if already covered by Forex branch.
5. **Limit orders in live pipeline** — requires `OrderContext` + payload fields + `StatefulClientRunner` + worker; depends on (1)(2) for stable behavior.
6. **E2E** — extend `test_forex_ibkr_e2e.py` after runner supports limit or after new API surface is stable.

## Scalability Considerations

| Concern | Notes |
|--------|--------|
| Qualify cache growth | Bound entries (LRU/TTL) if symbol universe grows. |
| Thread safety | `IBKRClient` uses `TaskQueue` / ib loop; cache dicts should follow same threading model as existing `_lot_size_cache`. |

## Sources

- Code: `backend_api_python/app/services/live_trading/ibkr_trading/client.py`
- Code: `backend_api_python/app/services/live_trading/ibkr_trading/symbols.py`
- Code: `backend_api_python/app/services/live_trading/runners/stateful_runner.py`
- Code: `backend_api_python/app/services/pending_order_worker.py`
- Code: `backend_api_python/app/routes/ibkr.py`
- Code: `backend_api_python/tests/test_forex_ibkr_e2e.py`
- Planning (historical): `.planning/milestones/v1.0-phases/08-quantity-normalization-ib-alignment/08-CONTEXT.md` (prior decision on `normalize()` not in main chain)
