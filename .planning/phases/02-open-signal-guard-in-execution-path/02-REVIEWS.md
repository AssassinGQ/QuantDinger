---
phase: 2
reviewers: [claude, opencode]
reviewed_at: "2026-04-18T08:20:00Z"
plans_reviewed: []
notes: "No *-PLAN.md yet; review targeted ROADMAP + REQUIREMENTS + 02-CONTEXT.md. gemini blocked on interactive auth; codex/coderabbit not installed. Consensus folded into 02-CONTEXT.md as checklist R-01–R-09."
---

# Cross-AI Plan Review — Phase 2

## Gemini Review

**Status:** CLI invoked but stopped at interactive prompt (`Opening authentication page in your browser. Do you want to continue? [Y/n]`). No model output collected in this environment.

**Action:** Run `gemini` locally after `gemini auth login` (or non-interactive token), then re-run `/gsd/review --phase 2 --gemini` to append.

---

## Claude Review

Phase 2 is well-scoped as a thin enforcement layer: inject a data-sufficiency gate inside `SignalExecutor.execute` that blocks open/add signals for IBKR live modes while letting close/reduce pass through. The decision doc (02-CONTEXT.md) provides concrete answers to the three hardest questions — exception fail-safe (D-01–D-04), injection ordering (D-05–D-08), and observability scope (D-09–D-10) — leaving implementers a clear, narrow lane. The primary risks are non-obvious: `target_weight`-derived signals that normalize to `add_*` after sizing, the synthetic reason-code spelling for evaluation failures, and the lack of an execution-path `get_kline` alignment test. These are all solvable but require deliberate attention during implementation, not deferred to Phase 3 or 4.

### Strengths

- **Decision-locked injection point**: Single gate in `SignalExecutor.execute` after state machine, before `_check_ai_filter` (D-05, D-07) — avoids double-blocking and keeps the sizing/signal-normalization steps as non-guard-dependent.
- **Clear signal classification**: D-06 explicitly names `open_*`, `add_*` as block targets and `close_*`/`reduce_*` as bypass — matches R3 semantics precisely.
- **Fail-safe exception contract is explicit**: D-01–D-04 resolve the Phase 1 carryover ("Phase 1 intentionally propagates without mapping") by defining synthetic `data_evaluation_failed` reason code + bounded diagnostics.
- **Observability scope is deliberately limited**: Two events only (`ibkr_data_sufficiency_check` + `ibkr_open_blocked_insufficient_data`), no `persist_notification` — avoids Phase 3 entanglement.
- **No cross-signal cache (D-11)**: Correctness-first choice; avoids cache invalidation complexity in thread pool `execute_batch`.
- **`exchange_config.exchange_id` gating**: Both `ibkr-paper` and `ibkr-live` explicitly named — covers the R3/N1 consistency requirement.

### Concerns

1. **`target_weight` Derived `add_*` Signal Classification — MEDIUM**  
   `_calculate_target_weight_amount` can return `add_long`/`add_short` from an original `open_long`/`open_short` after sizing. The guard runs before `_check_ai_filter`; the pre-normalized `sig` vs post-`_calculate_order_amount` `signal_type` must be defined so adds on existing positions are neither wrongly skipped nor wrongly allowed.

2. **Synthetic `data_evaluation_failed` Reason Code — LOW**  
   Enum addition must be atomic with guard implementation; plan should fix exact spelling.

3. **Execution-Path `get_kline` Alignment Test (D-12) — MEDIUM**  
   Carryover requires a seam test vs real or recorded `get_kline`; without it, Phase 1 mock drift can hide production misbehavior.

4. **Phase 1 Diagnostic Bounding vs. Operator Visibility — LOW**  
   Specify max length / no PII for `evaluation_error_summary` (or equivalent field).

5. **`execution_mode` vs `exchange_id` — LOW**  
   Confirm `_execution_mode == "live"` is the correct gate alongside `exchange_id in (ibkr-paper, ibkr-live)` (they are different dimensions).

6. **`exchange` kwarg Availability at Guard Time — LOW**  
   Verify `contract_details` / schedule snapshot inputs exist at the chosen injection point (not only later in the pipeline).

### Suggestions

1. Add `DATA_EVALUATION_FAILED` (or chosen spelling) to `DataSufficiencyReasonCode` as first task.
2. Add bounded `evaluation_error_summary` (or equivalent) on `DataSufficiencyDiagnostics`.
3. Add `ibkr_guard` / `DataSufficiencyGuard` façade wrapping `evaluate_ibkr_data_sufficiency_and_log` + exception translation for testability.
4. Write execution-path `get_kline` alignment test early (recorded fixtures).
5. Explicitly document `target_weight`: guard runs for any risk-increasing open/add intent per D-06.
6. Define `ibkr_open_blocked_insufficient_data` payload schema (field names) in the plan.

