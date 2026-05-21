# QuantDinger 量化交易平台

## What This Is

QuantDinger 是一个 AI 驱动的量化交易平台。已实现 IBKR 多市场（USStock/HShare/Forex/Metals）自动化交易和 NQ100 截面策略回测验证能力。

## Core Value

从数据获取、因子计算、回测验证到实盘执行的完整量化交易链路，确保回测结果真实可靠（无幸存者偏差、无未来函数、正确处理停牌）。

## Milestones

<details>
<summary>✅ v1.0 IBKR Forex IDEALPRO — SHIPPED 2026-04-11</summary>

12 phases, 15 plans. Forex symbol → contract → qualify → order → fill → automation 全链路。
</details>

<details>
<summary>✅ v1.1 Tech Debt Cleanup + Limit Orders — SHIPPED 2026-04-12</summary>

6 phases (13-18), 19 plans. Qualify 缓存、TIF 统一、Normalize 流水线、贵金属归类、Forex 限价单、E2E 全覆盖。
</details>

<details>
<summary>✅ v2.0 Cross-Sectional Strategy — SHIPPED 2026-05-21</summary>

6 phases (19-24), 19 plans, 43 tasks. NQ100 PIT universe、因子库 + 标准化、回测三坑修复、截面组合引擎、NQ100 策略类型（delisting policy）、网格搜索脚本。
</details>

## Current State

**Shipped v1.0** (2026-04-11) — 12 phases, 15 plans. IBKR Forex IDEALPRO 全链路。
**Shipped v1.1** (2026-04-12) — 6 phases (13-18), 19 plans. Tech debt cleanup + limit orders。
**Shipped v2.0** (2026-05-21) — 6 phases (19-24), 19 plans, 43 tasks. Cross-sectional strategy research capability。

Tech stack: Python 3.10+ backend (Flask + ib_insync), Vue.js 2.x frontend, PostgreSQL, Docker.
Backend: ~60K LOC app + ~18K LOC tests. Frontend: ~6.2K LOC trading assistant wizard.

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
- ✓ Metals E2E 验证（mock IBKR qualify+order+callback XAGUSD CMDTY） — v1.1 Phase 18
- ✓ Limit E2E 验证（normal+partial+cancel+error，cross-market USStock limit） — v1.1 Phase 18
- ✓ 前端 HTTP E2E（Flask test_client 策略 CRUD + Vue Jest wizard） — v1.1 Phase 18
- ✓ NQ100 成分股动态爬取 & 后端 API 缓存 & PIT 历史快照（UNIV-01/02/03） — v2.0 Phase 19
- ✓ 内置价量因子库（11 因子）+ 标准化工具模块（winsorize/z-score/rank）（FACTOR-01/02） — v2.0 Phase 20
- ✓ 回测三坑修复：幸存者偏差、T+1 对齐、停牌处理（AUDIT-01/02/03） — v2.0 Phase 21
- ✓ 多品种截面回测引擎——后端 API（BT-01） — v2.0 Phase 22
- ✓ NQ100Strategy 继承 CrossSectionalStrategy，动态 universe 绑定，三种 delisting_policy（STRAT-01/02） — v2.0 Phase 24
- ✓ 独立回测脚本：暴力因子网格搜索 + 指标输出 + checkpoint + walk-forward（SCRIPT-01/02/03/04） — v2.0 Phase 23

### Active

(None — start next milestone via `/gsd-new-milestone`)

### Out of Scope

- 截面策略前端 UI — v3.0
- A 股截面策略 — v3.0+
- 实盘截面交易自动化 — v3.0+
- TIF fallback (IOC→DAY 自动重试) — 留给后续
- cashQty 下单方式 — 留给后续

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| E2E 按主题拆分 + 共享 helpers | 减少重复 mock 代码，提高可维护性 | ✓ Good (Phase 18) |
| Flask test_client (非 Playwright) | CI/CD 不引入浏览器依赖，pytest 一致性 | ✓ Good (Phase 18) |
| Forex TIF = IOC | IDEALPRO 市价单需要 IOC（避免 DAY 挂单残留） | ✓ Good (Phase 6) |
| MarketPreNormalizer 两层架构 | 市场层 pre_normalize+pre_check（同步） vs 券商层 qualify+align（异步） | ✓ Good (Phase 15) |
| Metals CMDTY/SMART (非 Forex CASH/IDEALPRO) | Paper qualify 验证：Forex("XAUUSD") Error 200；Contract(CMDTY/SMART) 成功 | ✓ Good (Phase 16) |
| PIT universe API (get_constituents_as_of) | 动态成分绑定，避免静态 trading_config | ✓ Good (Phase 19/24) |
| T+1 执行强制执行 | signal date close → execution date next_open，禁止同 bar lookahead | ✓ Good (Phase 21) |
| 三种 delisting_policy 模式 | immediate / delayed_N_months / hold_until_signal_exit | ✓ Good (Phase 24) |
| Grid search HTTP API 调用 | 避免直接服务复用，保持回测引擎独立性 | ✓ Good (Phase 23) |

## Known Tech Debt (v2.0 Audit)

| Item | Priority | Notes |
|------|----------|-------|
| FACTOR-02 normalization unwired | Medium | Phase 20 built winsorize/rank/zscore but not consumed by backtest/grid search |
| Phase 20/22/24 Nyquist incomplete | Low | VALIDATION.md frontmatter needs nyquist_compliant: true |
| Phase 19/23 VERIFICATION.md missing | Low | UAT evidence exists but formal VERIFICATION.md not created |

## Constraints

- **Tech stack**: ib_insync，与现有 IBKR 集成一致
- **兼容性**: USStock/HShare/Forex/Metals 交易路径不受影响
- **架构**: BaseStatefulClient / StatefulClientRunner 模式

---
*Last updated: 2026-05-21 — v2.0 milestone shipped*
