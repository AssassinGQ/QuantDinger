# Phase 1: Internal IBKRClient Migration (v2.0) - Research

**Researched:** 2026-04-09
**Domain:** Python ib_insync integration, IBKR historical data API
**Confidence:** HIGH

## Summary

This phase migrates IBKRDataSource from external `ibkr_datafetcher` library to use internal `IBKRClient`. Key findings: (1) internal IBKRClient already has `get_quote()` method for ticker data, (2) only `get_historical_bars()` needs to be added to internal client, (3) the method signature must match BaseDataSource interface: `get_kline(symbol, timeframe, limit, before_time=None)`, (4) error handling follows existing framework patterns — get_kline returns `[]` on error, get_ticker returns `{last: 0}` on error.

**Primary recommendation:** Add `get_historical_bars(symbol, timeframe, limit, before_time=None)` method to internal IBKRClient that wraps `ib_insync.IB.reqHistoricalDataAsync()` and returns List[Dict] in BaseDataSource format.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-28:** Internal IBKRClient 添加 `get_historical_bars(symbol, timeframe, limit, before_time=None)` 方法，签名与 BaseDataSource.get_kline() 一致
- **D-29:** 返回 `List[Dict[str, Any]]`，格式: `[{"time": int, "open": float, "high": float, "low": float, "close": float, "volume": float}]`
- **D-30:** get_kline 异常 → `logger.error` 记录 → 返回 `[]` 空列表
- **D-31:** get_ticker 异常 → `logger.warning` 记录 → 返回 `{last: 0, "symbol": symbol}`
- **D-32:** 不自动重连，依赖 IBKRClient 内部健康检查机制
- **D-33:** 保持 v1.0 逻辑：数据库1m → 数据库5m → 数据库k线 → 拉网（调用内部 get_historical_bars）
- **D-34:** 直接返回 Dict 格式，与 BaseDataSource 接口定义一致，无需额外转换
- **D-35:** `get_ticker_price(contract)` → `get_quote(symbol, market_type)` (内部 IBKRClient 已实现)
- **D-36:** `make_contract(SymbolConfig)` → `_create_contract(symbol, market_type)` (内部已实现)

### Claude's Discretion
- 数据重试和错误处理的具体实现细节
- K线数据格式的微调

### Deferred Ideas (OUT OF SCOPE)
- 港股数据支持 — Phase 2
- 外汇数据支持 — Phase 2
- 数据缓存/存储优化 — 后续优化
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-V2-01 | 复用内部 IBKRClient，移除外部 ibkr_datafetcher 依赖 | Research confirms internal IBKRClient has get_quote() and _create_contract() methods already implemented |
| REQ-V2-02 | 在内部 IBKRClient 添加 get_historical_bars() 方法 | Research details ib_insync reqHistoricalDataAsync() API and required wrapper implementation |
| REQ-V2-03 | 在内部 IBKRClient 添加 get_ticker_price() 方法 → 使用 get_quote() | Confirmed get_quote() already exists at line 1297 in internal client.py |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ib_insync | 0.9.86 | IBKR Gateway API wrapper | Project already uses this for trading |
| Python 3.x | 3.x | Runtime | Project constraint |
| pytest | latest | Testing framework | Project uses pytest |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio | stdlib | Async event loop | Internal IBKRClient uses TaskQueue with asyncio |
| typing | stdlib | Type hints | Required by project conventions |

**Installation:**
```bash
pip install ib_insync==0.9.86
# Already in requirements.txt
```

**Version verification:**
- ib_insync 0.9.86 - confirmed from CLAUDE.md

---

## Architecture Patterns

### Recommended Project Structure
```
backend_api_python/
├── app/
│   ├── data_sources/
│   │   ├── base.py                    # BaseDataSource interface
│   │   ├── ibkr.py                    # IBKRDataSource (to be modified)
│   │   └── factory.py                 # DataSourceFactory
│   └── services/
│       └── live_trading/
│           └── ibkr_trading/
│               └── client.py          # Internal IBKRClient (to add method)
```

### Pattern 1: IBKRClient Method Addition
**What:** Add `get_historical_bars()` to internal IBKRClient that wraps ib_insync async API with synchronous interface

**When to use:** When IBKRDataSource needs to fetch historical kline data using internal client

