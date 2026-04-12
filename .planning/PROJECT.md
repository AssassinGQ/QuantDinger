# QuantDinger IBKR Forex 交易支持

## What This Is

QuantDinger 的 IBKR 交易客户端已扩展支持 Forex（外汇）交易。IBKRClient 支持美股（USStock）、港股（HShare）和 IBKR IDEALPRO 上的外汇货币对，策略系统可以自动执行外汇交易信号，前端支持 MT5 / IBKR Paper / IBKR Live 三种 Forex 交易所选择。

## Core Value

策略系统发出的 Forex 交易信号能正确通过 IBKRClient 在 IDEALPRO 上执行，从信号到成交的完整链路畅通。

## Current Milestone: v1.1 Tech Debt Cleanup + Limit Orders

**Goal:** 清理 v1.0 遗留的技术债务，增加 Forex 限价单能力，补全 E2E 测试覆盖。

**Target features:**
- Qualify 结果缓存（减少重复 IBKR API 调用）
- USStock/HShare open 信号统一 IOC（与 Forex 对齐）
- Forex 限价单（LimitOrder）
- 贵金属合约归类（XAUUSD/XAGUSD → 正确 secType）
- normalize() 调用时序修正
- E2E 测试 prefix 修复 + 前端 HTTP E2E

## Current State

**Shipped v1.0** (2026-04-11) — 12 phases, 15 plans.
**Phase 13 complete** (2026-04-11) — Qualify 缓存 + E2E prefix 修复, 931 backend tests passing.
**Phase 14 complete** (2026-04-11) — TIF 统一（Forex/USStock/HShare → IOC），956 backend tests passing.
**Phase 15 complete** (2026-04-12) — Normalize pipeline ordering (MarketPreNormalizer + pre_normalize → pre_check → qualify → align)，958 backend tests passing.
**Phase 16 complete** (2026-04-12) — Precious metals contract classification (XAUUSD/XAGUSD → CMDTY/SMART, paper-validated)，992 backend tests passing.
**Phase 17 complete** (2026-04-12) — Forex limit orders & automation (LimitOrder DAY TIF, minTick snap, PartiallyFilled cumulative overwrite, strategy→runner→worker limit pipeline)，1023 backend tests passing.

Tech stack: Python 3.10+ backend (Flask + ib_insync), Vue.js 2.x frontend, PostgreSQL, Docker.
Backend: ~57K LOC app + ~13K LOC tests. Frontend: ~6.2K LOC trading assistant wizard.

## Requirements

### Validated

- ✓ IBKRClient 支持美股（USStock）下单 — existing
- ✓ IBKRClient 支持港股（HShare）下单 — existing
- ✓ ib_insync 连接管理（自动重连、paper/live 单例） — existing
- ✓ 事件驱动的成交/仓位/PnL 追踪 — existing
- ✓ PendingOrderWorker 完整的下单流程（信号→pending→执行→成交） — existing
- ✓ Forex symbol 解析（EURUSD/EUR.USD/EUR/USD → base+quote） — v1.0 Phase 1
- ✓ Forex 合约创建（ib_insync.Forex + IDEALPRO） — v1.0 Phase 2
- ✓ Forex 合约 qualify 验证（conId/localSymbol/secType 防御） — v1.0 Phase 3
- ✓ supported_market_categories 包含 Forex — v1.0 Phase 4
- ✓ Forex 八信号双向映射（与 MT5 对齐） — v1.0 Phase 5
- ✓ Forex TIF = IOC（Paper 验证 DUQ123679） — v1.0 Phase 6
- ✓ Forex 市价单（base-currency totalQuantity） — v1.0 Phase 7
- ✓ ForexNormalizer passthrough + _align_qty_to_contract — v1.0 Phase 8
- ✓ Forex RTH 使用 IBKR liquidHours（24/5） — v1.0 Phase 9
- ✓ Forex fills/position/PnL 事件回调（localSymbol key + metadata） — v1.0 Phase 10
- ✓ 策略自动化（market_category=Forex + ibkr-paper/ibkr-live） — v1.0 Phase 11
- ✓ 前端 Forex 下拉框（MT5/IBKR Paper/IBKR Live） — v1.0 Phase 12
- ✓ Qualify 结果缓存（TTL per market, (symbol, market_type) key, 重连不清缓存） — v1.1 Phase 13
- ✓ E2E 测试 API prefix 统一（/api/strategy/ → /api/） — v1.1 Phase 13
- ✓ TIF 统一 Forex/USStock/HShare → IOC（IBKR SEHK 支持 IOC 确认） — v1.1 Phase 14
- ✓ Normalize pipeline ordering（MarketPreNormalizer: pre_normalize → pre_check → qualify → align，无重复） — v1.1 Phase 15
- ✓ 贵金属合约归类（XAUUSD/XAGUSD → CMDTY/SMART，market_type="Metals"，Paper DUQ123679 验证） — v1.1 Phase 16
- ✓ Forex 限价单（LimitOrder DAY TIF + minTick snap + IOC/DAY/GTC REST + PartiallyFilled 累计覆盖 + 策略自动化限价管道） — v1.1 Phase 17

