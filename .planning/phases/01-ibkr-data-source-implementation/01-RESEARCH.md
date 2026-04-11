# Phase 1: IBKR Data Source Implementation - Research

**Researched:** 2026-04-08
**Domain:** Python - Interactive Brokers (IBKR) data source integration
**Confidence:** HIGH

## Summary

Phase 1 requires implementing an IBKR data source that fetches K-lines and real-time quotes for `exchange_id = ibkr-live`, replacing current yfinance/Finnhub for live trading. The key challenge is integrating the existing IBKRClient from `/home/workspace/ws/ibkr-datafetcher/` into QuantDinger's DataSourceFactory while maintaining backward compatibility.

**Primary recommendation:** Implement IBKRDataSource as a new data source class that inherits BaseDataSource, extends DataSourceFactory.get_source() to accept optional `exchange_id` parameter, and reuses ib_insync 0.9.86 with the RateLimiter pattern from the reference implementation.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** DataSourceFactory.get_source() 添加可选 `exchange_id` 参数
- **D-02:** 当 `exchange_id='ibkr-live'` 时，返回 IBKRDataSource 实例
- **D-03:** 保持向后兼容，不传 exchange_id 时按 market 参数处理
- **D-04:** IBKRDataSource 内部复用 IBKRClient 实例
- **D-05:** 连接在首次使用时建立，后续调用复用同一连接
- **D-06:** 提供 disconnect() 方法供外部调用
- **D-07:** IBKRDataSource 作为独立数据源，不属于任何现有 market 类型
- **D-08:** exchange_id 优先级高于 market_category
- **D-09:** 架构支持后续扩展港股、外汇数据
- **D-10:** 支持所有标准周期：1m, 5m, 15m, 30m, 1H, 4H, 1D
- **D-11:** 股票代码使用 IBKR 格式：AAPL, MSFT, GOOGL
- **D-12:** 同步阻塞调用 get_ticker()，IBKRClient 内部使用异步请求+回调
- **D-13:** 策略执行时同时调用 get_ticker 和 get_kline（保持现有逻辑不变）
- **D-14:** 策略配置中包含 exchange_id
- **D-15:** trading_executor 将 exchange_id 传递给 DataSourceFactory
- **D-16:** 连接参数通过配置文件/环境变量管理（IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID）
- **D-17:** 实现自动重连机制，连接断开后自动重连
- **D-18:** 使用成员变量 `_pending_requests` 字典 + request_id 进行请求-回调通信
- **D-19:** get_kline 缓存：数据库1m点 → 数据库5m点 → 数据库k线 → 拉网（调用 kline_fetcher.get_kline）
- **D-20:** get_ticker 缓存：无缓存，直接调用 IBKRClient 获取
- **D-21:** 在 QuantDinger 的 `rate_limiter.py` 中添加 IBKR 限流器（复用 ibkr-datafetcher 的 RateLimiter 逻辑）
- **D-22:** 对 get_ticker 添加限流保护，防止触发 IBKR 内置限流
- **D-23:** get_kline 限流：复用现有 kline_fetcher 逻辑（已有数据库缓存减轻 API 压力）
- **D-24:** 回测保持原数据源，不使用 IBKRDataSource（无论原数据源是什么）
- **D-25:** 不改变 QuantDinger 现有架构，保持同步调用模式与现有数据源一致
- **D-26:** IBKR 内部的异步/线程封装对 DataSourceFactory 和 trading_executor 透明
- **D-27:** 不使用 WebSocket 或后台轮询，保持简洁的请求-响应模式

### Claude's Discretion

- 数据重试和错误处理的具体实现细节
- K线数据格式的微调

### Deferred Ideas (OUT OF SCOPE)

