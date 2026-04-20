# Phase 04 — Technical Research

**Phase:** Hardening and rollout safety  
**Date:** 2026-04-18  
**Question:** What do we need to know to PLAN this phase well?

## Summary

Phase 4 hardens **03-CONTEXT / 02-CONTEXT / N2** for production rollout:

1. **Operational visibility (04-CONTEXT D-01/D-02)** — Exit criteria do **not** require Prometheus; operators aggregate **`event`** (`ibkr_data_sufficiency_check` \| `ibkr_open_blocked_insufficient_data` \| `ibkr_insufficient_data_alert_sent`) plus **`reason_code`** and **`exchange_id`**. Today `build_ibkr_data_sufficiency_check_payload` omits **`exchange_id`** because Phase 1 orchestration does not receive strategy/exchange context; the **guard path** already logs `exchange_id` on blocked-open events. PLAN must thread optional **`exchange_id`** / **`strategy_id`** into evaluation logging when the caller is `SignalExecutor` so **all three** event families remain joinable in log pipelines.

2. **Schedule resilience (04-CONTEXT D-03/D-04)** — `get_ibkr_schedule_snapshot` in `ibkr_schedule_provider.py` is **pure** over `contract_details` (no network I/O in-file). **Transient failures** manifest as **exceptions** from parsing / `is_rth_check` / downstream helpers. **Bounded retry** belongs **around the first call** inside `evaluate_ibkr_data_sufficiency_and_log` (`data_sufficiency_service.py`), **not** a TTL cache of snapshots (explicitly **out of scope** per user). After retries exhausted, **re-raise** so Phase 2 guard maps to **synthetic insufficient** per existing contract.

3. **Rollout switches (04-CONTEXT D-05/D-06)** — Prefer **single deployment-wide env flag** read once at guard boundary (`SignalExecutor` sufficiency branch) or a tiny `app.config`-style helper under `backend_api_python/app/` to avoid scattered `os.getenv`. Default **enforce ON**; kill-switch OFF only when operators set env explicitly.

4. **Typed metadata strings (ROADMAP carryover)** — Replace free strings for `timezone_resolution` / `schedule_failure_reason` with **shared constants or StrEnum** in one module consumed by `ibkr_schedule_provider.py`, logs, and diagnostics to prevent drift.

5. **Regression + boundaries (04-CONTEXT D-07)** — Full `backend_api_python/tests` green; add `.planning` short **operator boundaries** note listing when false blocks may still occur (market data gaps vs evaluation failures).

## Key files

| Concern | Path |
|---------|------|
| Orchestration / retry seam | `backend_api_python/app/services/data_sufficiency_service.py` |
| Schedule adapter | `backend_api_python/app/services/live_trading/ibkr_trading/ibkr_schedule_provider.py` |
| Log emitters | `backend_api_python/app/services/data_sufficiency_logging.py` |
| Guard integration | `backend_api_python/app/services/signal_executor.py` |
| Types / reason codes | `backend_api_python/app/services/data_sufficiency_types.py` |

## Risks / pitfalls

- **Retry scope**: User locked **retry-only, no snapshot cache**. Do not persist last-good `IBKRScheduleSnapshot` across ticks.
- **Retry + logging spam**: Emit **structured** `ibkr_schedule_snapshot_retry` (or nested extra fields) **once per attempt** with `attempt`, `max_attempts`, `symbol`, bounded `error_class` — avoid stack traces in structured payload per Phase 2 R-04 spirit.
- **Kill-switch**: Document that disabling the guard **increases trading risk**; use only incident response.

## Validation Architecture

| Dimension | Phase 04 focus | Automated signal |
|-----------|----------------|------------------|
| Correctness | Retry then succeed vs exhaust; payloads include aggregation keys | pytest unit + integration |
| Safety | Kill-switch default ON; fail-safe after retry exhaustion | pytest env patch + executor path |
| Observability | Three `event` types + `reason_code` + `exchange_id` where wired | pytest payload asserts + grep docs |
| Regression | No Phase 1–3 behavior regression | **full** `pytest backend_api_python/tests` |
| Documentation | Operator boundaries doc exists | file presence + review |

Wave 0: **not required** — pytest suite already exists.

## RESEARCH COMPLETE

Planning can proceed with `04-CONTEXT.md`, `REQUIREMENTS.md`, `ROADMAP.md` Phase 4, and this file.
