# Roadmap: QuantDinger IBKR Forex (IDEALPRO)

## Milestones

- ✅ **v1.0 IBKR Forex IDEALPRO** — Phases 1-12 (shipped 2026-04-11)
- ✅ **v1.1 Tech Debt Cleanup + Limit Orders** — Phases 13-18 (shipped 2026-04-12)
- ✅ **v2.0 Cross-Sectional Strategy** — Phases 19-24 (shipped 2026-05-21)
- 📋 **v3.0** — (planning pending)

## Phases

<details>
<summary>✅ v1.0 IBKR Forex IDEALPRO (Phases 1-12) — SHIPPED 2026-04-11</summary>

- [x] Phase 1: Forex symbol normalization (1/1 plans) — completed 2026-04-09
- [x] Phase 2: Forex contract creation IDEALPRO (1/1 plans) — completed 2026-04-09
- [x] Phase 3: Contract qualification (1/1 plans) — completed 2026-04-09
- [x] Phase 4: Market category & worker gate (1/1 plans) — completed 2026-04-10
- [x] Phase 5: Signal-to-side mapping two-way FX (1/1 plans) — completed 2026-04-10
- [x] Phase 6: TIF policy for Forex (1/1 plans) — completed 2026-04-10
- [x] Phase 7: Forex market orders (1/1 plans) — completed 2026-04-10
- [x] Phase 8: Quantity normalization & IB alignment (2/2 plans) — completed 2026-04-10
- [x] Phase 9: Forex trading hours liquidHours (1/1 plans) — completed 2026-04-11
- [x] Phase 10: Fills, position & PnL events (1/1 plans) — completed 2026-04-11
- [x] Phase 11: Strategy automation Forex + IBKR (3/3 plans) — completed 2026-04-11
- [x] Phase 12: Frontend IBKR exchanges for Forex (1/1 plans) — completed 2026-04-11

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>✅ v1.1 Tech Debt Cleanup + Limit Orders (Phases 13-18) — SHIPPED 2026-04-12</summary>

- [x] Phase 13: Qualify result caching + E2E prefix fix (2/2 plans) — completed 2026-04-11
- [x] Phase 14: TIF unification USStock/HShare (1/1 plans) — completed 2026-04-11
- [x] Phase 15: Normalize pipeline ordering (4/4 plans) — completed 2026-04-12
- [x] Phase 16: Precious metals contract classification (3/3 plans) — completed 2026-04-12
- [x] Phase 17: Forex limit orders & automation (3/3 plans) — completed 2026-04-12
- [x] Phase 18: E2E & integration testing (6/6 plans) — completed 2026-04-12

Full details: `.planning/milestones/v1.1-ROADMAP.md`

</details>

<details>
<summary>✅ v2.0 Cross-Sectional Strategy (Phases 19-24) — SHIPPED 2026-05-21</summary>

- [x] Phase 19: NQ100 universe data plane (3/3 plans) — completed 2026-04-14
- [x] Phase 20: Built-in factors & normalization (2/2 plans) — completed 2026-04-15
- [x] Phase 21: Backtest correctness (2/2 plans) — completed 2026-04-15
- [x] Phase 22: Cross-sectional portfolio backtest engine (2/2 plans) — completed 2026-05-15
- [x] Phase 24: NQ100 strategy type (5/5 plans) — completed 2026-05-20
- [x] Phase 23: Grid-search research script (5/5 plans) — completed 2026-05-19

Full details: `.planning/milestones/v2.0-ROADMAP.md`

</details>

### 📋 v3.0 — (planning pending)

Next milestone to be defined via `/gsd-new-milestone`.

**Milestone goal:** Credible NQ100 cross-sectional research: PIT universe with change events, shared factor/normalization library, backtest correctness (survivorship, T+1, halts), a multi-symbol cross-sectional backtest engine, NQ100 strategy type with configurable delisting policy, and a disciplined grid-search script with checkpoint and walk-forward.

**Dependency order:** UNIV → FACTOR → AUDIT → BT (engine) → NQ100 Strategy → SCRIPT.

