---
phase: 16-precious-metals-contract-classification
plan: 01
subsystem: api
tags: [ibkr, symbols, metals, cmdty, smart, forex, pytest]

requires:
  - phase: 13-qualify-result-caching-e2e-prefix-fix
    provides: qualify cache and stable API prefixes for downstream trading paths
provides:
  - "_is_precious_metal_pair + parse_symbol Metals branch before KNOWN_FOREX_PAIRS"
  - "normalize_symbol(Metals) → (full pair, SMART, quote ccy) for CMDTY-style contracts"
  - "format_display_symbol preserves six-letter XAU/XAG on SMART"
  - "UC-16-T1-01..10 pytest coverage"
affects:
  - "16-02-PLAN (IBKR client CMDTY branch)"
  - "callers that infer market_type from parse_symbol (now Metals for XAU*/XAG*)"

tech-stack:
  added: []
  patterns:
    - "Precious metals detected before Forex set membership; XAUEUR explicitly excluded from Metals"

key-files:
  created: []
  modified:
    - backend_api_python/app/services/live_trading/ibkr_trading/symbols.py
    - backend_api_python/tests/test_ibkr_symbols.py

key-decisions:
  - "XAUEUR falls through to USStock (not Metals, not KNOWN_FOREX) per paper qualify research."
  - "Metals normalize returns full six-letter pair as ib_symbol with exchange SMART and quote = last three letters."

patterns-established:
  - "parse_symbol: HK → digits → precious metal pair → KNOWN_FOREX → default USStock"

requirements-completed: []

duration: 12min
completed: 2026-04-12
---

# Phase 16 Plan 01: Precious metals symbol classification Summary

**IBKR symbol layer routes validated XAU*/XAG* six-letter pairs to `Metals`, drops them from `KNOWN_FOREX_PAIRS`, and normalizes `Metals` to SMART + full pair for CMDTY-oriented contract building in 16-02.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-04-12T00:00:00Z (approx.)
- **Completed:** 2026-04-12T00:12:00Z (approx.)
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- `parse_symbol` returns `Metals` for `_is_precious_metal_pair` matches before `KNOWN_FOREX_PAIRS`.
- `normalize_symbol(..., "Metals")` validates like Forex cleaning rules with Metals-specific `ValueError` text.
- `format_display_symbol` leaves `XAUUSD`/`XAGUSD`-style SMART symbols undotted.
- Ten UC-named tests `test_uc_16_t1_01` … `test_uc_16_t1_10` cover the merged UC table.

## Task Commits

1. **Task 1: symbols.py + test_ibkr_symbols.py — precious metals detection, Metals normalize_symbol, and UC tests** - `5f9a99a` (feat)

**Plan metadata:** docs commit on `main` titled `docs(16-01): complete precious metals symbol classification plan`

## Files Created/Modified

- `backend_api_python/app/services/live_trading/ibkr_trading/symbols.py` — `_is_precious_metal_pair`, `Metals` branches, `KNOWN_FOREX` cleanup, SMART display for metals.
- `backend_api_python/tests/test_ibkr_symbols.py` — `TestPreciousMetalsSymbolUcs`, Forex parametrize uses `USDCAD` instead of `XAUUSD`, `test_metals_detected_as_metals`.

## Decisions Made

- **TRADE-04:** Requirement spans full Phase 16 (symbol + client + validation). This plan completes the **symbol gate** only; `REQUIREMENTS.md` TRADE-04 checkbox left open until 16-02/16-03 satisfy contract creation and routing end-to-end.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- 16-02 can consume `normalize_symbol(..., "Metals")` outputs for `Contract(secType=CMDTY, ...)` construction.

## Self-Check: PASSED

- `backend_api_python/app/services/live_trading/ibkr_trading/symbols.py` exists.
- `backend_api_python/tests/test_ibkr_symbols.py` exists.
- Commit `5f9a99a` present in history.
- `pytest tests/test_ibkr_symbols.py -q` exits 0.

---
*Phase: 16-precious-metals-contract-classification*
*Completed: 2026-04-12*