**Example:**
```python
# Source: Based on external ibkr_datafetcher implementation (line 232-269)
# Modified for internal client architecture (TaskQueue pattern)

def get_historical_bars(
    self,
    symbol: str,
    timeframe: str,
    limit: int,
    before_time: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    获取历史K线数据
    
    Args:
        symbol: 股票代码 (例如: AAPL, MSFT)
        timeframe: 时间周期 (1m, 5m, 15m, 30m, 1H, 4H, 1D)
        limit: 数据条数
        before_time: 获取此时间之前的数据（Unix时间戳）
        
    Returns:
        K线数据列表，格式:
        [{"time": int, "open": float, "high": float, "low": float, "close": float, "volume": float}, ...]
    """
    import asyncio as _aio
    
    async def _task():
        # Ensure connected
        await self._ensure_connected_async()
        
        # Create and qualify contract
        contract = self._create_contract(symbol, market_type="USStock")
        if not await self._qualify_contract_async(contract):
            return []
        
        # Determine duration based on timeframe and limit
        duration = self._calculate_duration(timeframe, limit)
        
        # Call ib_insync async API
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            "",  # end_date_time (empty = now)
            duration,
            timeframe,  # bar_size
            "TRADES",  # what_to_show
            True,  # useRTH
            2,  # formatDate
            False,  # keepUpToDate
        )
        
        # Convert to Dict format
        result = []
        for bar in bars:
            # bar.date is datetime
            ts = int(bar.date.timestamp())
            result.append({
                "time": ts,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            })
        
        # Filter by before_time if specified
        if before_time:
            result = [b for b in result if b["time"] < before_time]
        
        # Limit results (take most recent)
        if len(result) > limit:
            result = result[-limit:]
        
        return result
    
    try:
        return self._submit(_task(), timeout=120.0)
    except Exception as e:
        logger.error("get_historical_bars failed for %s: %s", symbol, e)
        return []
```

### Anti-Patterns to Avoid
- **Direct async call from sync method:** Don't call async directly - use TaskQueue._submit() pattern like existing get_quote() method
- **Missing contract qualification:** Always call _qualify_contract_async() before requesting data
- **No error handling:** Must catch exceptions and return [] as per D-30

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Historical data fetching | Custom async wrapper | `ib_insync.IB.reqHistoricalDataAsync()` | Official API, handles all IBKR quirks |
| Contract creation | Manual contract building | `_create_contract()` from internal client | Handles symbol normalization, exchange mapping |
| Quote fetching | Custom ticker implementation | `get_quote()` already exists | Implemented at line 1297 |

**Key insight:** Internal IBKRClient already has the infrastructure - just need to add the method following same patterns.

---

## Common Pitfalls

### Pitfall 1: Missing Contract Qualification
**What goes wrong:** reqHistoricalDataAsync returns empty or fails for unqualified contracts
**Why it happens:** IBKR requires contracts to be qualified (validated) before requesting data
**How to avoid:** Always call `_qualify_contract_async(contract)` before requesting historical data
**Warning signs:** Empty bar list, "contract not qualified" errors in logs

### Pitfall 2: Wrong Duration Calculation
**What goes wrong:** Request too much or too little data, causing performance issues or incomplete data
**Why it happens:** IBKR duration strings (e.g., "1 D", "1 W") don't map linearly to candle counts
**How to avoid:** Use BaseDataSource.calculate_time_range() with buffer_ratio=1.2 to estimate needed duration
**Warning signs:** Always getting exactly X bars regardless of limit, or taking very long time

### Pitfall 3: Timezone Handling
**What goes wrong:** K-line timestamps off by hours, causing wrong time filtering
**Why it happens:** IBKR returns datetime objects without timezone or in local timezone
**How to avoid:** Always convert to UTC timestamps using .timestamp() as shown in example
**Warning signs:** K-lines showing "future" times or times significantly off from expected

### Pitfall 4: Not Using TaskQueue Pattern
**What goes wrong:** Blocking calls freeze the event loop, causing deadlocks
**Why it happens:** Internal IBKRClient is designed to run on IBExecutor event loop thread
**How to avoid:** Wrap all ib_insync calls in async def and submit via self._submit() like get_quote()
**Warning signs:** Timeouts, hanging requests, "event loop" errors

### Pitfall 5: Forgetting Rate Limiter
**What goes wrong:** Trigger IBKR API rate limits, causing request failures
**Why it happens:** IBKR has built-in rate limits (especially for historical data)
**How to avoid:** Use existing rate_limiter from IBKRDataSource before calling get_historical_bars
**Warning signs:** "rate limit" errors, request timeouts after many rapid calls

### Pitfall 6: Not Using Cache Layer
**What goes wrong:** Always fetching from network, slow performance, hitting rate limits
**Why it happens:** Skipping kline_fetcher cache check (database 1m → 5m → kline)
**How to avoid:** Check kline_fetcher.get_kline() first before calling get_historical_bars (per D-33)
**Warning signs:** Consistently slow get_kline response times

---

## Code Examples

