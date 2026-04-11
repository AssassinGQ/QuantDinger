---
phase: 13
slug: qualify-result-caching-e2e-prefix-fix
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (project standard) |
| **Config file** | `backend_api_python/tests/conftest.py` (shared fixtures; no root pytest.ini) |
| **Quick run command** | `cd backend_api_python && python -m pytest tests/test_ibkr_client.py::TestQualifyContractForex -q` |
| **Full suite command** | `cd backend_api_python && python -m pytest` |
| **Estimated runtime** | ~60 seconds (full suite ~928 tests) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -k qualify -x -q`
- **After every plan wave:** Run `cd backend_api_python && python -m pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | INFRA-01 | unit | `pytest tests/test_ibkr_client.py -k qualify -x` | ✅ (extend) | ⬜ pending |
| 13-01-02 | 01 | 1 | INFRA-01 | unit | `pytest tests/test_ibkr_client.py -k cache -x` | ❌ W0 | ⬜ pending |
| 13-01-03 | 01 | 1 | INFRA-01 | unit | `pytest tests/test_ibkr_client.py -k invalidat -x` | ❌ W0 | ⬜ pending |
| 13-02-01 | 02 | 1 | TEST-01 | integration | `pytest tests/test_forex_ibkr_e2e.py -q` | ✅ (fix) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ibkr_client.py` — add cache hit/miss/invalidation test stubs
- [ ] Existing `tests/conftest.py` — sufficient; no new shared fixtures needed

*Existing infrastructure covers framework requirements.*

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
