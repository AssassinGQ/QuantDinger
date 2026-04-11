---
phase: 11
slug: strategy-automation-forex-ibkr
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest ~9.x |
| **Config file** | Inline markers in `tests/conftest.py` (`pytest_configure`) |
| **Quick run command** | `cd backend_api_python && python -m pytest tests/test_forex_ibkr_e2e.py -x -q` |
| **Full suite command** | `cd backend_api_python && python -m pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend_api_python && python -m pytest tests/test_forex_ibkr_e2e.py -x -q`
- **After every plan wave:** Run `cd backend_api_python && python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | RUNT-03 | unit | `pytest tests/test_exchange_engine.py -k validate_exchange -x` | ❌ W0 | ⬜ pending |
| 11-01-02 | 01 | 1 | RUNT-03 | integration | `pytest tests/test_forex_ibkr_e2e.py -x` | ❌ W0 | ⬜ pending |
| 11-01-03 | 01 | 1 | RUNT-03 | integration | `pytest tests/test_forex_ibkr_e2e.py -k smoke -x` | ❌ W0 | ⬜ pending |
| 11-01-04 | 01 | 1 | RUNT-03 | regression | `pytest tests/ -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_forex_ibkr_e2e.py` — E2E and smoke test stubs for RUNT-03
- [ ] API validation test stubs — in existing test files or new file

*Existing infrastructure (pytest, conftest.py, mock patterns) covers all framework requirements.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
