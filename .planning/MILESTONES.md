# Milestones

## v2.0 Internal IBKRClient Migration (Shipped: 2026-04-11)

**Phases completed:** 1 phase, 4 plans

**Key accomplishments:**

- 内部 IBKRClient 添加 get_historical_bars() 方法（复用 ib_insync）
- 内部 IBKRClient 添加 get_quote() 方法（复用 ib_insync）
- IBKRDataSource 从 ibkr_datafetcher 迁移到内部 IBKRClient
- 移除所有 ibkr_datafetcher 外部依赖（INT-05 完成）
- 新增 E2E 测试（test_ibkr_e2e.py，7 个测试）
- 修复既有测试（asyncio.coroutine → AsyncMock，price_fetcher mock 更新）

**Requirements:**
- INT-01: 复用内部 IBKRClient — ✅ Complete
- INT-02: IBKRClient 添加 get_historical_bars() — ✅ Complete
- INT-03: IBKRClient 添加 get_ticker_price() — ✅ Complete
- INT-04: IBKRDataSource 使用内部 IBKRClient — ✅ Complete
- INT-05: 移除 ibkr_datafetcher 依赖 — ✅ Complete

---

## v1.0 IBKR Data Source (Shipped: 2026-04-09)

**Phases completed:** 1 phase, 5 plans, 7 tasks

**Key accomplishments:**

- IBKRDataSource class with connection management (connect/disconnect/reconnect), inheriting from BaseDataSource
- get_kline() implementation with kline_fetcher cache integration
- get_ticker() implementation for real-time price without caching
- IBKR rate limiter (6 RPM for historical data, 3 RPM for news)
- DataSourceFactory integration with exchange_id priority over market

---
