# Phase 03 — Technical Research

**Phase:** Alerting and user decision support  
**Date:** 2026-04-18  
**Question:** What do we need to know to PLAN this phase well?

## Summary

Phase 3 sits **immediately downstream** of the Phase 2 open/add guard in `SignalExecutor.execute`: when `evaluate_ibkr_open_data_sufficiency` returns `sufficient is False`, the executor already emits `ibkr_open_blocked_insufficient_data` via `build_ibkr_open_blocked_insufficient_data_payload` + `emit_ibkr_open_blocked_insufficient_data`. Phase 3 MUST add **user-channel** notifications only at that **same block moment** (03-CONTEXT D-01), not on every sufficiency evaluation tick.

Implementation should:

1. **Reuse** `load_notification_config(strategy_id)` from `app.services.live_trading.records` when `strategy_ctx` does not already carry a complete config (runner paths may inject `_notification_config`; executor already reads it — prefer DB load only if missing).
2. **Dispatch** through `SignalNotifier.notify_signal(...)` with a dedicated `signal_type` string for this alert family (e.g. `ibkr_insufficient_data_block` or similar) and put machine-stable fields in `extra` so `_build_payload` merges them for webhook/email/browser parity.
3. **Dedup/cooldown** in a small dedicated module (process-local dict + `time.monotonic()` timestamps): composite key `strategy_id + symbol + reason_code + exchange_id`, default **300s** (5 minutes) per 03-CONTEXT D-03/D-04.
4. **Copy**: flat account → warning, no close/hold wording; open position → warning, title or first line MUST contain **有持仓**, plus explicit user close vs hold prompt (R5, D-06/D-07).
5. **Observability**: add `build_ibkr_insufficient_data_alert_sent_payload` + `emit_ibkr_insufficient_data_alert_sent` alongside existing N3 helpers in `data_sufficiency_logging.py` (keeps N3 events co-located) — emit **after** dedup allows send and notifier returns (D-11 granularity: prefer one event per logical emission with per-channel results in payload).

## Integration seam (authoritative)

```503:520:backend_api_python/app/services/signal_executor.py
                if not suff_result.sufficient:
                    syn_fail = (
                        suff_result.reason_code
                        == DataSufficiencyReasonCode.DATA_EVALUATION_FAILED
                    )
                    ecfg = strategy_ctx.get("exchange_config") or {}
                    payload = build_ibkr_open_blocked_insufficient_data_payload(
                        result=suff_result,
                        strategy_id=strategy_id,
                        symbol=symbol,
                        exchange_id=str(ecfg.get("exchange_id") or ""),
                        execution_mode=str(strategy_ctx.get("_execution_mode") or ""),
                        signal_type_raw=str(signal.get("type") or ""),
                        effective_intent=effective_intent,
                        synthetic_evaluation_failure=syn_fail,
                    )
                    emit_ibkr_open_blocked_insufficient_data(payload, logger=logger)
                    return False
```

Hook user alerts **after** `emit_ibkr_open_blocked_insufficient_data` and **before** `return False`, calling a pure orchestration function that: checks dedup → builds user payload (mirror stable keys from `payload` / 02-CONTEXT) → `SignalNotifier().notify_signal(...)` → emits `ibkr_insufficient_data_alert_sent`.

## Notifier contract

`SignalNotifier.notify_signal` accepts `notification_config: dict` and `extra: dict`; payload is built via `_build_payload` which merges `extra`. Use `strategy_id`, `strategy_name=strategy_ctx.get("_strategy_name","")`, `symbol`, `price=current_price`, `direction` from position side or neutral.

## Testing strategy

- **Unit**: dedup key boundaries (different symbol / reason / exchange_id resets cooldown); monotonic clock injection via module-level injectable `time_fn` or passing `now_monotonic` into pure functions.
- **Integration**: patch `SignalNotifier.notify_signal` to assert call kwargs, channels, and `extra` keys include `_execution_mode` / `exchange_id` alignment with Phase 2 payload naming where applicable (02-REVIEWS R-03 checklist).
- **Regression**: extend `test_signal_executor.py` / new `test_ibkr_insufficient_user_alert.py` — do not weaken Phase 2 assertions that guard scope does not call user alert APIs.

## Risks / pitfalls

- Calling alerts **only** from `sufficient is False` inside the guard block — not from `evaluate_ibkr_open_data_sufficiency` inside the guard library alone.
- **Spam**: without dedup, every blocked tick could notify; D-03 requires suppression within window.
- **Webhook secrets**: notifier already avoids logging full URLs; keep alert payloads free of raw webhook URLs.

## Validation Architecture

| Dimension | Phase 03 focus | Automated signal |
|-----------|------------------|------------------|
| Correctness | Alert only on real open/add block; payload fields R4/R5 | pytest: executor + notifier mocks |
| Safety | No auto-close; warning-only copy | grep/assert message substrings |
| Dedup | 5m window per composite key | pytest time injection |
| Observability | `ibkr_insufficient_data_alert_sent` after allowed send | log mock / caplog optional |
| Regression | Phase 2 logs unchanged semantics | existing `test_data_sufficiency_logging.py` + full suite |

Wave 0: not required — pytest already present under `backend_api_python/tests/`.

## RESEARCH COMPLETE

Planning can proceed with `03-CONTEXT.md` + this file + Phase 2 canonical refs.
