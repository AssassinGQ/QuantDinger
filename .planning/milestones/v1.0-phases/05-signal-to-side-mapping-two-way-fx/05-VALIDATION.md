---
phase: 05
slug: signal-to-side-mapping-two-way-fx
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none (implicit) — see `tests/conftest.py` |
| **Quick run command** | `cd backend_api_python && python -m pytest tests/test_exchange_engine.py -q --tb=line` |
| **Full suite command** | `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend_api_python && python -m pytest tests/test_exchange_engine.py -q --tb=line`
- **After every plan wave:** Run `cd backend_api_python && python -m pytest tests/ -x -q --tb=line`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | EXEC-02 | unit | `pytest tests/test_exchange_engine.py -k IBKR -q` | Extend existing | pending |
| 05-01-02 | 01 | 1 | EXEC-02 | unit | `pytest tests/test_exchange_engine.py -k IBKR -q` | Extend existing | pending |
| 05-01-03 | 01 | 1 | EXEC-02 | unit | `pytest tests/ -x -q --tb=line` | New runner test | pending |

*Status: pending · green · red · flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers all phase requirements. No new framework or fixture setup needed.
- `tests/test_exchange_engine.py` already contains `TestIBKRSignalMapping` — extend with Forex table-driven tests.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
