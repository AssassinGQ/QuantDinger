---
phase: 23
slug: grid-search-research-script
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-19
validated: 2026-05-19
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | backend_api_python/pytest.ini (project default) |
| **Quick run command** | `cd backend_api_python && pytest tests/test_grid_search_script.py -q` |
| **Full suite command** | `cd backend_api_python && pytest tests/ -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_grid_search_script.py -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 23-01-01 | 01 | 1 | SCRIPT-01 | T-23-01 | yaml.safe_load only | unit | `pytest tests/test_grid_search_script.py -k config -v` | ✅ | ✅ green |
| 23-01-02 | 01 | 1 | SCRIPT-01 | — | N/A | unit | `pytest tests/test_grid_search_script.py -k combos -v` | ✅ | ✅ green |
| 23-02-01 | 02 | 1 | SCRIPT-02 | — | N/A | unit | `pytest tests/test_grid_search_script.py -k score -v` | ✅ | ✅ green |
| 23-03-01 | 03 | 1 | SCRIPT-03 | — | N/A | unit | `pytest tests/test_grid_search_script.py -k checkpoint -v` | ✅ | ✅ green |
| 23-03-02 | 03 | 1 | SCRIPT-03 | — | N/A | unit | `pytest tests/test_grid_search_script.py -k jsonl -v` | ✅ | ✅ green |
| 23-04-01 | 04 | 2 | SCRIPT-04 | — | N/A | unit | `pytest tests/test_grid_search_script.py -k walk_forward -v` | ✅ | ✅ green |
| 23-04-02 | 04 | 2 | SCRIPT-04 | — | N/A | integration | `pytest tests/test_grid_search_script.py -k oos -v` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `backend_api_python/tests/test_grid_search_script.py` — test file for grid search script
- [x] `scripts/cross_sectional/test_grid_config.yaml` — minimal test config fixture
- [x] Mock Phase 22 API responses (unittest.mock.patch on requests.post)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| HTML report visual inspection | SCRIPT-02 | Visual rendering check | Open report.html in browser, verify tables render correctly |
| Walk-forward OOS curve interpretation | SCRIPT-04 | Domain interpretation | Review OOS summary table, verify window logic matches expectation |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated (2026-05-19)