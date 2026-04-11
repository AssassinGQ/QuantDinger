# Phase 12: Frontend IBKR exchanges for Forex - Research

**Researched:** 2026-04-11  
**Domain:** Vue 2 + Ant Design Vue strategy wizard (`trading-assistant/index.vue`), i18n, Jest (unit) + pytest (backend regression)  
**Confidence:** HIGH (code paths verified in-repo)

## Summary

Phase 12 is a **frontend-only** change: extend the Forex live-trading section so the broker dropdown lists **MT5**, **IBKR Paper**, and **IBKR Live**, persist `exchange_config` as `{ exchange_id: 'ibkr-paper' | 'ibkr-live' }` for IBKR (same shape as US/HK stock IBKR), and route **Test connection** to `POST /api/ibkr/connect` for Forex+IBKR. The backend already validates Forex + `ibkr-paper`/`ibkr-live` (Phase 11, `test_strategy_exchange_validation.py`).

Today, **`isIBKRMarket` is only true for `USStock` / `HShare`**, so the stock IBKR template never runs for Forex. **`isMT5Market` is `selectedMarketCategory === 'Forex'`**, so the entire Forex live UI is funneled through the “MT5/Forex” template, with `FOREX_BROKER_OPTIONS` containing only `mt5`, `initialValue: 'mt5'`, and submit always emitting MT5-shaped `exchange_config` (including MT5 credential fields) when `isMT5Market` is true. Implementing the locked decisions requires **renaming `isMT5Market` → `isForexMarket`**, adding **sub-checks** (`isForexMT5` / `isForexIBKR` or equivalent), **splitting template and submit/test paths** so Forex+IBKR mirrors stock+IBKR, and **removing auto-default** to MT5 in symbol-change handlers.

**Primary recommendation:** Treat **Forex+IBKR** as the same logical broker family as **stock IBKR** (`currentBrokerId` prefixed with `ibkr-`, `isIBKRBroker` already true): unify **IBKR test connection** on `isIBKRBroker` (or explicit `(isIBKRMarket || (isForexMarket && isForexIBKR))`) and emit **IBKR-only** `exchange_config` when Forex broker is IBKR; keep **MT5 fields and `/api/mt5/connect`** only when Forex broker is MT5.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Flat list** with three options: MT5 / IBKR Paper / IBKR Live — add IBKR entries to `FOREX_BROKER_OPTIONS` constant
- Reuse the same **IBKR Paper** / **IBKR Live** display names and style as the stock (USStock/HShare) broker path
- **No default value** — force the user to manually select a broker (currently defaults to `mt5`; remove that default)
- When Forex + IBKR is selected: **hide all MT5 fields** (mt5_server, mt5_login, mt5_password, mt5_terminal_path) — identical to stock + IBKR behavior, no additional config fields needed
- When Forex + MT5 is selected: show MT5 fields as before (no change)
- Test connection button: **reuse the stock IBKR test connection** path (`/api/ibkr/connect`) when Forex + IBKR is selected
- Rename `isMT5Market` → `isForexMarket` — the current name conflates "Forex" with "MT5" which is no longer accurate
- Inside `isForexMarket`, further distinguish IBKR vs MT5 by the selected broker value (e.g. `isForexIBKR` / `isForexMT5` sub-checks) to control field visibility and test connection routing
- **Auto-detect on edit**: read `exchange_config.exchange_id` from the existing strategy — `mt5` backfills to MT5 broker, `ibkr-paper`/`ibkr-live` backfills to IBKR broker. No user action needed
- **exchange_config format for Forex + IBKR**: identical to stock — `{ exchange_id: 'ibkr-paper' }` with no extra fields. Backend already handles this (Phase 11 validation + factory)

### Claude's Discretion
- i18n key naming for new broker options (follow existing `exchangeNames.*` / `brokerNames.*` pattern)
- Exact placement and ordering of brokers in the dropdown (MT5 first or IBKR first — pick what feels natural)
- Any cosmetic adjustments to the form layout when switching between MT5 and IBKR fields

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FRNT-01 | 策略创建/编辑页面，当 market_category=Forex 时，交易所选择列表包含 ibkr-paper 和 ibkr-live（不仅限于 MT5） | Extend `FOREX_BROKER_OPTIONS`; template + submit + edit backfill + test connection; verify with UI/unit tests + backend pytest regression |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Vue | 2.6.14 (`quantdinger_vue/package.json`) | Options API component | Project lock |
| ant-design-vue | 1.7.8 | Form, Select, wizard UI | Project lock |
| vue-i18n | 8.27.1 | `trading-assistant.brokerNames.*` | Project lock |
| axios / `$http` | 0.26.1 | `POST /api/ibkr/connect`, `/api/mt5/connect` | Existing pattern |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|-------------|--------------|
| @vue/test-utils | 1.3.0 | Mount/shallow-mount components | New Jest specs for wizard logic |
| jest (via `@vue/cli-plugin-unit-jest`) | ~27 (Vue CLI 5 stack) | Unit tests | `npm run test:unit` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Editing `index.vue` (~6k LOC) | Extract broker step mixin | Better testability but larger refactor — out of scope unless planner splits a follow-up |