- [x] **Phase 19: NQ100 universe data plane** — Scrape, API cache, APScheduler refresh, PostgreSQL PIT snapshots + change events (UNIV-01/02/03) (completed 2026-04-14)
- [x] **Phase 20: Built-in factors & normalization** — ≥6 price/volume factors + winsorize / z-score / rank shared module (FACTOR-01/02) (completed 2026-04-15)
- [x] **Phase 21: Backtest correctness** — Delisted bar retention, T+1 signal→open execution, halt/limit-day policy (AUDIT-01/02/03) (completed 2026-04-15)
- [x] **Phase 22: Cross-sectional portfolio backtest engine** — Backend API/service: panel + cross-sectional indicator + T+1 portfolio sim + metrics (BT-01) (completed 2026-05-15)
- [x] **Phase 24: NQ100 strategy type** — Inherit CrossSectionalStrategy, dynamic universe binding, 3 delisting policies: immediate / delayed_N_months / hold_until_signal_exit (STRAT-01/02) (completed 2026-05-20)
- [x] **Phase 23: Grid-search research script** — Factor subset × holding grid, standard metrics, JSONL checkpoint, walk-forward (SCRIPT-01/02/03/04) (completed 2026-05-19)

## Phase Details

### Phase 19: NQ100 universe data plane
**Goal**: Authoritative, queryable NQ100 membership with scheduled refresh — no "today's list" as stand-in for all history.
**Depends on**: Phase 18 (v1.1 complete)
**Requirements**: UNIV-01, UNIV-02, UNIV-03
**Success Criteria** (what must be TRUE):
  1. The system can **fetch and parse** the current NQ100 constituent list from a documented public source into **normalized symbols** (UNIV-01).
  2. The backend **caches** constituents and **refreshes** them on a **configurable schedule** via APScheduler (or equivalent), without a code deploy for routine updates (UNIV-02).
  3. Given a **past calendar date**, queries return the **constituent list as of that date** (PIT) from PostgreSQL-backed history, not from "current members only" (UNIV-03).
  4. Ingestion records **provenance** (e.g. source reference, scrape timestamp) so membership changes are auditable.
**Plans**: 3 plans (2 waves)

Plans:
- [x] `19-01-PLAN.md` — PostgreSQL PIT schema (`0055`), `universe_nq100_service` read path, `test_universe_pit_query.py` (UNIV-03)
- [ ] `19-02-PLAN.md` — Dependencies, `symbol_normalize`, `nq100_sources` parsers + fetch chain + fixtures + `test_nq100_universe_ingest.py` (UNIV-01)
- [ ] `19-03-PLAN.md` — Incremental `sync_nq100_universe`, APScheduler plugin, `GET/POST /api/universe/nq100`, registry and route tests (UNIV-01/02/03)

### Phase 20: Built-in factors & normalization
**Goal**: Shared library importable from cross-sectional indicators, backtest engine, and standalone scripts — one implementation for factors and cross-sectional transforms.
**Depends on**: Phase 19
**Requirements**: FACTOR-01, FACTOR-02
**Success Criteria** (what must be TRUE):
  1. The backend exposes **at least six** built-in price/volume-style factors (categories covering momentum, reversal, volatility, volume, mean-reversion, risk-adjusted) that **indicator code and scripts can import and call** on aligned panels (FACTOR-01).
  2. A **standardization toolkit** provides **winsorize**, **z-score**, and **rank** (and documented composition) as a shared module for reuse by indicators and scripts (FACTOR-02).
  3. A developer can run **documented examples or tests** showing factor output and standardized series on a small fixture panel without live market calls.
**Locked discussion notes (2026-04-14):**
  - v1 因子目录扩展为：动量（1M/3M/6M/12M-1M）、反转（1W/2W/1M）、波动（20D+60D）、风险调整（Sharpe+Sortino）。
  - 标准化主链路：`winsorize + rank`；`z-score` 需实现但默认不启用（可配置打开）。
  - `winsorize` 为必选（处理 NDX 极端值），`rank` 作为默认跨截面稳健输出。
**Plans**: 2 plans（wave 1: FACTOR-02 标准化；wave 2: FACTOR-01 因子+面板）

- [ ] `20-01-PLAN.md` — `NormalizeConfig`、winsorize/rank/z-score/NaN、`normalize_cross_section`、`tests/test_factor_normalize.py`（FACTOR-02）
- [ ] `20-02-PLAN.md` — `core`/`factor_defs`/`panel`、v1 注册表、`tests/test_factor_library.py` + fixture（FACTOR-01）

