# Phase 2: Forex contract creation (IDEALPRO) - Research

**Researched:** 2026-04-09
**Domain:** ib_insync contract construction — Forex (CASH/IDEALPRO) branch in IBKRClient
**Confidence:** HIGH

## Summary

Phase 2 is a surgical change: add a `market_type == "Forex"` branch inside `IBKRClient._create_contract` (currently 4 lines at line 780-783 of `client.py`) that returns `ib_insync.Forex(pair=ib_symbol)` instead of `ib_insync.Stock(...)`. The `ib_insync.Forex` class (verified in installed v0.9.86) accepts a 6-character `pair` argument, automatically sets `secType='CASH'`, `exchange='IDEALPRO'`, and splits `symbol`/`currency`. Phase 1 already ensures `normalize_symbol("EURUSD", "Forex")` returns `("EURUSD", "IDEALPRO", "USD")` — the 6-char pair is ready to pass directly.

An unknown `market_type` defense (`ValueError`) is a locked decision. All four callers of `_create_contract` (`place_market_order`, `place_limit_order`, `get_quote`, `is_market_open`) wrap their async coroutines in `try/except Exception` — a `ValueError` from the new `else` branch will be caught and produce a graceful per-request failure without crashing the process.

**Primary recommendation:** Implement the 3-branch `_create_contract` (`Forex`/`USStock`/`HShare` + `else ValueError`), add `MockForex` to test helpers, write use-case-driven tests for EURUSD/USDJPY contract fields and unknown market_type error, then run the full 845-test suite as regression gate.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- 使用 `ib_insync.Forex(pair=ib_symbol)` 构造 Forex 合约
- `ib_symbol` 来自 Phase 1 的 `normalize_symbol` 返回值（6 字母 pair，如 `"EURUSD"`）
- `Forex(pair='EURUSD')` 内部自动拆分为 `symbol='EUR'`, `currency='USD'`, `exchange='IDEALPRO'`
- 不使用显式拆分写法 `Forex(symbol='EUR', currency='USD', exchange='IDEALPRO')`——冗余且 Phase 1 已对齐
- `_create_contract` 收到未知/不支持的 `market_type` 时抛出 ValueError（不静默降级为 Stock）
- 明确报错信息，包含收到的 market_type 值
- 分支结构：`"Forex"` → Forex(pair=), `"USStock"` → Stock(...), `"HShare"` → Stock(...), `else` → ValueError
- 必须验证调用链的异常捕获

### Claude's Discretion
- 是否需要将 `exchange` 和 `currency` 参数也传给 `Forex()` 构造函数（`pair=` 已包含全部信息，但是否显式传 exchange 作为双重保险）
- 测试中是否需要 mock `ib_insync.Forex` 类来验证参数传递
- 现有 USStock/HShare 的 `Stock(...)` 调用是否需要显式判断 market_type 而非依赖 else

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CONT-01 | IBKRClient._create_contract 根据 market_type="Forex" 创建 ib_insync.Forex 合约（secType=CASH, exchange=IDEALPRO） | Verified ib_insync.Forex(pair=) sets secType='CASH', exchange='IDEALPRO' by default. normalize_symbol already returns 6-char pair. All callers have exception protection for the ValueError defense. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ib_insync | 0.9.86 (installed) | `Forex(pair=)` contract construction | Already used for Stock contracts; Forex is the same library's cash FX helper |
| pytest | 9.0.2 (installed) | Unit testing | Already used for all 845 existing tests |

### Supporting
No new libraries needed. Phase 2 uses existing `ib_insync` and `pytest` only.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `Forex(pair='EURUSD')` | `Contract(secType='CASH', symbol='EUR', currency='USD', exchange='IDEALPRO')` | Equivalent but verbose; `Forex()` is the idiomatic ib_insync pattern |
| `Forex(pair=, exchange='IDEALPRO')` | `Forex(pair=)` only | `IDEALPRO` is the default in Forex.__init__; explicit pass is redundant but harmless |

## Architecture Patterns

### Current `_create_contract` (before Phase 2)
```python
def _create_contract(self, symbol: str, market_type: str):
    _ensure_ib_insync()
    ib_symbol, exchange, currency = normalize_symbol(symbol, market_type)
    return ib_insync.Stock(symbol=ib_symbol, exchange=exchange, currency=currency)
```

