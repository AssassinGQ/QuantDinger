# ROADMAP

## Milestone M1: IBKR data-sufficiency risk gate

### Phase 1: IBKR schedule + sufficiency domain model

**Objective:** define canonical sufficiency contract and IBKR trading-day adapter.

**Plans:** 2 plans

Plans:
- [x] `01-01-PLAN.md` — typed sufficiency contract and IBKR schedule adapter (2026-04-17)
- [x] `01-02-PLAN.md` — deterministic validator and structured sufficiency logging (2026-04-17)

**Tasks**

1. Define `DataSufficiencyResult` schema (`sufficient`, `reason_code`, diagnostics).
2. Add IBKR trading-day/session provider abstraction.
3. Implement strategy-required lookback normalization.
4. Add structured logging for sufficiency decisions.

**Exit Criteria**

- Deterministic sufficiency result for IBKR symbols/timeframes.
- Unit tests for reason-code mapping and edge cases.

### Phase 2: Open-signal guard in execution path

**Objective:** enforce no-open-on-insufficient-data for `ibkr-paper` + `ibkr-live`.

**Tasks**

1. Inject sufficiency check before open/add signal execution.
2. Block open/add when insufficient.
3. Ensure close/reduce actions remain allowed.
4. Add audit log/events for blocked opens.

**Exit Criteria**

- Open/add blocked on insufficiency in both IBKR modes.
- Close/reduce path unaffected.
- Integration tests pass for allow/block matrix.

#### Carryover from Phase 01 RE-REVIEW (2026-04-17)

- **Real-path `get_kline` alignment:** Add at least one integration or contract test on the execution-side data path that compares `compute_available_bars_from_kline_fetcher` (or the Phase 2 guard’s bar acquisition seam) against real or recorded `kline_fetcher.get_kline` behavior for representative `(market, symbol, timeframe, limit)` tuples, covering `LOWER_LEVELS` fallback and gap semantics where feasible.
- **False insufficient / false sufficient guard:** Tune or assert thresholds using production-like series so Phase 1 mocked-bar drift cannot hide silently behind Phase 1 unit tests alone.
- **Orchestration / `get_kline` exception contract:** When wiring `evaluate_ibkr_data_sufficiency_and_log` (or its Phase 2 façade) into the open/add path, define whether a raised `get_kline` / adapter error maps to a fail-safe insufficient outcome (and which `reason_code` or synthetic diagnostic), is wrapped as a runner-visible error, or propagates unchanged. Phase 1 intentionally propagates without mapping (see `data_sufficiency_service.py`).

### Phase 3: Alerting and user decision support

**Objective:** notify users through strategy-configured channels and support close/hold decision.

**Tasks**

1. Reuse strategy notification configuration for insufficiency alerts.
2. Implement cooldown/dedup policy per strategy/symbol/reason.
3. Include position context and action recommendation in alert payload.
4. Add tests for channel routing and dedup behavior.

**Exit Criteria**

- Alerts delivered via configured channels.
- Repeated alerts deduplicated by cooldown.
- Payload includes actionable decision context.

#### Carryover from Phase 01 RE-REVIEW (2026-04-17)

- **`stale_prev_close` policy:** Define operator-facing staleness thresholds, cooldown interactions, and how `FreshnessMetadata` from Phase 1 maps to user-visible alerts (Phase 1 only defines schema + safe defaults).
- **Large `missing_window` (seconds) across multi-day gaps:** Document alert copy / severity so operators interpret `market_closed_gap` + large `missing_window` as expected wall-clock shortfall, not only “missing last bar.”

### Phase 4: Hardening and rollout safety

**Objective:** reduce false blocks and ensure production-safe rollout.

**Tasks**

1. Add metrics dashboards/counters for sufficiency outcomes.
2. Add fallback policy for schedule-fetch failures (default fail-safe).
3. Add config switches for staged rollout.
4. Perform regression on existing IBKR signal execution tests.

**Exit Criteria**

- No regression in existing IBKR execution flows.
- Operational visibility available for block/alert rates.
- Rollout checklist completed.

#### Carryover from Phase 01 RE-REVIEW (2026-04-17)

- **Typed constants for metadata strings:** Replace free-string `timezone_resolution` / `schedule_failure_reason` literals with enums or const objects shared across adapter, logs, and guards to prevent silent drift (extends T-01-02 hardening).
- **Optional `timezone_trusted` (or equivalent):** If operators still confuse `schedule_known_open` with UTC fallback, add an explicit boolean to the contract behind a compatibility-conscious migration.
