---
phase: 16-precious-metals-contract-classification
verified: 2026-04-12T12:00:00Z
status: passed
score: 3/3 roadmap criteria + TRADE-04 + all plan must_haves verified
re_verification: false
---

# Phase 16: Precious metals contract classification — Verification Report

**Phase goal:** XAUUSD/XAGUSD use the correct IB product type (e.g. CMDTY/SMART vs Forex CASH/IDEALPRO) with validated qualify results.

**Verified:** 2026-04-12  
**Status:** passed  
**Re-verification:** No — initial verification (no prior `*VERIFICATION.md` in this directory).

## Goal Achievement

### ROADMAP success criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | XAUUSD (and documented XAGUSD handling) routes through `_create_contract` / validation distinct from standard IDEALPRO Forex pairs | ✓ VERIFIED | `client.py`: `Forex` → `ib_insync.Forex(pair=...)`; `Metals` → `Contract(symbol=..., secType="CMDTY", exchange=SMART, currency=...)` from `normalize_symbol` (`symbols.py` L68–75). Tests: `test_ibkr_client.py` `TestUC16T3Client`, `TestPlaceMarketOrderForex` XAUUSD Metals, smoke/E2E XAGUSD CMDTY. |
| 2 | Post-qualify validation rejects wrong `secType`/routing when IB returns unexpected shapes | ✓ VERIFIED | `_validate_qualified_contract` (`client.py` L922–929): compares `contract.secType` to `_EXPECTED_SEC_TYPES["Metals"]=="CMDTY"`. Failure returns `Expected secType=CMDTY for Metals, got ...`. Qualify cache invalidated on validation failure (`place_market_order` L1196–1199). Test `test_uc_16_t3_04` asserts STK rejected. |
| 3 | Metals paths remain separable from EURUSD-style Forex so logs and positions show the correct instrument class | ✓ VERIFIED | **Orders:** `IBKROrderContext.market_type` and `market_category` set for Metals (`client.py` L1240–1245). **Runner:** `stateful_runner.py` resolves `market_type` from `ctx.market_category` / payload / exchange_config and passes `market_type=` and `market_category=` into `place_market_order`. **RTH:** closed-reason text differs Forex vs Metals (L1148–1157). **IB positions:** `ibkr_save_position` persists `sec_type`, `exchange` from contract (`client.py` / `records.py`) — CMDTY/SMART vs CASH/IDEALPRO distinguishable in `qd_ibkr_pnl_single`. |

**Score:** 3/3 roadmap criteria verified in code and tests.

### Plan must-haves (16-01)

| Truth | Status | Evidence |
|-------|--------|----------|
| `parse_symbol` maps XAUUSD/XAGUSD to Metals | ✓ | `_is_precious_metal_pair` + branch before `KNOWN_FOREX_PAIRS` (`symbols.py` L124–128) |
| XAUEUR → non-Forex path | ✓ | Excluded in `_is_precious_metal_pair` (L40–41); not in `KNOWN_FOREX_PAIRS`; falls through to USStock (L131) |
| `normalize_symbol(Metals)` → SMART + full pair | ✓ | L68–75: `(pair, "SMART", pair[3:6])` |
| XAUUSD/XAGUSD/XAUEUR removed from `KNOWN_FOREX_PAIRS` | ✓ | Set does not list them; comment L22 references CMDTY/SMART |
| Artifacts substantive + wired | ✓ | `symbols.py` imported by `client.py` (`normalize_symbol` in `_create_contract`). Tests: `test_uc_16_t1_01` … `test_uc_16_t1_10` present |

### Plan must-haves (16-02)

| Truth | Status | Evidence |
|-------|--------|----------|
| `_create_contract` CMDTY for Metals | ✓ | L846–852 |
| `_EXPECTED_SEC_TYPES['Metals']=='CMDTY'` | ✓ | L915–919 |
| `place_*` aligned≤0 copy for Metals | ✓ | L1212–1217, L1301–1306 (troy ounce, sizeIncrement/minSize 1.0, ~3200 / ~32) |
| IOC TIF + `map_signal_to_side` like Forex for Metals | ✓ | `_get_tif_for_signal` L177–178; `map_signal_to_side` L210–214 |
| `get_market_pre_normalizer('Metals')` → `ForexPreNormalizer` | ✓ | `order_normalizer/__init__.py` L53–55 |

