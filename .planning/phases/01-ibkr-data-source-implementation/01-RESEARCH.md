<user_constraints>
## User Constraints (from CONTEXT.md)

### Implementation Decisions

- **D-01:** DataSourceFactory.get_source() 添加可选 `exchange_id` 参数
- **D-02:** 当 `exchange_id='ibkr-live'` 时，返回 IBKRDataSource 实例
- **D-03:** 保持向后兼容，不传 exchange_id 时按 market 参数处理

### Connection Management

- **D-04:** IBKRDataSource 内部复用 IBKRClient 实例
- **D-05:** 连接在首次使用时建立，后续调用复用同一连接
- **D-06:** 提供 disconnect() 方法供外部调用

### Market Type Relationship

- **D-07:** IBKRDataSource 作为独立数据源，不属于任何现有 market 类型
- **D-08:** exchange_id 优先级高于 market_category
- **D-09:** 架构支持后续扩展港股、外汇数据

### Use Case 1: K线获取

- **D-10:** 支持所有标准周期：1m, 5m, 15m, 30m, 1H, 4H, 1D
- **D-11:** 股票代码使用 IBKR 格式：AAPL, MSFT, GOOGL

### Use Case 2: 实时报价

- **D-12:** 同步阻塞调用 get_ticker()，IBKRClient 内部使用异步请求+回调
- **D-13:** 策略执行时同时调用 get_ticker 和 get_kline（保持现有逻辑不变）

### Use Case 3: 数据源切换

- **D-14:** 策略配置中包含 exchange_id
- **D-15:** trading_executor 将 exchange_id 传递给 DataSourceFactory

### Use Case 4: 连接管理

- **D-16:** 连接参数通过配置文件/环境变量管理（IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID）
- **D-17:** 实现自动重连机制，连接断开后自动重连
- **D-18:** 使用成员变量 `_pending_requests` 字典 + request_id 进行请求-回调通信

### Cache Strategy

- **D-19:** get_kline 缓存：数据库1m点 → 数据库5m点 → 数据库k线 → 拉网（调用 kline_fetcher.get_kline）
- **D-20:** get_ticker 缓存：无缓存，直接调用 IBKRClient 获取

### Rate Limiting Strategy

- **D-21:** 在 QuantDinger 的 `rate_limiter.py` 中添加 IBKR 限流器（复用 ibkr-datafetcher 的 RateLimiter 逻辑）
- **D-22:** 对 get_ticker 添加限流保护，防止触发 IBKR 内置限流
- **D-23:** get_kline 限流：复用现有 kline_fetcher 逻辑（已有数据库缓存减轻 API 压力）

### Backtest Scenario

- **D-24:** 回测保持原数据源，不使用 IBKRDataSource（无论原数据源是什么）

### Claude's Discretion (自由决定领域)

- 数据重试和错误处理的具体实现细节
- K线数据格式的微调

### Deferred Ideas (不在 Phase 1 范围内)

- 港股数据支持 — Phase 2
- 外汇数据支持 — Phase 2
- 数据缓存/存储优化 — 后续优化
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IBKR-01 | 创建 IBKRDataSource 类，继承 BaseDataSource | BaseDataSource interface defined in base.py, can create new implementation |
| IBKR-02 | 实现 get_kline() 方法获取历史K线数据 | ibkr-datafetcher/ibkr_client.py has get_historical_bars() as reference |
| IBKR-03 | 实现 get_ticker() 方法获取实时报价 | ib_insync provides reqMktData for real-time quotes |
| IBKR-04 | 连接 IBKR Gateway 并处理连接/断开 | ibkr-datafetcher/ibkr_client.py has connect(), disconnect(), reconnect() as reference |
| INT-01 | DataSourceFactory 支持基于 exchange_id 选择数据源 | DataSourceFactory.get_source() needs optional parameter, current implementation only uses market |
| INT-02 | trading_executor 优先使用 exchange_id 选择数据源 | Need to pass exchange_id to PriceFetcher/DataSourceFactory |
| INT-03 | exchange_id="ibkr-live" 自动使用 IBKRDataSource | DataSourceFactory logic handles this |
</phase_requirements>

