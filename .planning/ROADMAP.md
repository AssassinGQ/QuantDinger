# Roadmap: QuantDinger IBKR Forex (IDEALPRO)

## Overview

This milestone extends the existing IBKR stack from US stocks and HK shares to IDEALPRO spot Forex. Work proceeds in dependency order: normalize symbols and build correct Forex contracts, open routing and execution policy (signal sides, TIF), deliver market orders with aligned quantities, then runtime behavior (hours, callbacks), strategy-driven automation, and finally frontend exchange selection. **Verification strategy (from config):** use-case-driven — each phase plan defines concrete use cases and test specs; implementation includes test code; verify runs **all** use cases including existing suite regressions.

**Suggested engineering sequence (research):** symbols → contract → qualification → category gate → signal mapping → TIF → market order + qty → RTH → callbacks → strategy config → integration/E2E paper → frontend.

## Phases

- [x] **Phase 1: Forex symbol normalization** — Parse EURUSD / EUR.USD / EUR/USD to base+quote without equity mis-routing (completed 2026-04-09)
- [x] **Phase 2: Forex contract creation (IDEALPRO)** — `Forex` contracts with CASH + IDEALPRO from `market_type=Forex` (completed 2026-04-09)
- [x] **Phase 3: Contract qualification** — `qualifyContracts` resolves conId, localSymbol for Forex (completed 2026-04-09)
- [x] **Phase 4: Market category & worker gate** — `supported_market_categories` + PendingOrderWorker validation for Forex (completed 2026-04-10)
- [x] **Phase 5: Signal-to-side mapping (two-way FX)** — Long/short-style signals map to BUY/SELL for Forex (completed 2026-04-10)
- [x] **Phase 6: TIF policy for Forex** — `_get_tif_for_signal` Forex → IOC for all signals (completed 2026-04-10)
- [x] **Phase 7: Forex market orders** — `place_market_order` for Forex with base-currency `totalQuantity` (completed 2026-04-10)
- [x] **Phase 8: Quantity normalization & IB alignment** — ForexNormalizer + `_align_qty_to_contract` on Forex path (completed 2026-04-10)
- [x] **Phase 9: Forex trading hours (liquidHours)** — `is_market_open` uses IBKR contract hours for 24/5 FX (completed 2026-04-11)
- [x] **Phase 10: Fills, position & PnL events** — Callbacks and keys correct for Forex symbols and currencies (completed 2026-04-11)
- [x] **Phase 11: Strategy automation (Forex + IBKR)** — Config `market_category=Forex` + ibkr-paper/live drives auto-trade (completed 2026-04-11)
- [x] **Phase 12: Frontend IBKR exchanges for Forex** — Strategy UI offers ibkr-paper / ibkr-live when Forex is selected (completed 2026-04-11)

## Phase Details

### Phase 1: Forex symbol normalization
**Goal**: All supported Forex symbol spellings resolve to a single internal base+quote representation so downstream code never defaults Forex to US `Stock`.
**Depends on**: Nothing (first phase)
**Requirements**: CONT-02
**Success Criteria** (what must be TRUE):
  1. Inputs like `EURUSD`, `EUR.USD`, and `EUR/USD` normalize to the same canonical base and quote the rest of the stack can consume.
  2. When the caller indicates Forex (or equivalent routing context), symbol handling does not silently treat the symbol as a US equity ticker.
  3. Automated tests document and lock accepted formats and edge cases (uppercase, separators).
**Plans:** 1/1 plans complete

Plans:
- [x] 01-01-PLAN.md — TDD: Forex symbol tests + normalize_symbol/parse_symbol/format_display_symbol Forex branches

### Phase 2: Forex contract creation (IDEALPRO)
**Goal**: `IBKRClient` builds `ib_insync.Forex` with IDEALPRO routing for Forex execution, not `Stock`/`SMART`.
**Depends on**: Phase 1
**Requirements**: CONT-01
**Success Criteria** (what must be TRUE):
  1. For `market_type`/`market_category` Forex, `_create_contract` returns a Forex contract with `secType=CASH` and `exchange=IDEALPRO` (via ib_insync conventions).
  2. USStock and HShare contract creation remain unchanged for non-Forex paths.
  3. Unit tests assert contract fields for representative pairs (e.g. EURUSD).
**Plans:** 1/1 plans complete

Plans:
- [x] 02-01-PLAN.md — TDD: MockForex + 6 use-case tests (RED) → _create_contract Forex/ValueError branches (GREEN)

### Phase 3: Contract qualification
**Goal**: Forex contracts qualify like equities: stable `conId`, `localSymbol`, and details for sizing and display. Post-qualify validation (`_validate_qualified_contract`) catches conId=0 and secType mismatches; error messages include market_type across all 4 callers.
**Depends on**: Phase 2
**Requirements**: CONT-03
**Success Criteria** (what must be TRUE):
  1. After `qualifyContracts` (or async equivalent), Forex contracts carry a valid `conId` and IB-expected `localSymbol` (e.g. `EUR.USD`).
  2. Qualification failure surfaces as a clear error; the system does not proceed with an unqualified Forex contract.
  3. Tests mock or record qualification outcomes for at least one liquid pair.
