---
phase: 12
slug: frontend-ibkr-exchanges-for-forex
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Frontend Framework** | Jest via `@vue/cli-plugin-unit-jest` |
| **Frontend Config file** | `quantdinger_vue/jest.config.js` |
| **Frontend Quick run** | `cd quantdinger_vue && npm run test:unit` |
| **Backend Framework** | pytest 9.x |
| **Backend Quick run** | `python -m pytest backend_api_python/tests/test_strategy_exchange_validation.py -q --tb=short` |
| **Backend Full suite** | `python -m pytest backend_api_python/tests/ -q` |
| **Estimated runtime** | ~5 min (backend full suite) |

---

## Sampling Rate

- **After every task commit:** `cd quantdinger_vue && npm run test:unit` (once specs exist) + targeted backend pytest
- **After every plan wave:** Full backend `python -m pytest backend_api_python/tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~300 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | FRNT-01 | unit/component | `cd quantdinger_vue && npm run test:unit` | ❌ W0 | ⬜ pending |
| 12-01-02 | 01 | 1 | FRNT-01 | integration | `python -m pytest backend_api_python/tests/test_strategy_exchange_validation.py -q` | ✅ | ⬜ pending |
| regression | — | — | — | integration | `python -m pytest backend_api_python/tests/ -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `quantdinger_vue/tests/unit/frnt-01-forex-ibkr-options.spec.js` — stubs for FRNT-01 (Forex broker list, payload shape, computed renames); same filename as `12-01-PLAN.md` Task 3
- [ ] Confirm `npm run test:unit` works in current project state

*Backend: existing `test_strategy_exchange_validation.py` covers Forex + ibkr-paper/ibkr-live API acceptance.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual dropdown renders correctly | FRNT-01 | Vue Test Utils can check DOM but not visual fidelity | Open strategy wizard, select Forex, verify dropdown shows MT5 / IBKR Paper / IBKR Live |
| Edit backfill displays correct broker | FRNT-01 | Requires saved strategy data | Edit existing Forex+MT5 strategy, verify MT5 selected; edit Forex+IBKR strategy, verify IBKR selected |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 300s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
