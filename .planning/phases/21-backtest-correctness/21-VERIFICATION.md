---
phase: 21-backtest-correctness
status: passed
verified_at: 2026-04-15T08:33:17Z
requirements:
  - AUDIT-01
  - AUDIT-02
  - AUDIT-03
---

# Phase 21 Verification Plan

## Must-Have Coverage

- AUDIT-01：退市样本历史保留，历史行不可因当期成分变化被移除。
- AUDIT-02：信号/执行严格隔离，T 日信号仅能在 T+1（或顺延后）成交，禁止同 bar lookahead。
- AUDIT-03：不可交易语义固定为“买失败留现金、卖失败继续持有”，并覆盖恢复交易周期与 cash M&A 例外。

## Gray-Case Full Matrix (Blocking)

1. `test_no_lookahead_gate`
2. `test_fallback_policy`
3. `test_untradable_filters`
4. `test_cash_substitution_no_replacement`
5. `test_sell_hold_and_resume_cycle`
6. `test_cash_mna_forced_exit`
7. `test_ic_effective_date_shift`
8. `test_determinism_gate`

## Blocking Verify Commands

1. `cd backend_api_python && pytest tests/test_backtest_correctness_phase21.py -q`
2. `cd backend_api_python && pytest tests/ -q`

## CI Must Fail If Any Violation

- 出现 `trade_date <= signal_date`
- 历史退市行缺失
- 不可买入场景出现候补替代买入
- 不可卖出场景仓位被直接清零
- 命中 IC effective_date 未顺延至 T+2
- 命中 cash M&A 未执行 `forced_cash_exit`
- 同 fixture 两次运行 execution log hash 不一致
- fallback 模式下缺少 `fallback_count_total` 或 `fallback_rate` 指标

## Verification Complete

All plan deliverables were implemented and validated.

## Execution Evidence

- `pytest tests/test_backtest_correctness_phase21.py -q` → **8 passed**
- `pytest tests/ -q` → **1113 passed, 11 skipped**

## Requirement Traceability

- **AUDIT-01:** Covered by fixture-backed untradable and corporate-action scenarios.
- **AUDIT-02:** Covered by `test_no_lookahead_gate` and explicit `execution_date > signal_date` enforcement.
- **AUDIT-03:** Covered by buy/sell untradable status tests and `test_cash_mna_forced_exit`.