- 港股数据支持 — Phase 2
- 外汇数据支持 — Phase 2
- 数据缓存/存储优化 — 后续优化

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IBKR-01 | 创建 IBKRDataSource 类，继承 BaseDataSource | BaseDataSource interface found in `app/data_sources/base.py` |
| IBKR-02 | 实现 get_kline() 方法获取历史K线数据 | IBKRClient.get_historical_bars() in reference implementation |
| IBKR-03 | 实现 get_ticker() 方法获取实时报价 | IBKRClient.get_quote() pattern in live trading client |
| IBKR-04 | 连接 IBKR Gateway 并处理连接/断开 | IBKRClient.connect/disconnect from reference + live trading |
| INT-01 | DataSourceFactory 支持基于 exchange_id 选择数据源 | Need to extend factory.get_source() with optional param |
| INT-02 | trading_executor 优先使用 exchange_id 选择数据源 | Current trading_executor has exchange_id param but doesn't pass to DataSourceFactory |
| INT-03 | exchange_id="ibkr-live" 自动使用 IBKRDataSource | Decision D-02 from CONTEXT.md |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ib_insync | 0.9.86 | Interactive Brokers API wrapper | [VERIFIED: pip3 show] - Used in reference implementation and existing live trading |
| ibkr-datafetcher | (reference) | Existing IBKRClient implementation | Source for connection management pattern |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | (existing) | Unit testing | Existing test infrastructure in backend_api_python/tests/ |
| RateLimiter | (custom) | IBKR API rate limiting | Reuse from ibkr-datafetcher implementation |

**Installation:**
```bash
pip install ib-insync==0.9.86
```

**Version verification:** ib_insync 0.9.86 confirmed from local environment.

## Architecture Patterns

### Recommended Project Structure

```
backend_api_python/app/data_sources/
├── __init__.py           # Add IBKRDataSource to exports
├── base.py               # Existing BaseDataSource (don't modify)
├── factory.py            # Extend with exchange_id support
├── ibkr.py               # NEW: IBKRDataSource implementation
└── rate_limiter.py       # Existing (add IBKR-specific limiter)
```

### Pattern 1: DataSourceFactory Extension with exchange_id

**What:** Extend DataSourceFactory.get_source() to accept optional `exchange_id` parameter that takes priority over market

**When to use:** When strategies specify `exchange_id` parameter (as seen in trading_executor.py line 46)

**Example:**
```python
# Source: Analysis of app/data_sources/factory.py
@classmethod
def get_source(cls, market: str, exchange_id: Optional[str] = None) -> BaseDataSource:
    # D-08: exchange_id priority over market_category
    if exchange_id == 'ibkr-live':
        return cls._get_ibkr_source()
    
    # D-03: Backward compatible - fall back to market
    if market not in cls._sources:
        cls._sources[market] = cls._create_source(market)
    return cls._sources[market]
```

### Pattern 2: IBKRClient Wrapper for Data Source

**What:** Wrap IBKRClient from reference implementation in a sync interface matching BaseDataSource

**When to use:** When implementing get_kline() and get_ticker() in IBKRDataSource

**Example:**
```python
# Source: /home/workspace/ws/ibkr-datafetcher/src/ibkr_datafetcher/ibkr_client.py
class IBKRDataSource(BaseDataSource):
    name = "ibkr"
    
    def __init__(self):
        self._client = None  # Lazy initialization (D-05)
    
    def _get_client(self):
        if self._client is None:
            config = GatewayConfig(
                host=os.getenv('IBKR_HOST', 'ib-gateway'),
                port=int(os.getenv('IBKR_PORT', 4004)),
                client_id=int(os.getenv('IBKR_CLIENT_ID', 1))
            )
            self._client = IBKRClient(config)
            self._client.connect()
        return self._client
```

### Pattern 3: Connection Management

**What:** Connect on first use, maintain persistent connection, explicit disconnect method

**When to use:** All IBKR data source operations

**Example:**
```python
# Source: Reference implementation + D-05, D-06
def __init__(self):
    self._client = None

def get_kline(self, symbol, timeframe, limit, before_time=None):
    client = self._get_client()  # Connect on first use
    # ... fetch data

def disconnect(self):
    if self._client:
        self._client.disconnect()
        self._client = None
```

