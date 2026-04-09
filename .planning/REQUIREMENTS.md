# Requirements: QuantDinger - IBKR Data Source

**Defined:** 2026-04-09
**Core Value:** 实盘交易策略使用与实际下单同一数据源，确保数据一致性

## v2.0 Requirements

### Internal IBKRClient

- [x] **INT-01**: 复用内部 IBKRClient (live_trading/ibkr_trading/client.py)
- [x] **INT-02**: 在内部 IBKRClient 添加 get_historical_bars() 方法
- [x] **INT-03**: 在内部 IBKRClient 添加 get_ticker_price() 方法
- [ ] **INT-04**: 修改 IBKRDataSource 使用内部 IBKRClient
- [ ] **INT-05**: 移除对外部 ibkr_datafetcher 库的依赖

## Out of Scope

| Feature | Reason |
|---------|--------|
| 港股数据获取 | v1.0 已排除 |
| 外汇数据获取 | v1.0 已排除 |
| 回测数据源 | 保持 yfinance |
| 数据存储/缓存优化 | 后续优化 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INT-01 | Phase 2 | Complete |
| INT-02 | Phase 2 | Complete |
| INT-03 | Phase 2 | Complete |
| INT-04 | Phase 2 | Pending |
| INT-05 | Phase 2 | Pending |

**Coverage:**
- v2.0 requirements: 5 total
- Mapped to phases: 0
- Unmapped: 5 ⚠️

---
*Requirements defined: 2026-04-09 for v2.0*
*Last updated: 2026-04-09 after v2.0 milestone start*
