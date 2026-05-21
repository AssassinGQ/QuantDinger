---
phase: 22-cross-sectional-portfolio-backtest-engine
plan: "01"
subsystem: api
tags: [cross-sectional, backtest, pytest, BT-01]
requires: []
provides:
  - scores+weights 指标硬契约（CROSS_SECTIONAL_CONTRACT）
  - CrossSectionalPortfolioBacktestService 单组合双套 neutral_off/on
  - Phase 21 执行过滤复用（CrossSectionalRunner._filter_phase21_signals）
affects: []
tech-stack:
  added: []
  patterns: ["权重策略 B：正权重按总和归一化；负权重拒绝（仅做多）"]
key-files:
  created:
    - backend_api_python/app/services/cross_sectional_portfolio_backtest.py
    - backend_api_python/tests/test_cross_sectional_portfolio_bt01.py
  modified:
    - backend_api_python/app/strategies/cross_sectional_indicator.py
    - backend_api_python/app/strategies/cross_sectional.py
    - backend_api_python/tests/test_trading_executor_te.py
key-decisions:
  - "行业中性：组内去均值残差用于 neutral_on 权重过滤后再归一化"
  - "可交易子集 = 在 panel 中有非空 OHLCV 的 symbols"
requirements-completed: ["BT-01"]
duration: 45min
completed: 2026-05-15
---

# Phase 22 Plan 01 小结

交付截面组合回测**后端内核**：`run_cross_sectional_indicator` 强制 `scores`/`weights` 全量可交易标的契约；新增 `CrossSectionalPortfolioBacktestService` 编排面板、指标、Phase 21 过滤与双套 `neutral_off`/`neutral_on` 权益与摘要；`pytest tests/` 全量通过。

## Files

- `backend_api_python/app/strategies/cross_sectional_indicator.py` — `weights` 沙箱键与契约校验；契约失败抛 `ValueError(CROSS_SECTIONAL_CONTRACT:...)`。
- `backend_api_python/app/services/cross_sectional_portfolio_backtest.py` — 组合回测编排、行业中性残差、与 `BacktestService` 指标对齐的摘要字段。
- `backend_api_python/tests/test_cross_sectional_portfolio_bt01.py` — 契约/引擎/PIT/中性/仅做多用例。
- `backend_api_python/app/strategies/cross_sectional.py` — 捕获契约异常并降级为无信号。

## Self-Check: PASSED

- `cd backend_api_python && python3 -m pytest tests/ -q` — 1219 passed（执行时全量）。
