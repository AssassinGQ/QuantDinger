# Roadmap: QuantDinger IBKR Forex (IDEALPRO)

## Overview

This milestone extends the existing IBKR stack from US stocks and HK shares to IDEALPRO spot Forex. Work proceeds in dependency order: normalize symbols and build correct Forex contracts, open routing and execution policy (signal sides, TIF), deliver market orders with aligned quantities, then runtime behavior (hours, callbacks), strategy-driven automation, and finally frontend exchange selection. **Verification strategy (from config):** use-case-driven — each phase plan defines concrete use cases and test specs; implementation includes test code; verify runs **all** use cases including existing suite regressions.

**Suggested engineering sequence (research):** symbols → contract → qualification → category gate → signal mapping → TIF → market order + qty → RTH → callbacks → strategy config → integration/E2E paper → frontend.

## Phases

- [ ] **Phase 1: Forex symbol normalization** — Parse EURUSD / EUR.USD / EUR/USD to base+quote without equity mis-routing
- [ ] **Phase 2: Forex contract creation (IDEALPRO)** — `Forex` contracts with CASH + IDEALPRO from `market_type=Forex`
- [ ] **Phase 3: Contract qualification** — `qualifyContracts` resolves conId, localSymbol for Forex
- [ ] **Phase 4: Market category & worker gate** — `supported_market_categories` + PendingOrderWorker validation for Forex
- [ ] **Phase 5: Signal-to-side mapping (two-way FX)** — Long/short-style signals map to BUY/SELL for Forex
- [ ] **Phase 6: TIF policy for Forex** — `_get_tif_for_signal` Forex branch (DAY/IOC/GTC per paper validation)
- [ ] **Phase 7: Forex market orders** — `place_market_order` for Forex with base-currency `totalQuantity`
- [ ] **Phase 8: Quantity normalization & IB alignment** — ForexNormalizer + `_align_qty_to_contract` on Forex path
- [ ] **Phase 9: Forex trading hours (liquidHours)** — `is_market_open` uses IBKR contract hours for 24/5 FX
- [ ] **Phase 10: Fills, position & PnL events** — Callbacks and keys correct for Forex symbols and currencies
- [ ] **Phase 11: Strategy automation (Forex + IBKR)** — Config `market_category=Forex` + ibkr-paper/live drives auto-trade
- [ ] **Phase 12: Frontend IBKR exchanges for Forex** — Strategy UI offers ibkr-paper / ibkr-live when Forex is selected

## Phase Details

### Phase 1: Forex symbol normalization
**Goal**: All supported Forex symbol spellings resolve to a single internal base+quote representation so downstream code never defaults Forex to US `Stock`.
**Depends on**: Nothing (first phase)
**Requirements**: CONT-02
**Success Criteria** (what must be TRUE):
  1. Inputs like `EURUSD`, `EUR.USD`, and `EUR/USD` normalize to the same canonical base and quote the rest of the stack can consume.
  2. When the caller indicates Forex (or equivalent routing context), symbol handling does not silently treat the symbol as a US equity ticker.
  3. Automated tests document and lock accepted formats and edge cases (uppercase, separators).
**Plans**: TBD

Plans:
- [ ] 01-01: Use cases + test specs for symbol formats; implement `normalize_symbol` Forex branch; run full existing test suite plus new cases

### Phase 2: Forex contract creation (IDEALPRO)
**Goal**: `IBKRClient` builds `ib_insync.Forex` with IDEALPRO routing for Forex execution, not `Stock`/`SMART`.
**Depends on**: Phase 1
**Requirements**: CONT-01
**Success Criteria** (what must be TRUE):
  1. For `market_type`/`market_category` Forex, `_create_contract` returns a Forex contract with `secType=CASH` and `exchange=IDEALPRO` (via ib_insync conventions).
  2. USStock and HShare contract creation remain unchanged for non-Forex paths.
  3. Unit tests assert contract fields for representative pairs (e.g. EURUSD).
**Plans**: TBD

Plans:
- [ ] 02-01: Use cases for contract creation; implement `_create_contract` Forex branch; regression on US/HK