# Phase 1: IBKR Data Source Implementation - Research

**Researched:** 2026-04-08
**Domain:** IBKR Gateway Integration via ib_insync
**Confidence:** HIGH

## Summary

This phase implements native IBKR data source for `exchange_id = ibkr-live` trading strategies, replacing yfinance/Finnhub with data from the same source used for actual order execution. The implementation requires creating a new IBKRDataSource class that inherits from BaseDataSource, modifying DataSourceFactory to support exchange_id-based selection, and integrating with the existing trading executor pipeline.

**Primary recommendation:** Create IBKRDataSource class in `backend_api_python/app/data_sources/` that wraps the existing IBKR client pattern from ibkr-datafetcher, integrate with DataSourceFactory by adding optional exchange_id parameter, and modify PriceFetcher to accept exchange_id from strategy configuration.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ib_insync | 0.9.86 | Interactive Brokers Gateway API client | [VERIFIED: pip show ib_insync] - Official library for IBKR integration |
| ibkr-datafetcher | (reference) | Reference implementation in `/home/workspace/ws/ibkr-datafetcher/` | [VERIFIED: source code] - Provides proven IBKRClient pattern with threading, async-to-sync bridge |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Flask 2.3.3 | (existing) | Web framework | API routes |
| SQLAlchemy 2.0.0 | (existing) | ORM | Database integration |
| APScheduler 3.10.0 | (existing) | Task scheduling | Background data collection |

**Installation:**
```bash
pip install ib_insync
```

**Version verification:** Verified ib_insync 0.9.86 installed in environment - [VERIFIED: python3 -c "import ib_insync; print(ib_insync.__version__)"]

## Architecture Patterns

### Recommended Project Structure
```
backend_api_python/app/data_sources/
├── __init__.py
├── base.py              # (existing) BaseDataSource abstract class
├── factory.py           # (modified) DataSourceFactory with exchange_id support
├── ibkr.py              # (new) IBKRDataSource implementation
├── crypto.py            # (existing)
├── us_stock.py          # (existing)
└── ...
```

### Pattern 1: IBKRDataSource Class
**What:** Data source class that wraps IBKR client for K-line and ticker data retrieval

**When to use:** When exchange_id = 'ibkr-live' is specified in strategy configuration

**Example:**
```python
# Source: Adapted from ibkr-datafetcher reference + BaseDataSource interface
from app.data_sources.base import BaseDataSource
from ibkr_datafetcher.ibkr_client import IBKRClient
from ibkr_datafetcher.rate_limiter import RateLimiter
from ibkr_datafetcher.config import GatewayConfig
from ibkr_datafetcher.types import Timeframe

class IBKRDataSource(BaseDataSource):
    """IBKR data source implementation"""
    
    name = "IBKR"
    
    def __init__(self):
        config = GatewayConfig(
            host=os.getenv("IBKR_HOST", "127.0.0.1"),
            port=int(os.getenv("IBKR_PORT", 7497)),
            client_id=int(os.getenv("IBKR_CLIENT_ID", 1))
        )
        self._client = IBKRClient(config)
        self._rate_limiter = RateLimiter(
            hist_requests_per_minute=6,
            identical_cooldown=15.0
        )
        self._connected = False
    
    def get_kline(self, symbol, timeframe, limit, before_time=None):
        """获取K线数据"""
        self._ensure_connection()
        self._rate_limiter.acquire(request_type="hist", symbol=symbol)
        
        # Convert timeframe format
        tf = Timeframe.from_str(timeframe)
        
        # Create contract (STK for stocks)
        contract = self._client.make_contract(SymbolConfig(
            symbol=symbol,
            sec_type="STK",
            exchange="SMART",
            currency="USD"
        ))
        
        # Get historical bars
        bars = self._client.get_historical_bars(contract, tf)
        
        # Format to standard K-line format
        return [self.format_kline(
            bar.timestamp,
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume
        ) for bar in bars]
    
    def get_ticker(self, symbol):
        """获取实时报价"""
        self._ensure_connection()
        self._rate_limiter.acquire(request_type="ticker", symbol=symbol)
        
        # Use reqMktData for real-time quote
        contract = self._client.make_contract(SymbolConfig(
            symbol=symbol,
            sec_type="STK",
            exchange="SMART",
            currency="USD"
        ))
        
        # Synchronous wrapper around async reqMktData
        ticker_data = self._get_ticker_sync(contract)
        
        return {
            'last': ticker_data.get('last', 0),
            'symbol': symbol,
            'change': ticker_data.get('change', 0),
            'changePercent': ticker_data.get('changePercent', 0),
            'high': ticker_data.get('high', 0),
            'low': ticker_data.get('low', 0),
            'open': ticker_data.get('open', 0),
            'previousClose': ticker_data.get('previousClose', 0)
        }
    
    def _ensure_connection(self):
        """确保已连接IBKR Gateway"""
        if not self._connected:
            self._connected = self._client.connect()
            if not self._connected:
                raise ConnectionError("Failed to connect to IBKR Gateway")
    
    def disconnect(self):
        """断开连接"""
        if self._connected:
            self._client.disconnect()
            self._connected = False
```

