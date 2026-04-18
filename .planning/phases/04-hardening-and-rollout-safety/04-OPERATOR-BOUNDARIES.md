# Phase 4 — Operator boundaries (IBKR data sufficiency)

This note explains **known residual false blocks**, **how to read structured logs**, and the **deployment kill-switch** for the IBKR sufficiency guard. It complements `.planning/ROADMAP.md` Phase 4 exit criteria. **Regression gate:** run full `python3 -m pytest backend_api_python/tests -q` before release.

## When a “false block” is expected vs a defect

- **Missing bars / schedule unknown:** The guard may block live IBKR `open_*` / `add_*` when bar history or session metadata does not meet configured `required_bars` / schedule classification. That can be correct risk-off behavior even when a human believes the market is tradable.
- **Evaluation failure after retries:** `get_ibkr_schedule_snapshot` is retried a bounded number of times; if all attempts fail, the execution path maps to a synthetic insufficient outcome (`DATA_EVALUATION_FAILED` semantics). Treat as infrastructure or contract-details health, not necessarily strategy logic.
- **Contract details unresolved:** When `ContractDetails` cannot be resolved for the symbol, the path fail-closes (insufficient) by design.

## Observability — four structured log families

Use these `event` keys (and suggested aggregation dimensions) in your log pipeline:

| `event` | Role | Typical aggregation keys |
|--------|------|---------------------------|
| `ibkr_data_sufficiency_check` | One info line per successful sufficiency classification on the evaluation path | `event`, `event_lane` (= `sufficiency_evaluation`), `reason_code`, `symbol`, `exchange_id` (when present), `strategy_id` (when present), `schedule_status` |
| `ibkr_open_blocked_insufficient_data` | Open/add blocked after sufficiency says insufficient | `event`, `strategy_id`, `exchange_id`, `reason_code`, `synthetic_evaluation_failure` |
| `ibkr_insufficient_data_alert_sent` | Phase 3 user-channel alert after a block (deduped) | `event`, `strategy_id`, `exchange_id`, `reason_code`, `dedup_*` |
| `ibkr_schedule_snapshot_retry` | Warning on transient snapshot failures before success or exhaustion | `event`, `attempt`, `max_attempts`, `symbol`, `exc_type`, `error_summary` |

**Query tips:** Correlate `ibkr_data_sufficiency_check` with `ibkr_open_blocked_insufficient_data` using `symbol`, `strategy_id`, and `exchange_id` when those dimensions are present on the check event.

## Kill-switch: `QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED`

- **Default:** Unset or empty → guard **enabled** (same effective behavior as after Phase 2 for live IBKR open/add).
- **Explicit disable:** Case-insensitive `false`, `0`, or `no` → **incident-only**: the executor skips the **entire** sufficiency branch for qualifying signals.
- **Alert coupling (R-03 / R-06):** When disabled, there is **no** sufficiency-driven open block **and** **no** Phase 3 insufficient user alerts that fire only from that blocked-open path. There is **no** “alerts without blocking” mode for this env flag in Phase 4.
- **Visibility:** The first skip in a process emits a single `ibkr_sufficiency_guard_disabled` warning (structured `event` key) so silent disable is avoided.

## Production threshold tuning

Per `.planning/phases/04-hardening-and-rollout-safety/04-CONTEXT.md` (D-07), **fine-tuning production sufficiency thresholds** (per-market `required_bars`, freshness windows, etc.) may remain future work. This document does not prescribe those numbers.

## Deferred fixtures (R-07)

Task 4 optional shared test fixtures were **not** extracted in this phase — churn outweighed value; tests remain colocated in existing modules.
