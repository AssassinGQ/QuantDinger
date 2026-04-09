---
phase: 04
slug: market-category-worker-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (see `pip show pytest` in env) |
| **Config file** | No dedicated pytest.ini; `tests/conftest.py` shared |
| **Quick run command** | `cd backend_api_python && python -m pytest tests/test_exchange_engine.py tests/test_pending_order_worker.py -x -q --tb=line` |
| **Full suite command** | `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` |
| **Estimated runtime** | ~3 minutes (860+ tests) |

---

## Sampling Rate

- **After every task commit:** targeted tests + **full suite** (per PLAN.md verify — user requirement)
- **Before phase gate:** Full suite must be green
- **Max feedback latency:** 180 seconds for full suite

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | CONT-04 / UC-1..6 | unit+integration | See PLAN.md per task | partial | ⬜ pending |
| 04-01-02 | 01 | 1 | CONT-04 / REGR-01 | regression | `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` | ✅ | ⬜ pending |

*Each task verify MUST include the full suite command above (no shell pipes).*

---

## Wave 0 Requirements

- [ ] `tests/test_pending_order_worker.py` — UC-4, UC-5 (`_execute_live_order`, not `_process_one_live_order`)
- [ ] `tests/test_exchange_engine.py` — UC-1..3, UC-6 (update frozenset + flip forex test)

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] Each task verify includes full `pytest tests/` run
- [ ] No `| head` / `| tail` in verify commands
- [ ] `nyquist_compliant: true` after phase pass

**Approval:** pending
