---
phase: 24
slug: nq100-strategy-type
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-20
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | backend_api_python/tests/conftest.py |
| **Quick run command** | `pytest tests/test_nq100_strategy.py tests/test_delisting_policy_filter.py -v -x` |
| **Full suite command** | `pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~45 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_nq100_strategy.py tests/test_delisting_policy_filter.py -v -x`
- **After every plan wave:** Run `pytest tests/ -v --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 24-01-01 | 01 | 1 | STRAT-01 | T-24-01 | Validate inheritance chain | unit | `pytest tests/test_nq100_strategy.py::TestStrategyInheritance -v` | ❌ W0 | ⬜ pending |
| 24-01-02 | 01 | 1 | STRAT-01 | T-24-02 | Implement get_universe_list interface | unit | `pytest tests/test_nq100_strategy.py::TestDynamicUniverseBinding -v` | ❌ W0 | ⬜ pending |
| 24-02-01 | 02 | 1 | STRAT-01 | T-24-01 | PIT API integration | unit | `pytest tests/test_nq100_strategy.py::TestNQ100PITIntegration -v` | ❌ W0 | ⬜ pending |
| 24-03-01 | 03 | 1 | STRAT-01/02 | T-24-03 | Config validation (mutual exclusion) | unit | `pytest tests/test_strategy_routes.py::TestConfigValidation::test_mutual_exclusion -v` | ❌ W0 | ⬜ pending |
| 24-03-02 | 03 | 1 | STRAT-02 | T-24-03 | delisting_policy validation | unit | `pytest tests/test_strategy_routes.py::TestDelistingPolicyValidation -v` | ❌ W0 | ⬜ pending |
| 24-03-03 | 03 | 1 | STRAT-02 | T-24-04 | force_exit_symbols validation | unit | `pytest tests/test_strategy_routes.py::TestForceExitSymbols -v` | ❌ W0 | ⬜ pending |
| 24-04-01 | 04 | 2 | STRAT-02 | — | DelistingPolicyFilter immediate mode | unit | `pytest tests/test_delisting_policy_filter.py::TestImmediateMode -v` | ❌ W0 | ⬜ pending |
| 24-04-02 | 04 | 2 | STRAT-02 | — | DelistingPolicyFilter delayed mode | unit | `pytest tests/test_delisting_policy_filter.py::TestDelayedMode -v` | ❌ W0 | ⬜ pending |
| 24-04-03 | 04 | 2 | STRAT-02 | — | DelistingPolicyFilter hold_until_signal_exit mode | unit | `pytest tests/test_delisting_policy_filter.py::TestHoldUntilSignalExit -v` | ❌ W0 | ⬜ pending |
| 24-04-04 | 04 | 2 | STRAT-02 | T-24-04 | force_exit_symbols handling | unit | `pytest tests/test_delisting_policy_filter.py::TestForceExitSymbols -v` | ❌ W0 | ⬜ pending |
| 24-04-05 | 04 | 2 | STRAT-02 | — | Backtest total loss handling | unit | `pytest tests/test_delisting_policy_filter.py::TestBacktestTotalLoss -v` | ❌ W0 | ⬜ pending |
| 24-05-01 | 05 | 2 | STRAT-02 | — | Runner filter chain integration | integration | `pytest tests/test_cross_sectional_runner_integration.py::TestDelistingFilterChain -v` | ❌ W0 | ⬜ pending |
| 24-06-01 | 06 | 2 | STRAT-02 | — | Strategy excluded_from_universe tracking | unit | `pytest tests/test_nq100_strategy.py::TestExcludedFromUniverse -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_nq100_strategy.py` — stubs for STRAT-01 inheritance and universe binding
- [ ] `tests/test_delisting_policy_filter.py` — stubs for STRAT-02 delisting policy modes
- [ ] `tests/test_cross_sectional_runner_integration.py` — stubs for Runner integration
- [ ] `tests/test_strategy_routes.py` — stubs for HTTP route validation (extend existing file)
- [ ] `tests/fixtures/phase24/` — test data fixtures (change events, delisting scenarios)
- [ ] Framework config: already exists in `conftest.py`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live trading forced sell execution timing | STRAT-02 | Requires real IBKR connection and market hours | Manual live test with test account, verify forced sell executes at correct time |

*Additional manual verification: None — all phase behaviors have automated verification.*

---

## Threat Model Reference

| Threat ID | STRIDE | Description | Mitigation Location |
|-----------|--------|-------------|---------------------|
| T-24-01 | Tampering | Invalid inheritance chain breaking base contract | Unit test verifies base class inheritance |
| T-24-02 | Tampering | get_universe_list returning unvalidated symbols | PIT API returns validated constituents |
| T-24-03 | Tampering | symbol_list + universe bypass causing ambiguity | Route validation mutual exclusion |
| T-24-04 | Tampering | force_exit_symbols injection attack | List type validation + symbol sanitization |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 45s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending