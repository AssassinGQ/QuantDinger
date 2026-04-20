---
phase: 03
slug: alerting-and-user-decision-support
status: draft
nyquist_compliant: false
wave_0_complete: true
created: 2026-04-18
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing backend suite) |
| **Config file** | none — reuse `backend_api_python/tests/conftest.py` |
| **Quick run command** | `python3 -m pytest backend_api_python/tests/test_ibkr_insufficient_user_alert.py -q` (after Wave 1 creates file) |
| **Full suite command** | `python3 -m pytest backend_api_python/tests -q` |
| **Estimated runtime** | ~120–300 seconds (includes e2e modules; CI may scope markers later) |

---

## Sampling Rate

- **After every task commit:** Run the task’s first `<automated>` line (focused tests), then **通过全量用例** = second line `python3 -m pytest backend_api_python/tests -q` MUST exit 0.
- **After every plan wave:** Full suite command above.
- **Before `/gsd-verify-work`:** Full suite green.

---

## Per-Task Verification Map

> 以各 `*-PLAN.md` 的 `<verify>` 为准；本表摘要命令。

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | R4/R5/N3 | T-webhook-leak | No raw webhook URLs in extra | compile + full | `compileall` + `pytest backend_api_python/tests` | ⬜ W1 | ⬜ pending |
| 03-01-02 | 01 | 1 | N3 | — | Structured log only after dispatch gate | unit + full | `pytest …/test_data_sufficiency_logging.py` + full | ⬜ W1 | ⬜ pending |
| 03-01-03 | 01 | 1 | R4/R5 | — | Hook wired; executor tests | integration + full | `pytest …/test_signal_executor.py` + full | ⬜ W1 | ⬜ pending |
| 03-02-01 | 02 | 2 | N4 | — | Dedup matrix | unit + full | `pytest …/test_ibkr_insufficient_user_alert.py` + full | ⬜ W2 | ⬜ pending |
| 03-02-02 | 02 | 2 | N4 | — | N3 payload shape | unit + full | `pytest …/test_data_sufficiency_logging.py` + full | ⬜ W2 | ⬜ pending |
| 03-02-03 | 02 | 2 | N4 | — | Executor notify integration | integration + full | `pytest …/test_signal_executor.py` + full | ⬜ W2 | ⬜ pending |
| 03-02-04 | 02 | 2 | ROADMAP copy | — | Docstring carryover | unit + full | `pytest …/test_ibkr_insufficient_user_alert.py` + full | ⬜ W2 | ⬜ pending |

---

## Wave 0 Requirements

- [x] Existing infrastructure covers phase requirements (`backend_api_python/tests/`, `conftest.py`).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real SMTP / Twilio delivery | R4 | External credentials | Staging: configure strategy `notification_config` and trigger one live block in paper account |

*If none automated: operator smoke only.*

---

## Validation Sign-Off

- [ ] All tasks include second verify line = full `backend_api_python/tests` suite
- [ ] Sampling continuity maintained
- [ ] `nyquist_compliant: true` after execution wave sign-off

**Approval:** pending
