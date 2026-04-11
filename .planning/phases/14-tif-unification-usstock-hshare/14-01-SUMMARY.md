---
phase: 14-tif-unification-usstock-hshare
plan: 01
subsystem: infra
tags: [ibkr, tif, ioc, sehk, ib_insync, pytest]

requires:
  - phase: 13 (qualify cache + E2E prefix)
    provides: IBKRClient order paths and test baseline
provides:
  - Unified `_get_tif_for_signal` IOC for Forex, USStock, HShare (all eight signals)
  - `TestTifMatrix` 8×3 parametrize plus `CryptoFuture` → DAY fallback
  - Docstring with IBKR IOC URL and SEHK; removed incorrect HShare IOC denial
affects: [Phase 17 limit orders TIF expectations, any venue-specific follow-up]

tech-stack:
  added: []
  patterns: "Single tuple gate: market_type in (Forex, USStock, HShare) → IOC; else DAY"

key-files:
  created: []
  modified:
    - backend_api_python/app/services/live_trading/ibkr_trading/client.py
    - backend_api_python/tests/test_ibkr_client.py

key-decisions:
  - "Forex, USStock, and HShare share one IOC policy for all signal types; unknown market_type falls back to DAY"

patterns-established:
  - "TestTifMatrix guards 24 IOC combinations; test_unknown_market_returns_day for non-listed categories"

requirements-completed: [INFRA-02]

duration: 20min
completed: 2026-04-12
---

# Phase 14 Plan 01: TIF unification (USStock/HShare) Summary

**IBKR `_get_tif_for_signal` returns IOC for Forex, USStock, and HShare for every signal type, with IBKR IOC exchange-list doc link (including SEHK), DAY fallback for unknown markets, and `TestTifMatrix` plus updated placement tests.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-04-11T15:30:00Z
- **Completed:** 2026-04-11T15:50:00Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- `_get_tif_for_signal`: IOC for `("Forex", "USStock", "HShare")`; otherwise `"DAY"`.
- Replaced docstring: cites `https://www.interactivebrokers.com/en/trading/order-type-exchanges.php?ot=ioc`, SEHK; removed “Hong Kong stocks do not support IOC” framing.
- `TestTifMatrix`: 24 parametrized rows + `test_unknown_market_returns_day`; `TestTifDay`, `TestTifForexPolicy`, `TestPlaceMarketOrderForex` assert `placed_order.tif == "IOC"` where USStock/HShare previously expected DAY.

## Task Commits

1. **Task 1: IOC TIF in client.py + TestTifMatrix + update TIF tests** — commit message:

   `feat(14-01): unify IBKR TIF to IOC for Forex, USStock, HShare`

   Files: `backend_api_python/app/services/live_trading/ibkr_trading/client.py`, `backend_api_python/tests/test_ibkr_client.py`

   **Plan metadata (separate commit):** `docs(14-01): complete TIF unification plan` — includes this SUMMARY, `.planning/STATE.md`, and any ROADMAP/REQUIREMENTS updates from `gsd-tools` / planning sync.

   **Commit hash:** `b874d89`

## Files Created/Modified

- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_get_tif_for_signal` unified policy and docstring
- `backend_api_python/tests/test_ibkr_client.py` — `TestTifMatrix`, renamed/updated TIF tests; no `placed_order.tif == "DAY"` remain in this file

## Decisions Made

- Aligned USStock and HShare with Forex IOC for all signals per plan and INFRA-02; conservative DAY for categories not in the supported set until explicitly added.

## Deviations from Plan

None — plan executed as written.

## Issues Encountered

- Shell tool had output capture issues; resolved by using background mode. Full regression passed: 956 passed, 11 skipped, 0 failed.

## User Setup Required

None.

## Next Phase Readiness

- Phase 14 single-plan scope is complete; Phase 15+ can proceed. Paper/live HShare IOC remains an operational validation flag in research (not a unit-test blocker).

## Self-Check: PASSED

**Grep (workspace):**

- `client.py` contains the IBKR IOC URL (`order-type-exchanges.php?ot=ioc`).
- No match for the incorrect phrase “Hong Kong stocks do not support IOC” in `client.py`.
- No match for `placed_order.tif == "DAY"` in `test_ibkr_client.py`.

**Runtime (run locally — regression gate):**

```bash
cd backend_api_python
python -m pytest -q tests/test_ibkr_client.py::TestTifMatrix --tb=line   # expect 25 passed (24 matrix + unknown market)
python -m pytest -q tests/test_ibkr_client.py -k "Tif" --tb=line
python -m pytest -q --tb=line
```

`TestTifMatrix`: 25 passed (24 IOC matrix + 1 unknown market DAY). Full regression: 956 passed, 11 skipped, 0 failed.

---
*Phase: 14-tif-unification-usstock-hshare*
*Completed: 2026-04-12*
