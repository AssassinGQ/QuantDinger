# Phase 1: Forex symbol normalization - Research

**Researched:** 2026-04-09
**Domain:** Forex symbol parsing, normalization, and display for IBKR ib_insync integration
**Confidence:** HIGH

## Summary

Phase 1 is a pure-Python string-processing task: extend `symbols.py` in the IBKR trading module to handle Forex symbols. The existing file has 91 lines with three functions (`normalize_symbol`, `parse_symbol`, `format_display_symbol`) that currently only handle `USStock` and `HShare`. Adding a `Forex` branch to each function is straightforward — the main complexity is ensuring the return value tuple matches what `_create_contract` expects so that downstream can build `ib_insync.Forex(pair=...)` instead of `Stock(...)`.

The MT5 module (`mt5_trading/symbols.py`) already has a proven `FOREX_PAIRS` set and separator-stripping logic that can be referenced. The IBKR module needs its own Forex-aware version because the return signature is different (`Tuple[str, str, str]` for `(ib_symbol, exchange, currency)` vs MT5's plain string). The key risk — Forex defaulting to US Stock — is eliminated by adding an explicit `market_type == "Forex"` branch that raises `ValueError` on malformed input instead of falling through to the else clause.

**Primary recommendation:** Add a `Forex` branch to all three functions in `ibkr_trading/symbols.py`, returning `(pair_6char, "IDEALPRO", quote_currency)` for `normalize_symbol`. Test with the 14 known DB pairs plus edge cases (separators, case, invalid length). Do NOT touch `_create_contract` in this phase — Phase 2 handles that.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- DB中 Forex symbol 统一为 **6 字母大写连写**：`EURUSD`、`XAUUSD`、`GBPJPY` 等
- 也应兼容 `EUR.USD`、`EUR/USD`、`eurusd` 等分隔/小写格式（strip 分隔符 + 转大写）
- `normalize_symbol` 对 Forex 返回 `(pair_6char, "IDEALPRO", quote_currency)` 格式
- quote_currency 从 pair 后 3 位提取（如 EURUSD → USD，USDJPY → JPY）
- `_create_contract` 拿到返回值后用 `Forex(pair=ib_symbol)` 构造合约（Phase 2 处理）
- `market_type="Forex"` 但 symbol 格式异常时 **抛出 ValueError**
- 不静默降级为美股——这是最大风险点
- 不导致整个服务崩溃
- 必须保持 `normalize_symbol(symbol, market_type) -> Tuple[str, str, str]` 签名不变
- 必须保持 `parse_symbol(symbol) -> Tuple[str, Optional[str]]` 签名不变

### Claude's Discretion
- `parse_symbol` 自动检测 Forex 的具体逻辑（可参考 MT5 的 `FOREX_PAIRS` 集合或 6 字母全字母规则）
- `format_display_symbol` 对 Forex 的显示格式（建议 `EUR.USD` 点分隔，与 IBKR `localSymbol` 一致）
- 是否需要额外的辅助函数（如 `split_forex_pair` 提取 base/quote）

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CONT-02 | normalize_symbol 支持 Forex 符号格式（EURUSD, EUR.USD, EUR/USD）解析为 base+quote | Full research coverage: return format `(pair_6char, "IDEALPRO", quote_currency)`, separator stripping, case normalization, ValueError on malformed input, test matrix for all 14 DB pairs + edge cases |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (`re`, `str`) | 3.10+ | String parsing and normalization | No external deps needed for symbol parsing |
| pytest | (project existing) | Unit testing | Already used across project (93 tests in test_ibkr_client.py) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| ib_insync | 0.9.86 (installed) | Forex class reference and contract constants | Verified: `Forex(pair='EURUSD')` requires exactly 6 chars, asserts `len(pair) == 6`, splits into `symbol[:3]` + `currency[3:]`, default `exchange='IDEALPRO'` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hardcoded `FOREX_PAIRS` set | 6-char all-alpha heuristic | Set is more precise but needs maintenance; heuristic is open-ended but may false-positive on stock tickers like `GOOGLL`. **Recommendation: use both** — check set first, fall back to 6-char alpha for `parse_symbol` auto-detect |
| Manual separator strip | Regex `r'[./\-_ ]+'` | Regex is cleaner for multiple separators; manual `.replace()` chain (MT5 approach) is simpler and proven. **Recommendation: use `.replace()` chain** matching MT5 pattern |

## Architecture Patterns

### Target File Structure
```
backend_api_python/app/services/live_trading/ibkr_trading/
├── symbols.py          # Modified: add Forex branch to all 3 functions
├── client.py           # NOT modified in Phase 1 (Phase 2: _create_contract)
└── ...

backend_api_python/tests/
├── test_ibkr_symbols.py  # NEW: dedicated symbol tests (Forex + regression for existing)
├── test_ibkr_client.py   # existing: NOT modified
└── ...
```

### Pattern 1: Three-Function Symbol Pipeline

The existing code has a clear three-function pipeline that must be preserved:

1. **`normalize_symbol(symbol, market_type) → (ib_symbol, exchange, currency)`**
   - Called by `_create_contract` with explicit `market_type`
   - For Forex: return `(pair_6char, "IDEALPRO", quote_currency)`
   - Must raise `ValueError` on invalid Forex symbols

2. **`parse_symbol(symbol) → (clean_symbol, market_type)`**
   - Auto-detection without explicit `market_type`
   - For Forex: detect and return `(clean_6char, "Forex")`

3. **`format_display_symbol(ib_symbol, exchange) → str`**
   - Reverse mapping for display
   - For Forex: `EURUSD` → `EUR.USD` (matches IBKR `localSymbol` convention)

### Pattern 2: Normalize-then-Validate

```python
def normalize_symbol(symbol: str, market_type: str) -> Tuple[str, str, str]:
    symbol = (symbol or "").strip().upper()
    market_type = (market_type or "").strip()

    if market_type == "Forex":
        # Strip separators: "EUR/USD" → "EURUSD", "EUR.USD" → "EURUSD"
        pair = symbol.replace("/", "").replace(".", "").replace("-", "").replace("_", "").replace(" ", "")
        if len(pair) != 6 or not pair.isalpha():
            raise ValueError(
                f"Invalid Forex symbol '{symbol}': expected 6 letters (e.g. EURUSD), got '{pair}'"
            )
        quote_currency = pair[3:]
        return pair, "IDEALPRO", quote_currency

    # ... existing USStock / HShare branches unchanged ...
```

**Key design points:**
- Separator strip BEFORE length check (handles `EUR/USD` → `EURUSD`)
- `isalpha()` rejects symbols with digits/specials
- `ValueError` with descriptive message — never falls through to Stock default
- `quote_currency` is last 3 chars (e.g. EURUSD → USD, USDJPY → JPY)

### Pattern 3: parse_symbol Forex Auto-Detection

```python
KNOWN_FOREX_PAIRS = {
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
    "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD",
    "NZDJPY", "NZDCHF", "NZDCAD",
    "CADJPY", "CADCHF", "CHFJPY",
    "USDMXN", "USDZAR", "USDTRY", "USDHKD", "USDSGD",
    "XAUUSD", "XAGUSD", "XAUEUR",
}

def parse_symbol(symbol: str) -> Tuple[str, Optional[str]]:
    symbol = (symbol or "").strip().upper()
    clean = symbol.replace("/", "").replace(".", "").replace("-", "").replace("_", "").replace(" ", "")

    # Check known forex pairs first (includes metals like XAUUSD)
    if clean in KNOWN_FOREX_PAIRS:
        return clean, "Forex"

    # Heuristic: 6 letter all-alpha could be Forex
    # But don't match stock tickers — only trigger for unrecognized 6-char alpha
    # This is a weak heuristic; known set above is primary

    # ... existing HShare / USStock detection ...
```

**Decision (Claude's Discretion):** Use a `KNOWN_FOREX_PAIRS` set (subset of MT5's set, filtered to pairs tradeable on IDEALPRO) as primary detection. Do NOT use the 6-char-alpha heuristic in `parse_symbol` because it would false-positive on 6-letter stock tickers. The set approach is safer and matches the finite set of pairs the project actually trades.

### Pattern 4: format_display_symbol for Forex

```python
def format_display_symbol(ib_symbol: str, exchange: str) -> str:
    if exchange == "IDEALPRO":
        # Forex: "EURUSD" → "EUR.USD" (matches IBKR localSymbol convention)
        if len(ib_symbol) == 6 and ib_symbol.isalpha():
            return f"{ib_symbol[:3]}.{ib_symbol[3:]}"
        return ib_symbol
    # ... existing SEHK / default branches ...
```

**Rationale:** IBKR's `localSymbol` for qualified Forex contracts is dot-separated (e.g. `EUR.USD`). Using this as display format provides consistency with what traders see in TWS/Gateway.

### Anti-Patterns to Avoid
- **Falling through to Stock default:** The current `else` branch in `normalize_symbol` returns `(symbol, "SMART", "USD")`. For Forex, this would silently create a Stock contract for "EURUSD" ticker. Phase 1's primary job is to prevent this.
- **Assuming 3+3 split for all pairs:** While currently all Forex pairs are 3+3, the code should assert `len == 6` rather than hardcode positions beyond `pair[:3]` and `pair[3:]`.
- **Sharing state with MT5 module:** IBKR and MT5 symbol modules should remain independent. Reference MT5's patterns, but don't import from it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Forex pair validation | Custom regex parser | Known-pairs set + `len==6 and isalpha()` | Simple, explicit, maintainable; regex adds no value for this input space |
| Currency code validation | ISO 4217 lookup library | Hardcoded `KNOWN_FOREX_PAIRS` set | We only need to validate pairs the system trades, not arbitrary currencies |
| Symbol separator normalization | Custom state machine | `.replace()` chain (proven in MT5 module) | 5 chained `.replace()` calls handle all known separators; no edge cases require a parser |

**Key insight:** This is string normalization, not parsing. The input domain is well-bounded (14 known pairs + potential future additions). Simple set lookup + string manipulation is the correct abstraction level.

## Common Pitfalls

### Pitfall 1: Forex Symbol Silently Treated as US Stock
**What goes wrong:** If `market_type` is not checked for "Forex" or if Forex branch is missing, `normalize_symbol` falls to the `else` clause which returns `(symbol, "SMART", "USD")`. Downstream `_create_contract` builds a `Stock` contract. `qualifyContracts` either fails (good case) or finds an unrelated equity (catastrophic).
**Why it happens:** The current code has no Forex awareness at all.
**How to avoid:** Add explicit `market_type == "Forex"` branch BEFORE the `else` clause. Test that unknown market types raise or are handled explicitly.
**Warning signs:** Test `normalize_symbol("EURUSD", "Forex")` returning `("EURUSD", "SMART", "USD")`.

### Pitfall 2: Separator Stripping Inconsistency
**What goes wrong:** `normalize_symbol` strips separators but `parse_symbol` doesn't (or vice versa), leading to different results for `EUR.USD` depending on code path.
**Why it happens:** Two functions independently parse the same input format.
**How to avoid:** Extract a shared `_clean_forex_symbol(raw) → str` helper that both functions call. Or at minimum, use the identical `.replace()` chain in both.
**Warning signs:** `parse_symbol("EUR.USD")` returning `("EUR.USD", "USStock")` instead of `("EURUSD", "Forex")`.

### Pitfall 3: Dot-Separated Format Confused with HK Stock
**What goes wrong:** `parse_symbol("0700.HK")` correctly detects HShare, but `parse_symbol("EUR.USD")` could theoretically trigger HShare detection if `.HK`-suffix logic is checked after dot-strip.
**Why it happens:** Multiple detection heuristics applied to overlapping input formats.
**How to avoid:** In `parse_symbol`, check Forex BEFORE HShare, or ensure the separator-stripped version is used for Forex detection while the original is used for HShare `.HK` suffix check. Current code checks `.HK` suffix first which is fine — Forex detection should be added after HShare but before USStock default.
**Warning signs:** `parse_symbol("EUR.USD")` returning HShare.

### Pitfall 4: Not Testing `ValueError` on Malformed Forex Inputs
**What goes wrong:** Edge cases like `normalize_symbol("EU", "Forex")` or `normalize_symbol("EURUSD1", "Forex")` or `normalize_symbol("", "Forex")` silently pass or raise unexpected errors.
**Why it happens:** Happy-path testing only.
**How to avoid:** Explicit parameterized tests for: empty string, too short, too long, contains digits, contains special chars, None input.
**Warning signs:** Errors surfacing in production with cryptic stack traces instead of clear ValueError messages.

## Code Examples

### normalize_symbol — Forex Branch (Recommended Implementation)

```python
# Source: Verified against ib_insync 0.9.86 Forex class:
# Forex(pair='EURUSD') asserts len(pair) == 6, sets symbol=pair[:3], currency=pair[3:]
# default exchange='IDEALPRO'

SEPARATORS = "/.-_ "

def _clean_forex_raw(symbol: str) -> str:
    """Strip common separators and uppercase."""
    result = (symbol or "").strip().upper()
    for sep in SEPARATORS:
        result = result.replace(sep, "")
    return result


def normalize_symbol(symbol: str, market_type: str) -> Tuple[str, str, str]:
    symbol = (symbol or "").strip().upper()
    market_type = (market_type or "").strip()

    if market_type == "Forex":
        pair = _clean_forex_raw(symbol)
        if len(pair) != 6 or not pair.isalpha():
            raise ValueError(
                f"Invalid Forex symbol '{symbol}': "
                f"expected 6 letters after cleaning (e.g. EURUSD), got '{pair}'"
            )
        return pair, "IDEALPRO", pair[3:]

    elif market_type == "USStock":
        return symbol, "SMART", "USD"

    elif market_type == "HShare":
        ib_symbol = symbol
        if ib_symbol.endswith(".HK"):
            ib_symbol = ib_symbol[:-3]
        ib_symbol = ib_symbol.lstrip("0") or "0"
        return ib_symbol, "SEHK", "HKD"

    else:
        return symbol, "SMART", "USD"
```

### parse_symbol — Forex Auto-Detection

```python
KNOWN_FOREX_PAIRS = {
    # Major pairs
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    # Cross pairs
    "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
    "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD",
    "NZDJPY", "NZDCHF", "NZDCAD",
    "CADJPY", "CADCHF", "CHFJPY",
    # Exotic (common on IDEALPRO)
    "USDMXN", "USDZAR", "USDTRY", "USDHKD", "USDSGD",
    "USDNOK", "USDSEK", "USDDKK",
    "EURTRY", "EURMXN", "EURNOK", "EURSEK", "EURDKK", "EURPLN", "EURHUF", "EURCZK",
    # Metals (traded as CASH on IDEALPRO)
    "XAUUSD", "XAGUSD", "XAUEUR",
}


def parse_symbol(symbol: str) -> Tuple[str, Optional[str]]:
    symbol = (symbol or "").strip().upper()

    # HK stock: ends with .HK (check before Forex separator stripping)
    if symbol.endswith(".HK"):
        return symbol, "HShare"

    # All digits (likely HK stock code)
    clean = symbol.lstrip("0")
    if clean.isdigit() and len(clean) <= 5:
        return symbol, "HShare"

    # Forex: strip separators, check against known set
    forex_clean = _clean_forex_raw(symbol)
    if forex_clean in KNOWN_FOREX_PAIRS:
        return forex_clean, "Forex"

    # Default to US stock
    return symbol, "USStock"
```

### format_display_symbol — Forex Display

```python
def format_display_symbol(ib_symbol: str, exchange: str) -> str:
    if exchange == "SEHK":
        padded = ib_symbol.zfill(4)
        return f"{padded}.HK"
    if exchange == "IDEALPRO":
        if len(ib_symbol) == 6 and ib_symbol.isalpha():
            return f"{ib_symbol[:3]}.{ib_symbol[3:]}"
        return ib_symbol
    return ib_symbol
```

### Test Examples

```python
import pytest
from app.services.live_trading.ibkr_trading.symbols import (
    normalize_symbol, parse_symbol, format_display_symbol
)

class TestNormalizeSymbolForex:
    """CONT-02: normalize_symbol supports Forex symbol formats."""

    @pytest.mark.parametrize("input_sym,expected_pair,expected_quote", [
        ("EURUSD", "EURUSD", "USD"),
        ("USDJPY", "USDJPY", "JPY"),
        ("XAUUSD", "XAUUSD", "USD"),
        ("GBPJPY", "GBPJPY", "JPY"),
    ])
    def test_6char_uppercase(self, input_sym, expected_pair, expected_quote):
        pair, exchange, currency = normalize_symbol(input_sym, "Forex")
        assert pair == expected_pair
        assert exchange == "IDEALPRO"
        assert currency == expected_quote

    @pytest.mark.parametrize("input_sym,expected_pair", [
        ("EUR/USD", "EURUSD"),
        ("EUR.USD", "EURUSD"),
        ("eur-usd", "EURUSD"),
        ("Eur_Usd", "EURUSD"),
        ("eur usd", "EURUSD"),
        ("eurusd", "EURUSD"),
    ])
    def test_separator_and_case_variants(self, input_sym, expected_pair):
        pair, exchange, currency = normalize_symbol(input_sym, "Forex")
        assert pair == expected_pair
        assert exchange == "IDEALPRO"

    @pytest.mark.parametrize("bad_symbol", [
        "", "EU", "EURUSDD", "EUR123", "12345", "EUR/US",
    ])
    def test_invalid_forex_raises(self, bad_symbol):
        with pytest.raises(ValueError, match="Invalid Forex symbol"):
            normalize_symbol(bad_symbol, "Forex")

    def test_does_not_default_to_stock(self):
        """Forex symbols must never fall through to Stock default."""
        pair, exchange, _ = normalize_symbol("EURUSD", "Forex")
        assert exchange == "IDEALPRO"
        assert exchange != "SMART"


class TestParseSymbolForex:
    """parse_symbol auto-detects Forex."""

    def test_detects_known_forex(self):
        clean, mtype = parse_symbol("EURUSD")
        assert mtype == "Forex"
        assert clean == "EURUSD"

    def test_detects_forex_with_separator(self):
        clean, mtype = parse_symbol("EUR/USD")
        assert mtype == "Forex"
        assert clean == "EURUSD"

    def test_hshare_not_confused_with_forex(self):
        _, mtype = parse_symbol("0700.HK")
        assert mtype == "HShare"

    def test_us_stock_not_confused_with_forex(self):
        _, mtype = parse_symbol("AAPL")
        assert mtype == "USStock"


class TestFormatDisplayForex:
    def test_forex_display(self):
        assert format_display_symbol("EURUSD", "IDEALPRO") == "EUR.USD"

    def test_hshare_unchanged(self):
        assert format_display_symbol("700", "SEHK") == "0700.HK"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `ib_insync.Forex` (unchanged since 0.9.x) | Same — `Forex(pair='EURUSD')` | Stable API | No migration concern |
| `Stock(symbol='EURUSD')` for FX (anti-pattern) | `Forex(pair='EURUSD')` | N/A — never correct | Prevents qualification failure |

**Deprecated/outdated:**
- None relevant. `ib_insync` 0.9.86 is the installed version; `Forex` class is stable and unchanged across recent versions.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (standard, no config file — uses default discovery) |
| Config file | none — default pytest discovery in `tests/` |
| Quick run command | `python -m pytest tests/test_ibkr_symbols.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q --ignore=tests/live_trading` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONT-02a | 6-char uppercase pair → (pair, IDEALPRO, quote) | unit | `python -m pytest tests/test_ibkr_symbols.py::TestNormalizeSymbolForex::test_6char_uppercase -x` | ❌ Wave 0 |
| CONT-02b | Separator variants (EUR/USD, EUR.USD, etc.) normalize correctly | unit | `python -m pytest tests/test_ibkr_symbols.py::TestNormalizeSymbolForex::test_separator_and_case_variants -x` | ❌ Wave 0 |
| CONT-02c | Invalid Forex symbols raise ValueError | unit | `python -m pytest tests/test_ibkr_symbols.py::TestNormalizeSymbolForex::test_invalid_forex_raises -x` | ❌ Wave 0 |
| CONT-02d | Forex never defaults to SMART/USD (stock path) | unit | `python -m pytest tests/test_ibkr_symbols.py::TestNormalizeSymbolForex::test_does_not_default_to_stock -x` | ❌ Wave 0 |
| CONT-02e | parse_symbol auto-detects Forex from known pairs | unit | `python -m pytest tests/test_ibkr_symbols.py::TestParseSymbolForex -x` | ❌ Wave 0 |
| CONT-02f | format_display_symbol renders EUR.USD for Forex | unit | `python -m pytest tests/test_ibkr_symbols.py::TestFormatDisplayForex -x` | ❌ Wave 0 |
| REGR-01 | Existing USStock/HShare normalize_symbol behavior unchanged | unit | `python -m pytest tests/test_ibkr_symbols.py::TestNormalizeSymbolRegression -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_ibkr_symbols.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q --ignore=tests/live_trading`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_ibkr_symbols.py` — covers CONT-02 (all sub-requirements) + regression
- No new fixtures needed — tests are pure function tests with no mocks required
- No framework install needed — pytest already in project

## Open Questions

1. **Should `parse_symbol` detect Forex for symbols NOT in `KNOWN_FOREX_PAIRS`?**
   - What we know: All 14 DB pairs are in the MT5 `FOREX_PAIRS` set. The proposed `KNOWN_FOREX_PAIRS` covers them plus common IDEALPRO pairs.
   - What's unclear: Whether future pairs should be auto-detected by heuristic (6-char alpha) or require set expansion.
   - Recommendation: **Use set-only detection for now** (safer, no false positives). Add a note in code that the set should be expanded when new pairs are onboarded. The 6-char heuristic can be added later if needed.

2. **Should `normalize_symbol` validate against `KNOWN_FOREX_PAIRS` set?**
   - What we know: When `market_type="Forex"` is explicit, the caller already knows it's Forex. Validating against the set would reject unknown but valid pairs.
   - What's unclear: Whether strictness (reject unknown pairs) or openness (accept any 6-char alpha) is preferred.
   - Recommendation: **Accept any valid 6-char alpha when `market_type="Forex"` is explicit.** The `market_type` parameter is the authority; `normalize_symbol` should not second-guess it. Use the set only in `parse_symbol` for auto-detection.

## Sources

### Primary (HIGH confidence)
- `ib_insync` 0.9.86 installed source — `Forex` class: `assert len(pair) == 6`, splits `symbol=pair[:3]`, `currency=pair[3:]`, default `exchange='IDEALPRO'`
- `backend_api_python/app/services/live_trading/ibkr_trading/symbols.py` — current implementation (91 lines, no Forex)
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py:780-783` — `_create_contract` calls `normalize_symbol` then `ib_insync.Stock()`
- `backend_api_python/app/services/live_trading/mt5_trading/symbols.py` — reference `FOREX_PAIRS` set and separator stripping
- `backend_api_python/tests/test_ibkr_client.py` — 93 existing unit tests, test patterns

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` — ib_insync Forex construction rules, verified against source
- `.planning/research/PITFALLS.md` — Pitfall 1 (Stock default) and Pitfall 2 (pair encoding)
- CONTEXT.md — User decisions on return format, error handling, discretion areas

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pure Python string processing, no external dependencies needed beyond installed ib_insync
- Architecture: HIGH — extending 3 existing functions with a new branch, patterns clear from USStock/HShare precedent
- Pitfalls: HIGH — the main risk (silent Stock default) is well-understood and directly addressable
- Test strategy: HIGH — pure function tests, no mocks needed, clear parametrization matrix

**Research date:** 2026-04-09
**Valid until:** 2026-07-09 (90 days — stable domain, no fast-moving dependencies)
