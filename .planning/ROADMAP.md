# Roadmap: QuantDinger IBKR Forex (IDEALPRO)

## Milestones

- ✅ **v1.0 IBKR Forex IDEALPRO** — Phases 1-12 (shipped 2026-04-11)
- 🔄 **v1.1 Tech Debt Cleanup + Limit Orders** — Phases 13-18 (in progress)

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

### v1.1 — Tech Debt Cleanup + Limit Orders

- [x] **Phase 13: Qualify result caching + E2E prefix fix** — TTL cache for `qualifyContractsAsync` with per-market TTL and targeted invalidation (qualify/validation failures); IBKR reconnect does **not** flush the cache; fix E2E test API prefix drift
- [ ] **Phase 14: TIF unification (USStock/HShare)** — Open signals IOC-aligned with Forex policy where supported; matrix tests (depends on 13)
- [ ] **Phase 15: Normalize pipeline ordering** — `check` → `normalize` → qualify → `align` with no duplicate steps (depends on 13)
- [ ] **Phase 16: Precious metals contract classification** — XAUUSD/XAGUSD routed to correct secType vs IDEALPRO Forex (depends on 13)
- [ ] **Phase 17: Forex limit orders & automation** — LimitOrder + partial fills + runner/worker limit price (depends on 14, 15, 16)
- [ ] **Phase 18: E2E & integration testing** — Metals/limit E2E (mock IBKR), frontend HTTP E2E (depends on 17)

**Execution order:** 13 → {14, 15, 16} (parallel) → 17 → 18

**Verification:** use-case-driven per `.planning/config.json`. **Regression:** existing backend suite (~928 tests) must remain green.

## Phase Details

### Phase 13: Qualify result caching + E2E prefix fix
**Goal**: Reduce redundant IB qualify traffic via in-memory TTL cache and targeted invalidation; IBKR reconnect does not flush the cache (TTL + failure/validation invalidation only). Fix E2E test API prefix drift.
**Depends on**: Phase 12 (v1.0 complete)
**Requirements**: INFRA-01, TEST-01
**Success Criteria** (what must be TRUE):
  1. A second request for the same symbol within the TTL reuses cached qualify output without a new `qualifyContractsAsync` round-trip (verifiable in tests or instrumentation).
  2. After qualify failure, qualify exception, or post-qualify validation failure for a symbol, the cached entry for that `(symbol, market_type)` is removed. IBKR reconnect does **not** flush the qualify cache (TTL + targeted invalidation only; see Phase 13 CONTEXT).
  3. TTL (or equivalent expiry) is configurable per market (Forex / USStock / HShare) and documented for operators (`IBKR_QUALIFY_TTL_*_SEC`).
  4. `test_forex_ibkr_e2e.py` blueprint prefix matches production API routing (no `/api/strategy/` vs `/api/` drift).
**Plans:** 2/2 plans complete
- [x] `13-01-PLAN.md` — Qualify TTL cache + docs + requirements reconcile
- [x] `13-02-PLAN.md` — E2E Flask blueprint `/api` prefix alignment (`test_forex_ibkr_e2e.py`)

### Phase 14: TIF unification (USStock/HShare)
**Goal**: Align open-signal TIF policy with Forex (IOC) where the venue accepts it, without silent regressions on exceptions.
**Depends on**: Phase 13 (qualify cache available for TIF validation tests)
**Requirements**: INFRA-02
**Success Criteria** (what must be TRUE):
  1. USStock **open** signals use IOC where applicable; behavior matches the agreed matrix.
  2. HShare exceptions (e.g. DAY-only where IOC is invalid) are explicit in code or docs and covered by tests—no accidental IOC on unsupported paths.
  3. A TIF matrix (signal type × market category) is enforced by automated tests so future changes cannot drift policy unnoticed.
**Plans**: TBD

### Phase 15: Normalize pipeline ordering
**Goal**: One consistent order pipeline: normalize after checks, align only after qualify, no duplicate normalize/align.
**Depends on**: Phase 13 (independent of TIF and metals)
**Requirements**: INFRA-03
**Success Criteria** (what must be TRUE):
  1. Market-order and limit-order paths both execute: check → normalize → qualify/contract validation → quantity align—never align before qualify.
  2. `normalize` and contract `align` are not applied twice on the same logical order step.
  3. Regressions are caught by unit/integration tests on the normalizer and order entry helpers.
**Plans**: TBD