### Active

- 前端 HTTP E2E 测试（Vue wizard → API round-trip）

### Out of Scope

- TIF fallback (IOC→DAY 自动重试) — 留给后续
- cashQty 下单方式 — 留给后续
- Forex 专用策略类型 — 复用现有策略框架
- ForexNormalizer 最小下单量检查 — IBKR 拒单兜底
- MT5 Forex 改动 — MT5 独立实现
- FXCONV 货币转换订单 — 非策略交易路径
- 止损/止盈/括号订单 — v2

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Forex TIF = IOC | IDEALPRO 市价单需要 IOC（避免 DAY 挂单残留） | ✓ Good (Phase 6) |
| 市价单优先 | 外汇流动性好，滑点可控 | ✓ Good (Phase 7) |
| ForexNormalizer passthrough + IB 对齐 | normalize 透传，_align_qty_to_contract 负责 sizeIncrement | ✓ Good (Phase 8) |
| RTH 复用 IBKR 合约时间 | Forex 24/5 由 IBKR liquidHours 正确反映 | ✓ Good (Phase 9) |
| Forex broker 平铺列表 | MT5/IBKR Paper/IBKR Live 无默认值 | ✓ Good (Phase 12) |
| isForexMarket 替代 isMT5Market | 更清晰的语义 + isForexMT5/isForexIBKR 子检查 | ✓ Good (Phase 12) |
| Qualify TTL 缓存 (symbol, market_type) | 减少冗余 qualifyContractsAsync，重连不清缓存 | ✓ Good (Phase 13) |
| TIF 统一 IOC (Forex/USStock/HShare) | 与 Forex 自动化一致；IBKR 确认 SEHK 支持 IOC | ✓ Good (Phase 14) |
| MarketPreNormalizer 两层架构 | 市场层 pre_normalize+pre_check（同步） vs 券商层 qualify+align（异步） | ✓ Good (Phase 15) |
| Metals CMDTY/SMART (非 Forex CASH/IDEALPRO) | Paper qualify 验证：Forex("XAUUSD") Error 200；Contract(CMDTY/SMART) 成功 | ✓ Good (Phase 16) |
| Limit TIF DAY + minTick snap | 自动化限价单 DAY（不随信号变），minTick BUY floor/SELL ceil | ✓ Good (Phase 17) |
| PartiallyFilled 累计覆盖 | 不做增量 +=，IBKR filled/remaining 是 snapshot | ✓ Good (Phase 17) |

## Known Tech Debt (from v1.0 Audit)

| Item | Priority | Source |
|------|----------|--------|
| ~~Qualify 结果缓存~~ | ~~Low~~ | ✓ Phase 13 |
| ~~USStock/HShare open → IOC~~ | ~~Medium~~ | ✓ Phase 14 |
| TIF fallback (IOC→DAY 重试) | Low | Phase 6 |
| cashQty 下单 (ADV-02) | Low | Phase 7 |
| ~~Forex 限价单 (ADV-01)~~ | ~~Low~~ | ✓ Phase 17 |
| ~~贵金属合约归类 (XAUUSD as CMDTY?)~~ | ~~Medium~~ | ✓ Phase 16 |

## Constraints

- **Tech stack**: ib_insync，与现有 IBKR 集成一致
- **兼容性**: USStock/HShare/Forex 交易路径不受影响（1023 tests regression-free）
- **架构**: BaseStatefulClient / StatefulClientRunner 模式

---
*Last updated: 2026-04-12 — Phase 17 complete*
