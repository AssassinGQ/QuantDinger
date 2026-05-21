---
phase: 24-nq100-strategy-type
plan: 04
subsystem: strategies/runners
tags: [STRAT-02, force_exit_symbols, backtest_total_loss, D-14, D-15, D-16]
dependencies:
  requires: [24-03]
  provides: [DelistingPolicyFilter.force_exit_override, execution_mode_context]
  affects: [cross_sectional_runner.py, cross_sectional_filter_chain.py]
tech_stack:
  added: [execution_mode flag, force_exit_symbols override, total_loss_assumption]
  patterns: [TDD, filter_chain, metadata_passthrough]
key_files:
  created: []
  modified:
    - backend_api_python/app/strategies/runners/cross_sectional_filter_chain.py
    - backend_api_python/tests/test_delisting_policy_filter.py
decisions:
  - D-14: Live trading immediate exit for force_exit_symbols (bypass policy)
  - D-15: Backtest total loss assumption (execution_price=0.0)
  - D-16: Manual marking via trading_config.force_exit_symbols
metrics:
  duration: 8min
  tasks: 2
  files: 2
  tests_added: 11
  tests_total: 27
  commit: 7668c9d
---

# Phase 24 Plan 04: Force Exit Override + Backtest Total Loss

**One-liner:** Implemented STRAT-02 special case handling: force_exit_symbols override (D-14/D-16) and backtest total loss assumption (D-15) for bankruptcy/fraud risk cases.

## Summary

Extended `DelistingPolicyFilter` to handle special cases where symbols need immediate forced exit:

1. **force_exit_symbols override (D-14/D-16):** Manual marking for bankruptcy/fraud/delisting risk
   - Bypasses all delisting_policy timing modes
   - Case-insensitive symbol matching
   - Passed via signal metadata from Runner

2. **Backtest total loss assumption (D-15):** Conservative approach for special cases
   - `execution_price=0.0` when execution_mode="backtest" + force_exit_symbols
   - Live trading uses actual execution price (ExecutionPriceFilter handles)
   - execution_mode defaults to "live" when not specified

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| force_exit_set normalization | Case-insensitive O(1) lookup | Implemented |
| execution_mode default "live" | Conservative default (actual price) | Implemented |
| Total loss only for force_exit | Normal delisting uses market price | Implemented |

## Implementation Details

### Task 1: Force Exit Override (D-14/D-16)

Added at top of `DelistingPolicyFilter.apply()`:
- Extract `force_exit_symbols` from signal metadata
- Normalize to uppercase set for case-insensitive matching
- If symbol in set: return immediate `forced_sell` with `force_exit_reason="manual_force_exit"`
- Bypass all delisting_policy timing logic

### Task 2: Backtest Total Loss (D-15)

Extended force_exit handling with execution_mode check:
- `execution_mode="backtest"`: Set `execution_price=0.0`, `price_source="total_loss_assumption"`
- `execution_mode="live"`: Don't set execution_price (ExecutionPriceFilter handles)
- Normal delisting events (not in force_exit_symbols) always use market_row price

## Deviations from Plan

None - plan executed exactly as written.

## Test Coverage

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestForceExitSymbols | 6 | D-14/D-16 override logic |
| TestBacktestTotalLoss | 5 | D-15 total loss assumption |
| Existing tests | 16 | Plan 03 functionality |

**Total: 27 tests passing**

### New Tests Added

- `test_force_exit_symbols_immediate_sell`: Override triggers forced_sell
- `test_force_exit_symbols_override_delisting_policy_mode`: Override bypasses hold_until_signal_exit
- `test_force_exit_symbols_empty_list_normal_logic`: Empty list fallback
- `test_force_exit_symbols_symbol_not_in_list`: Symbol not in list fallback
- `test_force_exit_symbols_from_signal_metadata`: Metadata passthrough
- `test_force_exit_symbols_case_insensitive`: Case normalization
- `test_backtest_force_exit_total_loss`: D-15 total loss
- `test_live_force_exit_actual_price`: D-14 live uses actual price
- `test_backtest_normal_delisting_market_price`: Normal delisting uses market
- `test_execution_mode_default_live`: Default behavior
- `test_backtest_total_loss_log_status`: Log status indicator

## Verification Results

```bash
pytest tests/test_delisting_policy_filter.py -v
# 27 passed in 0.11s

pytest tests/ -v --tb=short
# 1325 passed, 11 skipped, 1 warning in 256.11s
```

## Known Stubs

None - implementation complete.

## Threat Flags

None - existing mitigations cover force_exit_symbols validation (T-24-04 in Plan 02).

## Self-Check: PASSED

- [x] Files created: None (all modifications)
- [x] Files modified: cross_sectional_filter_chain.py, test_delisting_policy_filter.py
- [x] Commit exists: 7668c9d
- [x] Tests pass: 27/27 specific, 1325/1325 full suite

---
*Completed: 2026-05-20*
*Executor: parallel worktree agent*