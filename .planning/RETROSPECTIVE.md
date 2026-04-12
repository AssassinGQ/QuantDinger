# Retrospective

## Milestone: v1.0 — IBKR Forex IDEALPRO

**Shipped:** 2026-04-11
**Phases:** 12 | **Plans:** 15

### What Was Built

- Forex symbol normalization (EURUSD/EUR.USD/EUR/USD → base+quote)
- IBKR Forex contract creation via ib_insync.Forex(pair=) with IDEALPRO routing
- Post-qualify validation (_validate_qualified_contract) for conId/secType defense
- Market category & worker gate: Forex as first-class category in PendingOrderWorker
- Eight-signal Forex side mapping aligned with MT5 semantics
- Forex TIF policy: all signals → IOC (validated on IBKR Paper DUQ123679)
- Forex market orders with base-currency totalQuantity + IDEALPRO qty=0 hint
- ForexNormalizer passthrough + _align_qty_to_contract sizeIncrement alignment
- Forex RTH using IBKR liquidHours (24/5 with weekend/maintenance hints)
- Forex fills/position/PnL event callbacks with localSymbol keys + DB metadata
- Strategy automation: validate_exchange_market_category + full E2E chain
- Frontend: Forex broker dropdown (MT5/IBKR Paper/IBKR Live) with correct payloads

### What Worked

- **Dependency-ordered phase sequence** — symbols → contract → qualify → gate → signals → TIF → orders → qty → hours → callbacks → automation → frontend. Each phase built on the previous, zero dependency conflicts.
- **Use-case-driven verification** — every phase defined concrete UC-* test cases upfront; implementation included test code; full regression (928 tests) ran at every phase gate.
- **TDD approach** — RED → GREEN → REFACTOR pattern in early phases (1-4) caught design issues early.
- **Research-first planning** — phase researcher scoped exact code locations, line numbers, and control flow before planning began. Plans contained concrete values, not "align X with Y".
- **Full-chain E2E tests** — Phase 11 refactored from mocked `runner.execute` to real `IBKRClient.place_market_order` with simulated IBKR callbacks.

### What Was Inefficient

- **ROADMAP checkbox drift** — Phase 1-4 and 8 checkboxes/progress table were not auto-updated during early execution. Required manual cleanup before milestone completion.
- **VERIFICATION.md gaps** — Phase 10 and 11 were missing VERIFICATION.md files despite having SUMMARY.md. The `phase complete` CLI didn't catch this.
- **Nyquist frontmatter not updated** — Most VALIDATION.md files still have `nyquist_compliant: false` after successful execution. The executor doesn't auto-update VALIDATION frontmatter.
- **Frontend test is static-only** — Jest guard reads file content with regex, not component mounting. Adequate for source shape but thin on behavior.

### Patterns Established

- `_validate_qualified_contract` as centralized post-qualify defense (used by all 4 callers)
- `_FOREX_SIGNAL_MAP` + `market_category` parameter for signal routing
- `_get_tif_for_signal` with market_type branching for TIF policy
- `_fire_callbacks_after_fill` helper for simulating IBKR event sequences in tests
- `isForexMarket` / `isForexMT5` / `isForexIBKR` computed property pattern in Vue

### Key Lessons

1. **Run full test suite early and often** — the test isolation bug (`g.user_id` in dashboard tests) only surfaced when running the full suite, not individual test files.
2. **Lock decisions in CONTEXT.md before planning** — discuss-phase captured user intent precisely, preventing re-work during execution.
3. **E2E depth matters** — shallow E2E (mock at runner.execute) missed real issues; full-chain E2E (through IBKRClient.place_market_order + callbacks) caught secType mismatches.

### Cost Observations

- Model mix: primarily opus for research/planning/execution, sonnet for verification/checking
- Sessions: ~10 sessions over 3 days
- Notable: 12 phases in 3 days with full test coverage — research-first + TDD kept rework minimal

---

## Milestone: v1.1 — Tech Debt Cleanup + Limit Orders

