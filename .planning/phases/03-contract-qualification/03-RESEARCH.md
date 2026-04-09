# Phase 03: Contract Qualification - Research

**Researched:** 2026-04-09
**Domain:** ib_insync contract qualification (qualifyContractsAsync) for Forex/CASH contracts
**Confidence:** HIGH

## Summary

Phase 3 adds Forex contract qualification to IBKRClient. The core mechanism is already in place: `_qualify_contract_async` calls `ib.qualifyContractsAsync(contract)` and checks the return length. This works identically for Forex and Stock contracts because `qualifyContractsAsync` is contract-type-agnostic — it calls `reqContractDetailsAsync`, takes the first result if exactly one match, and copies all fields back into the original contract via `util.dataclassUpdate`. No Forex-specific code is needed in the qualify path itself.

The new work is: (1) a post-qualify validation method `_validate_qualified_contract` that checks `conId != 0` and `secType` matches expectations, (2) enhanced error messages with `market_type` in all 4 caller sites, and (3) comprehensive tests covering 9 use cases + 1 regression. The research confirms exact field values after qualification (conId=12087792, localSymbol='EUR.USD', tradingClass='EUR.USD', exchange='IDEALPRO' for EURUSD) and identifies key pitfalls around XAUUSD (not a Forex/CASH contract on IBKR) and the mock setup for in-place mutation.

**Primary recommendation:** Implement `_validate_qualified_contract` as a simple dict-based secType lookup, modify the 4 caller error messages to include market_type, and use side_effect-based mocking to simulate qualifyContractsAsync's in-place field mutation behavior.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Retry logic: Keep current behavior, same as Stock (no extra retries for Forex)
- Error messages: Include market_type in qualify failure messages (e.g. "Invalid Forex contract: EURUSD")
- Post-qualify defensive check: New `_validate_qualified_contract(self, contract, market_type) -> tuple[bool, str]` method
  - Checks: conId non-zero AND secType matches expected (Forex→CASH, USStock/HShare→STK)
  - Called by all 4 callers after qualify succeeds
- Test fields: Runtime checks for conId + secType; test assertions also cover localSymbol + exchange
- Qualify result caching: Deferred to later

### Claude's Discretion
- `_validate_qualified_contract` 的具体实现细节（如 `expected_sec_types` 映射表结构）
- 错误消息的精确措辞
- 测试 mock 的具体实现方式（如何模拟 qualify 后字段填充）
- 是否需要为 `_validate_qualified_contract` 单独创建测试类或并入现有测试类

### Deferred Ideas (OUT OF SCOPE)
- **Qualify 结果缓存**：同一 Forex 合约短时间内多次 qualify 浪费 API 调用。好想法，但当前 Stock 也没缓存，不在 Phase 3 范围内。
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CONT-03 | Forex 合约通过 qualifyContracts 验证，正确获取 conId 和 localSymbol | qualifyContractsAsync in-place mutation verified: populates conId, localSymbol, tradingClass, exchange via `dataclassUpdate`. Forex contracts get conId (e.g. 12087792 for EURUSD), localSymbol in dot-format (EUR.USD). `_validate_qualified_contract` ensures conId≠0 and secType=CASH. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ib_insync | 0.9.86 | IB API framework — `qualifyContractsAsync`, `Forex`, `Contract` | Already in use; the sole library for IBKR interaction in this codebase |
| pytest | (project version) | Test framework | Already used for all ~840 tests in the project |
| unittest.mock | stdlib | Mocking `qualifyContractsAsync` behavior | Already used extensively in test_ibkr_client.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio | stdlib | Running async mocks in tests | Already used in `_make_client_with_mock_ib()` for `_mock_qualify_async` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| unittest.mock | pytest-mock | No added value; unittest.mock already established in codebase |
| Manual secType mapping dict | Enum | Dict is simpler, more readable, and matches existing codebase style |

**No new dependencies needed.** All tools already exist in the project.

## Architecture Patterns

### Recommended Change Structure
```
backend_api_python/
├── app/services/live_trading/ibkr_trading/
│   └── client.py          # Add _validate_qualified_contract + modify 4 callers
└── tests/
    └── test_ibkr_client.py # Add 9 test cases + regression
```