### Target `_create_contract` (after Phase 2)
```python
def _create_contract(self, symbol: str, market_type: str):
    _ensure_ib_insync()
    ib_symbol, exchange, currency = normalize_symbol(symbol, market_type)
    if market_type == "Forex":
        return ib_insync.Forex(pair=ib_symbol)
    elif market_type in ("USStock", "HShare"):
        return ib_insync.Stock(symbol=ib_symbol, exchange=exchange, currency=currency)
    else:
        raise ValueError(f"Unsupported market_type: {market_type}")
```

### Pattern: ib_insync.Forex construction (verified from source)

From installed `ib_insync/contract.py` line 272-292:

```python
class Forex(Contract):
    def __init__(self, pair='', exchange='IDEALPRO',
                 symbol='', currency='', **kwargs):
        if pair:
            assert len(pair) == 6       # raises AssertionError if not 6 chars
            symbol = symbol or pair[:3]  # base currency
            currency = currency or pair[3:]  # quote currency
        Contract.__init__(self, 'CASH', symbol=symbol,
                          exchange=exchange, currency=currency, **kwargs)
```

Key behaviors verified:
- `Forex(pair='EURUSD')` → `secType='CASH'`, `symbol='EUR'`, `currency='USD'`, `exchange='IDEALPRO'`
- `pair` must be exactly 6 chars (asserted)
- `exchange` defaults to `'IDEALPRO'` — no need to pass explicitly
- `Forex` inherits from `Contract`, same base class as `Stock` — downstream code (qualify, placeOrder) works polymorphically

### Caller Exception Safety (verified)

All four `_create_contract` callers wrap the call inside an async coroutine submitted via `self._submit()`, surrounded by `try/except Exception`:

| Caller | Line | Exception Handling |
|--------|------|--------------------|
| `is_market_open` | 962 | `try/except` at 1005-1013 → `return False, f"RTH check failed: {e}"` |
| `place_market_order` | 1032 | `try/except` at 1076-1080 → `return LiveOrderResult(success=False, message=str(e))` |
| `place_limit_order` | 1097 | `try/except` at 1141-1145 → `return LiveOrderResult(success=False, message=str(e))` |
| `get_quote` | 1302 | `try/except` at 1320-1324 → `return {"success": False, "error": str(e)}` |

**Conclusion:** `ValueError` from the `else` branch is safely caught by every caller. No process crash risk.

### Anti-Patterns to Avoid
- **Using Stock() for Forex:** Would set secType='STK' and route to wrong exchange — qualification fails or trades wrong instrument
- **Passing `exchange='SMART'` for Forex:** SMART is equity routing; IDEALPRO is the correct FX spot venue
- **Silent fallback to Stock on unknown market_type:** Masks configuration bugs — ValueError is the correct behavior (locked decision)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Forex contract with correct secType/exchange | Manual `Contract(secType='CASH', exchange='IDEALPRO', ...)` | `ib_insync.Forex(pair=)` | Handles secType, exchange defaults, symbol/currency split automatically |
| Pair splitting (base/quote) | String slicing `pair[:3]`, `pair[3:]` | `Forex(pair=)` does this internally | Avoids duplication; pair validation via assert built-in |

## Common Pitfalls

### Pitfall 1: Forgetting to branch on market_type before Stock()
**What goes wrong:** All symbols, including Forex, create `Stock(symbol='EURUSD', exchange='IDEALPRO', currency='USD')` — secType is STK not CASH
**Why it happens:** The current code unconditionally returns `Stock()`
**How to avoid:** Explicit `if market_type == "Forex"` branch before the Stock path
**Warning signs:** `qualifyContracts` fails for Forex symbols; error messages about "invalid contract"

### Pitfall 2: normalize_symbol's else branch still defaults to Stock
**What goes wrong:** `normalize_symbol("EURUSD", "SomethingElse")` returns `("EURUSD", "SMART", "USD")` and creates a Stock — silent misconfiguration
**Why it happens:** `normalize_symbol`'s `else` branch defaults to USStock behavior
**How to avoid:** Phase 2 adds `else ValueError` in `_create_contract` to catch this; even if normalize_symbol returns values, the market_type check stops it
**Warning signs:** Unexpected Stock contracts appearing for Forex pairs in logs

### Pitfall 3: MockForex missing in test helpers
**What goes wrong:** Tests fail to verify Forex contract field values because mock module lacks `Forex` class
**Why it happens:** Existing `_make_mock_ib_insync()` only has `MockStock`, `MockMarketOrder`, `MockLimitOrder`
**How to avoid:** Add `MockForex` class that mirrors `Forex.__init__` behavior (split pair, set exchange/secType)
**Warning signs:** `AttributeError: Mock has no attribute 'Forex'` in test runs

