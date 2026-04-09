# Requirements: QuantDinger - IBKR Data Source

**Defined:** 2026-04-08
**Core Value:** 实盘交易策略使用与实际下单同一数据源，确保数据一致性

## v1 Requirements

### IBKR Data Source

- [ ] **IBKR-01**: 创建 IBKRDataSource 类，继承 BaseDataSource
- [x] **IBKR-02**: 实现 get_kline() 方法获取历史K线数据
- [ ] **IBKR-03**: 实现 get_ticker() 方法获取实时报价
- [ ] **IBKR-04**: 连接 IBKR Gateway 并处理连接/断开

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
| 1 | 01-01 | IBKRDataSource class | IBKR-01, IBKR-04 | Complete |
| 2 | 01-02 | get_kline implementation | IBKR-02 | Complete |
| 3 | 01-03 | get_ticker implementation | IBKR-03 | Complete |
| 4 | 01-04 | IBKR rate limiter | D-21, D-22 | Complete |
| 5 | 01-05 | DataSourceFactory with exchange_id | INT-01, INT-02, INT-03 | Complete |

**Plans:** 4/5 plans executed

**Wave 1 (4 plans, parallel execution):**
- [x] 01-01-PLAN.md — IBKRDataSource class + connection
- [x] 01-02-PLAN.md — get_kline implementation  
- [x] 01-03-PLAN.md — get_ticker implementation
- [x] 01-04-PLAN.md — IBKR rate limiter

**Wave 2 (1 plan, depends on Wave 1):**
- [x] 01-05-PLAN.md — DataSourceFactory with exchange_id

**Success Criteria:**
1. `exchange_id="ibkr-live"` 策略能获取 IBKR 数据
2. get_kline() 返回正确格式的 K线数据
3. get_ticker() 返回实时报价
4. Rate limiter prevents IBKR API limits
5. DataSourceFactory integrates with IBKRDataSource
6. 代码通过单元测试
7. 手动测试 IBKR Gateway 连接

---

## Summary

| Phase | Name | Requirements | Status |
|-------|------|-------------|--------|
| 1 | IBKR Data Source | 7 | Planned |

**Total:** 1 phase | 7 requirements

---
*Roadmap created: 2026-04-08*
*Last updated: 2026-04-08 after planning*
*Plans: 5 plans in 2 waves created*