### Pattern 1: Post-Qualify Validation (New Method)
**What:** `_validate_qualified_contract(self, contract, market_type) -> tuple[bool, str]`
**When to use:** Called by all 4 callers (is_market_open, place_market_order, place_limit_order, get_quote) after `_qualify_contract_async` returns `True`, before proceeding with business logic.
**Example:**
```python
# Source: CONTEXT.md locked decision + ib_insync contract field analysis
_EXPECTED_SEC_TYPES = {
    "Forex": "CASH",
    "USStock": "STK",
    "HShare": "STK",
}

def _validate_qualified_contract(self, contract, market_type: str) -> tuple:
    con_id = getattr(contract, "conId", 0) or 0
    if con_id == 0:
        return (False, f"conId is 0 after qualification for {market_type} contract")

    expected = self._EXPECTED_SEC_TYPES.get(market_type)
    if expected and contract.secType != expected:
        return (False, f"Expected secType={expected} for {market_type}, got {contract.secType}")

    return (True, "")
```

### Pattern 2: Caller Integration (Error Message Enhancement + Validation)
**What:** Each of the 4 callers gets two changes: (a) market_type in qualify-failure message, (b) `_validate_qualified_contract` call after qualify succeeds.
**When to use:** Every caller of `_qualify_contract_async`.
**Example (place_market_order):**
```python
# Before (current):
if not await self._qualify_contract_async(contract):
    return LiveOrderResult(success=False, message=f"Invalid contract: {symbol}", ...)

# After:
if not await self._qualify_contract_async(contract):
    return LiveOrderResult(success=False, message=f"Invalid {market_type} contract: {symbol}", ...)

valid, reason = self._validate_qualified_contract(contract, market_type)
if not valid:
    return LiveOrderResult(success=False, message=reason, ...)
```

### Pattern 3: Mock-Based Qualify Simulation (Test Pattern)
**What:** Use `side_effect` to simulate `qualifyContractsAsync`'s in-place field mutation.
**When to use:** All tests that verify post-qualify field values.
**Example:**
```python
async def _mock_qualify_success_forex(*contracts):
    for c in contracts:
        c.conId = 12087792
        c.localSymbol = "EUR.USD"
        c.tradingClass = "EUR.USD"
        # secType and exchange already set by Forex() constructor
    return list(contracts)

client._ib.qualifyContractsAsync = _mock_qualify_success_forex
```

### Anti-Patterns to Avoid
- **Mutating contract in `_validate_qualified_contract`:** This method ONLY reads fields. Never modify the contract here.
- **Adding qualify retries for Forex:** Locked decision — keep same as Stock. `is_market_open` already has `_RTH_QUALIFY_RETRIES`; other callers don't retry.
- **Checking localSymbol at runtime:** Locked decision — localSymbol is test-only assertion. Runtime checks are conId + secType only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Contract qualification | Custom API calls to reqContractDetails + field copy | `qualifyContractsAsync` | It does reqContractDetails + ambiguity check + field fixup + in-place update. Reimplementing risks missing the SMART exchange fixup and expiry trimming. |
| secType-to-market_type mapping | Nested if/elif chains | Simple dict `_EXPECTED_SEC_TYPES` | Dict is data, not logic. Easy to extend for future market types. |
| In-place contract mutation simulation | Manually setting each field in separate mock | `side_effect` function that mutates the passed contract | Mirrors real `qualifyContractsAsync` behavior (in-place via `dataclassUpdate`). One function, all fields. |

**Key insight:** `qualifyContractsAsync` is deceptively simple in its API but internally handles three distinct concerns (details fetch, ambiguity resolution, field fixup). Never replicate this logic.

## Common Pitfalls

### Pitfall 1: XAUUSD/XAGUSD Are NOT Forex on IBKR
**What goes wrong:** Treating gold (XAUUSD) and silver (XAGUSD) as Forex contracts. They pass `Forex(pair='XAUUSD')` through the 6-char assertion but IBKR classifies them as CMDTY (Commodity OTC Derivative) with secType='CMDTY', NOT 'CASH'. Qualification as Forex will fail or return wrong secType.
**Why it happens:** In MT5 and most retail brokers, XAUUSD is traded alongside Forex pairs. IBKR separates them into the metals/commodity product class (conId=69067924, exchange=SMART, not IDEALPRO).
**How to avoid:** The `_validate_qualified_contract` secType check (CASH for Forex) will catch this — if someone passes XAUUSD as Forex, qualify may succeed but validation will fail with "Expected secType=CASH for Forex, got CMDTY". This is the correct behavior. The QuantDinger strategy system should map metals to a different market_type in a future phase.
**Warning signs:** Test with XAUUSD should verify it's rejected by `_validate_qualified_contract`, not accepted.

