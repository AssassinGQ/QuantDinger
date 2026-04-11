---
phase: 14
slug: tif-unification-usstock-hshare
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (project standard) |
| **Config file** | `backend_api_python/tests/conftest.py` (shared fixtures; no root pytest.ini) |
| **Quick run command** | `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -k "Tif" -q` |
| **Full suite command** | `cd backend_api_python && python -m pytest -q` |
| **Estimated runtime** | ~180 seconds (full suite ~931 tests) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -k "Tif" -q`
- **After every plan wave:** Run `cd backend_api_python && python -m pytest -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | INFRA-02 | unit | `pytest tests/test_ibkr_client.py -k "_get_tif" -q` | ✅ (update) | ⬜ pending |
| 14-01-02 | 01 | 1 | INFRA-02 | unit | `pytest tests/test_ibkr_client.py::TestTifMatrix -q` | ❌ W0 | ⬜ pending |
| 14-01-03 | 01 | 1 | INFRA-02 | unit | `pytest tests/test_ibkr_client.py -k "Tif" -q` | ✅ (update) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ibkr_client.py` — add `TestTifMatrix` class with 24-combination parametrize
- [ ] Update `TestTifDay` assertions (DAY → IOC for USStock open)
- [ ] Existing pytest framework — no install gap

*Existing infrastructure covers framework requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| HShare IOC not rejected by IBKR | INFRA-02 | Needs paper/live IBKR | Place test order on paper account with HShare + IOC; confirm not rejected |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
