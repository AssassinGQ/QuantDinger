---
phase: 13
slug: qualify-result-caching-e2e-prefix-fix
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-11
updated: 2026-04-11
note: "Wave 0 N/A — tests are added/updated in 13-01 Task 2 per PLAN.md (no separate stub wave)."
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (project standard) |
| **Config file** | `backend_api_python/tests/conftest.py` (shared fixtures; no root pytest.ini) |
| **Quick run command (after 13-01 Task 2)** | `cd backend_api_python && python -m pytest tests/test_ibkr_client.py::TestQualifyContractForex tests/test_ibkr_client.py::TestQualifyContractCache -q` |
| **Full suite command** | `cd backend_api_python && python -m pytest` |
| **Estimated runtime** | ~60 seconds (full suite ~928 tests) |

---

## Sampling Rate

- **After 13-01 Task 1:** Run Task 1 automated verify only (`py_compile` + structural greps in `13-01-PLAN.md`); do not expect qualify pytest green until Task 2.
- **After 13-01 Task 2:** Run `cd backend_api_python && python -m pytest tests/test_ibkr_client.py::TestQualifyContractForex tests/test_ibkr_client.py::TestQualifyContractCache -q`
- **After full phase execution:** Run `cd backend_api_python && python -m pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command (matches PLAN.md) | Status |
|---------|------|------|-------------|-----------|--------------------------------------|--------|
| 13-01-01 | 01 | 1 | INFRA-01 | structural | `python -m py_compile …/client.py` + greps / `rg` (see 13-01 Task 1 `<verify>`) | ⬜ pending |
| 13-01-02 | 01 | 1 | INFRA-01 | unit | `pytest tests/test_ibkr_client.py::TestQualifyContractForex tests/test_ibkr_client.py::TestQualifyContractCache -q` | ⬜ pending |
| 13-01-03 | 01 | 1 | INFRA-01 | doc/grep | `grep` README + REQUIREMENTS (see 13-01 Task 3 `<verify>`) | ⬜ pending |
| 13-02-01 | 02 | 1 | TEST-01 | integration | `pytest tests/test_forex_ibkr_e2e.py -q` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- **N/A for this phase** — `13-01-PLAN.md` Task 2 extends `tests/test_ibkr_client.py` in the same wave as implementation (no advance stub file).

*Existing `conftest.py` remains sufficient; no new shared fixtures required.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| TTL env var documentation | INFRA-01 | Doc review | Check env var names documented in README or operator docs |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
