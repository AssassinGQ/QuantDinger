---
phase: 2
slug: forex-contract-creation-idealpro
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-09
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 (project existing) |
| **Config file** | none — default pytest discovery in `tests/` |
| **Quick run command** | `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -x -q` |
| **Full suite command** | `cd backend_api_python && python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend_api_python && python -m pytest tests/test_ibkr_client.py tests/test_ibkr_symbols.py -x -q` (IBKR client + symbols tests)
- **After every plan wave:** Run `cd backend_api_python && python -m pytest tests/ -x -q` (full ~845 test suite)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Use Cases & Specifications

| Use Case | Specification | Test ID |
|----------|---------------|---------|
| UC-1: Forex pair creates correct contract | Given symbol="EURUSD", market_type="Forex", `_create_contract` returns Forex with secType=CASH, symbol=EUR, currency=USD, exchange=IDEALPRO | CONT-01a |
| UC-2: Cross pair (JPY quote) creates correct contract | Given symbol="USDJPY", market_type="Forex", `_create_contract` returns Forex with symbol=USD, currency=JPY, exchange=IDEALPRO | CONT-01b |
| UC-3: USStock path unchanged | Given symbol="AAPL", market_type="USStock", `_create_contract` returns Stock with symbol=AAPL, exchange=SMART, currency=USD | CONT-01c |
| UC-4: HShare path unchanged | Given symbol="0700.HK", market_type="HShare", `_create_contract` returns Stock with symbol=700, exchange=SEHK, currency=HKD | CONT-01d |
| UC-5: Unknown market_type fails loudly | Given market_type="Crypto", `_create_contract` raises ValueError with message containing "Crypto" | CONT-01e |
| UC-6: Error propagation is safe | Given `_create_contract` raises ValueError, `place_market_order` catches and returns LiveOrderResult(success=False) without crashing | CONT-01f |

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | CONT-01a | unit | `python -m pytest tests/test_ibkr_client.py -k "test_create_contract_forex_eurusd" -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | CONT-01b | unit | `python -m pytest tests/test_ibkr_client.py -k "test_create_contract_forex_usdjpy" -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | CONT-01c | unit | `python -m pytest tests/test_ibkr_client.py -k "test_create_contract_usstock_regression" -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 1 | CONT-01d | unit | `python -m pytest tests/test_ibkr_client.py -k "test_create_contract_hshare_regression" -x` | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 1 | CONT-01e | unit | `python -m pytest tests/test_ibkr_client.py -k "test_create_contract_unknown_raises" -x` | ❌ W0 | ⬜ pending |
| 02-01-06 | 01 | 1 | CONT-01f | unit | `python -m pytest tests/test_ibkr_client.py -k "test_place_order_unknown_market_type_graceful" -x` | ❌ W0 | ⬜ pending |
| 02-01-07 | 01 | 1 | REGR | full suite | `python -m pytest tests/ -x -q` (845+ tests) | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `MockForex` class added to `_make_mock_ib_insync()` helper in `test_ibkr_client.py`
- [ ] New test class `TestCreateContractForex` in `test_ibkr_client.py` covering CONT-01a through CONT-01f
- No framework install needed — pytest 9.0.2 already in project

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
