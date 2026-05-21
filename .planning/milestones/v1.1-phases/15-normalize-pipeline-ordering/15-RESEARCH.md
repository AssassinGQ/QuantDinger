# Phase 15: Normalize pipeline ordering — Research

**Researched:** 2026-04-12  
**Domain:** Python refactor (IBKR order pipeline + market-level quantity pre-normalization)  
**Confidence:** HIGH (codebase-verified); MEDIUM (external library details N/A for this phase)

## Summary

Phase 15 is a **synchronous rename + pipeline-order refactor** in `backend_api_python`: the market-level normalizer hierarchy becomes `MarketPreNormalizer` with `pre_normalize()` / `pre_check()`, the factory becomes `get_market_pre_normalizer()`, and `IBKRClient.place_market_order` / `place_limit_order` must apply **pre_normalize → pre_check** on the sync path, then pass the **pre-normalized quantity** into the async `_do()` closure for qualify → `_align_qty_to_contract` → `placeOrder`. The shim package `ibkr_trading/order_normalizer/` is deleted; `IBKRClient` imports from `app.services.live_trading.order_normalizer` only. `SignalExecutor` keeps an upstream `pre_normalize` before enqueue (idempotent with the client).

**Critical behavioral change (intentional):** Today the client runs **`check(raw_qty)` only** — e.g. USStock `7.8` fails with “whole number”. After this phase, **`pre_normalize(7.8)→7` then `pre_check(7)`** succeeds and the order proceeds. Existing tests that expect rejection for fractional US quantities **must be rewritten** to expect success with floored quantity (or explicitly scoped to pre_check-only scenarios). Align must receive the **normalized** quantity, not the raw float, or broker-level alignment double-applies inconsistent inputs.

**Primary recommendation:** Implement with a single `normalizer = get_market_pre_normalizer(market_type)` instance per call, `qty = normalizer.pre_normalize(quantity, symbol)`, then `ok, reason = normalizer.pre_check(qty, symbol)`, then close over `qty` for `_align_qty_to_contract(contract, qty, symbol)` and `MarketOrder`/`LimitOrder` `totalQuantity`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Base class: `OrderNormalizer` → `MarketPreNormalizer`
- Subclass names: `USStockPreNormalizer`, `HSharePreNormalizer`, `ForexPreNormalizer`, `CryptoPreNormalizer`
- Factory: `get_normalizer()` → `get_market_pre_normalizer()`
- Methods: `normalize()` → `pre_normalize()`, `check()` → `pre_check()`
- IBKRClient pipeline: `pre_normalize` → `pre_check` → qualify → align → place
- SignalExecutor: keep upstream `pre_normalize` (rename from `get_normalizer().normalize()` to `get_market_pre_normalizer().pre_normalize()`); idempotent with IBKRClient
- Delete entire `ibkr_trading/order_normalizer/` (4 files); IBKRClient uses direct import from `app.services.live_trading.order_normalizer`
- Scope: IBKR + references only; no Binance/OKX/MT5/EF changes
- `CryptoPreNormalizer` / `ForexPreNormalizer` remain passthrough-style at market layer
- Synchronous only (no async changes)

### Claude's Discretion
- Exact docstring wording for renamed classes/methods
- Deprecation warnings vs hard rename
- Test organization within renamed test file
- Whether `pre_normalize` / `pre_check` run before or after TIF resolution inside `place_*` (no functional impact per CONTEXT)

### Deferred Ideas (OUT OF SCOPE)
- Fractional US shares support
- Unifying crypto engines’ `_normalize_quantity()` into `MarketPreNormalizer`
- `BaseStatefulClient` abstract pipeline methods

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-03 | Order pipeline: market pre-normalize and pre-check before qualify; align only after qualify; no duplicate normalize/align on the same logical step | Rename + single `qty` closure; delete shim; tests below |

</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|----------------|
| Python | 3.10+ | Runtime | Project backend |
| pytest | 9.0.2 (verified `python3 -m pytest --version` in env) | Unit/integration tests | Existing suite (~928 tests per ROADMAP) |
| unittest.mock | stdlib | `patch`, `MagicMock` | `test_ibkr_client.py` patterns |
| abc | stdlib | ABC / abstractmethod | Current normalizer base |

### Supporting

| Library | Purpose | When to Use |
|---------|---------|-------------|
| ib_insync | IBKR API | Already optional dep; client tests patch `ib_insync` |

**Installation:** No new packages for this phase.

**Version verification:** `pytest 9.0.2` (local run 2026-04-12).

## Architecture Patterns

### Recommended flow (IBKRClient)

**What:** One `MarketPreNormalizer` instance per `place_*` call; sync steps before `_submit(_do())`; async body uses the **same numeric `qty`** produced by `pre_normalize`.

