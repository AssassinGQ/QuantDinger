# Phase 1: IBKR Data Source Implementation - Context

**Gathered:** 2026-04-08
**Status:** Ready for planning

<domain>
## Phase Boundary

为 `exchange_id = ibkr-live` 的交易策略提供原生 IBKR 数据源，从 Interactive Brokers API 获取 K线和实时报价。目标是替代当前使用的 yfinance/Finnhub，确保实盘交易使用与下单同一数据源。

</domain>

<decisions>
## Implementation Decisions

### 数据源选择
- **D-01:** DataSourceFactory.get_source() 添加可选 `exchange_id` 参数
- **D-02:** 当 `exchange_id='ibkr-live'` 时，返回 IBKRDataSource 实例
- **D-03:** 保持向后兼容，不传 exchange_id 时按 market 参数处理

### 连接管理
- **D-04:** IBKRDataSource 内部复用 IBKRClient 实例
- **D-05:** 连接在首次使用时建立，后续调用复用同一连接
- **D-06:** 提供 disconnect() 方法供外部调用

### 市场类型关系
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

### 缓存策略
- **D-19:** get_kline 缓存：数据库1m点 → 数据库5m点 → 数据库k线 → 拉网（调用 kline_fetcher.get_kline）
- **D-20:** get_ticker 缓存：无缓存，直接调用 IBKRClient 获取

### 限流策略
- **D-21:** 在 QuantDinger 的 `rate_limiter.py` 中添加 IBKR 限流器（复用 ibkr-datafetcher 的 RateLimiter 逻辑）
- **D-22:** 对 get_ticker 添加限流保护，防止触发 IBKR 内置限流
- **D-23:** get_kline 限流：复用现有 kline_fetcher 逻辑（已有数据库缓存减轻 API 压力）

### 回测场景
- **D-24:** 回测保持原数据源，不使用 IBKRDataSource（无论原数据源是什么）

### 架构一致性确认
- **D-25:** 不改变 QuantDinger 现有架构，保持同步调用模式与现有数据源一致
- **D-26:** IBKR 内部的异步/线程封装对 DataSourceFactory 和 trading_executor 透明
- **D-27:** 不使用 WebSocket 或后台轮询，保持简洁的请求-响应模式

### Claude's Discretion
- 数据重试和错误处理的具体实现细节
- K线数据格式的微调

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 数据源架构
- `backend_api_python/app/data_sources/base.py` — BaseDataSource 接口定义
- `backend_api_python/app/data_sources/factory.py` — DataSourceFactory 工厂模式

### 参考实现
- `/home/workspace/ws/ibkr-datafetcher/` — 现有 IBKRClient 使用 ib_insync

### 需求文档
- `.planning/REQUIREMENTS.md` — IBKR-01 到 IBKR-04, INT-01 到 INT-03
- `.planning/PROJECT.md` — 项目愿景和约束

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BaseDataSource`: 抽象基类，定义 get_kline()/get_ticker() 接口
- `DataSourceFactory.get_source()`: 现有工厂方法，需要扩展
- `ib_insync.IB()`: 参考实现中的 IBKR 连接客户端

### Established Patterns
- 数据源使用单例模式（Factory 内部缓存）
- K线返回格式: `[{"time": int, "open": float, "high": float, "low": float, "close": float, "volume": float}]`
- get_ticker 返回: `{"last": float, "symbol": str, ...}`

### Integration Points
- `app/services/trading_executor.py`: 调用 DataSourceFactory 获取数据源
- `app/routes/market.py`: 提供 K线查询 API

</code_context>

<specifics>
## Specific Ideas

- 复用 `/home/workspace/ws/ibkr-datafetcher/` 中的 IBKRClient 实现
- exchange_id="ibkr-live" 优先于 market_category 选择数据源
- 架构需支持后续港股、外汇扩展

</specifics>

<deferred>
## Deferred Ideas

- 港股数据支持 — Phase 2
- 外汇数据支持 — Phase 2
- 数据缓存/存储优化 — 后续优化

</deferred>

---

*Phase: 01-ibkr-data-source-implementation*
*Context gathered: 2026-04-08*
