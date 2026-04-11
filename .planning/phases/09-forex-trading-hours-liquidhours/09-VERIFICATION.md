---
phase: 09-forex-trading-hours-liquidhours
verified: 2026-04-11T03:55:46Z
status: passed
score: 3/3 must-haves verified
re_verification: false
---

# Phase 9: Forex trading hours (liquidHours) — Verification Report

**Phase goal:** Session checks for Forex use IBKR contract trading/liquid hours (24/5), not equity-only assumptions.

**Verified:** 2026-04-11T03:55:46Z

**Status:** passed

**Re-verification:** No — initial verification (no prior `09-*-VERIFICATION.md` with `gaps:`).

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Forex session open/closed follows `ContractDetails.liquidHours` + `timeZoneId` via `is_rth_check` (not US equity RTH calendars). | ✓ VERIFIED | `is_rth_check` parses `contract_details.liquidHours` and `timeZoneId` in `trading_hours.py` (`parse_liquid_hours`, lines 140–156). `is_market_open` loads details via `reqContractDetailsAsync`, then calls `is_rth_check(details, server_time, …)` in `client.py` (~1038–1047). `TestForexLiquidHours` (UC-FX-L01–L09) and `TestForexRTHGate` (UC-FX-I01–I05) use mocked `liquidHours` strings, not equity calendars. |
| 2 | When Forex `is_market_open` is False, reason includes Forex 24/5 context (weekend/maintenance) distinguishable from equity RTH. | ✓ VERIFIED | `client.py` appends ` — Forex 24/5: closed outside liquid hours (weekend or daily maintenance window).` when `market_type == "Forex"` and `is_rth_check` is False (~1047–1053). `test_UC_FX_I05_forex_closed_message` asserts `"Forex 24/5"` and weekend/maintenance wording. |
| 3 | Unit tests UC-FX-L01–L09 and integration UC-FX-I01–I05 pass; Fri–Sun and holiday scenarios use mocked `liquidHours`. | ✓ VERIFIED | `test_trading_hours.py`: `TestForexLiquidHours` with explicit UC IDs L01–L09 (Fri close, Sat, Sun boundary, maintenance gap, `CLOSED` holiday mix, JST, XAGUSD). `test_ibkr_client.py`: `_make_forex_rth_client` injects `liquidHours`/`timeZoneId` into mocked contract details. Re-ran: `pytest tests/test_trading_hours.py -k Forex` → 9 passed; `pytest tests/test_ibkr_client.py -k ForexRTH` → 5 passed. Full suite reported green (902 passed per phase notes). |

**Score:** 3/3 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `backend_api_python/tests/test_trading_hours.py` | UC-FX-L01–L09; contains `UC-FX-L` | ✓ VERIFIED | `TestForexLiquidHours` with `@pytest.mark.Forex`; nine tests named `test_UC_FX_L0*` with docstrings referencing UC-FX-L01–L09 (~237–329). |
| `backend_api_python/app/services/live_trading/ibkr_trading/client.py` | `is_market_open`; Forex closed reason | ✓ VERIFIED | `is_market_open` at ~995–1065; Forex branch on closed `reason` ~1047–1053. |
| `backend_api_python/tests/test_ibkr_client.py` | `TestForexRTHGate`; UC-FX-I01–I05 | ✓ VERIFIED | `TestForexRTHGate` ~1206–1284; `_make_forex_rth_client` ~184–199; `wraps=_REAL_IS_RTH_CHECK_FN` overrides autouse mock. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `IBKRClient.is_market_open` | `is_rth_check(details, server_time, …)` | `reqContractDetailsAsync` → cache → `is_rth_check` | ✓ WIRED | Async path qualifies contract, fetches details, passes `details` + `server_time` from `reqCurrentTimeAsync`. |
| `tests/test_trading_hours.py` | `trading_hours.is_rth_check` | `_make_details` + `now=` | ✓ WIRED | Direct imports and assertions on `is_rth_check` / `parse_liquid_hours`. |
| `tests/test_ibkr_client.py` (`TestForexRTHGate`) | production `is_rth_check` | `patch(..., wraps=_REAL_IS_RTH_CHECK_FN)` | ✓ WIRED | Real `is_rth_check` runs against mocked `liquidHours` from `reqContractDetailsAsync`. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| **RUNT-01** | `09-01-PLAN.md` `requirements:` | `is_market_open` for Forex uses IBKR `liquidHours` (24/5), not equity-only assumptions | ✓ SATISFIED | End-to-end path uses contract details + `is_rth_check`; REQUIREMENTS.md lists RUNT-01 Phase 9 Complete; unit + integration tests prove behavior with mocked IB-style schedules. |

No additional requirement IDs appear in `09-01-PLAN.md`; **RUNT-01** is fully accounted for. No orphaned phase-9 requirement IDs found in `REQUIREMENTS.md` beyond this mapping.

### ROADMAP Success Criteria

| # | Criterion | Status |
| --- | --------- | ------ |
| 1 | `is_market_open` for Forex reflects `liquidHours` / contract metadata from IBKR | ✓ Met — `is_rth_check` reads `liquidHours` + `timeZoneId`; integration tests mock IBKR details. |
| 2 | Weekend and holiday behavior matches IBKR Forex schedule, not US equity RTH | ✓ Met — tests cover Sat/Sun/Fri boundaries and `CLOSED` segments; logic is schedule-driven, not equity calendar. |
| 3 | Tests include time-window scenarios with mocked hours | ✓ Met — UC-FX-L03–L07 and UC-FX-I01–I02 cover Fri–Sun and holiday-style `CLOSED`. |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
| ---- | ------- | -------- | ------ |
| — | None blocking | — | No `TODO`/`FIXME`/placeholder in verified Forex RTH paths. |

Note: `test_ibkr_client.py` may emit `PytestUnknownMarkWarning` for unrelated `@pytest.mark.integration` (pre-existing); not a phase-9 blocker.

### Human Verification Required

None mandatory for this phase: behavior is covered by deterministic unit and integration tests with mocked `liquidHours`. Optional: confirm wording with operators in a live Gateway session (cosmetic).

### Gaps Summary

None. Phase goal and RUNT-01 are supported by code, tests, and wiring.

---

_Verified: 2026-04-11T03:55:46Z_

_Verifier: Claude (gsd-verifier)_
