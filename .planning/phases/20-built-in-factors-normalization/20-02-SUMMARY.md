---
phase: 20-built-in-factors-normalization
plan: 02
subsystem: api
tags: [factor, registry, panel]
requires:
  - phase: 20-01
    provides: normalize config and pipeline
provides:
  - Built-in factor v1 registry (11 factors)
  - core factor pure functions
  - build_factor_panels panel constructor
affects: [phase-22, phase-23, phase-24]
tech-stack:
  added: []
  patterns: [registry-plus-pure-function-api, panel-first-timeseries]
key-files:
  created:
    - backend_api_python/app/factors/core.py
    - backend_api_python/app/factors/factor_defs.py
    - backend_api_python/app/factors/panel.py
    - backend_api_python/tests/test_factor_library.py
    - backend_api_python/tests/fixtures/factor_panel_fixture.csv
  modified:
    - backend_api_python/app/factors/__init__.py
key-decisions:
  - "MOM_12M_SKIP_1M 固定为 pct_change(252) - pct_change(21)"
  - "reversal 固定为 -pct_change(window) 与 mom 同窗相反"
patterns-established:
  - "注册表统一管理内置因子名与默认窗口参数"
requirements-completed: [FACTOR-01]
duration: 15min
completed: 2026-04-15
---

# Phase 20 Plan 02 Summary

**完成了内置因子库 v1（11 因子）与面板构建器，形成注册表 + 纯函数双 API。**

## Performance

- **Duration:** 15 min
- **Started:** 2026-04-15T06:18:00Z
- **Completed:** 2026-04-15T06:33:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- 实现 `mom/mom_skip/reversal/volatility/sharpe/sortino`
- 实现 `FactorSpec`、`get_builtin_factor_specs`、`compute_factor_by_name`
- 实现 `build_factor_panels` 并补齐 fixture 与 FACTOR-01 测试矩阵

## Task Commits

1. **Task 1** - N/A（本次为重执行校验，未拆分原子 commit）
2. **Task 2** - N/A（本次为重执行校验，未拆分原子 commit）

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 22/23/24 可直接引用因子注册表与面板构建结果。