### Pitfall 2: qualifyContractsAsync Mutates In-Place
**What goes wrong:** Treating `qualifyContractsAsync` as a pure function that returns new contracts. The original contract object IS mutated via `util.dataclassUpdate(contract, c)`.
**Why it happens:** Most Python APIs return new objects. ib_insync intentionally mutates the original for convenience.
**How to avoid:** In tests, the mock must also mutate the passed contract object (via side_effect), not just return a value. The current `_make_mock_ib_insync()` mock already handles this via `_mock_qualify_async` returning `client._ib.qualifyContracts.return_value`, but for Forex tests that check post-qualify fields, the mock must actually set fields on the contract.
**Warning signs:** Tests pass when checking return value but fail when checking `contract.conId` after qualify.

### Pitfall 3: qualifyContractsAsync Returns Empty List for Ambiguous Contracts
**What goes wrong:** Assuming qualify only fails for "unknown" contracts. It also fails when multiple matches exist (len(detailsList) > 1), logging "Ambiguous contract".
**Why it happens:** For well-specified Forex pairs (e.g., `Forex('EURUSD')` with exchange='IDEALPRO'), this never happens — there's exactly one EURUSD on IDEALPRO. But if exchange were omitted or set to 'SMART', ambiguity could occur.
**How to avoid:** Not a concern for Phase 3 — `Forex(pair=...)` constructor always sets `exchange='IDEALPRO'`, which uniquely identifies the pair. No action needed, but good to document.
**Warning signs:** Qualify returns empty list despite valid pair.

### Pitfall 4: MockForex Doesn't Have conId/localSymbol Fields Before Qualification
**What goes wrong:** Testing post-qualify assertions on a mock that doesn't simulate field population.
**Why it happens:** The current `MockForex` in test_ibkr_client.py sets `secType`, `symbol`, `currency`, `exchange` in `__init__`, but NOT `conId` or `localSymbol` (they default to 0/'' from Contract dataclass). The mock `_mock_qualify_async` returns the mock list but doesn't mutate fields.
**How to avoid:** For tests verifying qualify behavior (UC-1, UC-4-6), create a richer mock that simulates field mutation. For tests that just need "qualify succeeded" (UC-7, UC-8, UC-9), the existing mock is fine.
**Warning signs:** `contract.conId` is 0 even after "successful" qualify in test.

### Pitfall 5: order_normalizer Not Yet Implemented for Forex
**What goes wrong:** `place_market_order` and `place_limit_order` call `get_normalizer(market_type).check(quantity, symbol)` before contract creation. The order_normalizer module doesn't exist yet (Phase 8, EXEC-04).
**Why it happens:** Phase 3 only covers qualification, not order placement. But tests for UC-7 route through `place_market_order`.
**How to avoid:** UC-7 tests must mock `get_normalizer` or ensure the import path works. The existing test infrastructure already mocks `ib_insync` at module level — check that `get_normalizer` is also mockable. If order_normalizer doesn't exist for "Forex" market_type, the test needs to mock or skip the normalizer check.
**Warning signs:** ImportError or KeyError when testing place_market_order with Forex.

## Code Examples

### Example 1: qualifyContractsAsync Source (Verified)
```python
# Source: https://github.com/erdewit/ib_insync/blob/master/ib_insync/ib.py#L1845
async def qualifyContractsAsync(self, *contracts):
    detailsLists = await asyncio.gather(
        *(self.reqContractDetailsAsync(c) for c in contracts))
    result = []
    for contract, detailsList in zip(contracts, detailsLists):
        if not detailsList:
            self._logger.warning(f'Unknown contract: {contract}')
        elif len(detailsList) > 1:
            possibles = [details.contract for details in detailsList]
            self._logger.warning(
                f'Ambiguous contract: {contract}, '
                f'possibles are {possibles}')
        else:
            c = detailsList[0].contract
            assert c
            if contract.exchange == 'SMART':
                c.exchange = contract.exchange
            util.dataclassUpdate(contract, c)
            result.append(contract)
    return result
```
**Key observations:**
- Returns list of SUCCESSFULLY qualified contracts (not all input contracts)
- For Forex, exchange is 'IDEALPRO' (not 'SMART'), so the SMART exchange fixup is skipped
- `util.dataclassUpdate(contract, c)` copies ALL fields from IB's response into the original object

### Example 2: Real EURUSD After Qualification (From Official Notebook)
```python
# Source: https://github.com/erdewit/ib_insync/blob/master/notebooks/tick_data.ipynb
# After ib.qualifyContracts(Forex('EURUSD')):
Forex('EURUSD', conId=12087792, exchange='IDEALPRO',
      localSymbol='EUR.USD', tradingClass='EUR.USD')
```
**Fields populated by qualify:**
| Field | Before | After | Notes |
|-------|--------|-------|-------|
| conId | 0 | 12087792 | Stable across all accounts |
| secType | 'CASH' | 'CASH' | Already set by Forex() constructor |
| symbol | 'EUR' | 'EUR' | Already set by Forex() constructor |
| currency | 'USD' | 'USD' | Already set by Forex() constructor |
| exchange | 'IDEALPRO' | 'IDEALPRO' | Already set by Forex() constructor |
| localSymbol | '' | 'EUR.USD' | Dot-separated, set by IB |
| tradingClass | '' | 'EUR.USD' | Same as localSymbol for Forex |