**Shipped:** 2026-04-12
**Phases:** 6 | **Plans:** 19

### What Was Built

- Qualify result caching — `(symbol, market_type)` TTL cache with per-market env var config; reconnect-safe
- TIF unification — Forex/USStock/HShare all IOC; 24-combination `TestTifMatrix`
- Normalize pipeline ordering — `MarketPreNormalizer` two-layer architecture (market sync + broker async)
- Precious metals classification — XAUUSD/XAGUSD → CMDTY/SMART, validated via paper qualify
- Forex limit orders — LimitOrder DAY TIF + minTick snap + PartiallyFilled cumulative + runner/worker pipeline
- Comprehensive E2E test suite — qualify cache, limit/cancel/error, cross-market, strategy HTTP CRUD, Vue Jest wizard

### What Worked

- **Parallel phase execution** — Phases 14, 15, 16 ran independently after Phase 13, cutting wall-clock time for the three-phase dependency fan-out.
- **Shared test infrastructure (18-01)** — Extracting `ibkr_mocks.py` and `flask_strategy_app.py` first enabled rapid E2E module creation (18-02 through 18-06) with zero duplicated mock code.
- **CONTEXT.md locking product decisions** — Phase 17 CONTEXT locked "DAY only for automation", "cumulative snapshot not incremental", which prevented research rabbit holes.
- **UAT via test execution** — Phase 18 deliverables are test code; running `pytest` + `jest` provided immediate pass/fail UAT without manual browser verification.
- **gsd-plan-checker catch** — Checker caught an invalid `pytest -k` OR expression (`|` instead of `or`) in Phase 18-04 before execution.

### What Was Inefficient

- **TRADE-02/TRADE-03 checkbox drift** — Requirements and roadmap plan checkboxes for 17-02 and 17-03 were not updated to `[x]` during execution. Required manual fix at milestone completion.
- **STATE.md `advance-plan` parse errors** — The `gsd-tools state advance-plan` command failed on several plan completions due to "Current Plan" field format mismatches, requiring manual STATE.md edits.
- **VERIFICATION.md written but not machine-checked** — Phase VERIFICATION files exist but there's no automated gate that compares delivered artifacts against success criteria programmatically.

### Patterns Established

- `tests/helpers/ibkr_mocks.py` as central IBKR test double hub (FakeEvent, wire, qualify stubs, E2E client factory)
- `tests/helpers/flask_strategy_app.py` + `conftest.py` `strategy_client` for HTTP E2E without browser
- `MarketPreNormalizer` / `*PreNormalizer` naming convention for market-layer normalization
- `@jest-environment jsdom` per-file for Vue 2 component tests (keeping node-env for file-based tests)
- Theme-based E2E file splitting: `test_e2e_{theme}_ibkr.py`

### Key Lessons

1. **Mark requirements complete during plan execution, not after** — waiting until milestone completion created reconciliation overhead.
2. **Two-layer normalization (sync market + async broker)** resolves the "normalize before or after qualify" tension cleanly — worth replicating for future instrument types.
3. **E2E test infrastructure as Phase 1 of any test phase** — extracting shared helpers before writing test modules saves 50%+ time on subsequent plans.

### Cost Observations

- Model mix: opus for research/planning/execution, sonnet for checking/verification
- Sessions: ~5 sessions over 2 days
- Notable: 19 plans in 2 days — parallel phase execution + pre-extracted helpers kept throughput high

---

## Cross-Milestone Trends

| Metric | v1.0 | v1.1 |
|--------|------|------|
| Phases | 12 | 6 |
| Plans | 15 | 19 |
| Timeline | 3 days | 2 days |
| Test count | 928 | 1049 (+121) |
| Rework phases | 0 | 0 |
| Tech debt items | 7 | 2 (5 resolved) |
| Checkbox drift | yes | yes (fixed) |

---
*Retrospective started: 2026-04-11 · Updated: 2026-04-12 (v1.1)*
