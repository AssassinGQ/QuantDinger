---
phase: "04"
slug: hardening-and-rollout-safety
status: draft
nyquist_compliant: true
wave_0_complete: true
created: "2026-04-18"
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for Phase 4 (hardening + rollout).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Python 3.x) |
| **Config file** | `backend_api_python/pytest.ini` / project defaults |
| **Quick run command** | `python3 -m pytest backend_api_python/tests/path/to/test_module.py -q` |
| **Full suite command** | `python3 -m pytest backend_api_python/tests -q` |
| **Estimated runtime** | ~several minutes (machine-dependent) |

---

## Sampling Rate

- **After every task completion:** Run **full suite** command below (mandatory per phase plans).
- **Before `/gsd-verify-work`:** Full suite must be green.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|--------|
| 04-01-T1 | 01 | 1 | N3 / D-02 | TM-LOG-01 | No secrets in structured payloads | integration | `python3 -m pytest backend_api_python/tests -q` | pending |
| 04-01-T2 | 01 | 1 | D-05/D-06 | TM-ENV-01 | Kill-switch documented; default safe | integration | `python3 -m pytest backend_api_python/tests -q` | pending |
| 04-01-T3 | 01 | 1 | ROADMAP carryover | TM-CONST-01 | Typed constants reduce misconfiguration | unit | `python3 -m pytest backend_api_python/tests -q` | pending |
| 04-02-T1 | 02 | 1 | N2 / D-03/D-04 | TM-RETRY-01 | Exhaust → fail-safe via guard | integration | `python3 -m pytest backend_api_python/tests -q` | pending |
| 04-02-T2 | 02 | 1 | N4 | TM-TEST-01 | Replay retry behavior | unit | `python3 -m pytest backend_api_python/tests -q` | pending |
| 04-02-T3 | 02 | 1 | D-07 | — | Documentation only | manual review | Full pytest still after any code touch | pending |

---

## Wave 0 Requirements

Existing infrastructure covers Phase 04 — **no Wave 0 install**.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|---------------------|
| Production log queries | D-01 | Requires ELK/Loki stack | Run saved queries for `event` × `reason_code` × `exchange_id` after deploy |

---

## Validation Sign-Off

- [ ] Every task `<verify>` includes **full** `python3 -m pytest backend_api_python/tests -q`
- [ ] `nyquist_compliant: true` when research + validation strategy present

**Approval:** pending
