# Requirements: QuantDinger - IBKR Data Source

**Defined:** 2026-04-08
**Core Value:** 实盘交易策略使用与实际下单同一数据源，确保数据一致性

## v1 Requirements

### IBKR Data Source

- [x] **IBKR-01**: 创建 IBKRDataSource 类，继承 BaseDataSource
- [x] **IBKR-02**: 实现 get_kline() 方法获取历史K线数据
- [x] **IBKR-03**: 实现 get_ticker() 方法获取实时报价
- [x] **IBKR-04**: 连接 IBKR Gateway 并处理连接/断开

### Integration

- [x] **INT-01**: DataSourceFactory 支持基于 exchange_id 选择数据源
- [x] **INT-02**: trading_executor 优先使用 exchange_id 选择数据源
- [x] **INT-03**: exchange_id="ibkr-live" 自动使用 IBKRDataSource

## v2 Requirements

### Multi-Market

- **IBKR-02**: 支持港股数据获取
- **IBKR-03**: 支持外汇数据获取
- **IBKR-04**: 优化连接复用和重连机制

## Out of Scope

| Feature | Reason |
|---------|--------|
| 非IBKR策略数据源变更 | 保持现有 yfinance 数据源 |
| 回测数据源 | 回测仍使用 yfinance |
| 数据缓存/存储 | 后续优化 |

## Phase 1: IBKR Data Source Implementation

**Goal:** 实现基本的 IBKR 数据源，支持美股

| # | Plan | Goal | Requirements | Status |
|---|------|------|--------------|--------|
| 1 | 01-01 | IBKRDataSource 实现 | IBKR-01, IBKR-02, IBKR-03, IBKR-04, INT-01, INT-03 | Planned |
| 2 | 01-02 | 服务层集成 + 测试 | INT-02 | Planned |

**Plans:** 2 plans

**Plan list:**
- [x] 01-01-PLAN.md — IBKRDataSource 实现 + 工厂扩展
- [x] 01-02-PLAN.md — 服务层集成 + 测试

**Success Criteria:**
1. `exchange_id="ibkr-live"` 策略能获取 IBKR 数据
2. get_kline() 返回正确格式的 K线数据
3. trading_executor 正确选择数据源
4. 代码通过单元测试
5. 手动测试 IBKR Gateway 连接

---

## Summary

| Phase | Name | Requirements | Status |
|-------|------|-------------|--------|
| 1 | IBKR Data Source | 7 | Planned |

**Total:** 1 phase | 7 requirements

---
*Roadmap created: 2026-04-08*
*Last updated: 2026-04-08 after initial definition*
*Plans: 2 plans created*
