# Phase 2: Open-signal guard in execution path — Research

**Researched:** 2026-04-18 `[VERIFIED: local codebase + existing plans + ROADMAP/CONTEXT]`  
**Domain:** IBKR live execution-path sufficiency gate + audit logs + execution-side tests `[VERIFIED: .planning/phases/02-open-signal-guard-in-execution-path/02-CONTEXT.md]`  
**Confidence:** HIGH for repo-internal architecture; MEDIUM for IBKR async contract-resolution edge cases (defer detail to implementation + tests)

<user_constraints>
## User Constraints (from `02-CONTEXT.md`)

### Locked Decisions (execution path)
- **D-01–D-04:** Exceptions inside the sufficiency evaluation path MUST fail-safe toward **blocking open/add**, with synthetic `data_evaluation_failed` (exact string value) and bounded diagnostics — not silent allow. `[VERIFIED: 02-CONTEXT.md]`
- **D-05–D-07:** Single integration point: `SignalExecutor.execute`; ordering: **after state machine**, **before `_check_ai_filter`**, then sizing/enqueue. `[VERIFIED: 02-CONTEXT.md]`
- **D-06:** Gate only when `_execution_mode == live` AND `exchange_config.exchange_id in (ibkr-paper, ibkr-live)` AND normalized intent is open/add (including `target_weight` paths that become add). `[VERIFIED: 02-CONTEXT.md]`
- **D-08:** Close/reduce MUST bypass sufficiency entirely. `[VERIFIED: 02-CONTEXT.md]`
- **D-09–D-10:** Only `ibkr_data_sufficiency_check` + `ibkr_open_blocked_insufficient_data` in Phase 2; **no** `persist_notification` for sufficiency; Phase 3 owns `ibkr_insufficient_data_alert_sent` / user alerts. `[VERIFIED: 02-CONTEXT.md] [VERIFIED: .planning/REQUIREMENTS.md N3]`
- **D-11–D-12:** No cross-signal cache in Phase 2; at least one execution-path test wires guard kline seam to stubbed/recorded `kline_fetcher.get_kline` including `LOWER_LEVELS` fallback where feasible. `[VERIFIED: 02-CONTEXT.md] [VERIFIED: .planning/ROADMAP.md]`

### Claude's Discretion
- Guard module filename under `app/services/` (plan uses `data_sufficiency_guard.py`). `[VERIFIED: 02-02-PLAN.md]`
- Exact payload field spellings for blocked-open logs as long as stable + documented. `[VERIFIED: 02-CONTEXT.md]`
</user_constraints>

## Summary

Phase 2 is **not** a second sufficiency engine: it **consumes** Phase 1 `evaluate_ibkr_data_sufficiency_and_log` and adds an **execution-layer façade** that (a) applies user fail-safe policy on exceptions, (b) injects the gate at `SignalExecutor.execute`, and (c) emits enforcement logs. The Phase 1 library (`data_sufficiency_service.py`) intentionally **propagates** exceptions; Phase 2 **must not** treat that as authoritative for live open/add safety — the façade catches and maps per `02-CONTEXT.md`. `[VERIFIED: backend_api_python/app/services/data_sufficiency_service.py] [VERIFIED: 02-CONTEXT.md]`

Highest-risk gaps (from `02-REVIEWS.md` consensus): **`target_weight` reclassification** (open→add), **`execute_batch` historically passing `exchange=None`** (contract resolution for schedule/kline), and **mock drift** without an execution-path `get_kline` seam test. Plans `02-01-PLAN.md` / `02-02-PLAN.md` already encode mitigations; research below aligns implementers with **prescriptive** stack/patterns and **per-task test specifications**.

**Primary recommendation:** Implement a thin `data_sufficiency_guard.py` façade + minimal `signal_executor.py` reordering; thread `exchange` into `execute_batch` for cross-sectional runners; prove behavior with pytest mocks/patches on **guard entry**, **`kline_fetcher.get_kline`**, and **`pending_order_enqueuer.execute_exchange_order`**.

## Standard Stack

### Core