### Phase 21: Backtest correctness
**Goal**: Enforce survivorship-aware data use, execution timing, and tradeability rules before and inside the cross-sectional engine — fixes apply to the path that builds panels and simulates rebalances (not single-symbol `BacktestService` semantics alone).
**Depends on**: Phase 20
**Requirements**: AUDIT-01, AUDIT-02, AUDIT-03
**Success Criteria** (what must be TRUE):
  1. **Delisted** names' historical K-line rows **remain available** in the research/backtest panel; they are not removed from history just because they are absent from today's list (AUDIT-01).
  2. Portfolio simulation uses **signal day close** (or equivalent) for **cross-sectional ranking** and **executes at the next session's open** (or documented next liquid point), with **no same-bar lookahead** from close signal to same-bar fill (AUDIT-02).
  3. On rebalance days, names that **cannot be bought** (e.g. halt / limit-locked per implemented rules) result in **unspent cash** for intended buys; names that **cannot be sold** are **held** until a later tradeable session (AUDIT-03).
  4. Correctness is **verifiable** via automated tests or reproducible fixtures that demonstrate each rule.
**Locked discussion notes (2026-04-14):**
  - 对 NDX 截面策略，调仓信号使用 T 日收盘数据，调仓执行必须在 T+1 生效。
  - 明确禁止"用 T 收盘数据计算信号并在 T 当时点完成调仓"的同 bar 执行（未来函数）。
**Locked discussion notes (2026-04-15, execution/audit guardrails):**
  - 数据日期约束：用于因子计算与截面打分的价格口径固定为 **T 日收盘价**；禁止任何 T+1 数据在信号生成阶段混入。
  - 停牌/退市过滤：调仓候选需剔除当月停牌或已退市标的；不可买入标的按 AUDIT-03 处理（现金留存），不可卖出标的继续持有至可交易日。
  - 调仓日历约束：避开指数调整生效日当天执行调仓；默认在生效日后一个交易日执行，确保成分名单稳定。
**Plans**: TBD

### Phase 22: Cross-sectional portfolio backtest engine
**Goal**: Backend multi-symbol cross-sectional backtest — distinct from existing single-symbol `BacktestService.run()` — consuming UNIV + FACTOR + Phase 21 rules and returning portfolio-level results.
**Depends on**: Phase 21
**Requirements**: BT-01
**Success Criteria** (what must be TRUE):
  1. A caller can submit **cross-sectional indicator code**, a **symbol list** (or universe reference), and a **date range**, and the service **builds the panel**, **runs** the indicator, and runs **portfolio-level simulation** with Phase 21 execution rules (BT-01).
  2. The response includes a **portfolio equity curve** (or equivalent return series) and **standard summary metrics** consistent with the product's backtest reporting conventions.
  3. The engine produces **one portfolio outcome**, not N independent single-asset backtests averaged ad hoc.
  4. Results are **reproducible** for fixed inputs/config (deterministic enough for regression tests).
**Locked discussion notes (2026-04-14):**
  - 行业中性化作为引擎层可选能力：支持"按行业回归取残差"以降低科技权重偏置。
  - 行业中性化默认关闭，但必须在引擎参数层可开启并可复现。
  - 回测报告必须输出"行业中性化开启/关闭"两组对比结果。
**Locked discussion notes (2026-04-15, universe/execution guardrails):**
  - 成分股名单口径：组合构建使用来自 NDAQ/IC 的"最新已生效名单"（`effective_date <= 当前交易日`），禁止使用未来生效变更。
  - 双类别处理：同一发行主体双类别（如 `GOOG`/`GOOGL`）不得同时进入 Top-N（含 Top 30）；若同时入选需触发人工核查或预设 tie-break 规则并记录日志。
  - 成交假设：回测成交价格口径固定为 `next_open`；实盘执行默认开盘市价单（MOO），并在文档与测试中保持一一对应。
**Plans**: TBD