**Key link:** `place_market_order` imports and calls `get_market_pre_normalizer(market_type)` (L1177–1181) — Metals branch does not raise.

### Plan must-haves (16-03)

| Truth | Status | Evidence |
|-------|--------|----------|
| Engine tests include Metals | ✓ | `test_exchange_engine.py`: frozenset assertion + `test_uc_16_t5_01` / `test_uc_16_t5_02` |
| Strategy API ibkr-paper + Metals | ✓ | `test_strategy_exchange_validation.py`: `_metals_payload`, `test_uc_16_t5_03` |
| Smoke/E2E XAGUSD Metals + CMDTY | ✓ | `test_ibkr_forex_paper_smoke.py` (CMDTY, `market_type="Metals"`); `test_forex_ibkr_e2e.py` (`market_category: Metals`, contract asserts) |

### Required Artifacts

| Artifact | Expected | Status |
|----------|----------|--------|
| `ibkr_trading/symbols.py` | Metals parse/normalize/display | ✓ Present, substantive |
| `ibkr_trading/client.py` | CMDTY path, validation, TIF, messages | ✓ Wired into qualify + orders |
| `order_normalizer/__init__.py` | Metals factory | ✓ Wired |
| Test modules per plans | UC-named tests | ✓ Greps confirm `test_uc_16_t1_*`, `test_uc_16_t2_*`, `test_uc_16_t3_*`, `test_uc_16_t5_*`, integration tests |

### Key Link Verification (manual; gsd-tools returned no parsed `must_haves` for `verify artifacts`)

| From | To | Via | Status |
|------|-----|-----|--------|
| `parse_symbol` | Metals vs Forex | `_is_precious_metal_pair` before `KNOWN_FOREX_PAIRS` | ✓ |
| `place_market_order` | `get_market_pre_normalizer` | `market_type` argument | ✓ |
| `StatefulClientRunner.execute` | `place_market_order(..., market_type=..., market_category=...)` | `stateful_runner.py` L77–89 | ✓ |

### Requirements Coverage

| Requirement | Declared in plans | Description (REQUIREMENTS.md) | Status | Evidence |
|-------------|-------------------|-------------------------------|--------|----------|
| **TRADE-04** | 16-01, 16-02, 16-03 | 贵金属合约创建——XAUUSD/XAGUSD 正确 secType（CMDTY/SMART），与 Forex CASH/IDEALPRO 分开路由 | ✓ SATISFIED | Symbol layer Metals; client CMDTY/SMART + post-qualify check; normalizer; engine/strategy/smoke/E2E tests. Traceability table maps TRADE-04 → Phase 16 Complete. |

No orphaned Phase-16 requirement IDs: all plans cite only TRADE-04; REQUIREMENTS.md maps TRADE-04 to Phase 16 with implementation coverage above.

### Anti-Patterns

| File | Pattern | Severity | Notes |
|------|---------|----------|-------|
| — | TODO/FIXME in `symbols.py` / `client.py` (metals paths) | — | None found |

### Human Verification (optional)

| # | Test | Expected | Why human |
|---|------|----------|-----------|
| 1 | Paper account: qualify + market order XAUUSD/XAGUSD as Metals | IB accepts CMDTY/SMART; fills as commodity | Live IB behavior, venue hours, and account permissions are outside pytest mocks. |
| 2 | Compare portfolio row for XAUUSD vs EURUSD | `secType` CMDTY vs CASH; exchange SMART vs IDEALPRO | UI/Workstation display not covered by backend-only verification. |

Automated: user reports full backend suite **992 passed, 11 skipped, 0 failed** — aligns with regression gate.

### Gaps Summary

None. Phase goal and TRADE-04 are implemented with tests at unit, client, and integration layers; no stubbed or unwired metals paths found in reviewed code.

---

_Verified: 2026-04-12_  
_Verifier: Claude (gsd-verifier)_
