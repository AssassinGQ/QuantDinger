---
phase: 18
slug: e2e-integration-testing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-12
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + Jest 27.5.1 |
| **Config file** | `backend_api_python/tests/conftest.py` (markers); `quantdinger_vue/jest.config.js` |
| **Quick run command** | `cd backend_api_python && pytest tests/test_<module>.py -q --tb=short -x` |
| **Full suite command** | `cd backend_api_python && pytest` + `cd quantdinger_vue && npm run test:unit` |
| **Estimated runtime** | ~30 seconds (backend) + ~10 seconds (frontend) |

---

## Sampling Rate

- **After every task commit:** Run targeted `pytest tests/test_<touched_module>.py -x --tb=short`
- **After every plan wave:** Run `cd backend_api_python && pytest` (full backend) + `cd quantdinger_vue && npm run test:unit` (if Vue touched)
- **Before `/gsd:verify-work`:** Full backend + frontend suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Aligned with plan structure (TBD — populated during planning).

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Notes |
|---------|------|------|-------------|-----------|-------------------|-------|
| 18-W0-T1 | W0 | 0 | INFRA | setup | `cd backend_api_python && python -c "from tests.helpers.ibkr_mocks import FakeEvent"` | Extract mock helpers to tests/helpers/ |
| 18-W0-T2 | W0 | 0 | INFRA | setup | `cd backend_api_python && pytest tests/test_forex_ibkr_e2e.py -q --tb=short -x` | Shared Flask fixture in conftest.py; existing tests still green |
| 18-P1-T1 | 01 | 1 | TRADE-05 | E2E | `cd backend_api_python && pytest tests/test_e2e_qualify_cache_ibkr.py -q --tb=short -x` | Qualify cache: hit/miss/TTL/invalidation/reconnect |
| 18-P2-T1 | 02 | 1 | TRADE-06 | E2E | `cd backend_api_python && pytest tests/test_e2e_limit_cancel_errors_ibkr.py -q --tb=short -x` | Cancel scenarios + error paths |
| 18-P3-T1 | 03 | 2 | TRADE-05/06 | E2E | `cd backend_api_python && pytest tests/test_e2e_cross_market_usstock_hshare.py -q --tb=short -x` | USStock/HShare market + limit full chain |
| 18-P4-T1 | 04 | 2 | TEST-02 | integration | `cd backend_api_python && pytest tests/test_strategy_http_e2e.py -q --tb=short -x` | Flask test_client strategy CRUD + batch |
| 18-P5-T1 | 05 | 3 | TEST-02 | unit | `cd quantdinger_vue && npm run test:unit` | Vue Jest wizard component tests |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/helpers/__init__.py` + `tests/helpers/ibkr_mocks.py` — shared IBKR mock helpers (FakeEvent, _wire_ib_events, _make_qualify_for_pair, _fire_callbacks_after_fill, _make_mock_ib_insync, _make_ibkr_client_for_e2e)
- [ ] `tests/helpers/flask_strategy_app.py` — shared Flask app factory + login_required stub
- [ ] `tests/conftest.py` — shared Flask app fixture re-exporting helpers
- [ ] Existing `test_forex_ibkr_e2e.py` and `test_ibkr_forex_paper_smoke.py` updated to import from helpers (behavior unchanged)
- [ ] Full suite green after extraction: `cd backend_api_python && pytest`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Vue wizard renders correctly in browser | TEST-02 | Deferred — no Playwright per CONTEXT | Manual check: `npm run serve` + browser inspection |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