### Risk Assessment

**MEDIUM** — Tight scope and locked decisions; highest silent-failure modes are `get_kline` alignment test gap and `target_weight`/signal-type boundary.

---

## Codex Review

**Status:** `codex` CLI not installed in this environment (`command -v codex` → missing).

---

## CodeRabbit Review

**Status:** `coderabbit` CLI not installed (`command -v coderabbit` → missing).

---

## OpenCode Review

Phase 2 adds a critical safety guard to block new positions when IBKR market data is insufficient. The design leverages the Phase 1 data sufficiency service with a clear injection point in `SignalExecutor.execute`. Locked decisions provide good constraints, but there are risks around exception handling clarity, allow/block matrix edge cases, and testing gaps.

### Strengths

1. Single injection in `SignalExecutor.execute` avoids scattered checks.
2. Order state machine → sufficiency → AI filter → sizing → enqueue is coherent.
3. Fail-safe (1A) is appropriate for safety-critical open blocking.
4. Close/reduce preserved; audit trail via two log events (3A).

### Concerns

1. **Exception mapping (HIGH):** CONTEXT locks synthetic reason + diagnostics, but carryover text still echoes “propagate unchanged” from Phase 1 — planners should treat **02-CONTEXT D-01–D-04** as authoritative and echo it in PLAN to avoid implementer confusion.
2. **Execution-path integration test (HIGH):** 4A requires ≥1 test; none exists until implemented — critical for mock vs real `get_kline` drift.
3. **`target_weight` (MEDIUM):** Weight increase vs decrease must map clearly to open/add vs reduce for guard and tests.
4. **`execute_batch` N× fetch (MEDIUM):** No cross-signal cache can mean redundant fetches; acceptable for MVP but document.
5. **Reduce path (LOW):** Add explicit test that reduce/scale-down never invokes sufficiency.
6. **Bounded diagnostics (MEDIUM):** Define max chars, sanitization, categories (e.g. NETWORK, AUTH, RATE_LIMIT).

### Suggestions

1. Document exception contract in PLAN (or short ADR): `get_kline` errors → synthetic `DataSufficiencyReasonCode` + category; no stack traces in structured payload.
2. Add alignment test wiring guard seam to stubbed/recorded `get_kline`.
3. Clarify `target_weight` semantics in PLAN.
4. Optional: per-`execute()` call memoization without cross-signal cache if 4A is interpreted strictly — only if user approves later.
5. Reduce-path negative test for sufficiency invocation.
6. Bounded diagnostics spec (e.g. max 200 chars, no secrets).

### Risk Assessment

**MEDIUM–HIGH** — Core logic sound; residual ambiguity if PLAN does not restate exception contract and testing obligations from CONTEXT + ROADMAP carryover.

---

## Consensus Summary

Both reviewers agree Phase 2 is **narrow and implementable** with strong decisions on injection point, fail-safe blocking, dual-log observability without `persist_notification`, and IBKR `exchange_id` gating. **Shared high-priority gaps** for `/gsd-plan-phase 2 --reviews`:

1. **Execution-path `get_kline` alignment test** (ROADMAP carryover + CONTEXT D-12) — treat as exit-criterion work, not optional polish.
2. **`target_weight` / `open_*` vs post-sizing `add_*`** — spell out in PLAN which signal string(s) trigger the guard and how they interact with `_calculate_order_amount`.
3. **Explicit `ibkr_open_blocked_insufficient_data` payload schema** — field-level contract for audit and future Phase 3 correlation.
4. **Bounded synthetic diagnostics** — max length, no PII/secrets, optional error category enum.
5. **`_execution_mode` vs `exchange_id`** — one-line invariant in PLAN so implementers do not gate on the wrong field.

**Divergent views:** Overall risk **MEDIUM** (Claude) vs **MEDIUM–HIGH** (OpenCode) — OpenCode weights documentation gap between Phase 1 “propagates” wording and Phase 2 “synthesize” decision slightly more heavily; resolving via PLAN cross-reference to `02-CONTEXT.md` D-01–D-04 closes this.

### Agreed Strengths

- Single choke point in `SignalExecutor.execute`; sufficiency before AI filter (2B).
- Fail-safe on evaluation errors (1A); close/reduce bypass (D-08).
- Two structured logs only in Phase 2 (3A); Phase 3 owns user alerts.

### Agreed Concerns (highest first)

- Missing or underspecified **execution-path** test for `get_kline` seam (**MEDIUM–HIGH**).
- **`target_weight` / signal reclassification** boundary (**MEDIUM**).
- **Synthetic reason + diagnostics** must be specified in types and payloads (**MEDIUM** combined).

### Divergent Views

- **Risk level label** only; both list overlapping concrete risks.

---

*Phase: 02-open-signal-guard-in-execution-path*
