---
phase: 11-strategy-automation-forex-ibkr
slug: strategy-automation-forex-ibkr
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-11
updated: 2026-04-11
---

# Phase 11 — Validation Strategy

> Per-phase validation contract aligned with `11-01-PLAN.md`, `11-02-PLAN.md`, and `11-03-PLAN.md` (three plans, five executable tasks).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest ~9.x |
| **Config file** | Inline markers in `tests/conftest.py` (`pytest_configure`) |
| **Phase subset command** | `cd backend_api_python && python -m pytest tests/test_strategy_exchange_validation.py tests/test_forex_ibkr_e2e.py tests/test_ibkr_forex_paper_smoke.py -q --tb=short` |
| **Full suite command** | `cd backend_api_python && python -m pytest tests/ -q` |
| **Estimated runtime** | ~15–60 seconds (subset vs full) |

---

## Sampling Rate

- **After Plan 11-01 tasks:** `python -m pytest tests/test_strategy_exchange_validation.py -q --tb=short` (and Task 1 spot-check: factory `python -c` from `11-01-PLAN.md` Task 1 `<verify>`).
- **After Plan 11-02 Task 1:** `python -m pytest tests/test_forex_ibkr_e2e.py -q --tb=short`
- **After Plan 11-03 Task 1:** `python -m pytest tests/test_ibkr_forex_paper_smoke.py -q --tb=short`
- **After every plan wave / before verify-work:** `cd backend_api_python && python -m pytest tests/ -q`
- **Max feedback latency:** 60 seconds for full suite

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated command (from PLAN `<verify>`) | Status |
|---------|------|------|-------------|-----------|-------------------------------------------|--------|
| **11-01-T1** | `11-01-PLAN.md` Task 1 | 1 | RUNT-03 | factory/base | `cd backend_api_python && python -c "from app.services.live_trading.factory import validate_exchange_market_category as v; assert v('ibkr-paper','Forex')[0] is True; assert v('ibkr-paper','Crypto')[0] is False; assert v('binance','Forex')[0] is False"` | ⬜ pending |
| **11-01-T2** | `11-01-PLAN.md` Task 2 | 1 | RUNT-03 | integration | `cd backend_api_python && python -m pytest tests/test_strategy_exchange_validation.py -q --tb=short` | ⬜ pending |
| **11-02-T1** | `11-02-PLAN.md` Task 1 | 2 | RUNT-03 | e2e | `cd backend_api_python && python -m pytest tests/test_forex_ibkr_e2e.py -q --tb=short` | ⬜ pending |
| **11-02-T2** | `11-02-PLAN.md` Task 2 | 2 | RUNT-03 | runbook | From repo root: `test -f .planning/phases/11-strategy-automation-forex-ibkr/11-PAPER-RUNBOOK.md && rg -q "python -m pytest tests/" .planning/phases/11-strategy-automation-forex-ibkr/11-PAPER-RUNBOOK.md` | ⬜ pending |
| **11-03-T1** | `11-03-PLAN.md` Task 1 | 1 | RUNT-03 | smoke | `cd backend_api_python && python -m pytest tests/test_ibkr_forex_paper_smoke.py -q --tb=short` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Wave dependency:** Plan `11-02` (wave 2) `depends_on: ["01", "03"]` — run **11-01** and **11-03** verification before **11-02** E2E/runbook tasks.

---

## Wave 0

Not used for this phase: executable tests and commands are defined directly in each PLAN task (no separate stub wave).

---

## Manual-Only Verifications

- Optional: operator follow-up using `11-PAPER-RUNBOOK.md` (IBKR Paper EURUSD) — not required for Nyquist; automated suite is the gate.

---

## Validation Sign-Off

- [x] Each PLAN task has an `<automated>` verify block (Nyquist)
- [x] Task IDs map 1:1 to `11-01` / `11-02` / `11-03` PLAN tasks
- [x] No watch-mode flags in automated commands
- [ ] All automated commands green on target branch
- [ ] `nyquist_compliant: true` remains accurate after execution

**Approval:** pending
