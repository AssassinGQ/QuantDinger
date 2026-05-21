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
| **Quick run command** | `cd backend_api_python && pytest tests/test_ibkr_symbols.py tests/test_ibkr_client.py tests/test_order_normalizer.py -q --tb=short -x` |
| **Full suite command** | `cd backend_api_python && pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run the quick run command above (expand with modules touched in that task).
- **After every plan wave:** Run `cd backend_api_python && pytest` (or the wave’s combined modules per table below).
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

Aligned with `16-01-PLAN.md`, `16-02-PLAN.md`, `16-03-PLAN.md` (task order and waves).

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Notes |
|---------|------|------|-------------|-----------|-------------------|-------|
| 16-01-T1 | 01 | 1 | TRADE-04 | unit | `cd backend_api_python && pytest tests/test_ibkr_symbols.py -q --tb=short -x` | Single merged task: `symbols.py` + UC `test_uc_16_t1_01`…`10` |
| 16-02-T1 | 02 | 2 | TRADE-04 | unit | `cd backend_api_python && pytest tests/test_order_normalizer.py -q --tb=short -k "metals or Metals or uc_16_t2" -x` | `get_market_pre_normalizer("Metals")` |
| 16-02-T2 | 02 | 2 | TRADE-04 | smoke | `cd backend_api_python && python -c "from app.services.live_trading.ibkr_trading.client import IBKRClient; assert 'Metals' in IBKRClient.supported_market_categories; assert IBKRClient._EXPECTED_SEC_TYPES.get('Metals')=='CMDTY'"` | Full UC-16-T3-xx pytest proof is **16-02-T3** |
| 16-02-T3 | 02 | 2 | TRADE-04 | unit | `cd backend_api_python && pytest tests/test_ibkr_client.py -q --tb=short -x` | `test_uc_16_t3_01` … `test_uc_16_t3_08` + migrations |
| 16-03-T1 | 03 | 3 | TRADE-04 | integration | `cd backend_api_python && pytest tests/test_exchange_engine.py tests/test_strategy_exchange_validation.py -q --tb=short -k "uc_16_t5 or Metals or test_uc_sa_val" -x` | UC-16-T5-xx |
| 16-03-T2 | 03 | 3 | TRADE-04 | integration | `cd backend_api_python && pytest tests/test_ibkr_forex_paper_smoke.py -q --tb=short -x` | XAGUSD CMDTY smoke |
| 16-03-T3 | 03 | 3 | TRADE-04 | integration | `cd backend_api_python && pytest tests/test_forex_ibkr_e2e.py -q --tb=short -x` | XAGUSD E2E Metals |

*Status (optional tracking): ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ibkr_symbols.py` — `test_metals_detected_as_metals` + `test_uc_16_t1_01` … `test_uc_16_t1_10` (plan 16-01 single task)
- [ ] `tests/test_ibkr_client.py` — Metals CMDTY / `test_uc_16_t3_*` (plan 16-02 Task 3)
- [ ] Existing framework covers remaining modules

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|---------------------|
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
