---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
stopped_at: Completed 12-01-PLAN.md
last_updated: "2026-04-11T09:24:47.181Z"
progress:
  total_phases: 12
  completed_phases: 12
  total_plans: 15
  completed_plans: 15
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-04-09)

**Core value:** 策略系统发出的 Forex 交易信号能正确通过 IBKRClient 在 IDEALPRO 上执行，从信号到成交的完整链路畅通。

**Current focus:** Phase 12 — frontend-ibkr-exchanges-for-forex

## Current Position

Phase: 12 (frontend-ibkr-exchanges-for-forex) — COMPLETE
Plan: 1 of 1 (12-01 done)

## Performance Metrics

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 01 P01 | 2min | 2 tasks | 2 files |
| Phase 02 P01 | 8min | 2 tasks | 2 files |
| Phase 03 P01 | 30min | 2 tasks | 3 files |
| Phase 05 P01 | 10min | 1 tasks | 8 files |
| Phase 06 P01 | 5 min | 1 tasks | 2 files |
| Phase 07-forex-market-orders P01 | 12min | 2 tasks | 2 files |
| Phase 08 P01 | 4min | 1 tasks | 2 files |
| Phase 08-quantity-normalization-ib-alignment P02 | 12min | 1 tasks | 1 files |
| Phase 09-forex-trading-hours-liquidhours P01 | 25min | 3 tasks | 4 files |
| Phase 10-fills-position-pnl-events P01 | 30min | 4 tasks | 4 files |
| Phase 11-strategy-automation-forex-ibkr P03 | 12min | 1 tasks | 1 files |
| Phase 11-strategy-automation-forex-ibkr P01 | 25min | 2 tasks | 8 files |
| Phase 11-strategy-automation-forex-ibkr P02 | 25min | 2 tasks | 2 files |
| Phase 12-frontend-ibkr-exchanges-for-forex P01 | 28min | 3 tasks | 6 files |

## Accumulated Context

### Decisions

Logged in PROJECT.md Key Decisions. Roadmap follows research build order (symbols → contract → signal/TIF → execution → runtime → frontend) with use-case-driven verification per `config.json`.

- [Phase 01]: KNOWN_FOREX_PAIRS set for parse_symbol auto-detection (no heuristic fallback)
- [Phase 01]: Forex display format: dot-separated EUR.USD matching IBKR localSymbol convention
- [Phase 02]: Forex uses ib_insync.Forex(pair=ib_symbol) — pair= keyword delegates symbol/currency splitting
- [Phase 02]: Explicit elif market_type guard (USStock/HShare) — unknown market_type raises ValueError
- [Phase 03]: _EXPECTED_SEC_TYPES dict mapping (Forex→CASH, USStock/HShare→STK) for post-qualify validation
- [Phase 03]: Mock qualifyContractsAsync simulates in-place mutation (conId, secType) matching real IB dataclassUpdate
- [Phase 05]: Forex: IBKR uses _FOREX_SIGNAL_MAP (eight signals, MT5-aligned) when market_category is Forex.
- [Phase 05]: Non-Forex IBKR rejects short-style signals with ValueError containing 美股/港股不支持 short.
- [Phase 06]: Forex TIF (EXEC-03): _get_tif_for_signal returns IOC for all Forex signal types; USStock and HShare rules unchanged.
- [Phase 07-forex-market-orders]: Forex zero-after-alignment errors append IDEALPRO minimum-size hint; equity messages unchanged.
- [Phase 08-01 / EXEC-04]: ForexNormalizer `normalize` passthrough (`float`); IB increment alignment remains for 08-02 (`_align_qty_to_contract` tests).
- [Phase 08-quantity-normalization-ib-alignment]: Isolated _align_qty_to_contract tests use AsyncMock + SimpleNamespace; UC-A5 proves single reqContractDetailsAsync via cache.
- [Phase 09]: Forex is_market_open closed reason: append Forex 24/5 weekend/maintenance hint when market_type is Forex
- [Phase 10]: `qd_ibkr_pnl_single` stores sec_type/exchange/currency; `get_positions()` reads DB with STK/SMART/USD fallbacks; `_conid_to_symbol` and saves use `localSymbol` when string else `symbol`; `ibkr_save_pnl` dead clamps removed (UC-FP6).
- [Phase 11-strategy-automation-forex-ibkr]: Mock IBKR Paper smoke: test_ibkr_forex_paper_smoke.py uses _FakeEvent for handler registration, pair-specific qualify (EURUSD 12087792, GBPJPY 12345678, XAGUSD 87654321), and orderStatus→execDetails→position→pnlSingle after each fill; DB saves patched.
- [Phase 11-strategy-automation-forex-ibkr P01]: `validate_exchange_market_category` in factory + static `validate_market_category_static` on stateful clients; `StrategyService` validates non-empty `exchange_id` against `market_category` before INSERT/UPDATE; UC-SA-VAL-01–08 in `test_strategy_exchange_validation.py`.
- [Phase 11-strategy-automation-forex-ibkr]: E2E tests mock worker imports at pending_order_worker; API test uses mocked DB insert for real StrategyService.create_strategy path.
- [Phase 12-frontend-ibkr-exchanges-for-forex]: Vault save after strategy create only for crypto (isCryptoMarket); Forex MT5/IBKR excluded.
- [Phase 12-frontend-ibkr-exchanges-for-forex]: Jest uses @vue/vue2-jest transform for Vue 2 SFCs (CLI 5 peer).

### Pending Todos

None yet.

### Blockers/Concerns

- IDEALPRO paper trading remains useful to validate IOC fills in live-like conditions; policy is locked in code (EXEC-03).

## Session Continuity

**Last session:** 2026-04-11T09:16:53.090Z
**Stopped At:** Completed 12-01-PLAN.md
**Resume File:** None
