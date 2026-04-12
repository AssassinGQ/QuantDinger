# Milestones

## v1.1 Tech Debt Cleanup + Limit Orders (Shipped: 2026-04-12)

**Phases completed:** 6 phases, 19 plans
**Timeline:** 2 days (2026-04-11 → 2026-04-12)
**Commits:** ~117 phase-related commits
**Test suite:** 1049 backend tests + 3 Vue Jest tests passing

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
