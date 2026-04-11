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

## Cross-Milestone Trends

| Metric | v1.0 |
|--------|------|
| Phases | 12 |
| Plans | 15 |
| Timeline | 3 days |
| Test count | 928 |
| Rework phases | 0 |
| Tech debt items | 7 |

---
*Retrospective started: 2026-04-11*
