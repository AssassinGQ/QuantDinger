---
phase: 21-backtest-correctness
plan: 01
subsystem: strategy-runner
tags: [cross-sectional, execution, no-lookahead, untradable]
requires:
  - phase: 20-built-in-factors-normalization
    provides: normalized factor outputs for ranking signals
provides:
  - signal/execution ledger separation
  - effective-date execution shift enforcement
  - untradable and fallback-aware execution filter chain
affects: [phase-21-tests, backtest-correctness]
tech-stack:
  added: []
  patterns: [execution-policy, deterministic-filter-chain]
key-files:
  created: [backend_api_python/app/services/nq100_sources.py]
  modified:
    - backend_api_python/app/strategies/cross_sectional_signals.py
    - backend_api_python/app/strategies/cross_sectional.py
    - backend_api_python/app/strategies/runners/cross_sectional_runner.py
key-decisions:
  - "Keep no-lookahead enforcement in runner dispatch so strategy signal logic remains pure."
  - "Use strict fallback as default and expose fallback observability metrics for non-strict modes."
patterns-established:
  - "Execution date must always be greater than signal date."
  - "UNTRADABLE buy/sell semantics are explicit status logs, not implicit drops."
requirements-completed: [AUDIT-01, AUDIT-02, AUDIT-03]
duration: 35min
completed: 2026-04-15
---

# Phase 21 Plan 01 Summary

**Cross-sectional runner now enforces T->T+1 (or shifted T+2) execution semantics with explicit untradable and fallback filtering before dispatch.**

## Performance

- **Duration:** 35 min
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added execution-intent ledger fields (`signal_date`, `execution_date`) into cross-sectional signal flow.
- Added centralized execution price resolver supporting `strict|ffill|close|bfill`.
- Added Phase 21 filter chain with `forced_cash_exit`, untradable skip statuses, and fallback metrics.

## Task Commits

1. **Task 1: 信号-执行隔离与执行日期调度** - `a548a2b` (feat)
2. **Task 2: 执行过滤链与 UNTRADABLE 状态机** - `a548a2b` (feat)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.