### Example 3: IB Contract Info for EURUSD (From IB Contract Center)
```
# Source: https://misc.interactivebrokers.com/cstools/contract_info/v3.10/index.php?action=Details&site=GEN&conid=12087792
CONID: 12087792
Symbol: EUR
Exchange: IDEALPRO
Contract Type: Forex
Local Name: EUR.USD
Size Increment: 0.01 (for size > 0.01)
Price Increment: 0.00005 (for price > 0)
Trading Hours: Sun 17:15-Fri 17:00 ET (24/5)
```

### Example 4: USDCHF After Qualification (From Official Notebook)
```python
# Source: https://github.com/erdewit/ib_insync/blob/master/notebooks/ordering.ipynb
Position(account='DU772802', contract=Forex('USDCHF', conId=12087820,
         localSymbol='USD.CHF', tradingClass='USD.CHF'))
```
**Pattern confirmed:** localSymbol is always `BASE.QUOTE` with dot separator for Forex.

### Example 5: dataclassUpdate (In-Place Mutation Mechanism)
```python
# Source: https://github.com/erdewit/ib_insync/blob/master/ib_insync/util.py
def dataclassUpdate(obj, *srcObjs, **kwargs):
    if not is_dataclass(obj):
        raise TypeError(f'Object {obj} is not a dataclass')
    for srcObj in srcObjs:
        obj.__dict__.update(dataclassAsDict(srcObj))
    obj.__dict__.update(**kwargs)
    return obj
```
**Key: This updates `obj.__dict__` directly, mutating the original contract in-place.**

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| qualifyContracts (sync) | qualifyContractsAsync (async) | ib_insync 0.9.x | Codebase already uses async version — no change needed |
| Manual reqContractDetails + field copy | qualifyContractsAsync (wraps both) | Always been available | Never hand-roll; use the built-in |
| XAUUSD as Forex | XAUUSD as CMDTY (separate metals product) | IBKR classification | XAUUSD/XAGUSD are NOT Forex on IBKR — they're OTC commodity derivatives |

**Deprecated/outdated:**
- None relevant. ib_insync is stable (last release 0.9.86, last commit March 2024 — project author passed away). No breaking changes expected.

## Open Questions

1. **order_normalizer for Forex**
   - What we know: `place_market_order`/`place_limit_order` call `get_normalizer(market_type).check()` before creating the contract. This module doesn't exist for "Forex" yet (Phase 8).
   - What's unclear: Will UC-7 (error message test via `place_market_order`) hit an ImportError or KeyError when calling `get_normalizer("Forex")`?
   - Recommendation: Mock `get_normalizer` in UC-7 tests to return a normalizer that always passes. Or use a lower-level test path that bypasses the normalizer. Phase 8 will implement the actual Forex normalizer.

2. **Forex sizeIncrement from ContractDetails**
   - What we know: EURUSD sizeIncrement is 0.01 (per IB Contract Info Center). This is relevant for `_align_qty_to_contract` which runs after qualify.
   - What's unclear: Will `_align_qty_to_contract` behave correctly for Forex quantities (which are typically 20000+)?
   - Recommendation: Not Phase 3 scope (Phase 8, EXEC-04), but document for awareness. `math.floor(25000 / 0.01) * 0.01 = 25000.0` — works correctly.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (installed) |