### Pattern 2: DataSourceFactory with exchange_id
**What:** Modified factory to support exchange_id parameter for IBKR selection

**When to use:** When creating data source instances in trading executor or price fetcher

**Example:**
```python
# Source: Adapted from existing DataSourceFactory in factory.py
class DataSourceFactory:
    _sources: Dict[str, BaseDataSource] = {}
    
    @classmethod
    def get_source(cls, market: str = None, exchange_id: str = None) -> BaseDataSource:
        """
        获取数据源，支持 exchange_id 优先策略
        """
        # D-08: exchange_id 优先级高于 market_category
        if exchange_id == 'ibkr-live':
            if 'ibkr' not in cls._sources:
                from app.data_sources.ibkr import IBKRDataSource
                cls._sources['ibkr'] = IBKRDataSource()
            return cls._sources['ibkr']
        
        # D-03: 保持向后兼容，不传 exchange_id 时按 market 参数处理
        if market:
            return cls.get_source_by_market(market)
        
        # Default fallback
        return cls.get_source_by_market("Crypto")
```

### Pattern 3: PriceFetcher Integration
**What:** Modified PriceFetcher to pass exchange_id to DataSourceFactory

**When to use:** When fetching current price for strategy execution

**Example:**
```python
# Source: Adapted from existing price_fetcher.py
class PriceFetcher:
    def fetch_current_price(
        self,
        exchange: Any,
        symbol: str,
        market_type: Optional[str] = None,
        market_category: str = "Crypto",
        exchange_id: Optional[str] = None,  # NEW PARAMETER
    ) -> Optional[float]:
        # Use exchange_id if provided, otherwise fall back to market_category
        if exchange_id:
            ticker = DataSourceFactory.get_ticker(
                market=market_category,
                symbol=symbol,
                exchange_id=exchange_id  # NEW PARAMETER
            )
        else:
            ticker = DataSourceFactory.get_ticker(market_category, symbol)
```

### Anti-Patterns to Avoid

- **Don't create separate IBKR client instance per request:** D-04 requires internal reuse of IBKRClient instance across all requests. Create singleton in IBKRDataSource.__init__ and reuse it.
- **Don't make get_ticker async:** D-12 requires synchronous blocking calls. The internal IBKRClient uses async requests with callbacks, but expose a synchronous wrapper to match BaseDataSource interface.
- **Don't bypass rate limiter:** D-21-23 require using rate limiter for all IBKR API calls to avoid triggering built-in rate limits.
- **Don't change backtest data source:** D-24 requires keeping backtest using original data sources (yfinance), not IBKRDataSource.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IBKR connection management | Custom async-to-sync bridge | ibkr-datafetcher's IBKRClient with thread-based event loop | Handles complex threading, reconnection, client ID allocation automatically |
| Rate limiting | Custom implementation | ibkr-datafetcher's RateLimiter | Implements IBKR-specific rate limits (6 RPM for historical data, identical symbol cooldown) |
| Contract qualification | Manual contract validation | IBKRClient.qualify_contract() | Handles exchange-specific contract formats and validation |
| Timeframe conversion | Custom mapping | ibkr-datafetcher's Timeframe enum | Maps standard timeframes (1m, 5m) to IBKR bar sizes automatically |

