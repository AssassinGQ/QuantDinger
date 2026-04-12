# Phase 16: Precious metals contract classification - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Correctly classify and route XAUUSD/XAGUSD (and any XAU*/XAG* metals) through IBKR with the proper secType/exchange, separate from standard Forex CASH/IDEALPRO pairs. Post-qualify validation rejects unexpected contract shapes. Error messages are metals-specific. TIF matches Forex (IOC).

</domain>

<decisions>
## Implementation Decisions

### Contract routing strategy
- The correct secType (CASH/IDEALPRO vs CMDTY/SMART) for XAUUSD/XAGUSD is **unknown** — research phase MUST investigate via IBKR documentation and/or API experiments to confirm the correct routing
- Once confirmed, the correct secType/exchange is **hardcoded** (not runtime-detected, not configurable)
- Symbol detection uses **XAU*/XAG* prefix pattern** (not a hardcoded symbol list) to automatically cover future metals pairs (e.g. XAUEUR, XPTUSD)
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
- Exact implementation of XAU*/XAG* prefix detection (regex vs set vs startswith)
- Whether `_create_contract` uses a separate code path or extends the Forex path with a metals branch
- How to structure metals-specific error messages (exact wording)
- Whether to add `XAUEUR` and other metals pairs to test coverage beyond XAUUSD/XAGUSD
- Test organization and naming

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Contract creation and validation
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` lines 841-920 — `_create_contract`, `_qualify_contract_async`, `_EXPECTED_SEC_TYPES`, `_validate_qualified_contract`
- `backend_api_python/app/services/live_trading/ibkr_trading/symbols.py` — `KNOWN_FOREX_PAIRS` (metals listed with comment), `normalize_symbol`, `parse_symbol`

### Order entry (integrate metals routing)
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` lines 1159-1310 — `place_market_order` / `place_limit_order` (both call `_create_contract`)

### Normalizer (Phase 15 output)
- `backend_api_python/app/services/live_trading/order_normalizer/__init__.py` — `MarketPreNormalizer`, `get_market_pre_normalizer` factory (may need metals entry)

### Existing metals tests
- `backend_api_python/tests/test_ibkr_client.py` — `test_uc_m3_xauusd_buy_market` (currently treats as Forex)
- `backend_api_python/tests/test_ibkr_forex_paper_smoke.py` — `test_forex_paper_smoke_xagusd_uc_sa_smk_03`
- `backend_api_python/tests/test_forex_ibkr_e2e.py` — `test_uc_sa_e2e_xagusd_open_close_full_chain`
- `backend_api_python/tests/test_ibkr_symbols.py` — `test_metals_detected_as_forex`
- `backend_api_python/tests/test_trading_hours.py` — `test_UC_FX_I04_xagusd_window`, `test_UC_FX_L09_xagusd_distinct_window`

### Qualify cache (Phase 13 output)
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_qualify_ttl_seconds` (per-market TTL; metals may need its own TTL or reuse Forex TTL)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_create_contract` factory already dispatches by `market_type` — extend with metals branch
- `_EXPECTED_SEC_TYPES` dict — add metals entry after research confirms secType
- `normalize_symbol` in `symbols.py` — extend Forex path or add metals path
- `parse_symbol` auto-detection — update to detect XAU*/XAG* as Metals (currently returns "Forex")
- `MarketPreNormalizer` factory from Phase 15 — may need `MetalsPreNormalizer` or reuse `ForexPreNormalizer`

### Established Patterns
- Market-type dispatch: `if market_type == "Forex" ... elif market_type == "USStock" ... elif market_type == "HShare"` — add metals branch
- Qualify cache uses `(symbol, market_type)` key — works if metals gets its own market_type; if metals stays Forex, key still works
- `_validate_qualified_contract` strict secType check — pattern already proven for Forex/USStock/HShare

### Integration Points
- `symbols.py`: `KNOWN_FOREX_PAIRS` needs metals extracted or metals prefix detection added
- `client.py`: `_create_contract`, `_EXPECTED_SEC_TYPES`, possibly `_qualify_ttl_seconds`
- `order_normalizer/__init__.py`: `get_market_pre_normalizer` factory dispatch
- Tests: 5+ existing tests reference XAUUSD/XAGUSD as Forex — all need updating after reclassification

</code_context>

<specifics>
## Specific Ideas

- User emphasized that the **research phase must do experiments** (IBKR docs + API calls) to determine the correct secType/exchange/market_category for metals before any implementation
- Metals symbol matching should be **pattern-based** (XAU*/XAG*), not a hardcoded list, for future-proofing
- Metals TIF is **locked to IOC** — same as Forex, no research needed for this
- Error messages must be **metals-specific** when orders fail — don't use Forex "minimum tradable size" wording for metals

</specifics>

<deferred>
## Deferred Ideas

- Platinum (XPTUSD) and palladium (XPDUSD) support — covered by XAU*/XAG* pattern but not explicitly tested
- Metals-specific trading hours validation (if different from Forex 24/5)
- Metals position/PnL display in frontend (Phase 18 or beyond)

</deferred>

---

*Phase: 16-precious-metals-contract-classification*
*Context gathered: 2026-04-12*
