---
phase: 08
slug: quantity-normalization-ib-alignment
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 08 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none — uses default + repo conventions |
| **Quick run command** | `cd backend_api_python && python -m pytest tests/test_order_normalizer.py -x -q --tb=line` |
| **Full suite command** | `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` |
| **Estimated runtime** | ~150 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend_api_python && python -m pytest tests/test_order_normalizer.py -x -q --tb=line`
- **After every plan wave:** Run `cd backend_api_python && python -m pytest tests/ -x -q --tb=line`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 150 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | EXEC-04 | unit | `pytest tests/test_order_normalizer.py -k "ForexNormalizer" -x -q --tb=line` | ✅ existing (extend) | ⬜ pending |
| 08-01-02 | 01 | 1 | EXEC-04 | integration (mock IB) | `pytest tests/ -k "AlignQty" -x -q --tb=line` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend_api_python/tests/` — alignment test module (new or extended)
- [ ] Update `TestForexNormalizer.test_normalize` expectation from floor to passthrough

*Existing test infrastructure covers all phase needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| None | — | — | All phase behaviors have automated verification |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 150s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