**When to use:** All `place_market_order` / `place_limit_order` paths.

**Anti-pattern:** Calling `pre_normalize` / `pre_check` on the sync path but passing the **original** `quantity` into `_align_qty_to_contract` — breaks INFRA-03 and can mis-log align steps.

### Recommended flow (SignalExecutor)

**What:** After sizing, `amount = get_market_pre_normalizer(market_category).pre_normalize(amount, symbol)`; keep `amount <= 0` guard.

**When to use:** Unchanged call site (~364–376); only identifiers rename.

### Shim removal

**What:** No package under `ibkr_trading/order_normalizer/`; all imports from `app.services.live_trading.order_normalizer`.

**Anti-pattern:** Leaving any `from app.services.live_trading.ibkr_trading.order_normalizer import ...` in production code.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Ad-hoc quantity rules in `IBKRClient` | Inline `floor` / lot math | `MarketPreNormalizer` hierarchy | Rules already centralized; HK lot table lives in one module |
| New compatibility layer | Another re-export package | Direct imports | User explicitly deletes shim |

## Common Pitfalls

### Pitfall 1: Docs contradict locked pipeline wording
**What goes wrong:** `.planning/REQUIREMENTS.md` INFRA-03 text says normalize *after* check; `.planning/ROADMAP.md` Phase 15 success criteria mention “check → normalize”. **Locked CONTEXT** is `pre_normalize` → `pre_check`.  
**How to avoid:** Treat CONTEXT as source of truth for implementation; update REQUIREMENTS/ROADMAP wording in the same phase or a doc-follow-up so traceability matches code.

### Pitfall 2: Fractional US / HK tests left unchanged
**What goes wrong:** `TestQuantityGuard.test_market_order_rejects_fractional` and `test_limit_order_rejects_fractional` currently expect **failure** for `7.8` / `3.5` USStock. After pre_normalize + pre_check, these become **valid** (floored to 7 / 3).  
**Warning signs:** Pytest failures with messages still expecting `"whole number"` from the client path.

### Pitfall 3: Forgetting to thread `qty` into async closure
**What goes wrong:** `pre_normalize` runs but `_align_qty_to_contract` still uses raw `quantity`.  
**How to avoid:** Code review checklist: `placeOrder` `totalQuantity` equals post-`pre_normalize` value for market-level rules (before IB increment alignment).

### Pitfall 4: Removing shim without updating tests
**What goes wrong:** `TestBackwardCompatImport` in `test_order_normalizer.py` **expects** old imports to work.  
**How to avoid:** Replace with “import from deleted path raises `ModuleNotFoundError`” or delete those tests after shim removal (see test specs).

## Code Examples

### Factory and subclass pattern (after rename)

```python
# Conceptual — matches current get_normalizer dispatch
def get_market_pre_normalizer(market_category: str) -> MarketPreNormalizer:
    cat = (market_category or "").strip()
    if cat == "HShare":
        return HSharePreNormalizer()
    if cat == "Forex":
        return ForexPreNormalizer()
    if cat == "Crypto":
        return CryptoPreNormalizer()
    return USStockPreNormalizer()
```

### IBKRClient sync preamble (conceptual)

```python
from app.services.live_trading.order_normalizer import get_market_pre_normalizer

def place_market_order(self, symbol, side, quantity, market_type="USStock", **kwargs):
    n = get_market_pre_normalizer(market_type)
    qty = n.pre_normalize(quantity, symbol)
    ok, reason = n.pre_check(qty, symbol)
    if not ok:
        return LiveOrderResult(success=False, message=reason, exchange_id=self.engine_id)
    ...
    async def _do():
        ...
        q = await self._align_qty_to_contract(contract, qty, symbol)
```

Source: derived from current `client.py` structure and `15-CONTEXT.md`.

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|------------------|-------|
| Shim re-exports under `ibkr_trading/order_normalizer/` | Direct imports from `live_trading/order_normalizer` | Shim deleted this phase |
| `check` before `normalize` at IBKR boundary | `pre_normalize` before `pre_check` | Fixes INFRA-03 intent per CONTEXT |

## Open Questions

1. **REQUIREMENTS.md INFRA-03 literal text vs CONTEXT**
   - What we know: CONTEXT locks `pre_normalize` → `pre_check`.
   - Recommendation: Align REQUIREMENTS sentence with shipped behavior when merging Phase 15.

2. **ROADMAP success criteria line “check → normalize”**
   - What we know: Conflicts with implementation order.
   - Recommendation: Edit ROADMAP Phase 15 bullets to match `pre_normalize` → `pre_check` → qualify → align.

## Test Case Specifications

> **Convention:** `TC-15-<task>-<seq>` — **task** matches implementation tasks in PLAN.md (below are suggested task IDs T1–T5).

