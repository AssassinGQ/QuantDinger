---
phase: 15
slug: normalize-pipeline-ordering
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-12
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | none (uses defaults) |
| **Quick run command** | `cd backend_api_python && python3 -m pytest tests/test_order_normalizer.py tests/test_ibkr_client.py::TestQuantityGuard tests/test_ibkr_client.py::TestIBKRPreNormalizePipeline -x` |
| **Full suite command** | `cd backend_api_python && python3 -m pytest` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run `cd backend_api_python && python3 -m pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 15-01 T1 | 01 | 1 | INFRA-03 | inline assertions (TC-15-T1-01–T1-09) | `python3 -c "..."` (see plan) | N/A (inline) | ⬜ pending |
| 15-01 T2 | 01 | 1 | INFRA-03 | unit (TC-15-T5-01, T5-03, T1-01–T1-09) | `pytest tests/test_order_normalizer.py -v` | ✅ (update) | ⬜ pending |
| 15-02 T1 | 02 | 2 | INFRA-03 | grep + compileall | `rg` + `compileall` (see plan) | N/A | ⬜ pending |
| 15-02 T2 | 02 | 2 | INFRA-03 | unit+mock (TC-15-T2-01–T2-06, T6-01–T6-02) | `pytest tests/test_ibkr_client.py::TestQuantityGuard tests/test_ibkr_client.py::TestIBKRPreNormalizePipeline -v` | ✅ (update+new) | ⬜ pending |
| 15-03 T1 | 03 | 2 | INFRA-03 | grep (TC-15-T3-01, T3-02) | `rg` (see plan) | N/A | ⬜ pending |
| 15-03 T2 | 03 | 2 | INFRA-03 | unit (TC-15-T3-03) | `pytest tests/test_signal_executor.py::TestSignalExecutorMarketPreNormalize -v` | ❌ (new) | ⬜ pending |
| 15-04 T1 | 04 | 3 | INFRA-03 | filesystem + grep (TC-15-T4-01) | `test ! -f ... && ! rg ...` (see plan) | N/A | ⬜ pending |
| 15-04 T2 | 04 | 3 | INFRA-03 | unit (TC-15-T4-02, T5-02) | `pytest tests/test_order_normalizer.py -v` | ✅ (update) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## TC-15 Coverage Matrix

All 25 test cases from RESEARCH.md mapped to plan tasks:

| TC ID | Description | Plan | Task | Verify Type |
|-------|-------------|------|------|-------------|
| TC-15-T1-01 | Import MarketPreNormalizer as ABC | 15-01 | T1 | inline assertion |
| TC-15-T1-02 | USStock pre_normalize(7.8) → 7 | 15-01 | T1 | inline assertion |
| TC-15-T1-03 | USStock pre_check(3.5) → (False, "whole number") | 15-01 | T1 | inline assertion |
| TC-15-T1-04 | HShare pre_normalize(450.0, "00005") → 400 | 15-01 | T1 | inline assertion |
| TC-15-T1-05 | Forex pre_normalize passthrough | 15-01 | T1 | inline assertion |
| TC-15-T1-06 | Crypto pre_normalize passthrough | 15-01 | T1 | inline assertion |
| TC-15-T1-07 | Factory HShare → HSharePreNormalizer | 15-01 | T1 | inline assertion |
| TC-15-T1-08 | Factory "" → USStockPreNormalizer | 15-01 | T1 | inline assertion |
| TC-15-T1-09 | Factory None → USStockPreNormalizer | 15-01 | T1 | inline assertion |
| TC-15-T2-01 | Market order 7.8 USStock → success, qty=7 | 15-02 | T2 | pytest |
| TC-15-T2-02 | Limit order 3.5 USStock → success, qty=3 | 15-02 | T2 | pytest |
| TC-15-T2-03 | Negative qty → fail, no placeOrder | 15-02 | T2 | pytest |
| TC-15-T2-04 | HShare 3 on 00005 → fail, "400" | 15-02 | T2 | pytest |
| TC-15-T2-05 | Pipeline order: pre_normalize → pre_check → qualify | 15-02 | T2 | pytest |
| TC-15-T2-06 | Align receives normalized qty (7, not 7.8) | 15-02 | T2 | pytest |
| TC-15-T3-01 | signal_executor.py has get_market_pre_normalizer | 15-03 | T1 | grep |
| TC-15-T3-02 | signal_executor.py has pre_normalize, no normalize | 15-03 | T1 | grep |
| TC-15-T3-03 | Enqueue amount matches pre_normalize output | 15-03 | T2 | pytest |
| TC-15-T4-01 | No production ibkr_trading.order_normalizer imports | 15-04 | T1 | grep |
| TC-15-T4-02 | importlib raises ModuleNotFoundError | 15-04 | T2 | pytest |
| TC-15-T5-01 | test_order_normalizer.py docstring mentions MarketPreNormalizer | 15-01 | T2 | grep + pytest |
| TC-15-T5-02 | TestBackwardCompatImport removed | 15-04 | T2 | grep + pytest |
| TC-15-T5-03 | TestGetMarketPreNormalizer exists with new names | 15-01 | T2 | grep + pytest |
| TC-15-T6-01 | Market order fractional → success (same as T2-01) | 15-02 | T2 | pytest |
| TC-15-T6-02 | Limit order fractional → success (same as T2-02) | 15-02 | T2 | pytest |

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-12