### Phase 3: Contract qualification
**Goal**: Forex contracts qualify like equities: stable `conId`, `localSymbol`, and details for sizing and display.
**Depends on**: Phase 2
**Requirements**: CONT-03
**Success Criteria** (what must be TRUE):
  1. After `qualifyContracts` (or async equivalent), Forex contracts carry a valid `conId` and IB-expected `localSymbol` (e.g. `EUR.USD`).
  2. Qualification failure surfaces as a clear error; the system does not proceed with an unqualified Forex contract.
  3. Tests mock or record qualification outcomes for at least one liquid pair.
**Plans**: TBD

Plans:
- [ ] 03-01: Qualification use cases; wire qualify path for Forex; tests for success/failure

### Phase 4: Market category & worker gate
**Goal**: The runner and pending-order pipeline accept Forex as a first-class market category end-to-end.
**Depends on**: Phase 3
**Requirements**: CONT-04
**Success Criteria** (what must be TRUE):
  1. `IBKRClient.supported_market_categories` includes `"Forex"`.
  2. `PendingOrderWorker.validate_market_category` (or equivalent) allows Forex alongside existing categories.
  3. A Forex-marked signal is not rejected solely for category when other validations pass.
**Plans**: TBD

Plans:
- [ ] 04-01: Category list + worker validation use cases; tests covering accept/reject paths

### Phase 5: Signal-to-side mapping (two-way FX)
**Goal**: Strategy signal semantics for Forex map to correct IB BUY/SELL including short-style flows.
**Depends on**: Phase 4
**Requirements**: EXEC-02
**Success Criteria** (what must be TRUE):
  1. `open_long` → BUY, `close_long` → SELL, `open_short` → SELL, `close_short` → BUY for Forex (per project conventions).
  2. Forex no longer fails purely because “short” is disallowed as on single-stock equity assumptions.
  3. Table-driven tests cover all four signal types for `market_category=Forex`.
**Plans**: TBD

Plans:
- [ ] 05-01: Signal→side matrix use cases; implement `map_signal_to_side` Forex branch; full regression

### Phase 6: TIF policy for Forex
**Goal**: Time-in-force for Forex market orders matches IBKR behavior validated in paper (open vs close; DAY vs IOC vs GTC as decided).
**Depends on**: Phase 5
**Requirements**: EXEC-03
**Success Criteria** (what must be TRUE):
  1. `_get_tif_for_signal` applies a documented Forex-specific policy distinct from equity where needed.
  2. Submitted orders carry the TIF chosen by that policy for open and close scenarios.
  3. Tests encode the policy; paper trading notes document any IOC/DAY fallback (per research).
**Plans**: TBD

Plans:
- [ ] 06-01: TIF matrix use cases; paper validation checklist; implement branch; tests

### Phase 7: Forex market orders
**Goal**: Market orders for Forex submit through the same client surface as equities with correct `MarketOrder` + quantity.
**Depends on**: Phase 6
**Requirements**: EXEC-01
**Success Criteria** (what must be TRUE):
  1. `place_market_order` successfully submits a market order for a qualified Forex contract.
  2. `totalQuantity` is interpreted in base-currency units per IDEALPRO conventions.
  3. Integration-style tests (mock IB) show order construction for Forex without breaking US/HK order tests.
**Plans**: TBD

Plans:
- [ ] 07-01: Place-order use cases; implement Forex path; expand `test_ibkr_client` / exchange tests

### Phase 8: Quantity normalization & IB alignment
**Goal**: Lot sizing uses existing ForexNormalizer plus `_align_qty_to_contract` from `ContractDetails` for Forex.
**Depends on**: Phase 7
**Requirements**: EXEC-04
**Success Criteria** (what must be TRUE):
  1. Raw strategy quantities pass through ForexNormalizer integer rules before submission.
  2. `_align_qty_to_contract` adjusts to `sizeIncrement` / broker constraints using qualified Forex contract details.
  3. Tests cover rounding, increment alignment, and parity with existing normalizer behavior.
**Plans**: TBD

Plans:
- [ ] 08-01: Sizing use cases with mock `ContractDetails`; tests; no regression on US/HK qty paths

