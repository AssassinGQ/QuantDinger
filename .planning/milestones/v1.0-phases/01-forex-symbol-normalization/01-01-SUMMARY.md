---
phase: 01-forex-symbol-normalization
plan: 01
subsystem: trading
tags: [forex, ibkr, ib_insync, symbol-parsing, IDEALPRO]

requires:
  - phase: none
    provides: n/a (first phase)
provides:
  - "Forex branch in normalize_symbol → (pair, IDEALPRO, quote_currency)"
  - "parse_symbol auto-detects known Forex pairs via KNOWN_FOREX_PAIRS set"
  - "format_display_symbol renders Forex as dot-separated (EUR.USD)"
  - "KNOWN_FOREX_PAIRS constant with 35+ pairs (majors, crosses, exotics, metals)"
  - "_clean_forex_raw() helper for separator stripping"
affects: [02-forex-contract-creation, 03-signal-routing]

tech-stack:
  added: []
  patterns:
    - "Forex normalize: strip separators → validate 6-char alpha → return (pair, IDEALPRO, pair[3:])"
    - "Known-pairs set for auto-detection in parse_symbol (no heuristic fallback)"
    - "TDD workflow: RED (failing tests first) → GREEN (minimal implementation)"

key-files:
  created:
    - backend_api_python/tests/test_ibkr_symbols.py
  modified:
    - backend_api_python/app/services/live_trading/ibkr_trading/symbols.py

key-decisions:
  - "Use KNOWN_FOREX_PAIRS set for parse_symbol auto-detection (no 6-char-alpha heuristic to avoid stock ticker false positives)"
  - "Accept any valid 6-char alpha in normalize_symbol when market_type=Forex (set only used for auto-detect)"
  - "Forex display format: dot-separated EUR.USD matching IBKR localSymbol convention"

patterns-established:
  - "Forex symbols: 6-char uppercase, separators stripped via _clean_forex_raw()"
  - "IDEALPRO exchange for all Forex/metals pairs"
  - "ValueError on malformed Forex input (never silent fallthrough to Stock)"

requirements-completed: [CONT-02]

duration: 2min
completed: 2026-04-09
---

# Phase 01 Plan 01: Forex Symbol Normalization Summary

**Forex branch in IBKR symbols.py: normalize/parse/display with KNOWN_FOREX_PAIRS set, IDEALPRO exchange, and ValueError on invalid input**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-09T12:21:32Z
- **Completed:** 2026-04-09T12:24:01Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added Forex support to all 3 functions in `symbols.py` (normalize, parse, display)
- 36 dedicated symbol tests covering Forex normalization, separator variants, invalid input, auto-detection, display formatting, and USStock/HShare regression
- Full test suite green: 737 passed, 0 failures, no regressions
- CONT-02 fully addressed: `normalize_symbol("EURUSD", "Forex")` returns `("EURUSD", "IDEALPRO", "USD")`, never falls to Stock default

## Task Commits

Each task was committed atomically:

1. **Task 1: Create test_ibkr_symbols.py (TDD RED)** - `f04b3b7` (test)
2. **Task 2: Implement Forex branches in symbols.py (TDD GREEN)** - `7bcf2d3` (feat)

_TDD workflow: Task 1 created failing Forex tests + passing regression tests; Task 2 implemented Forex branches to make all tests green._

## Files Created/Modified
- `backend_api_python/tests/test_ibkr_symbols.py` - 138 lines: 5 test classes (NormalizeForex, ParseForex, FormatDisplayForex, NormalizeRegression, ParseRegression) with 36 test cases
- `backend_api_python/app/services/live_trading/ibkr_trading/symbols.py` - Extended from 91 to 137 lines: KNOWN_FOREX_PAIRS set, _clean_forex_raw helper, Forex branches in all 3 functions

## Decisions Made
- Used `KNOWN_FOREX_PAIRS` set (35+ pairs) for `parse_symbol` auto-detection — safer than 6-char-alpha heuristic which would false-positive on stock tickers like GOOGLL
- `normalize_symbol` accepts any valid 6-char alpha when `market_type="Forex"` is explicit (doesn't restrict to known set)
- Forex display format: dot-separated `EUR.USD` matching IBKR `localSymbol` convention

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `normalize_symbol` returns correct `(pair, "IDEALPRO", quote_currency)` tuple for Forex
- Phase 2 (contract creation) can now use this tuple to construct `ib_insync.Forex(pair=ib_symbol)` instead of `Stock()`
- `_create_contract` in `client.py` still creates `Stock()` for all market types — Phase 2 will add the Forex contract branch

---
*Phase: 01-forex-symbol-normalization*
*Completed: 2026-04-09*