### Anti-Patterns to Avoid

- **Creating new connection per request:** Violates D-05 (reuse connection)
- **Using async/await in DataSource methods:** Violates D-26 (sync interface for DataSourceFactory)
- **Not implementing disconnect():** Violates D-06 (must provide disconnect)
- **Changing BaseDataSource interface:** Will break existing data source implementations

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IBKR connection | Custom socket management | ib_insync.IB() | ib_insync handles IBKR Gateway protocol complexity |
| Rate limiting | Build from scratch | ibkr-datafetcher RateLimiter | IBKR has 50-requests/second limit, complex rule set |
| Contract qualification | Build contract resolver | IBKRClient.qualify_contract() | IBKR requires contract qualification before queries |

**Key insight:** IBKR API has strict rate limits (6 historical data requests/minute per contract) and complex connection semantics (client ID collision, Gateway authentication). ib_insync handles these intricacies.

## Common Pitfalls

### Pitfall 1: Connection Not Reused Across Requests

**What goes wrong:** Each get_kline() call creates new connection, causing performance issues and hitting rate limits faster

**Why it happens:** Not implementing lazy initialization pattern (D-05)

**How to avoid:** Use singleton pattern for IBKRClient within IBKRDataSource

**Warning signs:** Slow response times, IBKR Gateway errors about "already in use"

### Pitfall 2: Ignoring exchange_id in trading_executor

**What goes wrong:** trading_executor has exchange_id parameter but doesn't pass it to DataSourceFactory

**Why it happens:** DataSourceFactory.get_source() doesn't accept exchange_id (currently only accepts market)

**How to avoid:** Extend DataSourceFactory per D-01, update trading_executor to pass exchange_id

**Warning signs:** Strategies with exchange_id="ibkr-live" still use yfinance/finnhub

### Pitfall 3: Not Handling Connection Failures

**What goes wrong:** IBKR Gateway connection fails but no retry or error handling

**Why it happens:** IBKR Gateway may be restarted, network issues, client ID conflicts

**How to avoid:** Implement reconnection logic with exponential backoff (reference implementation has reconnect() method)

**Warning signs:** ConnectionError exceptions in logs, empty data returned

### Pitfall 4: Rate Limiter Not Shared Across Threads

**What goes wrong:** Multiple strategy threads exceed IBKR rate limits independently

**Why it happens:** Each thread creates its own IBKRDataSource or RateLimiter instance

**How to avoid:** Use singleton RateLimiter in DataSourceFactory, share across all IBKRDataSource instances

**Warning signs:** Rate limit errors increase under high strategy concurrency

## Code Examples

### Get K-line Implementation

```python
# Source: Based on ibkr_client.py get_historical_bars + BaseDataSource interface
def get_kline(
    self,
    symbol: str,
    timeframe: str,
    limit: int,
    before_time: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    获取K线数据 - IBKR implementation
    """
    client = self._get_client()
    
    # Convert symbol to IBKR contract
    contract = self._make_contract(symbol, "STK", "SMART", "USD")
    
    # Map timeframe to IBKR format
    ibkr_timeframe = self._map_timeframe(timeframe)
    
    # Calculate duration needed
    duration = self._calculate_duration(timeframe, limit)
    
    # Get historical bars
    bars = client.get_historical_bars(
        contract=contract,
        timeframe=ibkr_timeframe,
        duration=duration
    )
    
    # Convert to BaseDataSource format
    return [
        self.format_kline(
            timestamp=b.timestamp,
            open_price=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume
        )
        for b in bars
    ]
```

### IBKR Contract Creation