**Key insight:** The ibkr-datafetcher project already implements battle-tested patterns for IBKR Gateway integration. Reuse these patterns instead of reinventing connection management, rate limiting, and contract handling.

## Common Pitfalls

### Pitfall 1: IBKR Gateway Connection Failure
**What goes wrong:** Data source fails to connect to IBKR Gateway, causing all strategy K-line/ticker requests to fail

**Why it happens:** IBKR Gateway not running, wrong host/port configuration, or client ID conflict

**How to avoid:**
- Verify IBKR Gateway is running before creating data source
- Use environment variables (IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID) for configuration
- Implement automatic reconnection (D-17) with exponential backoff
- Provide clear error messages when connection fails

**Warning signs:**
- "Unable to connect" errors in logs
- Connection timeout after 60+ seconds
- "clientId already in use" errors

### Pitfall 2: Rate Limit Exceeded
**What goes wrong:** IBKR API returns rate limit error, causing data fetch failures

**Why it happens:** Too many requests in short period (exceeds 6 RPM for historical data)

**How to avoid:**
- Use RateLimiter from ibkr-datafetcher (D-21)
- Add delays between requests to same symbol (15 second cooldown)
- Implement request queuing for bulk data fetches

**Warning signs:**
- "Historical data request failed: rate limit exceeded"
- "No market data available" for recent requests

### Pitfall 3: Thread Safety Issues
**What goes wrong:** Concurrent access to IBKRClient causes race conditions or deadlocks

**Why it happens:** IBKRClient uses async event loop in dedicated thread, not thread-safe by default

**How to avoid:**
- Use ibkr-datafetcher's threading pattern (dedicated thread with event loop)
- Never call IBKRClient methods directly from multiple threads without synchronization
- Use thread-safe rate limiter (implemented in ibkr-datafetcher)

**Warning signs:**
- Inconsistent data responses
- Event loop stops unexpectedly
- "Event loop is closed" errors

### Pitfall 4: Incorrect Timeframe Mapping
**What goes wrong:** K-line data uses wrong timeframe (e.g., requesting 5m returns 1m data)

**Why it happens:** Incorrect timeframe mapping between QuantDinger format and IBKR format

**How to avoid:**
- Use Timeframe enum from ibkr-datafetcher for conversion
- Verify timeframe mapping in test cases
- Check IBKR bar size compatibility (not all timeframes supported)

**Warning signs:**
- Data mismatch between expected and actual timeframe
- Missing data for certain timeframes

## Code Examples

### Example 1: Timeframe Mapping
```python
# Source: ibkr-datafetcher/src/ibkr_datafetcher/types.py
from enum import Enum
from typing import Optional

class Timeframe(Enum):
    """Supported timeframes with IBKR format mapping"""
    
    MINUTE_1 = ("1m", "60 S", "1 D")
    MINUTE_5 = ("5m", "300 S", "1 D")
    MINUTE_15 = ("15m", "900 S", "1 D")
    MINUTE_30 = ("30m", "1800 S", "1 D")
    HOUR_1 = ("1H", "3600 S", "1 D")
    HOUR_4 = ("4H", "14400 S", "1 D")
    DAY_1 = ("1D", "1 D", "1 Y")
    
    def __init__(self, std_format: str, ibkr_bar_size: str, ibkr_max_duration: str):
        self.std_format = std_format
        self.ibkr_bar_size = ibkr_bar_size
        self.ibkr_max_duration = ibkr_max_duration
    
    @classmethod
    def from_str(cls, timeframe: str) -> "Timeframe":
        """Convert standard format to Timeframe enum"""
        for tf in cls:
            if tf.std_format == timeframe:
                return tf
        raise ValueError(f"Unsupported timeframe: {timeframe}")
```