**Plans:** 1/1 plans complete

Plans:
- [x] 03-01-PLAN.md — TDD: 9 UC tests (RED) → _validate_qualified_contract + 4-caller error message enhancement (GREEN)

### Phase 4: Market category & worker gate
**Goal**: The runner and pending-order pipeline accept Forex as a first-class market category end-to-end.
**Depends on**: Phase 3
**Requirements**: CONT-04
**Success Criteria** (what must be TRUE):
  1. `IBKRClient.supported_market_categories` includes `"Forex"`.
  2. `PendingOrderWorker.validate_market_category` (or equivalent) allows Forex alongside existing categories.
  3. A Forex-marked signal is not rejected solely for category when other validations pass.
**Plans:** 1/1 plans complete

Plans:
- [x] 04-01-PLAN.md — Forex in `supported_market_categories`; flip/extend `test_exchange_engine`; `test_pending_order_worker` UC-4/UC-5 via `_execute_live_order`

### Phase 5: Signal-to-side mapping (two-way FX)
**Goal**: Strategy signal semantics for Forex map to correct IB BUY/SELL including short-style flows.
**Depends on**: Phase 4
**Requirements**: EXEC-02
**Success Criteria** (what must be TRUE):
  1. `open_long` → BUY, `close_long` → SELL, `open_short` → SELL, `close_short` → BUY for Forex (per project conventions).
  2. Forex no longer fails purely because “short” is disallowed as on single-stock equity assumptions.
  3. Table-driven tests cover all four signal types for `market_category=Forex`.
**Plans:** 1/1 plans complete

Plans:
- [x] 05-01-PLAN.md — Base `map_signal_to_side(..., market_category=)`; IBKR `_FOREX_SIGNAL_MAP`; runner wiring; UC-F1–F6 / UC-E1–E3 / UC-R1 tests; REGR-01

### Phase 6: TIF policy for Forex
**Goal**: Time-in-force for Forex market orders matches IBKR behavior validated in paper (open vs close; DAY vs IOC vs GTC as decided).
**Depends on**: Phase 5
**Requirements**: EXEC-03
**Success Criteria** (what must be TRUE):
  1. `_get_tif_for_signal` applies a documented Forex-specific policy distinct from equity where needed.
  2. Submitted orders carry the TIF chosen by that policy for open and close scenarios.
  3. Tests encode the policy; paper trading notes document any IOC/DAY fallback (per research).
**Plans:** 1/1 plans complete

Plans:
- [x] 06-01-PLAN.md — Forex `_get_tif_for_signal` → IOC (UC-T1–T8, UC-E1–E3, REGR-01); tests in `test_ibkr_client.py`

### Phase 7: Forex market orders
**Goal**: Market orders for Forex submit through the same client surface as equities with correct `MarketOrder` + quantity.
**Depends on**: Phase 6
**Requirements**: EXEC-01
**Success Criteria** (what must be TRUE):
  1. `place_market_order` successfully submits a market order for a qualified Forex contract.
  2. `totalQuantity` is interpreted in base-currency units per IDEALPRO conventions.
  3. Integration-style tests (mock IB) show order construction for Forex without breaking US/HK order tests.
**Plans:** 1/1 plans complete

Plans:
- [x] 07-01-PLAN.md — Forex `place_market_order` integration tests (UC-M1–M3, UC-E1–E3, UC-R1–R2, REGR-01) + Forex qty=0-after-alignment message (IDEALPRO hint)

### Phase 8: Quantity normalization & IB alignment
**Goal**: Lot sizing uses existing ForexNormalizer plus `_align_qty_to_contract` from `ContractDetails` for Forex.
**Depends on**: Phase 7
**Requirements**: EXEC-04
**Success Criteria** (what must be TRUE):
  1. Raw strategy quantities pass through ForexNormalizer integer rules before submission.
  2. `_align_qty_to_contract` adjusts to `sizeIncrement` / broker constraints using qualified Forex contract details.
  3. Tests cover rounding, increment alignment, and parity with existing normalizer behavior.
**Plans:** 2/2 plans executed

Plans:
- [x] 08-01-PLAN.md — ForexNormalizer `normalize` passthrough + type `float`; tests UC-N1–UC-N6; update `1000.7` expectation; REGR-01
- [x] 08-02-PLAN.md — `_align_qty_to_contract` isolated tests UC-A1–UC-A5 (mock IB, cache, `conId=424242`); REGR-01

