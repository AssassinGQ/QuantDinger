# Phase 15: Normalize Pipeline Ordering - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Rename `OrderNormalizer` to `MarketPreNormalizer`, rename its methods, add `pre_normalize` to IBKRClient order entry, delete the backward-compatible re-export shim, and update all references. The result is a clear two-layer architecture: market-level pre-normalization (synchronous, no network) followed by broker-level qualify + align (async, IBKR gateway).

</domain>

<decisions>
## Implementation Decisions

### Rename `OrderNormalizer` → `MarketPreNormalizer`
- Base class: `OrderNormalizer` → `MarketPreNormalizer`
- Subclass names: `USStockPreNormalizer`, `HSharePreNormalizer`, `ForexPreNormalizer`, `CryptoPreNormalizer`
- Factory: `get_normalizer()` → `get_market_pre_normalizer()`
- Methods: `normalize()` → `pre_normalize()`, `check()` → `pre_check()`
- The name `MarketPreNormalizer` communicates that this is market-level preprocessing, not broker-level final normalization

### IBKRClient internal pipeline
- Both `place_market_order` and `place_limit_order` entry points become:
  1. `pre_normalize(quantity, symbol)` — synchronous, market-level quantity fix (e.g. floor to integer for US stocks, floor to lot multiple for HK)
  2. `pre_check(quantity, symbol)` — synchronous, market-level validation (e.g. must be positive integer, must be lot multiple)
  3. If `pre_check` fails → return `LiveOrderResult(success=False)`
  4. `_qualify_contract_async(contract)` — async, IBKR gateway
  5. `_align_qty_to_contract(contract, quantity)` — async, uses `sizeIncrement` from qualify result
  6. Place order
- `pre_normalize` and `pre_check` stay synchronous (no network, app-builtin rules only)
- Broker-level qualify + align stays inside async `_do()` — no change to the existing pattern

### Two-layer architecture rationale
- **Layer 1 (Market)**: `pre_normalize` + `pre_check` — governed by exchange rules (NYSE/NASDAQ integer, SEHK board lot). Same rules regardless of broker. Fast-fail without network.
- **Layer 2 (Broker)**: `qualify` + `align` — governed by broker-specific contract details (`sizeIncrement` from IBKR gateway). Each trading engine maintains its own broker-level alignment (Binance `stepSize`, OKX `lotSz`, etc.).
- `MarketPreNormalizer` does NOT include qualify/align. Each client maintains its own broker-level normalization independently.

### SignalExecutor upstream
- Keep the existing `pre_normalize` call in `SignalExecutor.execute()` (line ~364-372)
- Rename from `get_normalizer().normalize()` to `get_market_pre_normalizer().pre_normalize()`
- Idempotent: calling `pre_normalize` twice (upstream + IBKRClient) produces the same result
- Value: normalizes quantity before writing to DB (pending_orders table)

### Backward-compatible shim cleanup
- Delete the entire `ibkr_trading/order_normalizer/` directory (4 files: `__init__.py`, `us_stock.py`, `hk_share.py`, `forex.py`)
- These are pure re-export shims from when normalizer lived under `ibkr_trading/`
- Only consumer is IBKRClient itself (uses old import path)
- IBKRClient switches to direct import from `app.services.live_trading.order_normalizer`

### Scope
- Only IBKR ecosystem + references are modified; no changes to Binance/OKX/MT5/EF client logic
- Non-IBKR engines maintain their own quantity handling independently (as they already do)
- `CryptoPreNormalizer` remains a passthrough (crypto exchanges enforce their own precision)
- `ForexPreNormalizer` remains a passthrough (IBKR accepts float quantities for Forex)

### Claude's Discretion
- Exact docstring wording for renamed classes/methods
- Whether to add deprecation warnings or just hard-rename
- Test organization within the renamed test file
- Whether `pre_normalize` and `pre_check` should be called before or after TIF resolution (no functional impact, just ordering preference)

</decisions>

<specifics>
## Specific Ideas

- User emphasized that `MarketPreNormalizer` should clearly convey "based on market rules" in its naming — hence `Market` prefix on the base class, dropped from subclasses for brevity
- User confirmed that `pre_normalize` is idempotent and keeping it in both SignalExecutor and IBKRClient is acceptable (defense in depth)
- The distinction between market-level normalize and broker-level align was a key discussion point — user wanted clarity on which layer owns which responsibility

</specifics>

<canonical_refs>
## Canonical References

### Normalizer architecture
- `backend_api_python/app/services/live_trading/order_normalizer/__init__.py` — Current `OrderNormalizer` base class, `CryptoNormalizer`, `get_normalizer()` factory
- `backend_api_python/app/services/live_trading/order_normalizer/us_stock.py` — `USStockNormalizer` with `math.floor()` logic
- `backend_api_python/app/services/live_trading/order_normalizer/hk_share.py` — `HShareNormalizer` with `HK_LOT_SIZES` board lot dictionary
- `backend_api_python/app/services/live_trading/order_normalizer/forex.py` — `ForexNormalizer` passthrough

### IBKRClient order entry
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` lines 1159-1235 — `place_market_order` (check → qualify → align → placeOrder)
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` lines 1238-1310 — `place_limit_order` (same pattern)

### Upstream caller
- `backend_api_python/app/services/signal_executor.py` lines 364-372 — `get_normalizer().normalize()` call before DB write

### Shim to delete
- `backend_api_python/app/services/live_trading/ibkr_trading/order_normalizer/` — 4 files, backward-compatible re-exports only

### Tests
- `backend_api_python/tests/test_order_normalizer.py` — Full normalizer test suite (all references need renaming)

### Base class
- `backend_api_python/app/services/live_trading/base.py` — `BaseStatefulClient` has no normalize/check abstract methods (each engine decides its own pipeline)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `TaskQueue` + `_submit()` pattern in IBKRClient: async operations wrapped as sync calls. No need to make `pre_normalize`/`pre_check` async.
- `get_normalizer()` factory pattern: clean market→normalizer dispatch. Rename to `get_market_pre_normalizer()`.

### Established Patterns
- IBKRClient `place_market_order` / `place_limit_order` share identical structure: sync pre-check → async `_do()` with qualify/align/placeOrder. Both must be updated identically.
- `SignalExecutor` calls normalizer before DB write. This pattern is preserved (renamed only).

### Integration Points
- `IBKRClient.place_market_order` line 1163-1164: `get_normalizer(market_type).check()` → becomes `get_market_pre_normalizer(market_type).pre_normalize()` + `.pre_check()`
- `IBKRClient.place_limit_order` line 1242-1243: same change
- `SignalExecutor.execute()` line 364-367: `get_normalizer().normalize()` → `get_market_pre_normalizer().pre_normalize()`
- `tests/test_order_normalizer.py`: all class/method references

</code_context>

<deferred>
## Deferred Ideas

- Fractional share support for US stocks (IBKR supports it, current `USStockPreNormalizer` always floors to integer) — future phase if needed
- Unifying crypto engines' internal `_normalize_quantity()` into `MarketPreNormalizer` — not needed, crypto exchanges enforce their own precision
- Making `BaseStatefulClient` enforce a standard pipeline (normalize → qualify → align) via abstract methods — would require all engines to conform, not worth the coupling

</deferred>

---

*Phase: 15-normalize-pipeline-ordering*
*Context gathered: 2026-04-12*