```python
# Source: Based on ibkr_client.py make_contract
def _make_contract(self, symbol: str, sec_type: str, exchange: str, currency: str):
    """Create IBKR contract based on security type"""
    from ib_insync import Stock, Forex, Future, Index
    
    if sec_type == "STK":
        return Stock(symbol, exchange, currency)
    elif sec_type == "IND":
        return Index(symbol, exchange, currency)
    elif sec_type == "FUT":
        return Future(symbol, "", exchange, currency=currency)
    elif sec_type == "CASH":
        return Forex(symbol=symbol, exchange=exchange, currency=currency)
    else:
        raise ValueError(f"Unsupported sec_type: {sec_type}")
```

### DataSourceFactory Extension

```python
# Source: Extended from existing factory.py
@classmethod
def get_source(cls, market: str, exchange_id: Optional[str] = None) -> BaseDataSource:
    """
    获取数据源
    
    Args:
        market: 市场类型 (Crypto, USStock, AShare, etc.)
        exchange_id: 交易所ID (e.g., 'ibkr-live')
        
    Returns:
        数据源实例
    """
    # D-08: exchange_id 优先级高于 market_category
    if exchange_id == 'ibkr-live':
        if 'ibkr' not in cls._sources:
            from app.data_sources.ibkr import IBKRDataSource
            cls._sources['ibkr'] = IBKRDataSource()
        return cls._sources['ibkr']
    
    # D-03: 向后兼容
    if market not in cls._sources:
        cls._sources[market] = cls._create_source(market)
    return cls._sources[market]
```

### Rate Limiter Integration

```python
# Source: Adapted from ibkr-datafetcher/rate_limiter.py
# Integrate into existing QuantDinger rate_limiter.py
_ibkr_limiter = RateLimiter(
    hist_requests_per_minute=6,
    news_requests_per_minute=3,
    identical_cooldown=15.0,
    same_contract_limit=6,
    same_contract_window=2.0
)

def get_ibkr_limiter() -> RateLimiter:
    """获取 IBKR 限流器"""
    return _ibkr_limiter
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| yfinance/Finnhub for US stocks | IBKR native data | Phase 1 | Same data source for trading and market data |
| No exchange_id support | exchange_id parameter in DataSourceFactory | Phase 1 | Enables multi-exchange strategies |
| Connection per request | Persistent connection with lazy init | Phase 1 | Better performance, rate limit management |

**Deprecated/outdated:**

- yfinance for live trading: Being replaced by IBKR for consistency
- Finnhub as primary quote source: Now secondary/backup for IBKR

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|----|-------|---------|---------------|
| A1 | trading_executor.py needs modification to pass exchange_id to DataSourceFactory | INT-02 | Medium - Current code has exchange_id param but doesn't use it |
| A2 | IBKRConfig can use env vars similar to other data sources | Configuration | Low - Standard pattern in QuantDinger |
| A3 | get_ticker can use IBKRClient.get_quote() pattern | IBKR-03 | Medium - Need to verify IBKRClient has quote method |

A1 verified: trading_executor.py line 46 shows `exchange: Any, symbol: str, market_type: str, exchange_id: str` - parameter exists but not passed to DataSourceFactory.

## Open Questions

1. **How to handle IBKR rate limiting across multiple strategies?**
   - What we know: Reference implementation has RateLimiter with 6 RPM per contract
   - What's unclear: How to share rate limiter across multiple strategy threads
   - Recommendation: Use singleton RateLimiter instance, integrate with QuantDinger's rate_limiter.py

2. **Should IBKRDataSource use kline_fetcher caching?**
   - What we know: D-19 mentions kline_fetcher caching, but this is for other data sources
   - What's unclear: Whether IBKR should also use database caching or call IBKR directly
   - Recommendation: Call IBKR directly (no database caching initially), follow D-20 (no ticker caching)

3. **How to handle connection in multi-threaded trading executor?**
   - What we know: trading_executor can run 64 threads (max_threads config)
   - What's unclear: Single IBKR connection thread-safe?
   - Recommendation: IBKRClient is thread-safe (uses locks), reuse single connection across threads

## Environment Availability

> Step 2.6: SKIPPED (no external dependencies identified)

This is a code/configuration-only phase. The external dependency (IBKR Gateway) is already assumed to be running and accessible via environment variables.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | pytest.ini (if exists) |
| Quick run command | `pytest backend_api_python/tests/test_ibkr_data_source.py -x` (to be created) |
| Full suite command | `pytest backend_api_python/tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IBKR-01 | IBKRDataSource class creation | unit | `pytest tests/test_ibkr_data_source.py::test_class_creation -x` | ❌ Need to create |
| IBKR-02 | get_kline returns formatted data | unit | `pytest tests/test_ibkr_data_source.py::test_get_kline -x` | ❌ Need to create |
| IBKR-03 | get_ticker returns real-time quote | unit | `pytest tests/test_ibkr_data_source.py::test_get_ticker -x` | ❌ Need to create |
| IBKR-04 | Connection management | unit | `pytest tests/test_ibkr_data_source.py::test_connection -x` | ❌ Need to create |
| INT-01 | DataSourceFactory with exchange_id | unit | `pytest tests/test_ibkr_integration.py::test_factory_exchange_id -x` | ❌ Need to create |
| INT-02 | trading_executor passes exchange_id | unit | `pytest tests/test_ibkr_integration.py::test_executor_passes_exchange_id -x` | ❌ Need to create |
| INT-03 | ibkr-live triggers IBKRDataSource | unit | `pytest tests/test_ibkr_integration.py::test_auto_select_ibkr -x` | ❌ Need to create |