### Existing get_quote() Pattern (Internal IBKRClient)
```python
# Source: backend_api_python/app/services/live_trading/ibkr_trading/client.py (line 1297-1324)
def get_quote(self, symbol: str, market_type: str = "USStock") -> Dict[str, Any]:
    import asyncio as _aio

    async def _task():
        await self._ensure_connected_async()
        contract = self._create_contract(symbol, market_type)
        if not await self._qualify_contract_async(contract):
            return {"success": False, "error": f"Invalid contract: {symbol}"}
        ticker = self._ib.reqMktData(contract, "", False, False)
        await _aio.sleep(2)  # Wait for data
        result = {
            "success": True, "symbol": symbol,
            "bid": ticker.bid if ticker.bid and ticker.bid > 0 else None,
            "last": ticker.last if ticker.last and ticker.last > 0 else None,
            # ... other fields
        }
        self._ib.cancelMktData(contract)
        return result

    try:
        return self._submit(_task(), timeout=15.0)
    except Exception as e:
        logger.error("Get quote failed: %s", e)
        return {"success": False, "error": str(e)}
```

### BaseDataSource.get_kline() Interface
```python
# Source: backend_api_python/app/data_sources/base.py (line 41-61)
@abstractmethod
def get_kline(
    self,
    symbol: str,
    timeframe: str,
    limit: int,
    before_time: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    获取K线数据
    
    Args:
        symbol: 交易对/股票代码
        timeframe: 时间周期 (1m, 5m, 15m, 30m, 1H, 4H, 1D, 1W)
        limit: 数据条数
        before_time: 获取此时间之前的数据（Unix时间戳，秒）
        
    Returns:
        K线数据列表，格式:
        [{"time": int, "open": float, "high": float, "low": float, "close": float, "volume": float}, ...]
    """
    pass
```

### v1.0 IBKRDataSource Using External Library (To Be Replaced)
```python
# Source: backend_api_python/app/data_sources/ibkr.py (lines 9-11, current v1.0)
# External ibkr_datafetcher imports - TO BE REPLACED
from ibkr_datafetcher.config import GatewayConfig
from ibkr_datafetcher.ibkr_client import IBKRClient
from ibkr_datafetcher.types import KlineBar, SymbolConfig, Timeframe, resolve_timeframe

# Current implementation uses:
# - self._client.make_contract(symbol_config)
# - self._client.get_historical_bars(contract=contract, timeframe=tf)
# - self._client.get_ticker_price(contract)

# v2.0 will replace with:
# - get_ibkr_client() singleton
# - self._client._create_contract(symbol, market_type)
# - self._client.get_historical_bars(symbol, timeframe, limit)
# - self._client.get_quote(symbol, market_type)
```

---

## v2.0 Test Case Mapping

### From v2.0-test-cases.md

| ID | Category | Test Case | Implementation Location |
|----|----------|-----------|------------------------|
| TC-30 | Internal Client | _create_contract() 美股合约 | client.py (exists at line 780) |
| TC-31 | Internal Client | _create_contract() 中国股票 | client.py (exists at line 780) |
| TC-35 | Internal Client | get_quote() 美股报价 | client.py (exists at line 1297) |
| TC-36 | Internal Client | get_quote() 无效合约 | client.py (exists at line 1297) |
| TC-37 | Internal Client | get_quote() null值处理 | client.py (exists at line 1297) |
| TC-40 | **NEW** | get_historical_bars() 基础功能 | **client.py (NEEDS IMPLEMENTATION)** |
| TC-41 | **NEW** | get_historical_bars() 不同周期 | **client.py (NEEDS IMPLEMENTATION)** |
| TC-42 | **NEW** | get_historical_bars() 边界过滤 | **client.py (NEEDS IMPLEMENTATION)** |
| TC-43 | **NEW** | get_historical_bars() 错误处理 | **client.py (NEEDS IMPLEMENTATION)** |
| TC-50 | Migration | 使用内部Client | ibkr.py (replace imports) |
| TC-51 | Migration | 不使用外部库 | ibkr.py (remove ibkr_datafetcher) |
| TC-55 | Migration | make_contract → _create_contract | ibkr.py (method mapping) |
| TC-56 | Migration | qualify_contract → _qualify_contract_async | ibkr.py (method mapping) |
| TC-57 | Migration | get_historical_bars 新实现 | ibkr.py (call internal) |
| TC-58 | Migration | get_ticker_price → get_quote | ibkr.py (method mapping) |
| TC-60 | Format | KlineBar转Dict | ibkr.py (internal returns Dict) |
| TC-61 | Format | get_ticker返回格式 | ibkr.py (already correct) |
| TC-70 | Integration | 端到端kline获取 | Integration test |
| TC-71 | Integration | 端到端ticker获取 | Integration test |
| TC-72 | Integration | 缓存集成 | Integration test |
| TC-73 | Integration | 限流集成 | Integration test |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.x | Runtime | ✓ | 3.x | — |
| ib_insync | IBKR API | ✓ | 0.9.86 | — |
| pytest | Testing | ✓ | latest | — |
| IBKR Gateway | Data source | ✗ | — | Mock for testing |