### Pitfall 4: ib_insync.Forex assert on pair length
**What goes wrong:** `Forex(pair='EUR')` raises `AssertionError` (not ValueError)
**Why it happens:** `Forex.__init__` has `assert len(pair) == 6`
**How to avoid:** Phase 1's `normalize_symbol` already validates and returns exactly 6-char pairs for Forex; this is a defense-in-depth note
**Warning signs:** AssertionError in production logs for malformed symbols

## Code Examples

### Example 1: Forex contract creation (the core change)
```python
# Verified from ib_insync 0.9.86 source
import ib_insync

contract = ib_insync.Forex(pair='EURUSD')
# contract.secType == 'CASH'
# contract.symbol == 'EUR'
# contract.currency == 'USD'
# contract.exchange == 'IDEALPRO'
```

### Example 2: MockForex for tests
```python
class MockForex:
    def __init__(self, pair='', exchange='IDEALPRO', symbol='', currency='', **kwargs):
        if pair:
            assert len(pair) == 6
            symbol = symbol or pair[:3]
            currency = currency or pair[3:]
        self.secType = 'CASH'
        self.symbol = symbol
        self.currency = currency
        self.exchange = exchange
```

### Example 3: Updated _create_contract
```python
def _create_contract(self, symbol: str, market_type: str):
    _ensure_ib_insync()
    ib_symbol, exchange, currency = normalize_symbol(symbol, market_type)
    if market_type == "Forex":
        return ib_insync.Forex(pair=ib_symbol)
    elif market_type in ("USStock", "HShare"):
        return ib_insync.Stock(symbol=ib_symbol, exchange=exchange, currency=currency)
    else:
        raise ValueError(f"Unsupported market_type: {market_type}")
```

## Claude's Discretion Recommendations

### 1. Should `exchange` also be passed to `Forex()`?
**Recommendation: No.** `Forex(pair='EURUSD')` defaults `exchange='IDEALPRO'` in its `__init__`. Passing it explicitly (`Forex(pair='EURUSD', exchange='IDEALPRO')`) is harmless but redundant. The locked decision says to use `pair=` only, keeping it clean.

### 2. Should tests mock `ib_insync.Forex`?
**Recommendation: Yes.** Add `MockForex` to `_make_mock_ib_insync()` in `test_ibkr_client.py`. This allows tests to assert that `_create_contract` returns an object with correct `secType`, `symbol`, `currency`, `exchange` fields without needing a real ib_insync connection. The mock should replicate the pair-splitting logic for accurate assertions.

