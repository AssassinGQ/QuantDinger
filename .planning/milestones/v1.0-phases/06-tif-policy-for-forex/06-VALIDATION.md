---
phase: 06
slug: tif-policy-for-forex
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none (implicit) — see `tests/conftest.py` |
| **Quick run command** | `cd backend_api_python && python -m pytest tests/test_ibkr_client.py::TestTifDay -x -q --tb=line` |
| **Full suite command** | `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -k Tif -x -q --tb=line`
- **After every plan wave:** Run `cd backend_api_python && python -m pytest tests/ -x -q --tb=line`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | EXEC-03 | unit | `pytest tests/test_ibkr_client.py -k Tif -q` | Extend existing | pending |

*Status: pending · green · red · flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers all phase requirements. `TestTifDay` in `test_ibkr_client.py` provides the base pattern.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Paper account spot check | EXEC-03 | IB paper environment not in CI | Place EUR.USD market order, verify tif=IOC in TWS audit trail |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
