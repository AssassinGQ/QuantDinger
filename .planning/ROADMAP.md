# ROADMAP

## Milestone M1: IBKR data-sufficiency risk gate

### Phase 1: IBKR schedule + sufficiency domain model

**Objective:** define canonical sufficiency contract and IBKR trading-day adapter.

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
