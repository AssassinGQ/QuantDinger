# Phase 1: IBKR schedule + sufficiency domain model - Context

**Gathered:** 2026-04-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Define a canonical data sufficiency contract and an IBKR trading-day/session adapter for IBKR strategies. This phase establishes typed sufficiency outputs and evaluation boundaries for later open-signal guard enforcement; it does not implement the execution-path blocking itself.

</domain>

<decisions>
## Implementation Decisions

### Sufficiency Result Contract
- **D-01:** `DataSufficiencyResult` uses a strong-typed schema rather than a minimal dynamic payload.
- **D-02:** The schema must include stable top-level fields for downstream guard/alert consumers (not only nested diagnostics payloads).

### Reason Codes and Failure Policy
- **D-03:** `reason_code` uses fine-grained taxonomy (not coarse buckets).
- **D-04:** Schedule fetch/parse failure is fail-safe: open/add should be considered blocked by downstream guard; close/reduce remains allowed in later phases.
- **D-05:** Phase 1 output should carry explicit schedule-failure reason for downstream decisions.

### Lookback Normalization
- **D-06:** Strategy-side contract remains bars-first: strategy declares required `timeframe + bars`.
- **D-07:** Sufficiency threshold uses hard rule (`available_bars < required_bars` => insufficient), no tolerance window in this milestone.
- **D-08:** Session/trading-day interpretation is framework responsibility (not strategy responsibility).

### Component Boundaries
- **D-09:** `trading_hours` and `df_validator` (data sufficiency validator) are peer components, not merged into one module.
- **D-10:** A shared utility layer may be extracted for common concerns (time/session normalization, cache/fuse helpers, schedule normalization primitives).
- **D-11:** For this phase, prefer wrapping/reusing existing `trading_hours` behavior behind adapter-facing interfaces rather than replacing it immediately.

### Claude's Discretion
- Naming selection between `df_filter` vs `df_validator` vs `data_sufficiency_validator`.
- Exact typed field names in `DataSufficiencyResult` as long as D-01/D-02/D-05 are preserved.
- Utility module layout for shared helpers.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone Scope and Requirements
- `.planning/ROADMAP.md` — Phase 1 objective, tasks, and exit criteria.
- `.planning/REQUIREMENTS.md` — R1/R2/R3/N2 constraints that shape sufficiency and fail-safe behavior.
- `.planning/PROJECT.md` — milestone-level intent and success criteria.

### Existing IBKR Session Logic
- `backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py` — current liquidHours parsing, timezone mapping, RTH check, and fuse behavior.

### Existing Execution and Data Access Paths
- `backend_api_python/app/services/signal_executor.py` — execution flow where downstream guard will be consumed in later phase.
- `backend_api_python/app/services/kline_fetcher.py` — current K-line availability/read model relevant to sufficiency input data.
- `backend_api_python/tests/test_signal_executor.py` — existing execution-path test patterns to align future sufficiency/guard tests.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `trading_hours.is_rth_check`: existing IBKR liquidHours-based session gate logic.
- `trading_hours.parse_liquid_hours`: reusable parser for IBKR schedule segments.
- `trading_hours._fuse_until` + fuse helpers: reusable anti-chatter mechanism for repeated closed-session checks.
- `kline_fetcher.get_kline`: central K-line retrieval path usable for sufficiency input sampling.

### Established Patterns
- Fail-closed behavior already exists in `trading_hours` when sessions cannot be parsed.
- Service-layer modules keep broker API fetching and pure logic separated.
- Structured logging is used in execution paths; sufficiency should align with existing logging style.

### Integration Points
- Phase 1 outputs are consumed later by execution guards in signal/order path (`signal_executor` and related live-trading execution services).
- Reason-code and diagnostics schema should be testable via existing pytest patterns under `backend_api_python/tests/`.

</code_context>

<specifics>
## Specific Ideas

- Strategy contract should stay simple: strategy declares required bars/timeframe; framework interprets session/trading-day constraints using IBKR schedule context.
- Keep `trading_hours` focused on session truth and keep sufficiency validator focused on data completeness.

</specifics>

<deferred>
## Deferred Ideas

- Full replacement of `trading_hours` with a new implementation can be evaluated after guard/alert pipeline is stable.
- Optional future support for tolerance-based thresholds is deferred; this milestone locks hard-threshold policy.

</deferred>

---

*Phase: 01-ibkr-schedule-sufficiency-domain-model*
*Context gathered: 2026-04-16*
