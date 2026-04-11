---
phase: 10-fills-position-pnl-events
verified: 2026-04-11T12:00:00Z
status: passed
score: 4/4 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Paper TWS/Gateway: open a small Forex position and confirm API/UI rows match TWS for symbol label, size, and currency"
    expected: "DB-backed get_positions shows EUR.USD-style symbol, CASH/IDEALPRO, and expected currency; quantities align with IBKR"
    why_human: "Mocks prove wiring; live venue confirms pricing/currency edge cases noted in phase research"
---

# Phase 10: Fills, position & PnL events — Verification Report

**Phase goal:** Execution and portfolio events expose Forex positions with correct symbol keys, quantities, and currencies.

**Verified:** 2026-04-11T12:00:00Z

**Status:** passed

**Re-verification:** No — initial verification (no prior `10-VERIFICATION.md`).

## Goal Achievement

### Observable truths (from `10-01-PLAN.md` `must_haves.truths`)

| # | Truth | Status | Evidence |
|---|--------|--------|----------|
| 1 | Forex position/portfolio callbacks persist symbol label `EUR.USD` (`localSymbol`), not base `EUR` alone | ✓ VERIFIED | `_contract_symbol_label` prefers non-empty `localSymbol` over `symbol`; `_on_position` / `_on_update_portfolio` set `_conid_to_symbol[conId]` and pass `symbol=label` plus `sec_type`/`exchange`/`currency` to `ibkr_save_position` (`client.py` ~34–42, 611–674). UC-FP1, UC-FP2 assert `EUR.USD` and CASH/IDEALPRO/USD. |
| 2 | `get_positions()` returns `secType`/`exchange`/`currency` from DB for Forex rows (CASH, IDEALPRO, USD), not hardcoded STK/SMART/USD when columns populated | ✓ VERIFIED | `ibkr_get_positions` SELECT includes `sec_type`, `exchange`, `currency`; `get_positions` maps `row.get("sec_*")` to camelCase with fallbacks only when blank (`records.py` ~671–677, `client.py` ~1353–1367). UC-FP4, UC-FP7 assert CASH/IDEALPRO/USD. |
| 3 | `ibkr_save_pnl(account, daily_pnl, unrealized_pnl, realized_pnl)` runs without NameError when DB is mocked | ✓ VERIFIED | `ibkr_save_pnl` only clamps four floats and inserts into `qd_ibkr_pnl` — no undefined locals (`records.py` ~553–585). `test_uc_fp6_ibkr_save_pnl_runs_without_nameerror` exercises real function body. |
| 4 | Automated tests cover UC-FP7 Forex round-trip plus stock regression UC-FP5 | ✓ VERIFIED | `test_uc_fp7_forex_round_trip_position_pnl_get_positions`, `test_uc_fp5_get_positions_stock_regression` in `test_ibkr_client.py`; UC-FP6/UC-SCHEMA in `test_live_trading_records_ibkr.py`. `pytest -k "FP or ForexFillsPosition or ForexPositionPnL or uc_fp"`: 7 passed. |

**Score:** 4/4 truths verified.

### Required artifacts (PLAN `must_haves.artifacts`)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend_api_python/app/services/live_trading/records.py` | Schema ALTER; `ibkr_save_position` / `ibkr_get_positions`; `ibkr_save_pnl` without dead clamps | ✓ VERIFIED | ALTERs for `sec_type`/`exchange`/`currency` (~60–68); INSERT/ON CONFLICT with COALESCE for metadata (~607–624); SELECT returns metadata (~671–677). `ibkr_save_pnl` has no stray `position`/`avg_cost` clamps. |
| `backend_api_python/app/services/live_trading/ibkr_trading/client.py` | `localSymbol`-or-symbol map; metadata into saves; `get_positions` fallbacks | ✓ VERIFIED | `_contract_symbol_label`; callbacks wired to `records.ibkr_save_position` with metadata; `get_positions` reads DB fields. |
| `backend_api_python/tests/test_live_trading_records_ibkr.py` | UC-FP6 real `ibkr_save_pnl`; UC-SCHEMA | ✓ VERIFIED | File exists; tests call real `ibkr_save_pnl` / `ibkr_save_position` with mocks. |
| `backend_api_python/tests/test_ibkr_client.py` | UC-FP1–FP5, FP7 | ✓ VERIFIED | `TestForexFillsPositionPnLCallbacks`, `TestForexPositionPnLEvents`, UC-FP4/FP5 cases present and substantive. |

**Wiring:** `records` imported and used from `client.py`; tests patch `records.*` and assert call shapes — not orphaned.

### Key link verification (PLAN `must_haves.key_links`)

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `_on_position` / `_on_update_portfolio` | `records.ibkr_save_position` | Keyword args `sec_type`, `exchange`, `currency` | ✓ WIRED | `ibkr_save_position(..., sec_type=_contract_str_field(...), ...)` at ~629–635, ~668–674 |
| `records.ibkr_get_positions` | `client.get_positions` | `row.get("sec_type")` etc. | ✓ WIRED | `_query` returns `ibkr_get_positions`; loop uses `sec_type`/`exchange`/`currency` (~1340–1362) |

Note: `_on_pnl_single` calls `ibkr_save_position` without `sec_type`/`exchange`/`currency`; upsert COALESCE preserves metadata from earlier position/portfolio saves — consistent with design.

### Requirements coverage

| Requirement | Source plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| **RUNT-02** | `10-01-PLAN.md` (`requirements: [RUNT-02]`) | 成交/仓位/PnL 事件回调正确处理 Forex（symbol key、数量、币种） | ✓ SATISFIED | IBKR **position** / **updatePortfolio** / **pnlSingle** paths persist `localSymbol`-style keys and contract metadata; `get_positions` exposes them. `ibkr_save_pnl` account-level aggregate fixed. |

**Cross-check:** Only `RUNT-02` declared in PLAN frontmatter — **no orphaned requirement IDs** for this plan.

**Scope note (not a failing gap):** Order **fill** handling (`_handle_fill`) uses `IBKROrderContext.symbol` from placement (e.g. strategy `EURUSD`), not IBKR `localSymbol`. Phase 10 tests and code focus on portfolio/PnL IBKR events and DB snapshot API, matching `10-01-PLAN` and phase research. If product requires a single canonical key across **order notifications** and **portfolio rows**, that would be a follow-up.

### Anti-patterns found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| — | — | — | No TODO/FIXME/placeholder in touched production paths for this phase |

### Human verification required

See YAML frontmatter — optional live paper check for parity with TWS.

### Gaps summary

None. Phase goal and PLAN `must_haves` are met by the codebase; RUNT-02 is substantively implemented for IBKR position/portfolio/PnL-single and `get_positions` semantics.

---

_Verified: 2026-04-11T12:00:00Z_

_Verifier: Claude (gsd-verifier)_
