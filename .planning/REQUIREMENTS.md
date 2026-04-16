# REQUIREMENTS

## Scope

Milestone scope is limited to IBKR execution strategies (`ibkr-paper`, `ibkr-live`) and related risk/notification paths.

## Functional Requirements

### R1. Data Sufficiency Evaluation

System MUST evaluate data sufficiency per strategy tick before open-position execution:

- Input dimensions:
  - strategy-required data window (lookback bars / minimum required observations)
  - symbol + timeframe + market category
  - current available data window
  - IBKR trading-day/session context
- Output:
  - `sufficient: bool`
  - `reason_code` (e.g., missing_bars, stale_prev_close, market_closed_gap, unknown_schedule)
  - `missing_window` / `effective_lookback`

### R2. IBKR Trading-Day Awareness

For IBKR strategies, sufficiency logic MUST use IBKR-provided trading schedule/day information (or internally cached IBKR schedule source) to avoid incorrect natural-day assumptions.

### R3. Open Signal Guard

When `sufficient == false`, system MUST block open/add-position actions.

- Applies to both `ibkr-paper` and `ibkr-live`.
- MUST NOT block risk-reducing close/reduce actions.

### R4. User Alerting

On insufficiency detection (with deduplicated cooldown), system MUST notify user via strategy-configured channels.

Alert MUST include:

- strategy id/name
- symbol / mode (`ibkr-paper` or `ibkr-live`)
- insufficiency reason
- required vs available data summary
- current position snapshot (if any)
- recommendation: open blocked; user may review and decide whether to close

### R5. Existing Position Decision Support

When insufficiency is detected and position exists:

- system MUST emit warning-level risk notification
- system MUST NOT auto-force-close by default
- message MUST explicitly ask user to decide close/hold

## Non-Functional Requirements

### N1. Consistency

Guard behavior and reason codes should be consistent across both IBKR modes.

### N2. Safety

Failure to fetch schedule should fail safe for opening new positions unless explicit fallback policy is configured.

### N3. Observability

Add structured logs/metrics:

- `ibkr_data_sufficiency_check`
- `ibkr_open_blocked_insufficient_data`
- `ibkr_insufficient_data_alert_sent`

### N4. Testability

Add unit/integration tests to cover:

- sufficient path allows open
- insufficient path blocks open
- close/reduce still allowed during insufficiency
- alert channel dispatch with strategy notification config

## Out of Scope

- New frontend decision UI workflow
- Automatic forced close policy changes (unless separately approved)
- Non-IBKR exchanges

## Discussion Notes (Pending Design Decision)

The following idea is recorded for later design discussion and is not mandatory for immediate implementation:

1. Introduce an independent filtering/guard module for execution safety (for example, `DataSufficiencyGuard`) so sufficiency checks are centralized instead of being spread across runners/executors.
2. Let strategies explicitly declare required data contract back to the framework (e.g., required kline timeframes, minimum bars, freshness rules, optional derived features).
3. Framework consumes that contract and computes sufficiency against IBKR trading-day/session context before allowing open/add actions.

Rationale:

- Better separation of concerns (strategy signal generation vs framework risk gating)
- Easier auditing/testing of sufficiency logic
- Easier future extension to additional markets/data types without runner-specific patches
