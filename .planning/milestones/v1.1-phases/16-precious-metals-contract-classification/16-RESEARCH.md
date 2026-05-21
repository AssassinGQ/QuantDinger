# Phase 16: Precious metals contract classification - Research

**Researched:** 2026-04-12  
**Domain:** Interactive Brokers TWS API + `ib_insync` contract qualification for spot precious metals (XAU\*/XAG\*)  
**Confidence:** HIGH (paper qualify experiment confirmed CMDTY/SMART for XAUUSD/XAGUSD on account DUQ123679; Forex encoding FAILS)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- The correct secType (CASH/IDEALPRO vs CMDTY/SMART) for XAUUSD/XAGUSD is **unknown** — research phase MUST investigate via IBKR documentation and/or API experiments to confirm the correct routing
- Once confirmed, the correct secType/exchange is **hardcoded** (not runtime-detected, not configurable)
- Symbol detection uses **XAU\*/XAG\* prefix pattern** (not a hardcoded symbol list) to automatically cover future metals pairs (e.g. XAUEUR, XPTUSD)
- If qualify returns unexpected results after research confirms the correct path, treat as a bug (not a runtime fallback scenario)

### market_category classification

- Whether metals get their own independent `market_category` (like "Metals") or remain under Forex with a sub-flag is **decided by research** based on what works with IBKR API
- **Locked: TIF = IOC** — same as Forex, regardless of market_category outcome
- **Locked: normalizer behavior** — research must confirm if metals need integer/precision rounding (gold trades in troy ounces) or if passthrough (like Forex) is correct
- **Frontend**: metals only have IBKR Paper / IBKR Live brokers (no MT5 metals trading)

### Post-qualify validation

- `_EXPECTED_SEC_TYPES` gets a metals entry after research confirms the correct secType — e.g. `{"Metals": "CMDTY"}` or metals stays under Forex's `"CASH"`
- **No extra log/position fields needed** — symbol name (XAUUSD/XAGUSD) already identifies metals vs Forex
- **Metals-specific error messages** — when metals orders fail, error messages should reference "precious metals contract" and suggest checking contract configuration (not the generic Forex "minimum tradable size" wording)

### Claude's Discretion

- Exact implementation of XAU\*/XAG\* prefix detection (regex vs set vs startswith)
- Whether `_create_contract` uses a separate code path or extends the Forex path with a metals branch
- How to structure metals-specific error messages (exact wording)
- Whether to add `XAUEUR` and other metals pairs to test coverage beyond XAUUSD/XAGUSD
- Test organization and naming

### Deferred Ideas (OUT OF SCOPE)

- Platinum (XPTUSD) and palladium (XPDUSD) support — covered by XAU\*/XAG\* pattern but not explicitly tested
- Metals-specific trading hours validation (if different from Forex 24/5)
- Metals position/PnL display in frontend (Phase 18 or beyond)

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRADE-04 | 贵金属合约创建——XAUUSD/XAGUSD 使用正确 secType（CMDTY/SMART 或经 paper qualify 验证的类型），与 Forex CASH/IDEALPRO 分开路由 | Official IB “Commodities” contract sample (CMDTY/SMART); `Forex()` maps to CASH/IDEALPRO — separate branch; paper qualify locks hardcoded expectations |

</phase_requirements>

## Summary

Interactive Brokers documents **spot gold OTC** in the TWS API **“Commodities”** section using **`secType=CMDTY`**, **`symbol=XAUUSD`** (full string), **`exchange=SMART`**, **`currency=USD`** — not the same object shape as a standard FX pair built with `ib_insync.Forex`, which always constructs **`secType=CASH`** on **`IDEALPRO`** with **`symbol=XAU`** and **`currency=USD`**. Those are two different `Contract` encodings; `qualifyContractsAsync` is what resolves them to IB’s canonical `conId` and final fields.

The IB **Contract Information Center** entry for **London Gold** lists **`XAUUSD`**, describes the product as **Commodity (OTC Derivative)**, and gives **`conId=69067924`** (useful as a cross-check after qualification — not a substitute for post-qualify validation in code).

