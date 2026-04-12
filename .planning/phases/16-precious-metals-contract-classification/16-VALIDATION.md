---
phase: 16
slug: precious-metals-contract-classification
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-12
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (project `backend_api_python/tests/`) |
| **Config file** | none — markers in `tests/conftest.py` |
| **Quick run command** | `cd backend_api_python && pytest tests/test_ibkr_symbols.py tests/test_ibkr_client.py -q --tb=short -x` |
| **Full suite command** | `cd backend_api_python && pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend_api_python && pytest tests/test_ibkr_symbols.py tests/test_ibkr_client.py -q --tb=short -x`
- **After every plan wave:** Run `cd backend_api_python && pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 16-01-01 | 01 | 1 | TRADE-04 | unit | `pytest tests/test_ibkr_symbols.py -k metals -x` | ❌ W0 — update existing | ⬜ pending |
| 16-01-02 | 01 | 1 | TRADE-04 | unit | `pytest tests/test_ibkr_client.py -k metals -x` | ❌ W0 — add new | ⬜ pending |
| 16-02-01 | 02 | 1 | TRADE-04 | unit | `pytest tests/test_ibkr_client.py -k "metals and normalizer" -x` | ❌ W0 | ⬜ pending |
| 16-03-01 | 03 | 2 | TRADE-04 | integration | `pytest tests/ -k "xauusd or xagusd" -x` | ❌ W0 — update existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ibkr_symbols.py` — update `test_metals_detected_as_forex` → `test_metals_detected_as_metals`
- [ ] `tests/test_ibkr_client.py` — add mocked qualify snapshot tests for CMDTY metals
- [ ] Existing framework covers all other needs

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Paper qualify returns CMDTY for XAUUSD/XAGUSD | TRADE-04 | Requires live IB Gateway | Already verified 2026-04-12 via SSH script — see 16-RESEARCH.md "Paper Qualify Experiment" |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
