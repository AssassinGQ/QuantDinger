---
phase: 14
slug: tif-unification-usstock-hshare
status: draft
nyquist_compliant: true
wave_0_complete: true
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
| **Full suite command** | `cd backend_api_python && python -m pytest -q --tb=line` |
| **Estimated runtime** | ~180 seconds (full suite ~931 tests) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -k "Tif" -q`
- **After every plan wave:** Run `cd backend_api_python && python -m pytest -q --tb=line`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-T1 | 01 | 1 | INFRA-02 | unit | `pytest tests/test_ibkr_client.py::TestTifMatrix -q && pytest -q --tb=line` | ❌ W0 (TestTifMatrix new) + ✅ (existing tests updated) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_ibkr_client.py` — add `TestTifMatrix` class with 24+1 parametrize (24 IOC + 1 unknown→DAY)
- [x] Update `TestTifDay`, `TestTifForexPolicy`, `TestPlaceMarketOrderForex` assertions (DAY → IOC)
- [x] Existing pytest framework — no install gap

*All Wave 0 items are covered by Plan 14-01 Task 1.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| HShare IOC not rejected by IBKR | INFRA-02 | Needs paper/live IBKR | Place test order on paper account with HShare + IOC; confirm not rejected |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify (no pipe exit-code bug; full pytest propagates failure)
- [x] Sampling continuity: single task with full automated verify
- [x] Wave 0 covers all MISSING references (TestTifMatrix created in task)
- [x] No watch-mode flags
- [x] Feedback latency < 180s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready
