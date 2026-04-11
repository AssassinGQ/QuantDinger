---
phase: 01-forex-symbol-normalization
verified: 2026-04-09T14:30:00Z
status: passed
score: 13/13 must-haves verified
re_verification: false
---

# Phase 01: Forex symbol normalization — Verification Report

**Phase goal:** All supported Forex symbol spellings resolve to a single internal base+quote representation so downstream code never defaults Forex to US `Stock`.

**Verified:** 2026-04-09T14:30:00Z  
**Status:** passed  
**Re-verification:** No — initial verification (no prior `*-VERIFICATION.md` in phase directory).

**Tooling note:** `gsd-tools.cjs verify artifacts` / `verify key-links` returned `No must_haves.artifacts found` for `01-01-PLAN.md` (frontmatter parser mismatch). Artifact and link checks below were performed manually against the PLAN YAML.

## Goal Achievement

### Observable Truths (from `01-01-PLAN.md` `must_haves.truths`)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `normalize_symbol('EURUSD', 'Forex')` → `('EURUSD', 'IDEALPRO', 'USD')` | ✓ VERIFIED | `symbols.py` L51–58; `test_ibkr_symbols.py` `test_6char_uppercase` |
| 2 | `normalize_symbol('EUR/USD', 'Forex')` → same tuple | ✓ VERIFIED | `test_separator_and_case_variants` |
| 3 | `normalize_symbol('EUR.USD', 'Forex')` → same | ✓ VERIFIED | same |
| 4 | `normalize_symbol('eurusd', 'Forex')` → canonical pair + IDEALPRO | ✓ VERIFIED | parametrize includes `eurusd` |
| 5 | `normalize_symbol('USDJPY', 'Forex')` → quote `JPY` | ✓ VERIFIED | `test_6char_uppercase` |
| 6 | `normalize_symbol('EU', 'Forex')` raises `ValueError` | ✓ VERIFIED | `test_invalid_forex_raises` + L53–56 |
| 7 | Forex path never returns `exchange='SMART'` | ✓ VERIFIED | `test_does_not_default_to_stock`; branch returns IDEALPRO only |
| 8 | `parse_symbol('EURUSD')` → `('EURUSD', 'Forex')` | ✓ VERIFIED | `test_detects_known_forex` |
| 9 | `parse_symbol('EUR/USD')` → `('EURUSD', 'Forex')` | ✓ VERIFIED | `test_detects_forex_with_separator` |
| 10 | `parse_symbol('0700.HK')` → HShare unchanged | ✓ VERIFIED | `test_hshare_not_confused_with_forex` / `test_hk_suffix` |
| 11 | `parse_symbol('AAPL')` → USStock | ✓ VERIFIED | `test_us_stock_not_confused_with_forex` / `test_us_stock` |
| 12 | `format_display_symbol('EURUSD', 'IDEALPRO')` → `EUR.USD` | ✓ VERIFIED | `test_forex_display` |
| 13 | USStock / HShare `normalize_symbol` unchanged | ✓ VERIFIED | `TestNormalizeSymbolRegression` |

**Score:** 13/13 truths verified (implementation + `tests/test_ibkr_symbols.py`).

**Automated run:** `cd backend_api_python && python -m pytest tests/test_ibkr_symbols.py -q` → **36 passed** (2026-04-09).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend_api_python/tests/test_ibkr_symbols.py` | ≥80 lines, Forex + regression | ✓ VERIFIED | 138 lines; 5 test classes; parametrize + `pytest.raises(..., match="Invalid Forex symbol")` |
| `backend_api_python/app/services/live_trading/ibkr_trading/symbols.py` | Forex in `normalize_symbol` / `parse_symbol` / `format_display_symbol` | ✓ VERIFIED | `KNOWN_FOREX_PAIRS`, `_clean_forex_raw`, `market_type == "Forex"`, `IDEALPRO`, `forex_clean in KNOWN_FOREX_PAIRS` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `ibkr_trading/symbols.py` | `ibkr_trading/client.py` | `_create_contract` | ✓ WIRED | `from ...symbols import normalize_symbol` (L24); `normalize_symbol(symbol, market_type)` (L782) |

### Requirements Coverage

| Requirement | Source plan | Description (REQUIREMENTS.md) | Status | Evidence |
|-------------|-------------|-------------------------------|--------|----------|
| **CONT-02** | `01-01-PLAN.md` `requirements` | `normalize_symbol` 支持 EURUSD / EUR.USD / EUR/USD 等解析为 base+quote | ✓ SATISFIED | 6 字符清洗后 `pair` + `pair[3:]` 为报价货币；分隔符与大小写用例由测试锁定 |

**Orphan check:** `REQUIREMENTS.md` traceability 表中映射到 Phase 1 的 v1 项仅有 **CONT-02**。本阶段 PLAN 的 `requirements` 仅声明 **CONT-02**，无未纳入 PLAN 的 Phase 1 需求 ID。

### Anti-Patterns

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | 在 `symbols.py` / `test_ibkr_symbols.py` 中未发现 TODO/FIXME/placeholder 级阻断问题 |

### Scope Boundary (not gaps for Phase 01)

- **`_create_contract`** 仍为 `ib_insync.Stock(...)`（`client.py` L780–783）。PLAN 已说明 Phase 2 再改为 `Forex` 合约（CONT-01）。本阶段目标为 **归一化元组** 不再走 `SMART` 默认，而非合约类型切换。
- **`parse_symbol` / `format_display_symbol`（IBKR）** 目前除测试与包导出外，生产路径未调用；与 PLAN 交付一致，后续路由/UI 可接入。

### Human Verification Required

本阶段以纯函数与单测为主，无强制人工用例。若需端到端确认，可在 Phase 2（CONT-01）合并后，在纸面账户上验证 Forex 合约构造与 `normalize_symbol` 输出一致。

### Gaps Summary

无。阶段目标与 CONT-02 在代码库中有可执行证据（实现 + 36 项测试通过）。

---

_Verified: 2026-04-09T14:30:00Z_  
_Verifier: Claude (gsd-verifier)_
