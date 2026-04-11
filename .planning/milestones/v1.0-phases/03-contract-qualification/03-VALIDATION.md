---
phase: 03
slug: contract-qualification
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-09
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (installed) |
| **Config file** | No pytest.ini — uses default discovery |
| **Quick run command** | `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -x -q` |
| **Full suite command** | `cd backend_api_python && python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -x -q`
- **After every plan wave:** Run `cd backend_api_python && python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | CONT-03 / UC-1 | unit | `pytest tests/test_ibkr_client.py::TestQualifyContractForex::test_forex_qualify_success_fields -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | CONT-03 / UC-2 | unit | `pytest tests/test_ibkr_client.py::TestQualifyContractForex::test_forex_qualify_failure -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | CONT-03 / UC-3 | unit | `pytest tests/test_ibkr_client.py::TestQualifyContractForex::test_forex_qualify_exception -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | CONT-03 / UC-4 | unit | `pytest tests/test_ibkr_client.py::TestValidateQualifiedContract::test_forex_valid -x` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 1 | CONT-03 / UC-5 | unit | `pytest tests/test_ibkr_client.py::TestValidateQualifiedContract::test_forex_sectype_mismatch -x` | ❌ W0 | ⬜ pending |
| 03-01-06 | 01 | 1 | CONT-03 / UC-6 | unit | `pytest tests/test_ibkr_client.py::TestValidateQualifiedContract::test_conid_zero -x` | ❌ W0 | ⬜ pending |
| 03-01-07 | 01 | 1 | CONT-03 / UC-7 | unit | `pytest tests/test_ibkr_client.py::TestQualifyContractForex::test_error_message_includes_market_type -x` | ❌ W0 | ⬜ pending |
| 03-01-08 | 01 | 1 | CONT-03 / UC-8 | unit | `pytest tests/test_ibkr_client.py::TestValidateQualifiedContract::test_stock_valid -x` | ❌ W0 | ⬜ pending |
| 03-01-09 | 01 | 1 | CONT-03 / UC-9 | unit | `pytest tests/test_ibkr_client.py::TestValidateQualifiedContract::test_hshare_valid -x` | ❌ W0 | ⬜ pending |
| 03-01-10 | 01 | 1 | CONT-03 / REGR-01 | integration | `cd backend_api_python && python -m pytest tests/ -x -q` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ibkr_client.py::TestQualifyContractForex` — new test class for UC-1,2,3,7
- [ ] `tests/test_ibkr_client.py::TestValidateQualifiedContract` — new test class for UC-4,5,6,8,9
- [ ] Mock enhancement: `_mock_qualify_async` needs side_effect variant that mutates contract fields for Forex
- [ ] Framework install: None — pytest already available

*Existing infrastructure covers framework requirements.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
