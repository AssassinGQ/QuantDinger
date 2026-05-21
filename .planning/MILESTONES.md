# Milestones

## v2.0 Cross-Sectional Strategy (Shipped: 2026-05-21)

**Phases completed:** 6 phases, 19 plans, 43 tasks

**Key accomplishments:**

- PostgreSQL tables for NQ100 membership intervals and change events, plus `get_constituents_as_of` with mocked-DB tests proving empty/open/closed interval behavior.
- NDX_IC/NDX_EIV CSV now ingest into PIT membership plus EIV baseline tables with raw_payload fidelity and idempotent repeat imports.
- 交付了可执行的 NQ100 数据平面运行面：每周自动同步、手动刷新、PIT 成分查询与 EIV 按日查询，并保证 QQQ 权重补充失败不阻塞主流程。
- 交付了可复用的截面标准化模块与 fail-fast 配置解析，默认 `winsorize -> rank` 并支持可选 z-score。
- 完成了内置因子库 v1（11 因子）与面板构建器，形成注册表 + 纯函数双 API。
- Cross-sectional runner now enforces T->T+1 (or shifted T+2) execution semantics with explicit untradable and fallback filtering before dispatch.
- Phase 21 now has a deterministic, blocking correctness matrix that covers no-lookahead, untradable semantics, cash M&A forced exits, and effective-date schedule shifts.
- Wave 0 test infrastructure: pytest scaffold with 7 placeholder tests for grid search script + minimal YAML config fixture enabling automated verification from task 1 of subsequent plans
- YAML config loading with yaml.safe_load, itertools.combinations for 793 factor combos, and CLI argument parsing for grid search script
- Phase 22 HTTP API caller, indicator code builder, and score calculator
- Checkpoint resume, JSONL/CSV/HTML output generation
- Walk-forward rolling window validation, OOS aggregation, dual TOP 100 outputs, complete main() orchestration
- Three-layer inheritance structure for dynamic universe binding: DynamicCrossSectionalStrategy intermediate layer with get_universe_list() interface + NQ100Strategy calling Phase 19 PIT API + mutual exclusion validation for symbol_list/universe config
- Cross-sectional configuration validation in strategy routes with HTTP 400 responses for invalid delisting_policy, force_exit_symbols, and mutual exclusion violations
- One-liner:
- Integrated DelistingPolicyFilter into Runner FilterChain and implemented Strategy-layer hold_until_signal_exit tracking with excluded_from_universe persistence across rebalance cycles

---

## v1.1 Tech Debt Cleanup + Limit Orders (Shipped: 2026-04-12)

**Phases completed:** 6 phases (13-18), 19 plans
**Timeline:** 2 days (2026-04-11 → 2026-04-12)
**Commits:** ~121 phase-related commits
**Test suite:** 1060 backend tests + Vue Jest passing
**Audit:** tech_debt (11/11 requirements satisfied, 5 minor deferred items)

**Key accomplishments:**

1. Qualify result caching — `(symbol, market_type)` TTL cache reduces redundant `qualifyContractsAsync` API calls; per-market TTL via env vars; reconnect does not flush
2. TIF unification — Forex/USStock/HShare all use IOC for all 8 signal types; 24-combination `TestTifMatrix` prevents drift
3. Normalize pipeline ordering — `MarketPreNormalizer` two-layer architecture (market pre_normalize/pre_check + broker qualify/align), no duplicate steps
4. Precious metals contract classification — XAUUSD/XAGUSD route to CMDTY/SMART (not Forex CASH/IDEALPRO), validated via paper qualify
5. Forex limit orders & automation — LimitOrder DAY TIF + minTick snap (BUY floor/SELL ceil) + PartiallyFilled cumulative snapshot + runner/worker limit price pipeline
6. Comprehensive E2E testing — qualify cache, limit/cancel/error, cross-market USStock/HShare, strategy HTTP CRUD, and Vue Jest wizard coverage

**Archives:**

- `milestones/v1.1-ROADMAP.md`
- `milestones/v1.1-REQUIREMENTS.md`
- `milestones/v1.1-MILESTONE-AUDIT.md`

---

## v1.0 IBKR Forex IDEALPRO (Shipped: 2026-04-11)

**Phases completed:** 12 phases, 15 plans
**Timeline:** 3 days (2026-04-09 → 2026-04-11)
**Commits:** ~55 phase-related commits
**Test suite:** 928 backend tests passing

**Key accomplishments:**

1. Forex symbol normalization — EURUSD/EUR.USD/EUR/USD all resolve to canonical base+quote
2. IBKR Forex contract creation via `ib_insync.Forex(pair=)` with IDEALPRO routing and post-qualify validation
3. Eight-signal Forex side mapping (BUY/SELL for open/close long/short) aligned with MT5 semantics
4. Forex TIF policy: all signals → IOC, validated on IBKR Paper (DUQ123679)
5. Full trading chain: symbol → contract → qualify → market order → qty alignment → RTH check → fill → position → PnL
6. Strategy automation: `market_category=Forex` + `ibkr-paper/ibkr-live` drives auto-trade from API to IBKR execution
7. Frontend: Forex broker dropdown supports MT5 / IBKR Paper / IBKR Live with correct payload shapes

**Audit:** tech_debt (12/12 requirements satisfied, 7 deferred items — see `milestones/v1.0-MILESTONE-AUDIT.md`)

**Archives:**

- `milestones/v1.0-ROADMAP.md`
- `milestones/v1.0-REQUIREMENTS.md`
- `milestones/v1.0-MILESTONE-AUDIT.md`

---
