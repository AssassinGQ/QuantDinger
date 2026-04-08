# Requirements: QuantDinger - IBKR Data Source

**Defined:** 2026-04-08
**Core Value:** 实盘交易策略使用与实际下单同一数据源，确保数据一致性

## v1 Requirements

### IBKR Data Source

- [x] **IBKR-01**: 创建 IBKRDataSource 类，继承 BaseDataSource
- [x] **IBKR-02**: 实现 get_kline() 方法获取历史K线数据
- [ ] **IBKR-03**: 实现 get_ticker() 方法获取实时报价
- [x] **IBKR-04**: 连接 IBKR Gateway 并处理连接/断开

### Integration

- [ ] **INT-01**: DataSourceFactory 支持基于 exchange_id 选择数据源
- [ ] **INT-02**: trading_executor 优先使用 exchange_id 选择数据源
- [ ] **INT-03**: exchange_id="ibkr-live" 自动使用 IBKRDataSource

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

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| IBKR-01 | Phase 1 | Complete |
| IBKR-02 | Phase 1 | Complete |
| IBKR-03 | Phase 1 | Pending |
| IBKR-04 | Phase 1 | Complete |
| INT-01 | Phase 1 | Pending |
| INT-02 | Phase 1 | Pending |
| INT-03 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 7 total
- Mapped to phases: 7
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-08*
*Last updated: 2026-04-08 after initial definition*