### 3. Should USStock/HShare use explicit `elif` instead of falling through `else`?
**Recommendation: Yes — use explicit `elif` for each.** This is aligned with the locked decision's branch structure: Forex → elif USStock/HShare → else ValueError. Making all three known types explicit prevents silent fallback if a new market_type is introduced. The `else ValueError` becomes the catch-all for unknown types.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| All contracts use `Stock()` | Branch by `market_type`: Forex→`Forex()`, Stock types→`Stock()` | Phase 2 (this phase) | Forex pairs correctly identified as CASH/IDEALPRO |
| Unknown market_type silently becomes Stock | Unknown market_type raises ValueError | Phase 2 (this phase) | Configuration bugs surface immediately instead of creating wrong contracts |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `backend_api_python/pytest.ini` (or pyproject.toml) |
| Quick run command | `python -m pytest backend_api_python/tests/test_ibkr_client.py -x -q` |
| Full suite command | `python -m pytest backend_api_python/tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONT-01a | `_create_contract("EURUSD", "Forex")` returns Forex contract with secType=CASH, exchange=IDEALPRO, symbol=EUR, currency=USD | unit | `python -m pytest backend_api_python/tests/test_ibkr_client.py -k "test_create_contract_forex_eurusd" -x` | ❌ Wave 0 |
| CONT-01b | `_create_contract("USDJPY", "Forex")` returns Forex contract with symbol=USD, currency=JPY | unit | `python -m pytest backend_api_python/tests/test_ibkr_client.py -k "test_create_contract_forex_usdjpy" -x` | ❌ Wave 0 |
| CONT-01c | `_create_contract("AAPL", "USStock")` still returns Stock(AAPL, SMART, USD) — regression | unit | `python -m pytest backend_api_python/tests/test_ibkr_client.py -k "test_create_contract_usstock_regression" -x` | ❌ Wave 0 |
| CONT-01d | `_create_contract("0700.HK", "HShare")` still returns Stock(700, SEHK, HKD) — regression | unit | `python -m pytest backend_api_python/tests/test_ibkr_client.py -k "test_create_contract_hshare_regression" -x` | ❌ Wave 0 |
| CONT-01e | `_create_contract("AAPL", "Crypto")` raises ValueError — unknown market_type defense | unit | `python -m pytest backend_api_python/tests/test_ibkr_client.py -k "test_create_contract_unknown_raises" -x` | ❌ Wave 0 |
| CONT-01f | ValueError from _create_contract is caught by place_market_order → LiveOrderResult(success=False) | unit | `python -m pytest backend_api_python/tests/test_ibkr_client.py -k "test_place_order_unknown_market_type_graceful" -x` | ❌ Wave 0 |

### Use Cases (user special instruction)

Every test must be tied to a clear use case with specification:

| Use Case | Specification | Test |
|----------|---------------|------|
| UC-1: Forex pair creates correct contract | Given symbol="EURUSD", market_type="Forex", _create_contract returns Forex with secType=CASH, symbol=EUR, currency=USD, exchange=IDEALPRO | CONT-01a |
| UC-2: Cross pair (JPY quote) creates correct contract | Given symbol="USDJPY", market_type="Forex", _create_contract returns Forex with symbol=USD, currency=JPY, exchange=IDEALPRO | CONT-01b |
| UC-3: USStock path unchanged | Given symbol="AAPL", market_type="USStock", _create_contract returns Stock with symbol=AAPL, exchange=SMART, currency=USD | CONT-01c |
| UC-4: HShare path unchanged | Given symbol="0700.HK", market_type="HShare", _create_contract returns Stock with symbol=700, exchange=SEHK, currency=HKD | CONT-01d |
| UC-5: Unknown market_type fails loudly | Given market_type="Crypto", _create_contract raises ValueError with message containing "Crypto" | CONT-01e |
| UC-6: Error propagation is safe | Given _create_contract raises ValueError, place_market_order catches and returns LiveOrderResult(success=False) without crashing | CONT-01f |

### Sampling Rate
- **Per task commit:** `python -m pytest backend_api_python/tests/test_ibkr_client.py -x -q` (93 existing + new tests)
- **Per wave merge:** `python -m pytest backend_api_python/tests/ -x -q` (full 845-test suite)
- **Phase gate:** Full 845-test suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `MockForex` class in `_make_mock_ib_insync()` helper — needed for Forex contract field assertions
- [ ] New test class `TestCreateContractForex` in `test_ibkr_client.py` — covers CONT-01a through CONT-01f
- No framework install needed (pytest 9.0.2 already present)

## Open Questions

1. **Should `normalize_symbol` also raise ValueError for unknown market_type?**
   - What we know: Currently `normalize_symbol`'s `else` branch defaults to USStock `(symbol, "SMART", "USD")`. Phase 2's `_create_contract` adds ValueError as a second defense layer.
   - What's unclear: Whether to also change `normalize_symbol`'s else branch to raise ValueError (consistency) or leave it as-is (minimize blast radius).
   - Recommendation: Leave `normalize_symbol`'s else as-is for Phase 2 — `_create_contract`'s ValueError is sufficient. Changing `normalize_symbol` may affect other callers not covered by this phase.

## Sources

### Primary (HIGH confidence)
- `ib_insync/contract.py` (installed v0.9.86) — Forex class source, verified `pair` splitting, secType='CASH', default exchange='IDEALPRO'
- `client.py` lines 780-783, 962, 1032, 1097, 1302 — _create_contract and all callers with exception handling
- `symbols.py` — Phase 1 normalize_symbol implementation, returns 6-char pair for Forex
- `test_ibkr_client.py` — Existing 93 tests, mock patterns (`_make_mock_ib_insync`, `_make_client_with_mock_ib`)
- `test_ibkr_symbols.py` — Phase 1 symbol tests (39 tests), regression patterns

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` — ib_insync Forex construction rules, verified against installed source
- `.planning/research/ARCHITECTURE.md` — IBKRClient architecture and call chain analysis

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified against installed ib_insync 0.9.86 source code
- Architecture: HIGH — all callers read directly, exception handling verified line by line
- Pitfalls: HIGH — based on actual code patterns, not hypothetical scenarios

**Research date:** 2026-04-09
**Valid until:** 2026-05-09 (stable domain — ib_insync Forex API is mature and unchanged)