**Installation:** N/A — use existing `quantdinger_vue` dependencies.

**Version note:** `npm view vue` returns Vue 3.x latest; **authoritative versions are `quantdinger_vue/package.json`** (Vue 2.x).

## Architecture Patterns

### Current structure (verified)

- **Stock IBKR block:** `v-if="isIBKRMarket"` — `broker_id` select, IBKR alerts, uses `BROKER_OPTIONS` / `brokerOptions` (`index.vue` ~1343–1371).
- **Forex block:** `v-else-if="isMT5Market"` — `forex_broker_id` select from `FOREX_BROKER_OPTIONS` / `forexBrokerOptions`; MT5 fields gated by `currentBrokerId === 'mt5'` (~1374–1446).
- **Computed:** `isIBKRMarket`: `['USStock','HShare'].includes(selectedMarketCategory)`; `isMT5Market`: `selectedMarketCategory === 'Forex'` (~1743–1753).
- **Submit `exchange_config` (live):** ternary `isIBKRMarket` → `{ exchange_id: broker_id }` ; `isMT5Market` → MT5 object with `mt5_*` fields (~4282–4291).

### Recommended Project Structure (this phase)

- **Single file change (minimum):** `quantdinger_vue/src/views/trading-assistant/index.vue` — constants, computed, template, methods, submit, load/edit.
- **i18n:** `quantdinger_vue/src/locales/lang/*.js` — optional keys under `trading-assistant.brokerNames` for `ibkr-paper` / `ibkr-live` (today `brokerOptions` falls back to `BROKER_OPTIONS[].name` when translation missing — see `brokerOptions` / `forexBrokerOptions` mapping ~1871–1908).

### Pattern 1: Forex broker list + conditional MT5 vs IBKR panels

**What:** Keep one Forex live-trading template branch, but inside it: (1) three-way `forex_broker_id` select; (2) `v-if` MT5 credential fields only when `isForexMT5`; (3) IBKR gateway info block when `isForexIBKR` (copy structure from stock IBKR block for consistency).

**When to use:** Matches CONTEXT (“mirror stock + IBKR”, “hide MT5 fields for Forex+IBKR”).

### Pattern 2: IBKR test connection unification

**What:** `handleTestConnection` currently runs IBKR when `isIBKRMarket`, then MT5 when `isMT5Market` (~3947–4033). For Forex+IBKR, **`isMT5Market` is still true** (Forex category), so the code incorrectly attempts MT5 unless you branch first. **Fix:** run IBKR connect when `this.isIBKRBroker` (covers stock `ibkr-*` and Forex `ibkr-*`) *before* the MT5 path, or use `(isIBKRMarket || (isForexMarket && isForexIBKR))`.

**Example (illustrative):**

```javascript
// Conceptual ordering — align with existing handleTestConnection structure
if (this.isIBKRMarket || (this.isForexMarket && this.isForexIBKR)) {
  await this.$http.post('/api/ibkr/connect', { broker_id: this.currentBrokerId || 'ibkr-paper' })
} else if (this.isForexMarket && this.isForexMT5) {
  await this.$http.post('/api/mt5/connect', { ... })
}
```

### Pattern 3: Submit payload for Forex+IBKR

**What:** When live + Forex + IBKR, `exchange_config` must be **only** `{ exchange_id: 'ibkr-paper' | 'ibkr-live' }` (no `mt5_*` keys). Mirror the **stock** branch shape (~4282–4284), but read **`forex_broker_id`** (or align field names — planner decides one source of truth).

### Anti-Patterns to Avoid