**Missing dependencies with no fallback:**
- IBKR Gateway (actual IBKR account required for real data, mock available for testing)

**Missing dependencies with fallback:**
- None - all code dependencies available

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| External ibkr_datafetcher library | Internal IBKRClient | v2.0 (this phase) | Removes external dependency, unifies IBKR connection management |
| get_ticker_price(contract) | get_quote(symbol, market_type) | v2.0 (this phase) | Uses internal client method already implemented |
| make_contract(SymbolConfig) | _create_contract(symbol, market_type) | v2.0 (this phase) | Uses internal client method already implemented |

**Deprecated/outdated:**
- ibkr_datafetcher IBKRClient - to be replaced by internal client
- KlineBar dataclass from ibkr_datafetcher - internal client returns Dict directly

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Internal IBKRClient TaskQueue pattern works for historical data queries | Architecture Patterns | LOW - same pattern as get_quote() which works |
| A2 | ib_insync reqHistoricalDataAsync returns bars with .date, .open, .high, .low, .close, .volume | Code Examples | MEDIUM - based on external library implementation, not directly verified with IBKR docs |
| A3 | Duration string format "1 D", "1 W" works correctly | Common Pitfalls | MEDIUM - standard IBKR format but may need adjustment per timeframe |

**Risk mitigation:** A2 and A3 should be validated during implementation with mock gateway tests.

---

## Open Questions

1. **Duration calculation for different timeframes**
   - What we know: IBKR uses duration strings like "1 D", "1 W", not candle counts
   - What's unclear: Exact mapping between BaseDataSource timeframes (1m, 5m, 1H) and IBKR duration strings
   - Recommendation: Use BaseDataSource.calculate_time_range() to estimate seconds, then convert to IBKR duration format

2. **Mock gateway availability for testing**
   - What we know: ibkr-datafetcher has mock_gateway for testing
   - What's unclear: Whether internal IBKRClient can use same mock or needs separate setup
   - Recommendation: Reuse existing mock_gateway from ibkr-datafetcher for TC-40~TC-43 tests

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | none detected - default pytest |
| Quick run command | `pytest backend_api_python/tests/test_ibkr_datasource.py -x` |
| Full suite command | `pytest backend_api_python/tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-V2-01 | Use internal IBKRClient instead of external | Unit | `pytest backend_api_python/tests/test_ibkr_datasource.py::TestIBKRDataSourceImportChange -x` | ❌ New test needed |
| REQ-V2-02 | get_historical_bars() method works | Unit | `pytest backend_api_python/tests/test_ibkr_client.py::TestGetHistoricalBars -x` | ❌ New test needed |
| REQ-V2-03 | get_quote() returns correct format | Unit | `pytest backend_api_python/tests/test_ibkr_client.py::TestGetQuote -x` | ✅ Exists in v1.0 |

### Sampling Rate
- **Per task commit:** `pytest backend_api_python/tests/test_ibkr_datasource.py -x`
- **Per wave merge:** `pytest backend_api_python/tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend_api_python/tests/test_ibkr_datasource.py` — add tests for internal client import (TC-50~TC-51)
- [ ] `backend_api_python/tests/test_ibkr_client.py` — add get_historical_bars tests (TC-40~TC-43)
- [ ] Framework install: Already in requirements.txt

---

## Security Domain

> Not applicable - this is data source implementation, not authentication or security-critical change.

**Security enforcement disabled:** No ASVS categories apply to this migration (data source layer only).

---

## Sources

### Primary (HIGH confidence)
- `backend_api_python/app/data_sources/base.py` - BaseDataSource interface definition (get_kline signature)
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` - Internal IBKRClient (get_quote at line 1297, _create_contract at line 780)
- `/home/workspace/ws/ibkr-datafetcher/src/ibkr_datafetcher/ibkr_client.py` - Reference implementation (get_historical_bars at line 232)
- `.planning/v2.0-test-cases.md` - Test case specifications TC-40~TC-43
- `.planning/phases/01-ibkr-data-source-implementation/01-CONTEXT.md` - D-28 to D-36 locked decisions
- `backend_api_python/app/data_sources/ibkr.py` - Current v1.0 implementation showing what to replace

### Secondary (MEDIUM confidence)
- External ibkr_datafetcher implementation patterns - verified against existing codebase
- Project conventions from CLAUDE.md

### Tertiary (LOW confidence)
- ib_insync API behavior - inferred from external library implementation, not directly verified with IBKR official docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - confirmed from CLAUDE.md and existing code
- Architecture: HIGH - follows existing internal IBKRClient patterns (get_quote)
- Pitfalls: MEDIUM - based on external library implementation patterns

**Research date:** 2026-04-09
**Valid until:** 2026-05-09 (30 days - stable API)