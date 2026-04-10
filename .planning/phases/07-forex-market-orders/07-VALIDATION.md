---
phase: 07
slug: forex-market-orders
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none — uses default + repo conventions |
| **Quick run command** | `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -x -q --tb=line` |
| **Full suite command** | `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` |
| **Estimated runtime** | ~150 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -x -q --tb=line`
- **After every plan wave:** Run `cd backend_api_python && python -m pytest tests/ -x -q --tb=line`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 150 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | EXEC-01 | integration (mock IB) | `pytest tests/test_ibkr_client.py -k "PlaceMarketOrderForex" -x -q --tb=line` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend_api_python/tests/test_ibkr_client.py` — new `TestPlaceMarketOrderForex` class with UC-M1–M3, UC-E1–E3

*Existing test infrastructure (helpers, fixtures, mock patterns) covers all phase needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Forex market order fills on Paper Trading | EXEC-01 | CI uses mocked IB | Phase 6 VERIFICATION.md already covers EURUSD 20000 buy/sell on DUQ123679 |

*Paper trading verification already completed in Phase 6.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 150s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
