---
phase: 15
slug: normalize-pipeline-ordering
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-12
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | none (uses defaults) |
| **Quick run command** | `cd backend_api_python && python3 -m pytest tests/test_order_normalizer.py tests/test_ibkr_client.py::TestQuantityGuard -x` |
| **Full suite command** | `cd backend_api_python && python3 -m pytest` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend_api_python && python3 -m pytest tests/test_order_normalizer.py tests/test_ibkr_client.py::TestQuantityGuard -x`
- **After every plan wave:** Run `cd backend_api_python && python3 -m pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 1 | INFRA-03 | unit | `pytest tests/test_order_normalizer.py -x` | ✅ (update) | ⬜ pending |
| 15-01-02 | 01 | 1 | INFRA-03 | unit+mock | `pytest tests/test_ibkr_client.py::TestQuantityGuard -x` | ✅ (update) | ⬜ pending |
| 15-02-01 | 02 | 1 | INFRA-03 | grep | `rg 'ibkr_trading\.order_normalizer' backend_api_python/app` | N/A | ⬜ pending |
| 15-03-01 | 03 | 2 | INFRA-03 | unit | `pytest tests/test_order_normalizer.py tests/test_ibkr_client.py -x` | ✅ (update) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*

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