### Phase 24: NQ100 strategy type
**Goal**: Inherit `CrossSectionalStrategy` to create a dedicated NQ100 strategy class with dynamic universe binding and configurable delisting policy — handling the real-world nuance of index reconstitution events.
**Depends on**: Phase 22
**Requirements**: STRAT-01, STRAT-02
**Success Criteria** (what must be TRUE):
  1. A new `NQ100Strategy` (or equivalent) inherits `CrossSectionalStrategy` and binds `symbol_list` dynamically from the Phase 19 PIT universe API, not from a static `trading_config` list (STRAT-01).
  2. Three configurable `delisting_policy` modes are implemented: **immediate** (sell on effective date), **delayed_N_months** (hold N months post-removal), **hold_until_signal_exit** (keep until indicator signals exit, then exclude from universe) (STRAT-02).
  3. Special cases (bankruptcy, fraud, delisting risk) trigger **unconditional immediate exit** regardless of policy setting.
  4. Both backtest engine and live strategy respect the configured delisting policy.
**Locked discussion notes (2026-04-14):**
  - Mag7 集中度约束归入策略层：支持"组合约束/保留阈值"类配置（例如最少保留若干巨头），用于控制跟踪误差。
  - 实盘默认关闭行业中性化相关增强约束，创建截面策略时可显式开启。
**Plans**: 5 plans (4 waves)

Plans:
- [ ] `24-01-PLAN.md` — DynamicCrossSectionalStrategy + NQ100Strategy (three-layer inheritance, PIT integration, STRAT-01)
- [ ] `24-02-PLAN.md` — Strategy route validation (delisting_policy config, force_exit_symbols, mutual exclusion, STRAT-01/02)
- [ ] `24-03-PLAN.md` — DelistingPolicyFilter basic (immediate/delayed modes, change_events query, STRAT-02)
- [ ] `24-04-PLAN.md` — DelistingPolicyFilter advanced (force_exit override, backtest total loss, STRAT-02)
- [ ] `24-05-PLAN.md` — Runner integration + Strategy excluded tracking (FilterChain, hold_until_signal_exit, STRAT-02)

### Phase 23: Grid-search research script
**Goal**: Standalone `scripts/cross_sectional/` (or successor) batch job: large factor grid, reporting, checkpoint, walk-forward — last so it multiplies a correct engine.
**Depends on**: Phase 24
**Requirements**: SCRIPT-01, SCRIPT-02, SCRIPT-03, SCRIPT-04
**Success Criteria** (what must be TRUE):
  1. A researcher can run a **standalone script** that enumerates a **large grid** of factor subsets × holding counts (at least on the order of **793 combinations × 7 position sizes** per requirements) (SCRIPT-01).
  2. Each completed configuration outputs **standard metrics**: Sharpe, Calmar, max drawdown, annualized return, win rate, and **total trading months** (or equivalent month count) (SCRIPT-02).
  3. Long runs support **checkpoint resume** and **JSONL** (or equivalent line-oriented) **incremental** output so partial results survive interruption (SCRIPT-03).
  4. The script supports **walk-forward** evaluation: configurable **training** and **testing** windows that **slide** forward; outputs distinguish segments per configuration (SCRIPT-04).
**Locked discussion notes (2026-04-14):**
  - 动态因子权重（regime）归入研究脚本层：支持基于波动状态（例如 VIX 阈值）切换因子权重方案并输出对比结果。
  - 回测报告必须输出"静态权重 vs 动态权重"对比结果。
  - 实盘默认关闭动态权重，创建截面策略时可显式开启。
**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-12 | v1.0 | 15/15 | Complete | 2026-04-11 |
| 13-18 | v1.1 | 19/19 | Complete | 2026-04-12 |
| 19 | v2.0 | 3/3 | Complete | 2026-04-14 | - |
| 20 | v2.0 | 2/2 | Complete | 2026-04-15 |
| 21 | v2.0 | 2/2 | Complete | 2026-04-15 |
| 22 | v2.0 | 2/2 | Complete | 2026-05-15 |
| 24 | v2.0 | 5/5 | Complete    | 2026-05-20 |
| 23 | v2.0 | 5/5 | Complete | 2026-05-19 |

---
*Roadmap created: 2026-04-09 · v1.0 shipped: 2026-04-11 · v1.1 shipped: 2026-04-12 · v2.0 Phases 19-23 (13 requirements): 2026-04-13*