| Config file | No pytest.ini — uses default discovery |
| Quick run command | `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -x -q` |
| Full suite command | `cd backend_api_python && python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONT-03 / UC-1 | Forex qualify success — fields populated | unit | `pytest tests/test_ibkr_client.py::TestQualifyContractForex::test_forex_qualify_success_fields -x` | ❌ Wave 0 |
| CONT-03 / UC-2 | Forex qualify failure — returns False | unit | `pytest tests/test_ibkr_client.py::TestQualifyContractForex::test_forex_qualify_failure -x` | ❌ Wave 0 |
| CONT-03 / UC-3 | Forex qualify exception — doesn't crash | unit | `pytest tests/test_ibkr_client.py::TestQualifyContractForex::test_forex_qualify_exception -x` | ❌ Wave 0 |
| CONT-03 / UC-4 | _validate_qualified_contract: Forex OK | unit | `pytest tests/test_ibkr_client.py::TestValidateQualifiedContract::test_forex_valid -x` | ❌ Wave 0 |
| CONT-03 / UC-5 | _validate_qualified_contract: secType mismatch | unit | `pytest tests/test_ibkr_client.py::TestValidateQualifiedContract::test_forex_sectype_mismatch -x` | ❌ Wave 0 |
| CONT-03 / UC-6 | _validate_qualified_contract: conId=0 | unit | `pytest tests/test_ibkr_client.py::TestValidateQualifiedContract::test_conid_zero -x` | ❌ Wave 0 |
| CONT-03 / UC-7 | Error message includes market_type | unit | `pytest tests/test_ibkr_client.py::TestQualifyContractForex::test_error_message_includes_market_type -x` | ❌ Wave 0 |
| CONT-03 / UC-8 | Stock qualify regression | unit | `pytest tests/test_ibkr_client.py::TestValidateQualifiedContract::test_stock_valid -x` | ❌ Wave 0 |
| CONT-03 / UC-9 | HShare qualify regression | unit | `pytest tests/test_ibkr_client.py::TestValidateQualifiedContract::test_hshare_valid -x` | ❌ Wave 0 |
| CONT-03 / REGR-01 | Full test suite regression | integration | `cd backend_api_python && python -m pytest tests/ -x -q` | ✅ existing ~840 tests |

### Sampling Rate
- **Per task commit:** `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -x -q`
- **Per wave merge:** `cd backend_api_python && python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_ibkr_client.py::TestQualifyContractForex` — new test class for UC-1,2,3,7
- [ ] `tests/test_ibkr_client.py::TestValidateQualifiedContract` — new test class for UC-4,5,6,8,9
- [ ] Mock enhancement: `_mock_qualify_async` needs side_effect variant that mutates contract fields
- [ ] Framework install: None — pytest already available

## Sources

### Primary (HIGH confidence)
- [ib_insync/ib.py source](https://github.com/erdewit/ib_insync/blob/master/ib_insync/ib.py) — `qualifyContractsAsync` implementation (lines 1845-1866)
- [ib_insync/contract.py source](https://github.com/erdewit/ib_insync/blob/master/ib_insync/contract.py) — `Forex` class, `Contract` dataclass fields
- [ib_insync/util.py source](https://github.com/erdewit/ib_insync/blob/master/ib_insync/util.py) — `dataclassUpdate` in-place mutation
- [IB Contract Information Center: EURUSD](https://misc.interactivebrokers.com/cstools/contract_info/v3.10/index.php?action=Details&site=GEN&conid=12087792) — conId=12087792, localSymbol=EUR.USD, sizeIncrement=0.01
- [IB Contract Information Center: XAUUSD](https://misc.interactivebrokers.com/cstools/contract_info/index2.php?action=Details&conid=69067924&site=GEN) — conId=69067924, secType=Commodity (NOT Forex)
- [ib_insync official notebook: tick_data](https://github.com/erdewit/ib_insync/blob/master/notebooks/tick_data.ipynb) — Real EURUSD after qualify: conId=12087792, localSymbol='EUR.USD'
- [ib_insync official notebook: ordering](https://github.com/erdewit/ib_insync/blob/master/notebooks/ordering.ipynb) — EURUSD ordering example, USDCHF position example

### Secondary (MEDIUM confidence)
- [IBKR Spot Currency Min/Max Order Sizes](https://www.interactivebrokers.com/en/?f=%2Fen%2Ftrading%2FforexOrderSize.php) — EUR minimum 20,000, USD minimum 25,000
- [ib_insync Issue #649](https://github.com/erdewit/ib_insync/issues/649) — qualifyContractsAsync 4-step behavior explanation
- [ib_insync API docs](https://ib-insync.readthedocs.io/api.html) — qualifyContracts returns list of successfully qualified contracts

### Tertiary (LOW confidence)
- None — all critical claims verified with primary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries needed, all existing in codebase
- Architecture: HIGH — `_validate_qualified_contract` pattern straightforward, 4 callers clearly identified with exact line numbers
- Pitfalls: HIGH — XAUUSD/CMDTY distinction verified with IB Contract Center; in-place mutation verified with ib_insync source; MockForex gap identified from reading test code
- qualifyContractsAsync behavior: HIGH — verified from source code + official notebooks + IB Contract Center

**Research date:** 2026-04-09
**Valid until:** Indefinite — ib_insync is in maintenance mode (author deceased March 2024), no API changes expected
