# Roadmap: IBKR Data Source

**Created:** 2026-04-08
**Core Value:** 实盘交易策略使用与实际下单同一数据源，确保数据一致性

## Phase 1: IBKR Data Source Implementation

**Goal:** 实现基本的 IBKR 数据源，支持美股

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 1 | IBKR Data Source | 实现 IBKRDataSource 并集成 | IBKR-01, IBKR-02, IBKR-03, IBKR-04, INT-01, INT-02, INT-03 | 3 |

**Requirements:** IBKR-01, IBKR-02, IBKR-03, IBKR-04, INT-01, INT-02, INT-03

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
| 1 | IBKR Data Source | 7 | Pending |

**Total:** 1 phase | 7 requirements

---
*Roadmap created: 2026-04-08*