### Phase 9: Forex trading hours (liquidHours)
**Goal**: Session checks for Forex use IBKR contract trading/liquid hours (24/5), not equity-only assumptions.
**Depends on**: Phase 8
**Requirements**: RUNT-01
**Success Criteria** (what must be TRUE):
  1. `is_market_open` (or equivalent) for Forex reflects `liquidHours` / contract metadata from IBKR.
  2. Weekend and holiday behavior matches IBKR’s Forex schedule, not US equity RTH calendars.
  3. Tests include time-window scenarios (e.g. Fri–Sun boundaries) with mocked hours.
**Plans**: TBD

Plans:
- [ ] 09-01: Hours use cases; implement Forex branch; tests

### Phase 10: Fills, position & PnL events
**Goal**: Execution and portfolio events expose Forex positions with correct symbol keys, quantities, and currencies.
**Depends on**: Phase 9
**Requirements**: RUNT-02
**Success Criteria** (what must be TRUE):
  1. Fill and position updates for Forex use stable identifiers consistent with qualified symbols (e.g. `localSymbol` / internal key scheme).
  2. PnL or notional displays use quote/base currency context appropriate to Forex, not equity “shares” assumptions.
  3. Automated tests or harness assertions cover at least one round-trip position lifecycle for Forex mocks.
**Plans**: TBD

Plans:
- [ ] 10-01: Event/callback use cases; implement parity fixes; tests + existing callback suite

### Phase 11: Strategy automation (Forex + IBKR)
**Goal**: Operators can turn on automated Forex trading via strategy config and IBKR paper/live exchanges; backend integration and paper E2E validate the full chain.
**Depends on**: Phase 10
**Requirements**: RUNT-03
**Success Criteria** (what must be TRUE):
  1. A strategy configured with `market_category=Forex` and `exchange_id` of `ibkr-paper` or `ibkr-live` is accepted by the runner and reaches `IBKRClient` for Forex.
  2. End-to-end integration tests (mocked or recorded IB) prove signal → pending → order for Forex.
  3. Paper trading runbook: at least one liquid pair (e.g. EURUSD) open/close with reconciled fills/positions; **verify** runs all defined use cases plus full existing test suite.
**Plans**: TBD

Plans:
- [ ] 11-01: Config + runner wiring use cases; integration test suite; paper E2E checklist; run-all verification

### Phase 12: Frontend IBKR exchanges for Forex
**Goal**: Strategy authors pick IBKR paper/live for Forex in the UI, not only MT5.
**Depends on**: Phase 11
**Requirements**: FRNT-01
**Success Criteria** (what must be TRUE):
  1. On strategy create/edit, when `market_category` is Forex, the exchange dropdown (or equivalent) lists **ibkr-paper** and **ibkr-live**.
  2. Selecting those options persists and reloads correctly.
  3. UI-level or E2E tests (per project norms) cover Forex + IBKR selection; **verify** includes frontend cases plus full backend regression.
**Plans**: TBD

Plans:
- [ ] 12-01: UI use cases; implement exchange list branch for Forex; tests

## Progress

**Execution order:** 1 → 2 → … → 12 (decimal phases reserved for `/gsd:insert-phase` if needed).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Forex symbol normalization | 0/1 | Not started | - |
| 2. Forex contract creation (IDEALPRO) | 0/1 | Not started | - |
| 3. Contract qualification | 0/1 | Not started | - |
| 4. Market category & worker gate | 0/1 | Not started | - |
| 5. Signal-to-side mapping (two-way FX) | 0/1 | Not started | - |
| 6. TIF policy for Forex | 0/1 | Not started | - |
| 7. Forex market orders | 0/1 | Not started | - |
| 8. Quantity normalization & IB alignment | 0/1 | Not started | - |
| 9. Forex trading hours (liquidHours) | 0/1 | Not started | - |
| 10. Fills, position & PnL events | 0/1 | Not started | - |
| 11. Strategy automation (Forex + IBKR) | 0/1 | Not started | - |
| 12. Frontend IBKR exchanges for Forex | 0/1 | Not started | - |

---
*Roadmap created: 2026-04-09 · Granularity: fine (12 phases) · Coverage: 12/12 v1 requirements*