- **Leaving `isMT5Market` meaning “Forex”** while also using it for “show MT5 connect” — rename per CONTEXT and split MT5 vs IBKR behavior explicitly.
- **Defaulting Forex to MT5** in `handleWatchlistSymbolChange` / `handleMultiSymbolChange` (~2541–2546, ~2584–2589) — conflicts with “no default”; clear or omit `forex_broker_id` until user selects.
- **Duplicating `exchange_id` vs `broker_id` inconsistently** — stock uses `broker_id`; Forex uses `forex_broker_id`; keep one clear mapping in submit.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IBKR connectivity check | Custom socket probe | Existing `POST /api/ibkr/connect` | Same as stock path; gateway managed by backend env |
| Forex+IBKR validation | Client-only rules | Backend already validates pairs (Phase 11) | Single source of truth; `test_strategy_exchange_validation.py` |

**Key insight:** Backend acceptance of Forex + `ibkr-paper`/`ibkr-live` is already proven — frontend must only emit the correct JSON and UX.

## Common Pitfalls

### Pitfall 1: Forex+IBKR hits MT5 test path

**What goes wrong:** `handleTestConnection` checks `isMT5Market` after `isIBKRMarket`; for Forex, `isIBKRMarket` is false, `isMT5Market` is true → MT5 API runs without server/login.

**Why it happens:** Forex and MT5 were previously equivalent in the UI model.

**How to avoid:** IBKR branch must run for Forex when broker is `ibkr-*` (see Pattern 2).

**Warning signs:** Successful IBKR gateway but UI still asks for MT5 fields; or `/api/mt5/connect` errors when IBKR is selected.

### Pitfall 2: `isLiveTradingAvailable` / gating

**What goes wrong:** `isLiveTradingAvailable` returns true for Forex only when `currentBrokerId === 'mt5'` (~1859–1862). IBKR Forex would appear “not available” for live.

**How to avoid:** Extend Forex branch to treat `ibkr-paper` / `ibkr-live` as live-capable (same as MT5 for this product).

### Pitfall 3: Edit backfill forces MT5

**What goes wrong:** `loadStrategyDataToForm` sets `forex_broker_id` and `currentBrokerId` from `exchange_id || 'mt5'` for Forex (~2959–2967, ~2990–2991). Saved `ibkr-paper` strategies may display wrong broker if logic assumes MT5-only.

**How to avoid:** Map `exchange_id` to the correct broker option for all three IDs; remove `'mt5'` fallback when `exchange_id` is IBKR (CONTEXT: auto-detect from `exchange_id`).

### Pitfall 4: Ant Design Form `initialValue: 'mt5'`

**What goes wrong:** Decorator initial value pre-selects MT5, conflicting with “no default.”

**How to avoid:** Remove or set `undefined` and rely on validation `required: true` on user selection.

### Pitfall 5: String `broker_id` vs `ibkr`

**What goes wrong:** Some fallbacks use `'ibkr'` while options use `ibkr-paper` / `ibkr-live` (~2955–2957, ~4283). Inconsistent fallbacks can submit invalid IDs.

**How to avoid:** Prefer `ibkr-paper` as safe default only where stock UI already does (~1347), and align Forex IBKR with the same IDs.

## Code Examples

### Existing FOREX broker constant (extend)

```1720:1725:quantdinger_vue/src/views/trading-assistant/index.vue
const FOREX_BROKER_OPTIONS = [
  { value: 'mt5', labelKey: 'mt5', name: 'MetaTrader 5' }
  // Future forex brokers can be added here:
  // { value: 'mt4', labelKey: 'mt4', name: 'MetaTrader 4' },
  // { value: 'ctrader', labelKey: 'ctrader', name: 'cTrader' },
]
```

### Existing live `exchange_config` branch (Forex = MT5-shaped today)

```4282:4292:quantdinger_vue/src/views/trading-assistant/index.vue
              exchange_config: isLive ? (this.isIBKRMarket ? {
                exchange_id: values.broker_id || this.currentBrokerId || 'ibkr'
              } : this.isMT5Market ? {
                // MT5/Forex broker configuration
                exchange_id: values.forex_broker_id || this.currentBrokerId || 'mt5',
                // MT5 specific fields
                mt5_server: values.mt5_server || '',
                mt5_login: values.mt5_login || '',
                mt5_password: values.mt5_password || '',
                mt5_terminal_path: values.mt5_terminal_path || ''
              } : {
```

### Auto-default to MT5 on symbol change (remove per CONTEXT)

