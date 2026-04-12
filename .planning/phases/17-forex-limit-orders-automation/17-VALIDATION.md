---
phase: 17
slug: forex-limit-orders-automation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-12
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (project standard) |
| **Config file** | `backend_api_python/tests/conftest.py` |
| **Quick run command** | `cd backend_api_python && pytest tests/test_ibkr_client.py tests/test_ibkr_order_callback.py -x -q` |
| **Full suite command** | `cd backend_api_python && pytest` |
| **Estimated runtime** | ~30 seconds (quick) / ~120 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run quick command for touched modules
- **After every plan wave:** Run full suite
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 17-01-T1 | 01 | 1 | TRADE-01 | unit | `pytest tests/test_ibkr_client.py -k "limit or tif or mintick or snap" -x` | ❌ W0 | ⬜ pending |
| 17-02-T1 | 02 | 2 | TRADE-02 | unit | `pytest tests/test_ibkr_order_callback.py tests/test_ibkr_client.py -x` | ❌ W0 | ⬜ pending |
| 17-02-T2 | 02 | 2 | TRADE-02 | unit | `pytest tests/test_ibkr_order_callback.py -x` | ❌ W0 | ⬜ pending |
| 17-02-T3 | 02 | 2 | TRADE-02 | manual | Paper port 4004 observation | N/A | ⬜ pending |
| 17-03-T1 | 03 | 2 | TRADE-03 | unit | `pytest tests/test_pending_order_enqueuer.py tests/test_signal_executor_limit_enqueue.py -x` | ❌ W0 | ⬜ pending |
| 17-03-T2 | 03 | 2 | TRADE-03 | unit | `pytest tests/test_stateful_runner_execute.py -x` | ❌ W0 | ⬜ pending |
| 17-03-T3 | 03 | 2 | TRADE-03 | unit | `pytest tests/test_pending_order_worker.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Extend `tests/test_ibkr_client.py` — TIF limit DAY + minTick BUY floor / SELL ceil snap cases (UC-01a–g)
- [ ] Extend `tests/test_ibkr_order_callback.py` — PartiallyFilled cumulative overwrite, monotonic/sum invariants (UC-02c–g)
- [ ] New `tests/test_pending_order_fill_snapshot.py` — DB snapshot helper args (UC-02a/b)
- [ ] New `tests/test_stateful_runner_execute.py` — limit OrderContext → place_limit_order (UC-03e/f)
- [ ] New/extend `tests/test_pending_order_enqueuer.py` — order_type + price enqueue (UC-03d)
- [ ] New `tests/test_signal_executor_limit_enqueue.py` — pip helper + limit price calc (UC-03a–c)
- [ ] New/extend `tests/test_pending_order_worker.py` — OrderContext.price parity (UC-03g/h)

*Existing infrastructure (conftest, fixtures) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Multi-fill Forex limit on paper | TRADE-02 | Requires live IBKR Forex session (market hours) | Place DAY limit via REST on paper (port 4004); verify sequential `orderStatus` logs show non-decreasing `filled` and `filled + remaining ≈ totalQuantity`. Do not commit credentials. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

---

*Phase: 17-forex-limit-orders-automation*
*Validation strategy created: 2026-04-12*
