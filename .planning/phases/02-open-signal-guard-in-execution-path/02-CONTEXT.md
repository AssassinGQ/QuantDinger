# Phase 2: Open-signal guard in execution path - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

For IBKR execution strategies (`ibkr-paper`, `ibkr-live`) in **live** execution mode, inject a data-sufficiency gate so that **open/add** signals are **not** sent to the order pipeline when evaluation concludes data is insufficient or when evaluation cannot complete safely. **Close/reduce** (risk-reducing) signals **must not** be blocked by this gate. Deliver structured audit logs for blocked opens. Phase 3 owns user-channel alerting and dedup (REQUIREMENTS R4); Phase 2 uses **structured logs only** for enforcement visibility (see Observability — **User: 3A**).

</domain>

<decisions>
## Implementation Decisions

### Kline / orchestration exception contract (ROADMAP carryover) — **User: 1A**
- **D-01:** On any exception raised from `get_ibkr_schedule_snapshot`, `compute_available_bars_from_kline_fetcher` / `get_kline_callable`, or other unexpected failure **inside** the sufficiency evaluation path used by the guard: **do not** treat as an unhandled crash for the strategy runner’s open/add attempt. Instead, **fail-safe toward blocking open/add** (consistent with REQUIREMENTS N2).
- **D-02:** Represent the failure as a **synthetic insufficient outcome** suitable for guards and logs: extend `DataSufficiencyReasonCode` with a dedicated machine-stable code (e.g. `data_evaluation_failed` — exact spelling is implementation detail) rather than overloading `unknown_schedule` or `missing_bars`.
- **D-03:** Preserve **bounded** diagnostic detail for operators: extend `DataSufficiencyDiagnostics` with an optional field for a **short, non-sensitive** evaluation error summary (e.g. exception type + truncated message cap). Do **not** log full stack traces inside the hot notification payload; use normal logger `exc_info` only at the callsite where the exception is first translated.
- **D-04:** When evaluation completes **without** exception, continue to emit the existing `ibkr_data_sufficiency_check` structured log from Phase 1 orchestration. When translating an exception into a synthetic result, still emit **`ibkr_open_blocked_insufficient_data`** per D-09 so blocked opens are never “silent.”

### Guard injection point and ordering — **User: 2B**
- **D-05:** Implement the gate in **`SignalExecutor.execute`** as the **single** integration point for this phase (not a second independent gate inside `pending_order_enqueuer` / worker).
- **D-06:** Run the guard only when **all** hold: internal strategy context key **`_execution_mode`** (string) equals **`live`** — i.e. `str(strategy_ctx.get("_execution_mode") or "").strip().lower() == "live"` (same convention as `SignalExecutor.execute` today; not a bare `execution_mode` top-level key). Strategy `exchange_config.exchange_id` must be **`ibkr-paper` or `ibkr-live`**. Effective signal intent (after normalization / `target_weight` handling per R-05) must be **open/add** (`open_*`, `add_*`). Do **not** run for non-live modes, non-IBKR `exchange_id`, or reduce/close paths (**D-08**).
- **D-07:** Ordering relative to existing gates: after the **position state machine** allows the signal, run sufficiency **before** `_check_ai_filter`, then proceed with `_calculate_order_amount`, normalizer, and `pending_order_enqueuer.execute_exchange_order`. **Rationale (user choice 2B):** avoid AI/LLM work when data is already insufficient; sufficiency does not depend on computed order size.
- **D-08:** Close/reduce/close-like signals must **bypass** the sufficiency gate entirely (only intercept risk-increasing actions).

### Observability (REQ N3 vs Phase 3) — **User: 3A (Pkg-A)**

- **D-09:** Use **two structured log events** only — **no** `persist_notification` in Phase 2 (avoids overlap with Phase 3 R4 user alerts and dedup policy).  
  - **`ibkr_data_sufficiency_check`:** evaluation outcome (Phase 1 style), emitted when the sufficiency evaluation path runs to completion (including `sufficient: false` outcomes from normal classification).  
  - **`ibkr_open_blocked_insufficient_data`:** enforcement outcome — the guard **prevented** enqueue of an open/add order (includes synthetic insufficient path from **1A** / D-01–D-03).
- **D-10:** Phase 3 **must** treat user-visible insufficiency alerting as its own channel; Phase 2 logs remain the **machine audit trail** for “evaluated vs blocked enqueue.” Do not repurpose Phase 2 logs as end-user notification payloads.

### Concurrency and testing (ROADMAP carryover) — **User: 4A**
- **D-11:** Under `execute_batch` thread pool: run sufficiency evaluation **once per signal execution** inside `execute()` — **no** cross-signal cache in Phase 2 (correctness and simplicity first).
- **D-12:** Phase 2 exit criteria **includes** at least **one** integration or contract test on the **execution-side** data path that ties the guard’s bar-acquisition seam to **recorded or stubbed** `kline_fetcher.get_kline` behavior for representative `(market_category, symbol, timeframe, limit)` tuples, covering `LOWER_LEVELS` fallback where feasible — per ROADMAP “Real-path `get_kline` alignment.”

### Claude's Discretion
- Exact helper/module naming for the guard façade (thin wrapper calling `evaluate_ibkr_data_sufficiency_and_log`).
- Exact spelling of the new `DataSufficiencyReasonCode` member and payload field names for `ibkr_open_blocked_insufficient_data`, as long as D-09/D-10 remain distinguishable.
- How to treat `target_weight`-derived signals at the sufficiency branch boundary (must still match D-06 intent: only risk-increasing open/add).

### Review-derived planning checklist (cross-AI: `02-REVIEWS.md`)

These items elaborate locked decisions (D-xx) for **plan authors and implementers**; they do not override user choices. `/gsd-plan-phase 2` should fold each into tasks or acceptance criteria.

