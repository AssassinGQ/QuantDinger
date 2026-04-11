# QuantDinger - IBKR 数据源

## What This Is

为 `exchange_id = ibkr-live` 的交易策略提供原生 IBKR 数据源，从 Interactive Brokers API 获取 K线和实时报价，替代当前使用的 yfinance/Finnhub。

**Core value**: 实盘交易策略使用与实际下单同一数据源，确保数据一致性。

## Current Milestone: v1.1 IBKR策略数据源集成 + E2E测试

**Goal:** 让 IBKR 策略真正使用 IBKRDataSource，通过 broker_id 透传 + 完整 E2E 测试验证

**Target features:**
- Runner broker_id 透传：single_symbol_runner 等从 strategy['trade_config'] 取 broker_id，传给 price_fetcher.fetch_current_price(exchange_id=broker_id)
- E2E 测试：Python 直接调用链路，mock ib_insync，验证策略 → price_fetcher → DataSourceFactory → IBKRDataSource → ib_insync

## Requirements

### Validated

- ✓ IBKRDataSource 类创建 — v1.0
- ✓ get_kline() 实现 — v1.0
- ✓ get_ticker() 实现 — v1.0
- ✓ 连接 IBKR Gateway — v1.0
- ✓ DataSourceFactory 支持 exchange_id — v1.0
- ✓ trading_executor 传递 exchange_id — v1.0
- ✓ exchange_id="ibkr-live" 使用 IBKRDataSource — v1.0
- ✓ 内部 IBKRClient 添加 get_historical_bars() — v2.0
- ✓ 内部 IBKRClient 添加 get_quote() — v2.0
- ✓ IBKRDataSource 从 ibkr_datafetcher 迁移到内部 IBKRClient — v2.0
- ✓ 移除 ibkr_datafetcher 外部依赖 — v2.0

### Active

- [ ] Runner 透传 broker_id — single_symbol_runner 等传 exchange_id=broker_id 给 price_fetcher
- [ ] E2E 测试 — 完整链路 mock ib_insync，验证策略 → IBKRDataSource

### Out of Scope

- 非 IBKR 实盘策略的数据源变更
- 回测数据源（保持 yfinance）
- 数据存储/缓存优化
- `/api/market/kline` 和 `/api/market/price` 的 exchange_id 参数

## Context

- **现有代码库**: QuantDinger 交易平台
- **参考实现**: `/home/workspace/ws/ibkr-datafetcher/` 使用 ib_insync
- **当前 USStock 数据源**: IBKR 原生数据源 (v2.0)
- **目标 exchange_id**: `ibkr-live`
- **技术栈**: ib_insync, Python, Flask
- **里程碑**: v1.1 started 2026-04-11

## Constraints

- **技术**: 使用 ib_insync 库连接 IBKR Gateway
- **IBKR Gateway**: 需要本地运行 IBKR Gateway 或 IBKR 账户
- **兼容性**: 支持多种市场类型（架构设计）

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 基于 exchange_id 选择数据源 | 与 trading executor 的 exchange_id 一致，支持多数据源 | ✓ Good - 已通过 DataSourceFactory 实现 |
| 优先美股，后续港股外汇 | ibkr-live 当前只有美股策略 | ✓ Good - v1.0 专注美股，v2.0 迁移内部 Client |
| 内部 IBKRClient 复用 ib_insync | 避免外部库依赖，统一连接管理 | ✓ Good - v2.0 完成 |
| v2.0 E2E 测试覆盖 | 验证 DataSourceFactory → IBKRDataSource → ib_insync 链路 | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---

*Last updated: 2026-04-11 after v1.1 milestone started*
