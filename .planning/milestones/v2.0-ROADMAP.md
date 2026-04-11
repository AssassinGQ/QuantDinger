# Roadmap: QuantDinger - IBKR Data Source

## Milestones

- ✅ **v1.0 IBKR Data Source** — Phase 1 (shipped 2026-04-09)
- 🔄 **v2.0 Internal IBKRClient Migration** — Phase 2 (in progress)

## Phases

<details>
<summary>✅ v1.0 IBKR Data Source (Phase 1) — SHIPPED 2026-04-09</summary>

- [x] Phase 1: IBKR Data Source Implementation (5/5 plans) — completed 2026-04-09

</details>

<details>
<summary>✅ v2.0 Internal IBKRClient Migration (Phase 2) — COMPLETE</summary>

- [x] 02-01: Internal IBKRClient migration — completed
- [x] 02-02: get_kline() with internal client — completed
- [x] 02-03: get_ticker() with internal client — completed
- [x] 02-04: IBKRDataSource migration verification (INT-04, INT-05) — completed 2026-04-11
- [x] 02-05: (reserved — INT-05 covered by 02-04)

</details>

## Backlog

### Phase 999.1: IBKR策略数据源集成 (BACKLOG)

**Goal:** 让 IBKR 策略真正使用 IBKRDataSource，当前 single_symbol_runner.fetch_current_price() 不传 exchange_id，导致永远不走 IBKRDataSource

**Requirements:** TBD

**Plans:** 0 plans

**问题描述:**
- single_symbol_runner 等 runner 的 fetch_current_price() 不传 exchange_id
- DataSourceFactory.get_kline() 不支持 exchange_id 参数
- /api/market/kline 不支持 exchange_id 参数
- IBKRDataSource 建好了但 IBKR 策略根本不用它

**需要实现:**
1. runner 传 exchange_id（策略配置里有）
2. DataSourceFactory.get_kline() 支持 exchange_id
3. /api/market/kline 支持 exchange_id 参数

Plans:
- [ ] TBD (promote with /gsd-review-backlog when ready)

---

*Roadmap updated: 2026-04-11*
