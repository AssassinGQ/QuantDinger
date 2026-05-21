---
phase: 22-cross-sectional-portfolio-backtest-engine
status: passed
verified: 2026-05-15
---

# Phase 22 验证

## 自动化

- `cd backend_api_python && python3 -m pytest tests/ -q` — 全量通过（1219 passed, 11 skipped）。

## Must-haves（对照 PLAN）

| 条目 | 证据 |
|------|------|
| scores + weights 硬契约 | `run_cross_sectional_indicator` 抛 `CROSS_SECTIONAL_CONTRACT`；`test_indicator_contract_*` |
| neutral_off / neutral_on 双套 | `CrossSectionalPortfolioBacktestService.run` 返回两键；`test_neutral_off_on_both_summaries` |
| Phase 21 复用 | `_filter_phase21_signals` 于 `cross_sectional_portfolio_backtest.py` |
| HTTP 包络与 D-03 | `test_pool_validation_*`；成功 `code==1,msg==OK` — `test_api_success_structure` |
| 无 traceback 泄漏 | `test_api_contract_error_no_traceback_in_json` |

## 人工

- 无（本 phase 范围后端 + 契约测试）。