| Library / facility | Purpose | Why Standard (this repo) |
|--------------------|---------|---------------------------|
| Python 3.10+ backend | Runtime | Matches `backend_api_python` |
| `pytest` | Unit/integration tests | Already used across `backend_api_python/tests/` |
| `unittest.mock` / `MagicMock` / `patch` | Isolate IBKR, kline, datetime, guard | Existing pattern in `test_signal_executor.py`, `test_data_sufficiency_integration.py` |
| stdlib `logging` | Structured `extra=` payloads | Matches `data_sufficiency_logging.py` emitters |
| Phase 1 modules | `data_sufficiency_service`, `data_sufficiency_types`, `kline_fetcher` | Phase 2 must delegate bar semantics — **do not fork** |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Inline guard logic inside `execute()` only | Dedicated `data_sufficiency_guard.py` | Second module is clearer for testing and keeps executor readable `[RECOMMENDED: 02-02-PLAN.md]` |
| Propagate exceptions from Phase 1 service in live open path | Façade catch + synthetic insufficient | Violates N2 / D-01; unsafe for open/add `[REJECTED: 02-CONTEXT.md]` |

**Installation:** No new dependencies required for Phase 2 unless implementation chooses optional helpers (avoid unless justified).

## Architecture Patterns

### Pattern 1: Library vs execution policy split

**What:** `evaluate_ibkr_data_sufficiency_and_log` remains the Phase 1 **library** orchestration (may raise). Phase 2 **`evaluate_ibkr_open_data_sufficiency`** (name per plan) wraps it and **never** raises to `SignalExecutor` for policy decisions — returns `DataSufficiencyResult` including synthetic failure path. `[VERIFIED: data_sufficiency_service.py docstring] [VERIFIED: 02-CONTEXT.md D-01–D-04]`

**When to use:** Every IBKR live open/add evaluation invoked from execution.

### Pattern 2: Single choke point + explicit ordering

**What:** Only `SignalExecutor.execute` integrates the gate (not a second gate in enqueue worker per `02-CONTEXT.md` deferred items). Reorder so sufficiency runs **before** `_check_ai_filter` to skip LLM work when already insufficient. `[VERIFIED: 02-CONTEXT.md D-05–D-07]`

**Pitfall:** Current `execute()` calls `_check_ai_filter` before sizing; planner explicitly moves sufficiency **above** AI filter — implementation must follow plan, not legacy order. `[VERIFIED: backend_api_python/app/services/signal_executor.py]`

### Pattern 3: Intent classification for `target_weight`

**What:** Mirror the **branch structure** of `_calculate_target_weight_amount` to label effective intent (`open_*`, `add_*`, `reduce_*`, `close_*`, hold). Gate applies only when effective intent is `open_*` or `add_*`. `[VERIFIED: 02-REVIEWS.md / R-05] [VERIFIED: signal_executor._calculate_target_weight_amount]`

### Pattern 4: Thread IBKR `exchange` through `execute_batch`

**What:** `CrossSectionalRunner` currently dispatches `execute_batch` without `exchange`; Phase 2 needs contract context for schedule snapshot. Add `exchange` parameter and forward from `run()` into `_dispatch_signals` → `execute_batch`. `[VERIFIED: backend_api_python/app/strategies/runners/cross_sectional_runner.py] [VERIFIED: 02-02-PLAN.md Task 3]`

## Don't Hand-Roll

| Problem | Use Instead |
|---------|--------------|
| Bar counting / timeframe / `LOWER_LEVELS` aggregation | `compute_available_bars_from_kline_fetcher` + real `kline_fetcher.get_kline` seam (wrapped, not reimplemented) `[VERIFIED: test_data_sufficiency_integration.py]` |
| Schedule/session truth | Existing `get_ibkr_schedule_snapshot` / Phase 1 adapter `[VERIFIED: ibkr_schedule_provider.py]` |
| New user notification channel for sufficiency | Nothing in Phase 2 — logs only per D-09 |

## Common Pitfalls

| Pitfall | Mitigation |
|---------|------------|
| Gating on wrong field (paper trading account vs `exchange_id`) | Require **both** `_execution_mode == live` and `exchange_id in {ibkr-paper, ibkr-live}` `[VERIFIED: R-06]` |
| Blocking reduce/close | Explicit bypass for reduce/close signal families; negative test with guard spy call_count == 0 `[VERIFIED: R-07]` |
| `execute_batch` with `exchange=None` fails closed or skips guard incorrectly | Thread `exchange` + test forward path `[VERIFIED: 02-02-PLAN.md]` |
| Logging full tracebacks inside structured audit payload | Truncate summary; use normal logger `exc_info` only at translation site `[VERIFIED: D-03]` |
| Expecting `ibkr_insufficient_data_alert_sent` in Phase 2 | Treat as Phase 3 only `[VERIFIED: R-02]` |

## Code Examples

### Existing execution entry (integration point)