- **R-01 (exception contract vs Phase 1 docstring):** Phase 2 **guard façade** maps exceptions per **D-01–D-04**. Phase 1 `evaluate_ibkr_data_sufficiency_and_log` still documents library-level propagation; PLAN must state explicitly that **execution path** behavior follows **02-CONTEXT**, not the raw service default alone.
- **R-02 (REQ N3 event naming):** `.planning/REQUIREMENTS.md` N3 lists `ibkr_insufficient_data_alert_sent` — treat as **Phase 3** user-channel dispatch (R4). Phase 2 delivers **D-09** events only; PLAN should note this split so verification does not expect `*_alert_sent` in Phase 2.
- **R-03 (`ibkr_open_blocked_insufficient_data` schema):** Define stable payload fields (strategy id, symbol, exchange_id/mode, signal types, key `DataSufficiencyResult` fields, synthetic failure marker) before calling Phase 2 complete.
- **R-04 (bounded diagnostics):** Specify numeric max length for evaluation-error summary, prohibit secrets/tokens in structured payload, optional coarse category (e.g. schedule vs kline vs unknown) — implements **D-03** precisely.
- **R-05 (`target_weight` / signal reclassification):** Document whether the guard keys off **pre-sizing** `sig`, **post-`_calculate_order_amount`** `signal_type`, or a single rule covering “risk-increasing intent” so `open_*`→`add_*` paths cannot mis-classify (see **02-REVIEWS.md** consensus).
- **R-06 (joint gate):** Implementation checklist: **`_execution_mode == live`** and **`exchange_config.exchange_id in (ibkr-paper, ibkr-live)`** both required (**D-06**); PLAN should state invariants so routing is not confused with paper/live **account** naming elsewhere.
- **R-07 (negative test — close/reduce):** Add an integration or unit test proving **reduce / close / scale-down** signals do **not** invoke the sufficiency evaluator on the guarded path (exit criterion “close/reduce unaffected”).
- **R-08 (`get_kline` alignment):** Treat **D-12** / ROADMAP carryover as **blocking exit work**: ≥1 test tying the guard’s bar seam to recorded or stubbed `kline_fetcher.get_kline` (incl. `LOWER_LEVELS` where feasible).
- **R-09 (performance):** Per-signal evaluation may duplicate fetches under `execute_batch` (**D-11**); acceptable for Phase 2. Optional revisit: memoize **within** a single `execute()` call only if needed — do not add cross-signal cache without a new decision.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope
- `.planning/ROADMAP.md` — Phase 2 objective, tasks, exit criteria, Phase 01 carryover, and Phase 2 review follow-up pointer.
- `.planning/REQUIREMENTS.md` — R3 open/add block; N2 fail-safe; N3 observability event names; R4 Phase 3 alerting.
- `.planning/PROJECT.md` — Milestone intent for IBKR open blocking.
- `.planning/phases/02-open-signal-guard-in-execution-path/02-REVIEWS.md` — cross-AI review; consensus summarized as **R-01–R-09** in this file.

### Prior phase contract
- `.planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md` — Phase 1 decisions D-01–D-11 and component boundaries consumed by this phase.

### Implementation anchors
- `backend_api_python/app/services/data_sufficiency_service.py` — Phase 1 orchestration and documented exception propagation contract.
- `backend_api_python/app/services/data_sufficiency_types.py` — `DataSufficiencyResult`, reason codes, diagnostics (extend in Phase 2 per D-02/D-03).
- `backend_api_python/app/services/signal_executor.py` — Injection site per D-05–D-07 (sufficiency before `_check_ai_filter` per 2B).
- `backend_api_python/app/services/kline_fetcher.py` — K-line acquisition semantics for integration tests per D-12.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `evaluate_ibkr_data_sufficiency_and_log`: Phase 1 end-to-end evaluator + `ibkr_data_sufficiency_check` logging.
- `SignalExecutor.execute` / `execute_batch`: Unified live enqueue path (`pending_order_enqueuer.execute_exchange_order`) for IBKR live/paper when **`_execution_mode == live`**. IBKR **`exchange`** (contract resolution) is threaded **`CrossSectionalRunner.run(exchange)` → `_run_single_tick(..., exchange)` → `_dispatch_signals(..., exchange)` → `execute_batch(..., exchange=...)` → `execute(..., exchange=...)`** so batch strategies do not silently pass `exchange=None` through the sufficiency gate.
- `DataHandler` / strategy payload: `exchange_config.exchange_id` available via strategy config loader for IBKR detection.

### Established Patterns
- Early gates in `execute()`: state machine, then (per **2B**) sufficiency for qualifying IBKR live open/add, then `_check_ai_filter`, then sizing and enqueue.
- Live mode returns after enqueue without local position update; sufficiency must run **before** enqueue to be effective.

### Integration Points
- Primary: `SignalExecutor.execute` after state machine, **before** `_check_ai_filter`, for qualifying IBKR live open/add signals.
- Secondary: extend typed sufficiency enums/diagnostics for synthetic failure path (D-02/D-03).

</code_context>

<specifics>
## Specific Ideas

- User decisions: **1A** (exception fail-safe), **2B** (sufficiency before AI), **3A** (dual structured logs only, no `persist_notification`), **4A** (per-signal eval + mandatory execution-path `get_kline` alignment test).

</specifics>

<deferred>
## Deferred Ideas

- Second-line guard inside `pending_order_enqueuer` / worker (optional hardening; not required for Phase 2 single choke point per D-05).
- Cross-signal caching of sufficiency results under `execute_batch` (performance optimization only).

</deferred>

---

*Phase: 02-open-signal-guard-in-execution-path*
*Context gathered: 2026-04-18*