### Phase 9: Forex trading hours (liquidHours)
**Goal**: Session checks for Forex use IBKR contract trading/liquid hours (24/5), not equity-only assumptions.
**Depends on**: Phase 8
**Requirements**: RUNT-01
**Success Criteria** (what must be TRUE):
  1. `is_market_open` (or equivalent) for Forex reflects `liquidHours` / contract metadata from IBKR.
  2. Weekend and holiday behavior matches IBKR’s Forex schedule, not US equity RTH calendars.
  3. Tests include time-window scenarios (e.g. Fri–Sun boundaries) with mocked hours.
**Plans:** 1/1 plans executed

Plans:
- [x] 09-01-PLAN.md — UC-FX-L01–L09 + UC-FX-I01–I05; Forex closed reason; `TestForexLiquidHours` / `TestForexRTHGate`; RUNT-01

### Phase 10: Fills, position & PnL events
**Goal**: Execution and portfolio events expose Forex positions with correct symbol keys, quantities, and currencies.
**Depends on**: Phase 9
**Requirements**: RUNT-02
**Success Criteria** (what must be TRUE):
  1. Fill and position updates for Forex use stable identifiers consistent with qualified symbols (e.g. `localSymbol` / internal key scheme).
  2. PnL or notional displays use quote/base currency context appropriate to Forex, not equity “shares” assumptions.
  3. Automated tests or harness assertions cover at least one round-trip position lifecycle for Forex mocks.
**Plans:** 1/1 plans complete

Plans:
- [x] 10-01-PLAN.md — DB columns + records (`ibkr_save_position`, `ibkr_get_positions`, `ibkr_save_pnl` fix); `localSymbol` + metadata in callbacks; `get_positions` DB-backed secType/exchange/currency; tests UC-FP1–FP7; RUNT-02

### Phase 11: Strategy automation (Forex + IBKR)
**Goal**: Operators can turn on automated Forex trading via strategy config and IBKR paper/live exchanges; backend integration and paper E2E validate the full chain.
**Depends on**: Phase 10
**Requirements**: RUNT-03
**Success Criteria** (what must be TRUE):
  1. A strategy configured with `market_category=Forex` and `exchange_id` of `ibkr-paper` or `ibkr-live` is accepted by the runner and reaches `IBKRClient` for Forex.
  2. End-to-end integration tests (mocked or recorded IB) prove signal → pending → order for Forex.
  3. Paper trading runbook: at least one liquid pair (e.g. EURUSD) open/close with reconciled fills/positions; **verify** runs all defined use cases plus full existing test suite.
**Plans:** 3/3 plans complete

Plans:
- [x] 11-01-PLAN.md — `validate_exchange_market_category` + strategy save validation + `test_strategy_exchange_validation.py` (UC-SA-VAL-*)
- [x] 11-02-PLAN.md — `test_forex_ibkr_e2e.py` (Flask + worker chain) + `11-PAPER-RUNBOOK.md`
- [x] 11-03-PLAN.md — `test_ibkr_forex_paper_smoke.py` (three pairs, mocked IBKR Paper callbacks)

### Phase 12: Frontend IBKR exchanges for Forex
**Goal**: Strategy authors pick IBKR paper/live for Forex in the UI, not only MT5.
**Depends on**: Phase 11
**Requirements**: FRNT-01
**Success Criteria** (what must be TRUE):
  1. On strategy create/edit, when `market_category` is Forex, the exchange dropdown (or equivalent) lists **ibkr-paper** and **ibkr-live**.
  2. Selecting those options persists and reloads correctly.
  3. UI-level or E2E tests (per project norms) cover Forex + IBKR selection; **verify** includes frontend cases plus full backend regression.
**Plans:** 1/1 plans complete

Plans:
- [x] 12-01-PLAN.md — Forex broker list (MT5 + IBKR paper/live), submit/test/backfill, i18n, Jest guard + pytest regression

## Progress

**Execution order:** 1 → 2 → … → 12 (decimal phases reserved for `/gsd:insert-phase` if needed).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Forex symbol normalization | 1/1 | Complete | 2026-04-09 |
| 2. Forex contract creation (IDEALPRO) | 1/1 | Complete | 2026-04-09 |
| 3. Contract qualification | 1/1 | Complete | 2026-04-09 |
| 4. Market category & worker gate | 1/1 | Complete | 2026-04-10 |
| 5. Signal-to-side mapping (two-way FX) | 1/1 | Complete | 2026-04-10 |
| 6. TIF policy for Forex | 1/1 | Complete | 2026-04-10 |
| 7. Forex market orders | 1/1 | Complete | 2026-04-10 |
| 8. Quantity normalization & IB alignment | 2/2 | Complete | 2026-04-10 |
| 9. Forex trading hours (liquidHours) | 1/1 | Complete | 2026-04-11 |
| 10. Fills, position & PnL events | 1/1 | Complete | 2026-04-11 |
| 11. Strategy automation (Forex + IBKR) | 3/3 | Complete | 2026-04-11 |
| 12. Frontend IBKR exchanges for Forex | 1/1 | Complete | 2026-04-11 |

---
*Roadmap created: 2026-04-09 · Granularity: fine (12 phases) · Coverage: 12/12 v1 requirements*
