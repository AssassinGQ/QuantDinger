---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: — Tech Debt Cleanup + Limit Orders
status: unknown
stopped_at: Completed `15-01-SUMMARY.md` — Phase 15 plan 01 (MarketPreNormalizer rename + tests + planning docs)
last_updated: "2026-04-12T12:35:00.000Z"
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 7
  completed_plans: 4
---

# Project State

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** 清理 v1.0 遗留技术债务，增加 Forex 限价单，补全 E2E 测试覆盖。

**Current focus:** Phase 15 — normalize-pipeline-ordering

**Verification:** use-case-driven (`.planning/config.json`). **Regression gate:** backend pytest suite must stay green.

## Current Position

Phase: 15 (normalize-pipeline-ordering) — EXECUTING
Plan: 2 of 4

## Performance Metrics

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| *(v1.1 TBD)* | — | — | — |
| Phase 13 P02 | 5min | 1 tasks | 1 files |

*(v1.0 metrics retained in git history / prior STATE revisions.)*

| Phase 13-qualify-result-caching-e2e-prefix-fix P01 | 25min | 3 tasks | 6 files |
| Phase 14-tif-unification-usstock-hshare P01 | ~20min | 1 task | 2 files |
| Phase 15-normalize-pipeline-ordering P01 | 15min | 2 tasks | 11 files |

## Accumulated Context

### Decisions

- **Roadmap order (v1.1):** qualify cache → TIF unification → normalize timing → precious metals classification → Forex limit orders (client + partials + runner/worker) → E2E/API prefix/optional Playwright — per `.planning/research/SUMMARY.md`.
- **Requirement mapping:** each v1.1 requirement maps to exactly one phase (see `.planning/REQUIREMENTS.md` traceability).
- **[Phase 13]:** E2E test Flask app registers `strategy_bp` with `url_prefix='/api'` and POST `/api/strategies/create`, matching `register_routes` (TEST-01).
- [Phase 13]: Qualify cache: (symbol, market_type) key, per-market IBKR_QUALIFY_TTL_*_SEC, no flush on reconnect
- **[Phase 15-01]:** Market-layer helpers renamed to `MarketPreNormalizer` / `*PreNormalizer` with `pre_normalize` / `pre_check`; factory `get_market_pre_normalizer`; shim re-exports new symbols until plan 15-04; `ibkr_trading/client.py` and `signal_executor` call sites updated in the same change set.

### Pending Todos

- Continue Phase 15: execute `15-02-PLAN.md` (IBKR client pipeline order) then `15-03` / `15-04` per ROADMAP.

### Blockers/Concerns

- Paper/sandbox validation may still be needed for venue-specific metals and HShare TIF edge cases (see research flags).

## Session Continuity

**Last session:** 2026-04-12T02:12:55.882Z
**Stopped At:** Completed 15-01-PLAN.md
**Resume File:** 15-02-PLAN.md (IBKRClient pipeline)
