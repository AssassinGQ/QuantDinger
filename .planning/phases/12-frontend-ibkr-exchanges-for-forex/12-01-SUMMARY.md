---
phase: 12-frontend-ibkr-exchanges-for-forex
plan: "01"
subsystem: ui
tags: [vue, forex, ibkr, jest, i18n]

requires:
  - phase: 11-strategy-automation-forex-ibkr
    provides: Backend validates Forex + ibkr-paper/live exchange_config
provides:
  - Forex strategy wizard lists MT5, IBKR Paper, and IBKR Live with correct payloads and test-connection routing
  - FRNT-01 regression test (static source guard) and Jest transform fix (@vue/vue2-jest)
affects:
  - strategy create/edit UX for market_category Forex

tech-stack:
  added: ["@vue/vue2-jest (dev)"]
  patterns:
    - "Forex computed split: isForexMarket, isForexMT5, isForexIBKR; IBKR connect shared for stock and Forex IBKR"

key-files:
  created:
    - quantdinger_vue/tests/unit/frnt-01-forex-ibkr-options.spec.js
  modified:
    - quantdinger_vue/src/views/trading-assistant/index.vue
    - quantdinger_vue/src/locales/lang/en-US.js
    - quantdinger_vue/src/locales/lang/zh-CN.js
    - quantdinger_vue/jest.config.js
    - quantdinger_vue/package.json

key-decisions:
  - "Vault credential save after create runs only for crypto (`isCryptoMarket`), not Forex MT5 or IBKR."
  - "Jest Vue SFC transform uses `@vue/vue2-jest` (Vue CLI 5 peer) instead of missing `vue-jest`."

patterns-established:
  - "Forex live `exchange_config`: `{ exchange_id: ibkr-* }` only for IBKR; MT5 branch retains mt5_* fields."

requirements-completed: [FRNT-01]

duration: 28min
completed: 2026-04-11
---

# Phase 12 Plan 01: Frontend IBKR exchanges for Forex Summary

**Forex strategy wizard offers MT5 plus IBKR Paper/Live with stock-aligned `exchange_id` payloads, `/api/ibkr/connect` for Forex+IBKR, and a static Jest guard for FRNT-01.**

## Performance

- **Duration:** ~28 min
- **Started:** 2026-04-11 (session)
- **Completed:** 2026-04-11
- **Tasks:** 3
- **Files modified/created:** 6

## Accomplishments

- Extended `FOREX_BROKER_OPTIONS`, renamed `isMT5Market` → `isForexMarket`, added `isForexMT5` / `isForexIBKR`, and wired load/submit/test/vault behavior per FRNT-01.
- Added `trading-assistant.brokerNames` entries for `ibkr-paper` and `ibkr-live` in English and Chinese.
- Added `frnt-01-forex-ibkr-options.spec.js` and fixed Jest to use `@vue/vue2-jest` so `npm run test:unit -- --testPathPattern=frnt-01-forex-ibkr-options` runs.

## Task Commits

1. **Task 1: trading-assistant index.vue — Forex IBKR behavior** — `4c5e9f6` (feat)
2. **Task 2: i18n brokerNames for ibkr-paper and ibkr-live** — `8e85a1e` (feat)
3. **Task 3: Jest guard + regression commands** — `1d29358` (test)

**Plan metadata:** docs commit bundles SUMMARY, STATE, ROADMAP, REQUIREMENTS (see `git log -1 --oneline` after pull).

## Files Created/Modified

- `quantdinger_vue/src/views/trading-assistant/index.vue` — Forex broker UX, computed flags, load/submit, test connection, vault gate.
- `quantdinger_vue/src/locales/lang/en-US.js` — broker display names for IBKR paper/live.
- `quantdinger_vue/src/locales/lang/zh-CN.js` — broker display names for IBKR paper/live.
- `quantdinger_vue/tests/unit/frnt-01-forex-ibkr-options.spec.js` — static FRNT-01 guard.
- `quantdinger_vue/jest.config.js` — Vue transform → `@vue/vue2-jest`.
- `quantdinger_vue/package.json` — devDependency `@vue/vue2-jest`.

## Decisions Made

- Followed CONTEXT: no default Forex broker; user must select MT5 or IBKR.
- Chose `@vue/vue2-jest` to satisfy Vue CLI 5 unit-jest peer and unblock Jest (replacing unresolved `vue-jest`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Jest could not resolve `vue-jest`**

- **Found during:** Task 3 (Jest guard)
- **Issue:** `jest.config.js` referenced `vue-jest`, which was not installed; `@vue/cli-plugin-unit-jest` expects `@vue/vue2-jest` as optional peer for Vue 2.
- **Fix:** Added `@vue/vue2-jest` to devDependencies and updated the `.vue` transform in `jest.config.js`.
- **Files modified:** `quantdinger_vue/jest.config.js`, `quantdinger_vue/package.json`
- **Verification:** `npm run test:unit -- --testPathPattern=frnt-01-forex-ibkr-options` passes.
- **Committed in:** `1d29358`

**2. Locale `node --check` (plan acceptance)**

- **Found during:** Task 2 verification
- **Issue:** `en-US.js` / `zh-CN.js` use ESM `import`; plain `node --check` fails (not a syntax error in the build pipeline).
- **Fix:** None required — Webpack/babel compiles these modules; keys were validated with `grep`.

---

**Total deviations:** 1 auto-fixed (blocking infra); 1 documented verification nuance.

**Impact on plan:** Jest dependency aligns with Vue CLI 5; no change to FRNT-01 product behavior.

## Issues Encountered

None blocking — `pytest tests/` (928 passed, 11 skipped) and Jest guard both green after `@vue/vue2-jest` fix.

## User Setup Required

None.

## Next Phase Readiness

Phase 12 plan 01 complete; Forex + IBKR paper/live is selectable in the strategy wizard with correct API test and persistence shapes.

---
*Phase: 12-frontend-ibkr-exchanges-for-forex*

## Self-Check: PASSED

- `12-01-SUMMARY.md` present at `.planning/phases/12-frontend-ibkr-exchanges-for-forex/12-01-SUMMARY.md`
- Task commits `4c5e9f6`, `8e85a1e`, `1d29358`; planning/docs commit includes SUMMARY and state updates