### Task T1 — Rename `order_normalizer` package (base, subclasses, factory)

| Test ID | Test name | Input | Expected output | Category |
|---------|-----------|-------|-----------------|----------|
| TC-15-T1-01 | Import base class | `from app.services.live_trading.order_normalizer import MarketPreNormalizer` | No exception; `MarketPreNormalizer` is ABC | Rename verification |
| TC-15-T1-02 | USStock pre_normalize parity | `USStockPreNormalizer().pre_normalize(7.8, "AAPL")` | `7` (int) | Behavioral preservation |
| TC-15-T1-03 | USStock pre_check rejects fractional **input** | `pre_check(3.5, "AAPL")` | `(False, msg)` with “whole number” | Behavioral preservation |
| TC-15-T1-04 | HShare pre_normalize HSBC | `pre_normalize(450.0, "00005")` | `400` | Behavioral preservation |
| TC-15-T1-05 | Forex passthrough | `ForexPreNormalizer().pre_normalize(1000.7, "EURUSD")` | `1000.7` | Behavioral preservation |
| TC-15-T1-06 | Crypto passthrough | `CryptoPreNormalizer().pre_normalize(0.00123, "BTCUSDT")` | `0.00123` | Behavioral preservation |
| TC-15-T1-07 | Factory dispatch HShare | `type(get_market_pre_normalizer("HShare")).__name__` | `'HSharePreNormalizer'` | Rename verification |
| TC-15-T1-08 | Factory default US | `type(get_market_pre_normalizer("")).__name__` | `'USStockPreNormalizer'` | Behavioral preservation |
| TC-15-T1-09 | Factory None → US | `type(get_market_pre_normalizer(None)).__name__` | `'USStockPreNormalizer'` | Behavioral preservation |

### Task T2 — `IBKRClient.place_market_order` / `place_limit_order`

| Test ID | Test name | Input | Expected output | Category |
|---------|-----------|-------|-----------------|----------|
| TC-15-T2-01 | Order: US fractional floors then submits | `place_market_order("AAPL","buy",7.8,"USStock")` with mocks | `success=True`; `placeOrder` order `totalQuantity==7` (after align) | New behavior |
| TC-15-T2-02 | Limit: US fractional floors | `place_limit_order("AAPL","buy",3.5,150.0,"USStock")` | `success=True`; `totalQuantity==3` | New behavior |
| TC-15-T2-03 | Sync failure still no gateway call | `place_market_order("AAPL","buy",-5,"USStock")` | `success=False`; `placeOrder` not called | Regression |
| TC-15-T2-04 | HShare invalid lot still fails before async | `place_market_order("00005","buy",3,"HShare")` | `success=False`; `"400"` in message; `placeOrder` not called | Regression |
| TC-15-T2-05 | Pipeline order spy (optional) | Patch `MarketPreNormalizer.pre_normalize` / `pre_check` on instance or module | `pre_normalize` called before `pre_check`; both before `qualifyContractsAsync` | New behavior |
| TC-15-T2-06 | Align input uses normalized qty | Mock `_align_qty_to_contract`; `place_market_order(..., 7.8, "USStock")` | `_align_qty_to_contract` called with quantity `7` (not `7.8`) | New behavior |

### Task T3 — `signal_executor.py`

| Test ID | Test name | Input | Expected output | Category |
|---------|-----------|-------|-----------------|----------|
| TC-15-T3-01 | Import path | Static: `grep get_market_pre_normalizer signal_executor.py` | Single factory name; no `get_normalizer` | Rename verification |
| TC-15-T3-02 | Method names | Static: `pre_normalize(` present; `normalize(` absent for normalizer | Pass | Rename verification |
| TC-15-T3-03 | Integration (optional) | Extend `test_signal_executor` with patch on `get_market_pre_normalizer` | Enqueue receives `amount` after `pre_normalize` same as today’s semantics | Regression |

### Task T4 — Delete `ibkr_trading/order_normalizer/` shim

| Test ID | Test name | Input | Expected output | Category |
|---------|-----------|-------|-----------------|----------|
| TC-15-T4-01 | No production imports | `rg 'ibkr_trading\.order_normalizer'` under `backend_api_python/app` | Zero matches | Regression |
| TC-15-T4-02 | Deleted path import fails | `importlib.import_module("app.services.live_trading.ibkr_trading.order_normalizer")` | Raises `ModuleNotFoundError` | New behavior |

### Task T5 — Tests: `test_order_normalizer.py` rename + shim tests