```320:361:backend_api_python/app/services/signal_executor.py
    def execute(
        self,
        strategy_ctx: Dict[str, Any],
        signal: Dict[str, Any],
        **exec_kwargs
    ) -> bool:
        ...
            state = position_state(current_positions)

            # Target weight sizing inherently allows adding to an existing position,
            ...
            if signal.get("target_weight") is None and not is_signal_allowed(state, signal_type):
                return False

            if market_type == "spot" and "short" in signal_type:
                return False

            sig = signal_type.strip().lower()

            if not self._check_ai_filter(strategy_ctx, symbol, sig, signal_ts):
                return False
```

**Research note:** Phase 2 inserts sufficiency **after** state machine / spot checks and **before** `_check_ai_filter` (plan-driven reorder).

### Phase 1 library boundary (exceptions propagate)

```53:60:backend_api_python/app/services/data_sufficiency_service.py
    """End-to-end sufficiency for IBKR: adapter + kline bar count + pure classify + one log.

    Raises:
        Exception: Any exception raised by ``get_ibkr_schedule_snapshot`` or
            ``compute_available_bars_from_kline_fetcher`` ...
```

### Reference kline stub pattern (Phase 1 integration)

See `backend_api_python/tests/test_data_sufficiency_integration.py::test_adapter_to_service_emits_ibkr_data_sufficiency_check` for `LOWER_LEVELS`-style `get_kline` behavior — Phase 2 should replicate **through the guard façade**, not duplicate validator math.

---

## Per-Plan Task → Test Case Specifications

> Aligns with `02-01-PLAN.md` / `02-02-PLAN.md` `<test_spec>` tables. Automated checks should use **`python3 -m pytest backend_api_python/tests -q`** after task-level subset passes.

### Plan `02-01` — Types + blocked-open logging

| Task | Case ID | Scenario | Expected |
|------|---------|----------|----------|
| Task 1 (types) | TS-01 | Enum value for synthetic failure | `DATA_EVALUATION_FAILED.value == "data_evaluation_failed"` |
| Task 1 | TS-02 | Long error string | `truncate_evaluation_error_summary` returns ≤200 chars with ellipsis |
| Task 1 | TS-03 | `None` input | Truncation returns `None` |
| Task 1 | TS-04 | Legacy diagnostics construction | New fields default `None`; no breakage in Phase 1 call sites |
| Task 2 (logging) | TS-10 | Builder minimal payload | All stable keys from plan exist (`event`, `strategy_id`, `exchange_id`, …) |
| Task 2 | TS-11 | Synthetic flag | `synthetic_evaluation_failure=True` when mapped from exception path |
| Task 2 | TS-12 | Emitter | Logger `extra["event"] == "ibkr_open_blocked_insufficient_data"` |

### Plan `02-02` — Guard + executor + batch + integration

| Task | Case ID | Scenario | Expected |
|------|---------|----------|----------|
| Task 1 (façade) | TS-20 | Underlying service raises | Result `reason_code==data_evaluation_failed`, bounded summary |
| Task 1 | TS-21 | Normal insufficient | Pass-through `DataSufficiencyResult`; `ibkr_data_sufficiency_check` emitted inside service |
| Task 1 | TS-22 | Kline seam | `kline_fetcher.get_kline` invoked with `(market_category, symbol, timeframe, …)` |
| Task 2 (executor) | TS-30 | IBKR live open, sufficient | `execute_exchange_order` called |
| Task 2 | TS-31 | IBKR live open, insufficient | Blocked log + **no** enqueue |
| Task 2 | TS-32 | reduce under insufficient | Enqueue still allowed |
| Task 2 | TS-33 | `target_weight` → `add_*` | Treated as risk-increasing; guard applies |
| Task 2 | TS-34 | Non-IBKR `exchange_id` | Guard path skipped (spy call_count 0) |
| Task 2 | TS-35 | Exception→synthetic | No unhandled exception; blocked audit emitted |
| Task 3 (batch) | TS-40 | `execute_batch(..., exchange=mock)` | Inner `execute` receives same mock |
| Task 3 | TS-41 | Cross-sectional runner | Forwards exchange into batch |
| Task 4 (integration) | TS-50 | `LOWER_LEVELS` | Fallback timeframe invoked at least once |
| Task 4 | TS-51 | Reduce path | Sufficiency evaluator **not** invoked |

---

## Verification Commands (Nyquist / CI alignment)

| Scope | Command |
|-------|---------|
| Task-level (fast) | `python3 -m pytest backend_api_python/tests/test_<module>.py -q` |
| Phase regression | `python3 -m pytest backend_api_python/tests -q` |

---

## RESEARCH COMPLETE