### Wave 0 Gaps
- [ ] `backend_api_python/tests/test_ibkr_data_source.py` — covers IBKR-01 to IBKR-04
- [ ] `backend_api_python/tests/test_ibkr_integration.py` — covers INT-01 to INT-03
- [ ] `backend_api_python/app/data_sources/ibkr.py` — IBKRDataSource implementation

*(If no gaps: "None — existing test infrastructure covers all phase requirements")*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | IBKR uses API credentials, not application auth |
| V3 Session Management | no | IBKR connection is stateless per request |
| V4 Access Control | no | IBKR data is strategy-specific, not user-access-controlled |
| V5 Input validation | yes | Symbol validation, contract type validation |
| V6 Cryptography | no | IBKR Gateway uses TLS, not app-level crypto |

### Known Threat Patterns for IBKR Integration

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Invalid symbol causes contract qualification failure | Tampering | Validate symbol format before API call |
| Rate limit exhaustion causes DoS | Denial of Service | Use RateLimiter from reference implementation |
| Connection leak in multi-threaded environment | Resource Exhaustion | Singleton pattern for connection, explicit disconnect |

## Sources

### Primary (HIGH confidence)
- `/home/workspace/ws/ibkr-datafetcher/src/ibkr_datafetcher/ibkr_client.py` - IBKRClient implementation (source of truth)
- `/home/workspace/ws/ibkr-datafetcher/src/ibkr_datafetcher/rate_limiter.py` - Rate limiter implementation
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/base.py` - BaseDataSource interface
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/factory.py` - DataSourceFactory pattern
- `pip3 show ib-insync` - Version verification (0.9.86)

### Secondary (MEDIUM confidence)
- `/home/workspace/ws/QuantDinger/backend_api_python/app/services/trading_executor.py` - Integration point verification (line 46 has exchange_id param)
- `/home/workspace/ws/QuantDinger/backend_api_python/tests/test_ibkr_client.py` - Existing IBKR testing patterns

### Tertiary (LOW confidence)
- [ib_insync documentation](https://ib-insync.readthedocs.io/) - API details (needs verification)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - ib_insync version verified, reference implementation examined
- Architecture: HIGH - DataSourceFactory pattern well-established in codebase
- Pitfalls: MEDIUM - Based on IBKR API constraints and QuantDinger patterns

**Research date:** 2026-04-08
**Valid until:** 2026-05-08 (30 days - stable technology)