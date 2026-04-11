# Phase 12: Frontend IBKR exchanges for Forex - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Strategy create/edit UI offers ibkr-paper and ibkr-live as Forex broker options alongside existing MT5. When the user selects Forex as market_category, the broker dropdown includes all three choices (MT5, IBKR Paper, IBKR Live). Selecting IBKR hides MT5-specific fields; selecting MT5 shows them. No new backend changes — backend already supports Forex + ibkr-paper/ibkr-live (Phase 11).

</domain>

<decisions>
## Implementation Decisions

### Forex Broker List
- **Flat list** with three options: MT5 / IBKR Paper / IBKR Live — add IBKR entries to `FOREX_BROKER_OPTIONS` constant
- Reuse the same `IBKR Paper` / `IBKR Live` display names and style as the stock (USStock/HShare) broker path
- **No default value** — force the user to manually select a broker (currently defaults to `mt5`; remove that default)

### Form Field Switching
- When Forex + IBKR is selected: **hide all MT5 fields** (mt5_server, mt5_login, mt5_password, mt5_terminal_path) — identical to stock + IBKR behavior, no additional config fields needed
- When Forex + MT5 is selected: show MT5 fields as before (no change)
- Test connection button: **reuse the stock IBKR test connection** path (`/api/ibkr/connect`) when Forex + IBKR is selected

### Computed Property Rename
- Rename `isMT5Market` to `isForexMarket` — the current name conflates "Forex" with "MT5" which is no longer accurate
- Inside `isForexMarket`, further distinguish IBKR vs MT5 by the selected broker value (e.g. `isForexIBKR` / `isForexMT5` sub-checks) to control field visibility and test connection routing

### Edit Backfill & Compatibility
- **Auto-detect on edit**: read `exchange_config.exchange_id` from the existing strategy — `mt5` backfills to MT5 broker, `ibkr-paper`/`ibkr-live` backfills to IBKR broker. No user action needed
- **exchange_config format for Forex + IBKR**: identical to stock — `{ exchange_id: 'ibkr-paper' }` with no extra fields. Backend already handles this (Phase 11 validation + factory)

### Claude's Discretion
- i18n key naming for new broker options (follow existing `exchangeNames.*` / `brokerNames.*` pattern)
- Exact placement and ordering of brokers in the dropdown (MT5 first or IBKR first — pick what feels natural)
- Any cosmetic adjustments to the form layout when switching between MT5 and IBKR fields

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Frontend (primary change target)
- `quantdinger_vue/src/views/trading-assistant/index.vue` — Strategy create/edit wizard; contains `FOREX_BROKER_OPTIONS`, `BROKER_OPTIONS`, `isMT5Market`, `isIBKRMarket`, broker dropdown templates, `exchange_config` assembly logic, and edit backfill logic
- `quantdinger_vue/src/api/strategy.js` — `createStrategy` / `updateStrategy` API wrappers
- `quantdinger_vue/src/locales/lang/en-US.js` (and other locale files) — `exchangeNames`, `brokerNames` i18n keys

### Backend (reference only — no changes expected)
- `backend_api_python/app/services/live_trading/factory.py` — `create_client` dispatches `ibkr-paper`/`ibkr-live` for IBKR
- `backend_api_python/app/services/strategy.py` — `validate_exchange_market_category` allows Forex + ibkr-paper/ibkr-live
- `.planning/phases/11-strategy-automation-forex-ibkr/11-CONTEXT.md` — Phase 11 decisions on API validation

### Requirements
- `.planning/REQUIREMENTS.md` §FRNT-01 — "策略创建/编辑页面，当 market_category=Forex 时，交易所选择列表包含 ibkr-paper 和 ibkr-live"

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BROKER_OPTIONS` constant: already has `{ value: 'ibkr-paper', ... }` and `{ value: 'ibkr-live', ... }` — can be directly referenced or merged into the Forex broker list
- `brokerOptions` computed property: maps `BROKER_OPTIONS` to display names via i18n — same pattern for `forexBrokerOptions`
- `handleBrokerSelectChange`: existing IBKR broker change handler — can be reused or shared for Forex + IBKR path
- IBKR test connection logic: `this.$http.post('/api/ibkr/connect', { broker_id })` — already implemented for stock path

### Established Patterns
- Market category → broker/exchange conditional rendering: `<template v-if="isIBKRMarket">` / `<template v-else-if="isMT5Market">` / `<template v-else>` (Crypto)
- `exchange_config` assembly in form submit: branch by `isIBKRMarket` / `isMT5Market` / else(Crypto)
- Edit backfill: `setFieldsValue` in `loadStrategyForEdit` reads `exchange_config.exchange_id` to restore form state

### Integration Points
- `FOREX_BROKER_OPTIONS` constant (~line 1719): add `ibkr-paper` and `ibkr-live` entries
- `isMT5Market` computed property (~line 1870): rename to `isForexMarket`; add sub-check for IBKR vs MT5
- Template section for Forex broker (~line 1383–1420): conditional rendering based on selected broker within Forex
- Form submit `exchange_config` assembly (~line 4282): add Forex + IBKR branch (same as stock IBKR format)
- `selectedMarketCategory` watcher / `handleMultiSymbolChange`: remove hardcoded `currentBrokerId = 'mt5'` for Forex; do not auto-set a default

</code_context>

<specifics>
## Specific Ideas

- "和股票的方式一致即可" — user explicitly wants Forex + IBKR to mirror the existing stock + IBKR UX pattern as closely as possible
- No new UI paradigms — the only difference from stock is that Forex also has MT5 as an alternative broker option

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 12-frontend-ibkr-exchanges-for-forex*
*Context gathered: 2026-04-11*
