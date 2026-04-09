---
phase: 1
slug: forex-symbol-normalization
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-09
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (project existing) |
| **Config file** | none — default pytest discovery in `tests/` |
| **Quick run command** | `python -m pytest tests/test_ibkr_symbols.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q --ignore=tests/live_trading` |
| **Estimated runtime** | ~3 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_ibkr_symbols.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q --ignore=tests/live_trading`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | CONT-02a | unit | `python -m pytest tests/test_ibkr_symbols.py::TestNormalizeSymbolForex::test_6char_uppercase -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | CONT-02b | unit | `python -m pytest tests/test_ibkr_symbols.py::TestNormalizeSymbolForex::test_separator_and_case_variants -x` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | CONT-02c | unit | `python -m pytest tests/test_ibkr_symbols.py::TestNormalizeSymbolForex::test_invalid_forex_raises -x` | ❌ W0 | ⬜ pending |
| 01-01-04 | 01 | 1 | CONT-02d | unit | `python -m pytest tests/test_ibkr_symbols.py::TestNormalizeSymbolForex::test_does_not_default_to_stock -x` | ❌ W0 | ⬜ pending |
| 01-01-05 | 01 | 1 | CONT-02e | unit | `python -m pytest tests/test_ibkr_symbols.py::TestParseSymbolForex -x` | ❌ W0 | ⬜ pending |
| 01-01-06 | 01 | 1 | CONT-02f | unit | `python -m pytest tests/test_ibkr_symbols.py::TestFormatDisplayForex -x` | ❌ W0 | ⬜ pending |
| 01-01-07 | 01 | 1 | REGR-01 | unit | `python -m pytest tests/test_ibkr_symbols.py::TestNormalizeSymbolRegression -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ibkr_symbols.py` — stubs for CONT-02 (all sub-requirements) + USStock/HShare regression
- No new fixtures needed — tests are pure function tests with no mocks required
- No framework install needed — pytest already in project

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
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