```2541:2546:quantdinger_vue/src/views/trading-assistant/index.vue
      // Auto-set broker ID based on market category
      if (this.selectedMarketCategory === 'Forex') {
        this.currentBrokerId = 'mt5'
        try {
          this.form && this.form.setFieldsValue && this.form.setFieldsValue({ forex_broker_id: 'mt5' })
        } catch (e) { }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Forex live = MT5 only | Forex live = MT5 or IBKR paper/live | Phase 12 | UI + payload branching |
| `isMT5Market` = Forex | `isForexMarket` + MT5/IBKR sub-checks | Phase 12 | Clearer semantics |

**Deprecated/outdated:** N/A — incremental extension.

## Open Questions

1. **Should `handleTestConnection` collapse to `if (this.isIBKRBroker)` for all IBKR?**  
   - What we know: `isIBKRBroker` is `currentBrokerId.startsWith('ibkr-')` (~1746–1748), true for both stock and Forex IBKR.  
   - What's unclear: Any edge case where `currentBrokerId` is unset during stock flow.  
   - Recommendation: Prefer explicit `(isIBKRMarket || (isForexMarket && isForexIBKR))` first; then refactor to `isIBKRBroker` if manual QA passes.

2. **Unit test vs E2E**  
   - What we know: Jest config exists; **no `tests/unit/**/*.spec.js` files found** in repo snapshot — Wave 0 gap for frontend automated tests.  
   - Recommendation: Add first spec(s) for computed helpers + payload builder (extract small pure functions if needed), or follow project E2E norms if documented elsewhere.

## Validation Architecture

> `workflow.nyquist_validation` is **true** in `.planning/config.json` — section included.

### Test Framework

| Property | Value |
|----------|-------|
| Frontend framework | Jest via `@vue/cli-plugin-unit-jest` (`quantdinger_vue/jest.config.js`) |
| Frontend config | `quantdinger_vue/jest.config.js` — `testMatch`: `**/tests/unit/**/*.spec.*`, `**/__tests__/*` |
| Frontend quick run | `cd quantdinger_vue && npm run test:unit` |
| Backend framework | pytest (`backend_api_python/tests/`, e.g. `test_strategy_exchange_validation.py`) |
| Backend quick run | `cd backend_api_python && python -m pytest tests/test_strategy_exchange_validation.py -q --tb=short` |
| Backend full suite | `cd backend_api_python && python -m pytest tests/ -q` (per Phase 11 runbook; ~minutes) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| FRNT-01 | Forex broker list includes ibkr-paper & ibkr-live; persistence shape | unit/component (preferred) or E2E | `cd quantdinger_vue && npm run test:unit` (once spec exists) | ❌ Wave 0 — add spec |
| FRNT-01 | Backend still accepts Forex + IBKR IDs | integration | `cd backend_api_python && python -m pytest tests/test_strategy_exchange_validation.py -q` | ✅ |
| Regression | No backend breakage | integration | `cd backend_api_python && python -m pytest tests/ -q` | ✅ suite exists |

### Sampling Rate

- **Per task commit:** `npm run test:unit` (after specs exist) + targeted `pytest` for strategy validation.
- **Per wave merge / phase gate:** Full backend `pytest tests/` + frontend unit suite green.

### Wave 0 Gaps

- [ ] `quantdinger_vue/tests/unit/**/*.spec.js` — new tests for Forex IBKR broker list / payload / computed renames (covers FRNT-01).
- [ ] Confirm whether project uses Playwright/Cypress elsewhere for E2E — none found under `quantdinger_vue` in this research pass; planner may scope **UI-level** as Jest + Vue Test Utils only.

*(Backend: none for FRNT-01 acceptance — validation tests already exist.)*

## Sources

### Primary (HIGH confidence)

- `quantdinger_vue/src/views/trading-assistant/index.vue` — template, computed, `handleTestConnection`, submit, `loadStrategyDataToForm`, symbol handlers
- `quantdinger_vue/package.json` — dependency versions
- `quantdinger_vue/jest.config.js` — unit test discovery
- `backend_api_python/tests/test_strategy_exchange_validation.py` — Forex + `ibkr-paper` / `ibkr-live` API acceptance
- `.planning/phases/12-frontend-ibkr-exchanges-for-forex/12-CONTEXT.md` — locked decisions

### Secondary (MEDIUM confidence)

- `.planning/phases/11-strategy-automation-forex-ibkr/11-VALIDATION.md` — pytest command patterns

### Tertiary (LOW confidence)

- None for core findings

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — pinned in `package.json`
- Architecture: **HIGH** — direct file inspection
- Pitfalls: **HIGH** — derived from control-flow in `handleTestConnection` and Forex defaults

**Research date:** 2026-04-11  
**Valid until:** ~30 days (frontend file may drift)
