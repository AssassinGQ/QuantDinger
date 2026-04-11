# Milestones

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
