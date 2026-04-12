# Roadmap: QuantDinger - IBKR Data Source

## Milestones

- ✅ **v1.0 IBKR Data Source** — Phase 1 (shipped 2026-04-09)
- ✅ **v2.0 Internal IBKRClient Migration** — Phase 2 (shipped 2026-04-11)
- 🔄 **v1.1 IBKR策略数据源集成 + E2E测试** — Phase 3 (in progress)

## Phases

<details>
<summary>✅ v1.0 IBKR Data Source (Phase 1) — SHIPPED 2026-04-09</summary>

- [x] Phase 1: IBKR Data Source Implementation (5/5 plans) — completed 2026-04-09

</details>

<details>
<summary>✅ v2.0 Internal IBKRClient Migration (Phase 2) — SHIPPED 2026-04-11</summary>

- [x] 02-01: Internal IBKRClient migration — completed
- [x] 02-02: get_kline() with internal client — completed
- [x] 02-03: get_ticker() with internal client — completed
- [x] 02-04: IBKRDataSource migration verification (INT-04, INT-05) — completed 2026-04-11

</details>

---

### Phase 3: IBKR策略数据源集成 + E2E测试

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 1 | 03-01 | Runner broker_id 透传 | INT-06, INT-07, INT-08 | 3 runners传 broker_id |
| 2 | 03-02 | E2E 测试链路 | INT-09 | 链路验证通过 |

**Phase 03-01: Runner broker_id 透传**

**Goal**: single_symbol_runner 等从 strategy['trade_config'] 取 broker_id，传给 price_fetcher.fetch_current_price(exchange_id=broker_id)

**Requirements**: INT-06, INT-07, INT-08

**Plans**:
- [ ] 03-01-PLAN.md — 3 runners pass broker_id to price_fetcher
**Tasks**:
1. single_symbol_runner 透传 broker_id
2. regime_runner 透传 broker_id
3. single_regime_weighted_runner 透传 broker_id

**Phase 03-02: E2E 测试**

**Goal**: 验证完整链路：Python直接调用 → price_fetcher → DataSourceFactory → IBKRDataSource → ib_insync (mocked)

**Requirements**: INT-09

**Tasks**:
1. E2E 测试：price_fetcher.fetch_current_price(exchange_id='ibkr-paper') 链路验证
2. Mock ib_insync.IB 完整链路测试

---

*Roadmap updated: 2026-04-11*