| Test ID | Test name | Input | Expected output | Category |
|---------|-----------|-------|-----------------|----------|
| TC-15-T5-01 | Module docstring | File header mentions `MarketPreNormalizer` | N/A | Rename verification |
| TC-15-T5-02 | Remove or invert backward-compat class | Old `TestBackwardCompatImport` | Either deleted or replaced by TC-15-T4-02 | New behavior |
| TC-15-T5-03 | All factory tests use new names | `TestGetNormalizer` → e.g. `TestGetMarketPreNormalizer` | `isinstance(..., HSharePreNormalizer)` etc. | Rename verification |

### Task T6 — `test_ibkr_client.py` quantity guard updates

| Test ID | Test name | Input | Expected output | Category |
|---------|-----------|-------|-----------------|----------|
| TC-15-T6-01 | Replace `test_market_order_rejects_fractional` | `7.8` USStock | **Success** with quantity 7; update docstring | New behavior |
| TC-15-T6-02 | Replace `test_limit_order_rejects_fractional` | `3.5` USStock | **Success** with quantity 3 | New behavior |

---

## Catalog: existing `tests/test_order_normalizer.py` → renamed equivalent

| # | Class | Method | New name / note |
|---|-------|--------|-----------------|
| 1 | `TestHKSymbolKey` | `test_strips_leading_zeros` | Unchanged (`_hk_symbol_key` unchanged) |
| 2 | | `test_strips_hk_suffix` | Unchanged |
| 3 | | `test_plain_number` | Unchanged |
| 4 | | `test_zero` | Unchanged |
| 5 | | `test_empty` | Unchanged |
| 6 | `TestUSStockNormalizer` | `test_normalize_floors` | `TestUSStockPreNormalizer` / `test_pre_normalize_floors` |
| 7 | | `test_normalize_whole` | `test_pre_normalize_whole` |
| 8 | | `test_normalize_small` | `test_pre_normalize_small` |
| 9 | | `test_check_valid` | `test_pre_check_valid` |
| 10 | | `test_check_zero` | `test_pre_check_zero` |
| 11 | | `test_check_negative` | `test_pre_check_negative` |
| 12 | | `test_check_fractional` | `test_pre_check_fractional` |
| 13 | | `test_check_float_whole` | `test_pre_check_float_whole` |
| 14–26 | `TestHShareNormalizer` | all 20 methods | Same tests; class `TestHSharePreNormalizer`; call `pre_normalize` / `pre_check` |
| 27–36 | `TestForexNormalizer` | all 10 methods | `TestForexPreNormalizer`; `pre_normalize` / `pre_check`; keep UC-N1…N6 intent |
| 37–39 | `TestCryptoNormalizer` | 3 methods | `TestCryptoPreNormalizer` |
| 40–45 | `TestGetNormalizer` | 6 methods | `TestGetMarketPreNormalizer`; assert subclass names `*PreNormalizer` |
| 46–47 | `TestBackwardCompatImport` | 2 methods | **Remove** or replace with shim deletion test (TC-15-T4/T5) |

**Total:** 54 test methods in file today (including 2 backward-compat tests to remove/replace).

## Sources

### Primary (HIGH confidence)
- `backend_api_python/app/services/live_trading/order_normalizer/*.py` — current behavior
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — lines 1159–1315
- `backend_api_python/app/services/signal_executor.py` — lines 364–372
- `backend_api_python/tests/test_order_normalizer.py`, `test_ibkr_client.py` — test expectations
- `.planning/phases/15-normalize-pipeline-ordering/15-CONTEXT.md` — locked decisions

### Secondary (MEDIUM)
- `.planning/ROADMAP.md` Phase 15 — success criteria wording may need sync

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none found in `backend_api_python/` (uses defaults) |
| Quick run | `cd backend_api_python && python3 -m pytest tests/test_order_normalizer.py -x` |
| Full suite | `cd backend_api_python && python3 -m pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated command | File |
|--------|----------|-----------|-------------------|------|
| INFRA-03 | pre_normalize → pre_check → qualify → align; single logical qty | unit + client mock | `pytest tests/test_order_normalizer.py tests/test_ibkr_client.py::TestQuantityGuard -x` | Exists; **update** TestQuantityGuard |

### Sampling Rate
- Per task commit: targeted pytest above
- Phase gate: full `python3 -m pytest` green

### Wave 0 Gaps
- [ ] Optional: dedicated test `test_ibkr_pre_normalize_before_pre_check_order` (spy/patch) if not folded into T2-05
- [ ] REQUIREMENTS/ROADMAP text alignment with CONTEXT (non-code)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — repo env
- Architecture: HIGH — read from `client.py` + CONTEXT
- Pitfalls: HIGH — fractional US case proven in `test_ibkr_client.py` vs new pipeline
- Test specs: HIGH — mapped from existing tests + intended behavior change

**Research date:** 2026-04-12  
**Valid until:** ~30 days (stable domain)
