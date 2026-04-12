---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: — Tech Debt Cleanup + Limit Orders
status: active
stopped_at: Completed 15-04-SUMMARY.md
last_updated: "2026-04-12T02:23:05.369Z"
progress:
  total_phases: 6
  completed_phases: 3
  total_plans: 7
  completed_plans: 7
---

# Project State

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** 清理 v1.0 遗留技术债务，增加 Forex 限价单，补全 E2E 测试覆盖。

**Current focus:** Phase 15 — normalize-pipeline-ordering

**Verification:** use-case-driven (`.planning/config.json`). **Regression gate:** backend pytest suite must stay green.

## Current Position

Phase: 15 (normalize-pipeline-ordering) — **COMPLETE** (4/4 plans)
Plan: Next — Phase 16 (precious metals contract classification) per ROADMAP

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

### Pending Todos

- Continue v1.1 roadmap: Phase 16 (precious metals contract classification), then 17–18 as dependencies allow.

### Blockers/Concerns

- Paper/sandbox validation may still be needed for venue-specific metals and HShare TIF edge cases (see research flags).

## Session Continuity

**Last session:** 2026-04-12T02:23:05.366Z
**Stopped At:** Completed 15-04-SUMMARY.md
**Resume File:** None