**Primary recommendation:** Implement a **dedicated metals branch** that builds **`ib_insync.Contract(symbol='XAUUSD', secType='CMDTY', exchange='SMART', currency='USD')`** (and **`XAGUSD`** analogously), run **paper `qualifyContractsAsync`**, then **hardcode** the validated `secType` / `exchange` / `localSymbol` expectations **as decided in CONTEXT**. If paper shows a different qualified shape (e.g. some environments still resolving to CASH), **trust the qualify snapshot for that account** and still **keep routing separate** from EURUSD-style Forex so logs and validation stay correct.

**Primary recommendation (one line):** Use the **IB-documented CMDTY/SMART `XAUUSD`/`XAGUSD` contract pattern** with `ib_insync.Contract`, **not** `Forex(pair=...)`, unless paper qualify proves your account only accepts the CASH/IDEALPRO encoding — in that case hardcode **that** qualified shape but **still** use a distinct `market_type` from standard Forex.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|----------------|
| `ib-insync` | **0.9.86** (verify: `pip show ib-insync`; project pins `ib_insync>=0.9.86` in `backend_api_python/requirements.txt`) | Async/sync IB API wrapper; `Contract`, `Forex`, `qualifyContractsAsync` | De facto Python stack for IBKR; matches existing `IBKRClient` |
| IB Gateway / TWS | Current stable (paper for validation) | Contract qualification and order routing | Only authoritative way to confirm qualified `secType`/`conId` for an account |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | (project default) | Unit/integration tests | Mock qualify/place paths per existing `test_ibkr_client.py` patterns |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `Contract(CMDTY/SMART/...)` | `Forex('XAUUSD')` | `Forex` **always** sets `secType='CASH'` and `exchange='IDEALPRO'` — matches **FX cash** docs for EUR.USD-style pairs, **not** the IB **Commodities** sample for `XAUUSD` |
| Symbol-only discovery | `conId` from qualify | CONTEXT requires hardcoding after research; optional: use known `conId` from Contract Information Center only as **sanity check**, not as the only key |

**Installation (already in repo):**

```bash
pip install "ib_insync>=0.9.86"
```

**Version verification:** `pip show ib-insync` → document **0.9.86** as installed in this environment; bump if `requirements.txt` changes.

## Architecture Patterns

### Recommended contract objects (ib_insync)

**1) Precious metals (IB “Commodities” sample — use for dedicated routing)**

```python
# Source: https://interactivebrokers.github.io/tws-api/basic_contracts.html
# Section "Commodities" — XAUUSD example
import ib_insync

gold = ib_insync.Contract(
    symbol="XAUUSD",
    secType="CMDTY",
    exchange="SMART",
    currency="USD",
)
silver = ib_insync.Contract(
    symbol="XAGUSD",
    secType="CMDTY",
    exchange="SMART",
    currency="USD",
)
```

**2) Standard Forex (existing EURUSD-style path — do not reuse for metals if CMDTY is confirmed)**

```python
# ib_insync.contract.Forex — ALWAYS builds secType CASH + IDEALPRO
eurusd = ib_insync.Forex("EURUSD")  # symbol EUR, currency USD
xau_via_forex_helper = ib_insync.Forex("XAUUSD")  # symbol XAU, currency USD — CASH/IDEALPRO
```

**When to use which:** Use **(1)** for XAU\*/XAG\* **if** paper qualify shows **`CMDTY`** and SMART routing as returned by IB. Use qualification results to set `_EXPECTED_SEC_TYPES` and `_validate_qualified_contract`. If paper instead returns **`CASH`** / **`IDEALPRO`** with **XAU+USD** decomposition, that is the **hardcoded** truth for that deployment — still **separate `market_type`** from EURUSD so routing and messages stay explicit (TRADE-04).

### Recommended project structure (conceptual)

```
ibkr_trading/
├── client.py          # _create_contract: add Metals branch → Contract(CMDTY/…) not Forex()
├── symbols.py         # parse_symbol: XAU*/XAG* → Metals; normalize_symbol: metals-specific tuple if needed
order_normalizer/
├── __init__.py        # get_market_pre_normalizer: optional MetalsPreNormalizer or reuse Forex pass-through
```

### Anti-Patterns to Avoid

- **Using `Forex(pair='XAUUSD')` and assuming it is “the” IB metals contract** — it bakes in **CASH/IDEALPRO**; may disagree with the **Commodities** sample and with qualified `secType`.
- **Silent fallback** between CMDTY and CASH — CONTEXT forbids runtime fallback; fail loud + invalidate qualify cache.
- **Treating metals quantity like arbitrary FX “units”** without `_align_qty_to_contract` — metals use **troy ounces** in product docs; let **ContractDetails** drive increments.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Resolving IB contract identity | String heuristics only | `qualifyContractsAsync` + optional `reqContractDetailsAsync` | IB returns authoritative `conId`, `secType`, `tradingClass`, `minTick`, `sizeIncrement` |
| Lot / increment alignment | Ad-hoc rounding | Existing `_align_qty_to_contract` | Already uses `sizeIncrement` / `minSize` from IB |
| IOC semantics | Custom TIF logic | **IOC locked** same as Forex per CONTEXT | INFRA-02 already unified TIF matrix |

**Key insight:** The “hard part” is not guessing metals — it is **binding** to IB’s returned contract after qualification.

## Common Pitfalls

### Pitfall 1: Confusing product label with API `secType`

**What goes wrong:** IB marketing pages describe “spot gold” and “OTC”; Contract Information Center says “Commodity (OTC Derivative)” while `Forex()` still produces `CASH`.

**Why it happens:** IB uses multiple **contract encodings** in samples (FX **CASH** vs **Commodities CMDTY**).

**How to avoid:** Treat **`qualifyContractsAsync` output** as source of truth for `secType`/`exchange` after you submit the **documented Commodities-style** `Contract`.

**Warning signs:** Qualified `secType` does not match `_EXPECTED_SEC_TYPES`; `conId == 0`.

### Pitfall 2: SMART routing ambiguity

**What goes wrong:** `exchange='SMART'` can match multiple lines; qualify may return multiple or wrong line without enough fields.

**Why it happens:** `CMDTY` on SMART is a pattern-level request until disambiguated.

**How to avoid:** Rely on qualify; persist snapshot; consider `localSymbol` / `tradingClass` in validation if IB populates them.

### Pitfall 3: Regional / entity product differences

**What goes wrong:** US **USGOLD** narrative vs **London Gold XAUUSD** — different pages, different eligibility.

**Why it happens:** IB product set varies by **entity** and **permissions**.

**How to avoid:** Paper account in the **same** region as production; qualify there.

**Warning signs:** Empty qualify list; error 200 / “No security definition”.

### Pitfall 4: Minimum size and commissions

**What goes wrong:** Orders rejected for size/permission though contract qualifies.

**Why it happens:** Metals OTC has **minimum commission** and **size** constraints on retail pages.

**How to avoid:** Surface **metals-specific** errors (per CONTEXT), not generic Forex min-size text.

### Pitfall 5: Tests assuming “Forex” market_type

**What goes wrong:** `test_metals_detected_as_forex` and UC tests break when `market_type` becomes **Metals**.

**Why it happens:** Intentional reclassification for TRADE-04.

**How to avoid:** Update assertions to **Metals** + mocked qualify snapshots with **CMDTY** (or paper-observed `secType`).

## Code Examples

### IB-documented Commodities contract (authoritative sample)

```text
# Source: https://interactivebrokers.github.io/tws-api/basic_contracts.html — "Commodities"
contract.Symbol = "XAUUSD";
contract.SecType = "CMDTY";
contract.Exchange = "SMART";
contract.Currency = "USD";
```

### `ib_insync.Forex` implementation (shows CASH/IDEALPRO)

```python
# Installed ib_insync 0.9.86 — Forex.__init__ ends with:
# Contract.__init__(self, 'CASH', symbol=symbol, exchange=exchange, currency=currency, **kwargs)
# pair 'XAUUSD' -> symbol 'XAU', currency 'USD'
```

### Post-qualify validation (pattern already in `client.py`)

