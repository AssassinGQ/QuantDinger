# Roadmap: v2.0 Internal IBKRClient Migration

**Defined:** 2026-04-09
**Core Value:** 将 IBKRDataSource 从外部 `ibkr_datafetcher` 库迁移到内部 `IBKRClient`

## Goal

将 IBKRDataSource 从依赖外部 `ibkr_datafetcher` 库迁移到使用内部 `IBKRClient` (live_trading/ibkr_trading/client.py)

## Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| INT-01 | 复用内部 IBKRClient | ✅ Complete |
| INT-02 | IBKRClient 添加 get_historical_bars() | ✅ Complete |
| INT-03 | IBKRClient 添加 get_ticker_price() | ✅ Complete |
| INT-04 | IBKRDataSource 使用内部 IBKRClient | Pending |
| INT-05 | 移除 ibkr_datafetcher 依赖 | Pending |

## Phase 2: Internal IBKRClient Migration

| # | Plan | Goal | Requirements | Status |
|---|------|------|--------------|--------|
| 1 | 02-01 | Internal IBKRClient migration | INT-01, INT-02, INT-03 | Complete |
| 2 | 02-02 | get_kline() with internal client | INT-04 | Complete |
| 3 | 02-03 | get_ticker() with internal client | INT-04 | Complete |

---
*Roadmap created: 2026-04-09*
