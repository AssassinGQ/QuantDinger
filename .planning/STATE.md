---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: — Tech Debt Cleanup + Limit Orders
status: unknown
stopped_at: Completed 18-03-PLAN.md
last_updated: "2026-04-12T08:35:00.000Z"
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 19
  completed_plans: 18
---

# Project State

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** 清理 v1.0 遗留技术债务，增加 Forex 限价单，补全 E2E 测试覆盖。

**Current focus:** Phase 18 — e2e-integration-testing

**Verification:** use-case-driven (`.planning/config.json`). **Regression gate:** backend pytest suite must stay green.

## Current Position

Phase: 18 (e2e-integration-testing) — EXECUTING
Plan: 18-03 complete — next unchecked: `18-06-PLAN.md` (see ROADMAP)

## Performance Metrics

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| *(v1.1 TBD)* | — | — | — |
| Phase 13 P02 | 5min | 1 tasks | 1 files |

*(v1.0 metrics retained in git history / prior STATE revisions.)*

| Phase 13-qualify-result-caching-e2e-prefix-fix P01 | 25min | 3 tasks | 6 files |
| Phase 14-tif-unification-usstock-hshare P01 | ~20min | 1 task | 2 files |
| Phase 15-normalize-pipeline-ordering P01 | 15min | 2 tasks | 11 files |
| Phase 15-normalize-pipeline-ordering P03 | 1min | 2 tasks | 2 files |
| Phase 15-normalize-pipeline-ordering P02 | 25min | 2 tasks | 4 files |
| Phase 15-normalize-pipeline-ordering P04 | 12min | 2 tasks | 5 files |
| Phase 16-precious-metals-contract-classification P01 | 12min | 1 tasks | 2 files |
| Phase 16-precious-metals-contract-classification P03 | 18min | 3 tasks | 4 files |
| Phase 17-forex-limit-orders-automation P01 | 25min | 1 tasks | 3 files |
| Phase 18-e2e-integration-testing P01 | 8min | 2 tasks | 6 files |
| Phase 18-e2e-integration-testing P05 | 5min | 1 tasks | 1 files |
| Phase 18-e2e-integration-testing P04 | 10min | 2 tasks | 1 files |
| Phase 18-e2e-integration-testing P03 | 25min | 2 tasks | 1 files |
| Phase 18-e2e-integration-testing P02 | 25min | 2 tasks | 1 files |

## Accumulated Context

### Decisions

- **Roadmap order (v1.1):** qualify cache → TIF unification → normalize timing → precious metals classification → Forex limit orders (client + partials + runner/worker) → E2E/API prefix/optional Playwright — per `.planning/research/SUMMARY.md`.
- **Requirement mapping:** each v1.1 requirement maps to exactly one phase (see `.planning/REQUIREMENTS.md` traceability).
- **[Phase 13]:** E2E test Flask app registers `strategy_bp` with `url_prefix='/api'` and POST `/api/strategies/create`, matching `register_routes` (TEST-01).
- [Phase 13]: Qualify cache: (symbol, market_type) key, per-market IBKR_QUALIFY_TTL_*_SEC, no flush on reconnect
- **[Phase 15-01]:** Market-layer helpers renamed to `MarketPreNormalizer` / `*PreNormalizer` with `pre_normalize` / `pre_check`; factory `get_market_pre_normalizer`; shim re-exports new symbols until plan 15-04; `ibkr_trading/client.py` and `signal_executor` call sites updated in the same change set.
- [Phase 15-normalize-pipeline-ordering]: 15-03: SignalExecutor module-level get_market_pre_normalizer + pre_normalize before enqueue; TC-15-T3-03 mocks factory and asserts enqueued amount.
- [Phase 15]: Phase 15-02: IBKRClient place_market_order/limit_order run pre_normalize then pre_check from order_normalizer; pre-normalized qty feeds _align_qty_to_contract; HShare pre_normalize keeps sub-lot positives for board-lot pre_check messages.
- [Phase 15-normalize-pipeline-ordering]: 15-04: Removed ibkr_trading/order_normalizer shim; tests assert ModuleNotFoundError via importlib; canonical path is app.services.live_trading.order_normalizer only.
- [Phase 16-precious-metals-contract-classification]: Symbol layer: XAU*/XAG* six-letter pairs classify as Metals before Forex set; XAUEUR excluded; normalize_symbol(Metals) returns full pair + SMART + quote for CMDTY inputs.
- [Phase 16-precious-metals-contract-classification]: 16-02: IBKRClient `Metals` uses `Contract` CMDTY/SMART; `ForexPreNormalizer` for factory; IOC + Forex signal map; qualify TTL shares `IBKR_QUALIFY_TTL_FOREX_SEC`; TRADE-04 satisfied at client layer.
- [Phase 16-precious-metals-contract-classification]: 16-03: Integration tests — engine/strategy Metals; smoke/E2E XAGUSD with `market_category` Metals, qualify CMDTY, conId 77124483; TRADE-04 closed with full pytest gate.
- **[Phase 17-forex-limit-orders-automation]:** 17-01: `_get_tif_for_signal(..., order_type)` — limit→DAY; `place_limit_order` minTick snap (BUY floor/SELL ceil); optional `time_in_force` IOC/DAY/GTC; REST `timeInForce` when key present; TRADE-01 satisfied at client + route + tests.
- **[Phase 18-e2e-integration-testing]:** 18-01: Shared `tests/helpers/ibkr_mocks` + `flask_strategy_app` + `conftest` `strategy_client` / `patched_records`; smoke and `test_forex_ibkr_e2e` refactored to shared imports (foundation for TRADE-05/06 + TEST-02 work in 18-02+).
- [Phase 18-e2e-integration-testing]: 18-05: Strategy HTTP E2E tests patch get_strategy_service inside tests after strategy_client to avoid reload clearing mocks
- [Phase 18-e2e-integration-testing]: 18-04: Added test_e2e_cross_market_usstock_hshare_ibkr.py — USStock/HShare market full chains + USStock limit (minTick 0.01, DAY TIF); TRADE-05/TRADE-06 cross-market worker coverage.
- [Phase 18-e2e-integration-testing]: 18-03: test_e2e_limit_cancel_errors_ibkr.py covers TRADE-06 limit/partial/cancel and qualify/validation/price error paths with documented rejection layers.
- [Phase 18-e2e-integration-testing]: 18-02: test_e2e_qualify_cache_ibkr.py covers qualify cache (monotonic TTL, invalidation, reconnect) and TRADE-05 XAGUSD CMDTY worker chain

### Pending Todos

- Continue Phase 18: execute `18-06-PLAN.md` (Vue Jest); Phase 18 plans 18-01–18-05 and 18-03 complete per ROADMAP.

### Blockers/Concerns

- Paper/sandbox validation may still be needed for venue-specific metals and HShare TIF edge cases (see research flags).

## Session Continuity

**Last session:** 2026-04-12T08:35:00.000Z
**Stopped At:** Completed 18-03-PLAN.md
**Resume File:** `.planning/phases/18-e2e-integration-testing/18-06-PLAN.md`