Extend `_EXPECTED_SEC_TYPES` with a **Metals** (or chosen name) key once paper shows the stable `secType`:

```python
# Conceptual — align key name with parse_symbol market_type decision
_EXPECTED_SEC_TYPES = {
    "Forex": "CASH",
    "Metals": "CMDTY",  # example — must match qualified output
    # ...
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Treat XAUUSD as `Forex` → `Forex()` CASH | Route XAU\*/XAG\* as **CMDTY SMART** per IB Commodities sample + qualify | Documented in IB basic contracts (legacy HTML; still cited) | Correct `secType` expectations and separate from EURUSD |
| Guess metals = Forex IDEALPRO | Use Contract Information Center + qualify | Ongoing | Avoids wrong validation |

**Deprecated/outdated:**

- Assuming **all** 6-letter “pair” symbols use `Forex()` — **metals need explicit research** per CONTEXT.

## Paper Qualify Experiment (2026-04-12)

**Account:** DUQ123679 (Paper Trading)  
**IB Gateway:** ib-gateway:4004  
**Method:** `qualifyContractsAsync` via `ib_insync` clientId=99, readonly=True

### Qualify Results

| Test | Contract Encoding | Result | conId | secType | exchange | localSymbol | tradingClass |
|------|-------------------|--------|-------|---------|----------|-------------|--------------|
| XAUUSD CMDTY | `Contract(symbol="XAUUSD", secType="CMDTY", exchange="SMART", currency="USD")` | **QUALIFIED** | **69067924** | **CMDTY** | **SMART** | **XAUUSD** | **XAUUSD** |
| XAUUSD Forex | `Forex("XAUUSD")` → `secType=CASH, exchange=IDEALPRO, symbol=XAU` | **FAILED** | — | — | — | Error 200: No security definition | — |
| XAGUSD CMDTY | `Contract(symbol="XAGUSD", secType="CMDTY", exchange="SMART", currency="USD")` | **QUALIFIED** | **77124483** | **CMDTY** | **SMART** | **XAGUSD** | **XAGUSD** |
| XAGUSD Forex | `Forex("XAGUSD")` → `secType=CASH, exchange=IDEALPRO, symbol=XAG` | **FAILED** | — | — | — | Error 200: No security definition | — |
| XAUEUR CMDTY | `Contract(symbol="XAUEUR", secType="CMDTY", exchange="SMART", currency="EUR")` | **FAILED** | — | — | — | Error 200: No security definition | — |
| EURUSD Forex (control) | `Forex("EURUSD")` | **QUALIFIED** | **12087792** | **CASH** | **IDEALPRO** | **EUR.USD** | **EUR.USD** |

### ContractDetails Results

| Symbol | longName | minTick | sizeIncrement | minSize | priceMagnifier | tradingHours (sample) |
|--------|----------|---------|---------------|---------|----------------|----------------------|
| **XAUUSD** | London Gold | **0.01** | **1.0** | **1.0** | 1 | 18:00-17:00 (Sun-Fri, US ET) |
| **XAGUSD** | London Silver | **0.0005** | **1.0** | **1.0** | 1 | 18:00-17:00 (Sun-Fri, US ET) |

### Conclusions (HARDCODE THESE)

1. **XAUUSD and XAGUSD are CMDTY/SMART — NOT Forex CASH/IDEALPRO.** The Forex encoding (`Forex("XAUUSD")`) returns Error 200 "No security definition" on this paper account. This is definitive.
2. **`_EXPECTED_SEC_TYPES["Metals"] = "CMDTY"`** — hardcode with confidence.
3. **XAUEUR is NOT available** on this paper account (CMDTY/SMART/EUR fails). Remove from `KNOWN_FOREX_PAIRS` and do NOT include in metals detection scope for now. Defer to future phase if needed.
4. **sizeIncrement = 1.0 troy ounce** for both gold and silver. `_align_qty_to_contract` will work correctly via existing ContractDetails path — no custom rounding needed.
5. **minTick differs**: gold = 0.01, silver = 0.0005. This only matters for limit orders (Phase 17), not market orders.
6. **Trading hours**: 18:00-17:00 ET, Sun-Fri — nearly 23h/day, similar to Forex but NOT identical. The existing RTH framework (`is_rth` via `liquidHours`) handles this automatically.
7. **conId cross-check**: XAUUSD = 69067924 (matches IB Contract Information Center), XAGUSD = 77124483.

## Open Questions (Post-Experiment)

1. ~~Will paper trading return CMDTY?~~ → **YES, confirmed. CMDTY/SMART is the only working encoding.**
2. ~~Does XAUEUR use the same CMDTY pattern?~~ → **NO. XAUEUR CMDTY/SMART/EUR fails on this account. Out of scope.**
3. **XAUEUR should be removed from `KNOWN_FOREX_PAIRS`** — it is not tradable as either Forex or CMDTY on this account. Remove to avoid confusion.

## Validation Architecture

> `workflow.nyquist_validation` is enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` (project `backend_api_python/tests/`) |
| Config file | none dedicated — markers in `tests/conftest.py` |
| Quick run command | `cd backend_api_python && pytest tests/test_ibkr_client.py -q --tb=no -x` |
| Full suite command | `cd backend_api_python && pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| TRADE-04 | Metals use non-Forex contract branch + expected `secType` | unit (mocked IB) | `pytest tests/test_ibkr_client.py -k metals -x` | ❌ Wave 0 — add/update after implementation |
| TRADE-04 | `parse_symbol` XAU\*/XAG\* → Metals | unit | `pytest tests/test_ibkr_symbols.py -x` | ❌ update existing `test_metals_detected_as_forex` |
| TRADE-04 | Qualify cache key `(symbol, market_type)` with Metals | unit | extend `test_ibkr_client.py` qualify tests | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** targeted `pytest` on touched test modules  
- **Per wave merge:** `cd backend_api_python && pytest`  
- **Phase gate:** full backend pytest green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] Update metals tests currently asserting `market_type=="Forex"` for XAUUSD/XAGUSD  
- [ ] Add mocked qualify snapshot asserting **`CMDTY`** (or paper-observed `secType`)  
- [ ] Confirm no regression in `test_forex_ibkr_e2e.py` / paper smoke chains after `market_type` rename  

## Sources

### Primary (HIGH confidence)

- [Interactive Brokers TWS API — Basic Contracts — Commodities (XAUUSD example)](https://interactivebrokers.github.io/tws-api/basic_contracts.html) — `secType=CMDTY`, `symbol=XAUUSD`, `exchange=SMART`, `currency=USD`  
- [Interactive Brokers TWS API — Basic Contracts — FX Pairs (CASH / IDEALPRO)](https://interactivebrokers.github.io/tws-api/basic_contracts.html) — contrast with metals sample  
- [IB Contract Information Center — conId 69067924 (London Gold / XAUUSD)](https://misc.interactivebrokers.com/cstools/contract_info/index2.php?action=Details&conid=69067924&site=GEN) — product typing as Commodity OTC; cross-check `conId`  
- **Installed `ib_insync` 0.9.86** — `Forex` class source (CASH/IDEALPRO behavior)

### Secondary (MEDIUM confidence)

- [Stack Overflow — IDEALPRO for FX](https://stackoverflow.com/questions/36712921/requesting-forex-data-through-ib-api-invalid-destination-exchange-specified) — reinforces **IDEALPRO** for FX CASH (not a metals primary source, but shows exchange discipline)  
- [IBKR US Spot Gold marketing (USGOLD)](https://api.ibkr.com/en/trading/products-metals.php) — **product naming differs** from API `XAUUSD`; use for business context only  

### Tertiary (LOW confidence — validate in paper)

- Forum posts claiming “metals are just Forex on IDEALPRO” — **contradicts** IB Commodities sample; do **not** rely without qualify  

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — repo pins `ib_insync`; patterns match IB docs  
- Architecture: **HIGH** — explicit IB sample + paper qualify experiment confirmed  
- Pitfalls: **HIGH** — paper qualify experiment resolved all regional/permission questions for account DUQ123679  

**Research date:** 2026-04-12  
**Valid until:** ~30 days (stable IB API); re-check if `ib_insync` or IB contract DB changes  
