---
phase: 01
slug: ibkr-schedule-sufficiency-domain-model
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-16
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest 9.0.2` |
| **Config file** | none detected |
| **Quick run command** | `python3 -m pytest backend_api_python/tests/test_trading_hours.py -q` |
| **Full suite command** | `python3 -m pytest backend_api_python/tests -q` |
| **Estimated runtime** | ~25 seconds for phase-targeted suites; full backend suite is a blocking final gate |

---

## Sampling Rate

- **After every task commit:** Run the narrowest affected phase-targeted test file, for example `python3 -m pytest backend_api_python/tests/test_data_sufficiency_types.py -q` or `python3 -m pytest backend_api_python/tests/test_data_sufficiency_validator.py -q`.
- **After every plan wave:** Run `python3 -m pytest backend_api_python/tests/test_trading_hours.py backend_api_python/tests/test_data_sufficiency_types.py backend_api_python/tests/test_ibkr_schedule_provider.py backend_api_python/tests/test_data_sufficiency_integration.py -q` for Plan 01, and `python3 -m pytest backend_api_python/tests/test_data_sufficiency_validator.py backend_api_python/tests/test_data_sufficiency_logging.py backend_api_python/tests/test_data_sufficiency_service.py backend_api_python/tests/test_data_sufficiency_integration.py -q` for Plan 02
- **Before `/gsd-verify-work`:** `python3 -m pytest backend_api_python/tests -q` must be green.
- **Max feedback latency:** 25 seconds for phase-targeted suites

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-T1 | 01 | 1 | Typed contract + bounded diagnostics + seconds semantics | T-01-02 | Stable enum values + bounded diagnostics prevent ad-hoc payload drift | unit | `python3 -m pytest backend_api_python/tests/test_data_sufficiency_types.py -q` | ❌ W0 | ⬜ pending |
| 01-01-T2 | 01 | 1 | IBKR schedule adapter over public `trading_hours` seam | T-01-01 | Preserve `schedule_unknown` vs known closed/open; surface timezone fallback metadata | unit | `python3 -m pytest backend_api_python/tests/test_ibkr_schedule_provider.py backend_api_python/tests/test_trading_hours.py -q` | ❌ W0 | ⬜ pending |
| 01-01-T3 | 01 | 1 | Plan 01 integration + regression gate | T-01-ALL | Contract + adapter + integration + existing schedule suite green | integration | `python3 -m pytest backend_api_python/tests/test_data_sufficiency_types.py backend_api_python/tests/test_ibkr_schedule_provider.py backend_api_python/tests/test_data_sufficiency_integration.py backend_api_python/tests/test_trading_hours.py -q` | ❌ W0 | ⬜ pending |
| 01-02-T1 | 02 | 2 | Pure validator + kline-derived bar counting + precedence | T-01-04 | Deterministic precedence; no logging side effects in validator | unit | `python3 -m pytest backend_api_python/tests/test_data_sufficiency_validator.py -q` | ❌ W0 | ⬜ pending |
| 01-02-T2 | 02 | 2 | Structured logging payload + emit helper | T-01-05 | Stable `ibkr_data_sufficiency_check` fields; no raw broker blobs | unit | `python3 -m pytest backend_api_python/tests/test_data_sufficiency_logging.py -q` | ❌ W0 | ⬜ pending |
| 01-02-T3 | 02 | 2 | Orchestration service + end-to-end emission + regression gate | T-01-07 | Single emission per evaluation; orchestration owns side effects | integration | `python3 -m pytest backend_api_python/tests/test_data_sufficiency_validator.py backend_api_python/tests/test_data_sufficiency_logging.py backend_api_python/tests/test_data_sufficiency_service.py backend_api_python/tests/test_data_sufficiency_integration.py -q` | ❌ W0 | ⬜ pending |
| 01-XX-FULL | all | all | Full phase regression gate | T-01-ALL | All Phase 1 use cases and backend regression suite pass before verification | integration | `python3 -m pytest backend_api_python/tests -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend_api_python/tests/test_data_sufficiency_types.py` — typed contract and enum/reason-code cases
- [ ] `backend_api_python/tests/test_data_sufficiency_validator.py` — sufficiency classification, lookback, schedule-known vs unknown, edge-case matrix
- [ ] `backend_api_python/tests/test_ibkr_schedule_provider.py` — adapter behavior over current `trading_hours` seam
- [ ] `backend_api_python/tests/test_data_sufficiency_logging.py` — structured log payload assertions
- [ ] `backend_api_python/tests/test_data_sufficiency_service.py` — orchestration wiring + single-emission behavior
- [ ] `backend_api_python/tests/test_data_sufficiency_integration.py` — adapter/service end-to-end checks
- [ ] Every implementation task must include explicit use-case specifications and expected outputs in its acceptance criteria / verify steps

---

## Manual-Only Verifications

All phase behaviors should have automated verification. No manual-only validation is expected for this phase.

---

## RE-REVIEW additions (2026-04-17)

Cross-AI RE-REVIEW feedback is folded into `01-01-PLAN.md`, `01-02-PLAN.md`, and phase carryover bullets in `.planning/ROADMAP.md` (Phases 2–4). Validation expectations below augment the per-task map.

| Topic | Expectation |
|-------|-------------|
| Float seconds | Assertions on `effective_lookback` / `missing_window` use epsilon (`abs(a-b) < 1e-6` or documented equivalent), not bare `==` on floats. |
| Timeframe map | `TIMEFRAME_SECONDS_MAP` (or equivalent) exists in repo and is referenced by validator tests (`test_effective_lookback_seconds_boundary`). |
| Adapter next open | `test_next_session_open_utc_populated` green in adapter suite. |
| Validator purity | Static or import-time checks per plan: no `logging`, no `kline_fetcher` import in `data_sufficiency_validator.py`. |
| `get_kline` errors | `test_get_kline_raises_documented_behavior` documents chosen propagation contract. |
| Integration mock fidelity | `test_adapter_to_service_emits_ibkr_data_sufficiency_check` uses LOWER_LEVELS-plausible mock; production drift additionally tracked in ROADMAP Phase 2. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s for phase-targeted suites
- [ ] Every task defines explicit use-case specifications
- [ ] Every task includes a verify step that runs the full relevant use-case suite
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