### Phase 16: Precious metals contract classification
**Goal**: XAUUSD/XAGUSD use the correct IB product type (e.g. CMDTY/SMART vs Forex CASH/IDEALPRO) with validated qualify results.
**Depends on**: Phase 13 (qualify cache benefits metals validation; independent of TIF and normalize)
**Requirements**: TRADE-04
**Success Criteria** (what must be TRUE):
  1. XAUUSD (and documented handling for XAGUSD) routes through `_create_contract` / validation distinct from standard IDEALPRO Forex pairs.
  2. Post-qualify validation rejects wrong `secType`/routing for these symbols when IB returns unexpected shapes.
  3. Metals paths remain separable from EURUSD-style Forex so logs and positions show the correct instrument class.
**Plans**: TBD

### Phase 17: Forex limit orders & automation
**Goal**: Full limit-order execution: REST/automation parity, minTick prices, partial fills, and runner/worker support.
**Depends on**: Phase 14 (TIF policy), Phase 15 (normalize pipeline), Phase 16 (metals contract classification)
**Requirements**: TRADE-01, TRADE-02, TRADE-03
**Success Criteria** (what must be TRUE):
  1. A Forex limit order can be placed with limit price snapped to `ContractDetails.minTick`, with TIF choices (IOC/DAY/GTC) per policy.
  2. `PartiallyFilled` and subsequent updates adjust **remaining** correctly; cumulative fills do not double-apply positions or PnL.
  3. `StatefulClientRunner` / `PendingOrderWorker` accept limit signals and pass limit price (and order type) so automated trading matches manual/API behavior.
  4. Terminal order statuses remain consistent with existing trackers (no stuck or duplicate terminal handling).
**Plans**: TBD

### Phase 18: E2E & integration testing
**Goal**: End-to-end coverage for metals + limit orders; frontend HTTP E2E.
**Depends on**: Phase 17 (limit orders and metals both available)
**Requirements**: TRADE-05, TRADE-06, TEST-02
**Success Criteria** (what must be TRUE):
  1. Precious-metals E2E (mock IBKR) exercises qualify → order → callback path end-to-end.
  2. Limit-order E2E covers normal fill, partial fill, and cancel scenarios with mocks.
  3. Frontend HTTP E2E (e.g. Playwright) proves the Vue wizard can round-trip Forex+IBKR strategy creation against the API.
  4. Full backend test suite remains green (including existing ~928 tests).
**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Forex symbol normalization | v1.0 | 1/1 | Complete | 2026-04-09 |
| 2. Forex contract creation (IDEALPRO) | v1.0 | 1/1 | Complete | 2026-04-09 |
| 3. Contract qualification | v1.0 | 1/1 | Complete | 2026-04-09 |
| 4. Market category & worker gate | v1.0 | 1/1 | Complete | 2026-04-10 |
| 5. Signal-to-side mapping (two-way FX) | v1.0 | 1/1 | Complete | 2026-04-10 |
| 6. TIF policy for Forex | v1.0 | 1/1 | Complete | 2026-04-10 |
| 7. Forex market orders | v1.0 | 1/1 | Complete | 2026-04-10 |
| 8. Quantity normalization & IB alignment | v1.0 | 2/2 | Complete | 2026-04-10 |
| 9. Forex trading hours (liquidHours) | v1.0 | 1/1 | Complete | 2026-04-11 |
| 10. Fills, position & PnL events | v1.0 | 1/1 | Complete | 2026-04-11 |
| 11. Strategy automation (Forex + IBKR) | v1.0 | 3/3 | Complete | 2026-04-11 |
| 12. Frontend IBKR exchanges for Forex | v1.0 | 1/1 | Complete | 2026-04-11 |
| 13. Qualify result caching + E2E prefix fix | 2/2 | Complete    | 2026-04-11 | 2026-04-11 |
| 14. TIF unification (USStock/HShare) | v1.1 | 0/? | Not started | — |
| 15. Normalize pipeline ordering | v1.1 | 0/? | Not started | — |
| 16. Precious metals classification | v1.1 | 0/? | Not started | — |
| 17. Forex limit orders & automation | v1.1 | 0/? | Not started | — |
| 18. E2E & integration testing | v1.1 | 0/? | Not started | — |

---
*Roadmap created: 2026-04-09 · v1.0 shipped: 2026-04-11 · v1.1 phases 13-18: 2026-04-11*
