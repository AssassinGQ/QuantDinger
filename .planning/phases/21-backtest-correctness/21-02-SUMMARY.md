---
phase: 21-backtest-correctness
plan: 02
subsystem: testing
tags: [pytest, fixtures, determinism, verification-gate]
requires:
  - phase: 21-backtest-correctness
    provides: execution semantics implementation from plan 01
provides:
  - phase21 blocking regression matrix
  - deterministic local fixtures for gray-area scenarios
  - fallback observability and no-lookahead gates in CI tests
affects: [verification, regression-gate]
tech-stack:
  added: []
  patterns: [fixture-first-testing, deterministic-hash-gate]
key-files:
  created:
    - backend_api_python/tests/test_backtest_correctness_phase21.py
    - backend_api_python/tests/fixtures/phase21/prices.csv
    - backend_api_python/tests/fixtures/phase21/prices_with_invalid_open.csv
    - backend_api_python/tests/fixtures/phase21/corp_actions.json
    - backend_api_python/tests/fixtures/phase21/halts.csv
    - backend_api_python/tests/fixtures/phase21/ic_effective_dates.csv
    - backend_api_python/tests/fixtures/phase21/market_calendar.csv
    - backend_api_python/tests/fixtures/phase21/target_weights.json
    - backend_api_python/tests/fixtures/phase21/tradability_timeline.csv
    - backend_api_python/tests/fixtures/phase21/mna_cash_events.json
  modified: []
key-decisions:
  - "All phase21 scenarios are fixture-backed and fully local (no network reads)."
  - "Determinism is enforced by hashing execution outputs across repeated runs."
patterns-established:
  - "Phase-level correctness must assert state transitions and execution logs, not only final PnL."
requirements-completed: [AUDIT-01, AUDIT-02, AUDIT-03]
duration: 25min
completed: 2026-04-15
---

# Phase 21 Plan 02 Summary

**Phase 21 now has a deterministic, blocking correctness matrix that covers no-lookahead, untradable semantics, cash M&A forced exits, and effective-date schedule shifts.**

## Performance

- **Duration:** 25 min
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Added 8 dedicated phase21 regression tests with required names and assertions.
- Added all 9 required phase21 fixture files under `tests/fixtures/phase21/`.
- Verified determinism and fallback metrics (`fallback_count_total`, `fallback_rate`) in automated tests.

## Task Commits

1. **Task 1: 落地 7 个灰度场景测试矩阵** - `8176144` (test)
2. **Task 2: 固化 fixture 与 determinism 门禁** - `8176144` (test)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Full `pytest tests/ -q` initially failed due backward-compat behavior in runner dispatch.  
Resolved by adding a metadata-absence passthrough path; all regressions are now green.
