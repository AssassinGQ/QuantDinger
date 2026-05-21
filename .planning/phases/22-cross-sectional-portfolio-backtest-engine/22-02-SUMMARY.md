---
phase: 22-cross-sectional-portfolio-backtest-engine
plan: "02"
subsystem: api
tags: [flask, blueprint, BT-01, D-03, D-02]
requires:
  - phase: 22-01
    provides: CrossSectionalPortfolioBacktestService 与指标契约
provides:
  - POST `/api/indicator/cross-sectional-portfolio-backtest`
  - symbolList/universe 互斥校验与可复现 repro 块
affects: []
tech-stack:
  added: []
  patterns: ["成功包络 code=1 msg=OK 与 backtest 路由对齐；错误不返回 traceback 文本"]
key-files:
  created:
    - backend_api_python/app/routes/cross_sectional_portfolio_backtest.py
  modified:
    - backend_api_python/app/routes/__init__.py
    - backend_api_python/tests/test_cross_sectional_portfolio_bt01.py
key-decisions:
  - "鉴权与单标的回测一致：@login_required + Bearer JWT"
  - "K 线面板通过 BacktestService._fetch_kline_data 拉取多标的"
requirements-completed: ["BT-01"]
duration: 25min
completed: 2026-05-15
---

# Phase 22 Plan 02 小结

新增同步 POST 截面组合回测 HTTP API：`symbolList` 与 `universe` 互斥（D-03）、请求体与 `indicatorCode` 长度上限、成功响应 `code==1`/`msg==OK` 与 `data.repro`（universe_digest、indicator_config_hash、execution_profile 等）及 `neutral_off`/`neutral_on`；契约类错误映射 422 且不向客户端泄漏栈文本。

## Self-Check: PASSED

- `pytest tests/test_cross_sectional_portfolio_bt01.py` 含 HTTP 用例；全量 `tests/` 已通过。
