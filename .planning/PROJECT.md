# QuantDinger IBKR Forex 交易支持

## What This Is

QuantDinger 的 IBKR 交易客户端已扩展支持 Forex（外汇）交易。IBKRClient 支持美股（USStock）、港股（HShare）和 IBKR IDEALPRO 上的外汇货币对，策略系统可以自动执行外汇交易信号，前端支持 MT5 / IBKR Paper / IBKR Live 三种 Forex 交易所选择。

## Core Value

策略系统发出的 Forex 交易信号能正确通过 IBKRClient 在 IDEALPRO 上执行，从信号到成交的完整链路畅通。

## Current State

**Shipped v1.0** (2026-04-11) — 12 phases, 15 plans, 928 backend tests passing.

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

### Active

(None — next milestone requirements TBD)

### Out of Scope

- 限价单 — v1 仅市价单
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

## Known Tech Debt (from v1.0 Audit)

| Item | Priority | Source |
|------|----------|--------|
| Qualify 结果缓存 | Low | Phase 3 |
| USStock/HShare open → IOC | Medium | Phase 6 |
| TIF fallback (IOC→DAY 重试) | Low | Phase 6 |
| cashQty 下单 (ADV-02) | Low | Phase 7 |
| Forex 限价单 (ADV-01) | Low | Phase 7 |
| 贵金属合约归类 (XAUUSD as CMDTY?) | Medium | Phase 8 |

## Constraints

- **Tech stack**: ib_insync，与现有 IBKR 集成一致
- **兼容性**: USStock/HShare 交易路径不受影响（928 tests regression-free）
- **架构**: BaseStatefulClient / StatefulClientRunner 模式

---
*Last updated: 2026-04-11 after v1.0 milestone*