### Example 2: Synchronous Ticker Request
```python
# Source: Adapted from ibkr-client pattern + BaseDataSource synchronous requirement
def _get_ticker_sync(self, contract) -> dict:
    """Synchronous wrapper for async reqMktData"""
    result = {}
    request_id = self._generate_request_id()
    
    # Store pending request
    self._pending_requests[request_id] = threading.Event()
    
    # Make async request
    self._ib.reqMktData(request_id, contract, "", False, False)
    
    # Wait for callback with timeout
    event = self._pending_requests[request_id]
    if not event.wait(timeout=10):
        del self._pending_requests[request_id]
        raise TimeoutError("Ticker request timeout")
    
    return self._pending_ticker_data.pop(request_id)

def _on_tick(self, request_id: int, tick):
    """Callback for market data updates"""
    if request_id in self._pending_requests:
        self._pending_ticker_data[request_id] = {
            'last': tick.last,
            'change': tick.change,
            'changePercent': tick.changePercent,
            'high': tick.high,
            'low': tick.low,
            'open': tick.open,
            'previousClose': tick.prevClose
        }
        event = self._pending_requests.pop(request_id)
        event.set()
```

### Example 3: Connection with Auto-Reconnect
```python
# Source: Adapted from ibkr-datafetcher/ibkr_client.py
def _ensure_connected(self, max_retries: int = 3) -> bool:
    """Ensure connection to IBKR Gateway with auto-reconnect"""
    if self._connected and self._client.is_connected():
        return True
    
    # Try to reconnect
    for attempt in range(max_retries):
        if self._client.connect():
            self._connected = True
            logger.info(f"Connected to IBKR Gateway on attempt {attempt + 1}")
            return True
        logger.warning(f"Connection attempt {attempt + 1} failed, retrying...")
        time.sleep(5)
    
    logger.error("Failed to connect to IBKR Gateway after {max_retries} attempts")
    return False
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| yfinance for US stock K-lines | IBKRDataSource for ibkr-live strategies | Phase 1 | Data consistency between data source and order execution |
| Finnhub for real-time quotes | IBKRDataSource for ibkr-live strategies | Phase 1 | Real-time data from same source as trading |
| Market-based data source selection | Exchange ID-based selection | Phase 1 | More flexible, supports multiple exchanges per market type |

**Deprecated/outdated:**
- yfinance: Still used for non-ibkr-live strategies and backtesting
- Finnhub: Still used as fallback for US stock quotes

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research. The planner and discuss-phase use this section to identify decisions that need user confirmation before execution.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | trading_executor has access to exchange_id from strategy configuration | INT-02 | If exchange_id not available in strategy config, INT-02 cannot be implemented as described - need alternative approach |
| A2 | PriceFetcher is the only entry point for real-time price in strategy execution | INT-02 | If other components also fetch prices, need to update them as well |
| A3 | IBKR Gateway will be running on same machine (127.0.0.1) | D-16 | If IBKR Gateway runs remotely, need network configuration |
| A4 | IBKR data source only needed for live trading, not backtesting | D-24 | If backtesting also needs IBKR data, architecture changes required |
| A5 | No existing IBKR data source tests in backend_api_python/tests/ | Validation | If tests exist, need to verify compatibility |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed.

## Open Questions

1. **How does trading_executor pass exchange_id to PriceFetcher?**
   - What we know: trading_executor has strategy configuration with exchange_id
   - What's unclear: Current PriceFetcher only accepts market_category - need to verify how to add exchange_id parameter
   - Recommendation: Add exchange_id as optional parameter to PriceFetcher.fetch_current_price(), pass through from strategy config

2. **What happens if IBKR Gateway is not running when DataSourceFactory is called?**
   - What we know: Connection established on first use (D-05), should handle connection failure gracefully
   - What's unclear: Error handling strategy - raise exception or return empty data?
   - Recommendation: Raise ConnectionError with clear message, strategy executor should catch and handle gracefully

3. **Should IBKRDataSource singleton be shared across all requests or per-exchange?**
   - What we know: D-04 says internal reuse of IBKRClient instance
   - What's unclear: If multiple strategies use same ibkr-live, should they share connection?
   - Recommendation: Use singleton pattern in DataSourceFactory, share IBKRDataSource instance for all ibkr-live requests

## Environment Availability

> Step 2.6: SKIPPED (no external dependencies identified beyond existing environment)

- Python 3.13.11: Available (existing project requirement)
- ib_insync 0.9.86: Available (verified in environment)
- IBKR Gateway: Required but not installed - user's responsibility (D-16: managed via environment variables)
- pytest: Available in backend_api_python/tests/ (existing project)

**Note:** IBKR Gateway is external dependency that must be running for IBKR data source to work. This is configured via environment variables (IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID) as per D-16.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | none detected |
| Quick run command | `pytest backend_api_python/tests/test_ibkr_client.py -xvs` |
| Full suite command | `pytest backend_api_python/tests/ -xvs` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IBKR-01 | Create IBKRDataSource class | unit | `pytest backend_api_python/tests/test_ibkr_data_source.py -xvs` | ❌ Need to create |
| IBKR-02 | get_kline() returns formatted K-lines | unit | `pytest backend_api_python/tests/test_ibkr_data_source.py::test_get_kline -xvs` | ❌ Need to create |
| IBKR-03 | get_ticker() returns ticker dict | unit | `pytest backend_api_python/tests/test_ibkr_data_source.py::test_get_ticker -xvs` | ❌ Need to create |
| IBKR-04 | connect/disconnect handles connection | integration | `pytest backend_api_python/tests/test_ibkr_data_source.py::test_connection -xvs` | ❌ Need to create |
| INT-01 | DataSourceFactory supports exchange_id | unit | `pytest backend_api_python/tests/test_data_source_factory.py -xvs` | ❌ Need to create |
| INT-02 | trading_executor passes exchange_id | unit | `pytest backend_api_python/tests/test_trading_executor.py::test_exchange_id -xvs` | ❌ Need to verify/update |
| INT-03 | exchange_id="ibkr-live" uses IBKRDataSource | integration | `pytest backend_api_python/tests/test_data_source_integration.py -xvs` | ❌ Need to create |

### Sampling Rate
- **Per task commit:** `pytest backend_api_python/tests/test_ibkr_data_source.py -xvs`
- **Per wave merge:** `pytest backend_api_python/tests/ -xvs`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend_api_python/tests/test_ibkr_data_source.py` — covers IBKR-01, IBKR-02, IBKR-03, IBKR-04
- [ ] `backend_api_python/tests/test_data_source_factory.py` — covers INT-01
- [ ] Framework install: pytest already available in backend_api_python

Existing test infrastructure:
- `backend_api_python/tests/test_ibkr_client.py` exists - may provide reusable test patterns
- `backend_api_python/tests/test_price_fetcher.py` exists - will need to update for exchange_id support

## Security Domain

> Not applicable - this is data source integration, not security-critical component. No ASVS categories apply to this implementation.

## Sources

### Primary (HIGH confidence)
- `/home/workspace/ws/ibkr-datafetcher/src/ibkr_datafetcher/ibkr_client.py` - Reference implementation with connection management, threading pattern, async-to-sync bridge
- `/home/workspace/ws/ibkr-datafetcher/src/ibkr_datafetcher/rate_limiter.py` - Reference implementation with IBKR-specific rate limiting
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/base.py` - BaseDataSource interface definition
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/factory.py` - DataSourceFactory current implementation

### Secondary (MEDIUM confidence)
- `/home/workspace/ws/QuantDinger/backend_api_python/app/services/price_fetcher.py` - Current PriceFetcher implementation showing integration point
- `/home/workspace/ws/QuantDinger/backend_api_python/app/strategies/runners/single_symbol_runner.py` - Strategy execution showing data source usage

### Tertiary (LOW confidence)
- N/A - all critical information obtained from primary sources

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH - ib_insync is the official IBKR library, verified version installed
- Architecture: HIGH - Based on verified existing patterns from ibkr-datafetcher and current codebase
- Pitfalls: HIGH - Common issues with IBKR Gateway integration well-documented in reference implementation

**Research date:** 2026-04-08
**Valid until:** 2026-05-08 (30 days for stable library)