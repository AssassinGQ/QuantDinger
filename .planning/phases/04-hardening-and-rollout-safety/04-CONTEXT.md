# Phase 4: Hardening and rollout safety - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Reduce **false blocks** where feasible, increase **operational visibility** into sufficiency outcomes and block/alert rates, define explicit **schedule-fetch resilience** (bounded retry → fail-safe), provide **simple deployment-level controls** for rollout (no mandatory per-strategy phased toggles), and **regress** existing IBKR execution tests so production rollout does not weaken prior phases. Scope stays within ROADMAP Phase 4 tasks and REQUIREMENTS N2/N3 alignment.

</domain>

<decisions>
## Implementation Decisions

### Observability (metrics / dashboards)
- **D-01:** Primary operational visibility MUST be delivered via **structured logs** (existing logging stack): unify or extend **aggregatable fields** so operators can derive rates (blocked opens, evaluations, user alerts) from log queries — **no requirement** to introduce Prometheus `/metrics` or a new metrics middleware for Phase 4 exit criteria.
- **D-02:** Mandatory **cardinality-conscious** dimensions for aggregation: **`reason_code`** + **`exchange_id` (`ibkr-paper` / `ibkr-live`)** + **event kind** distinguishing **evaluation vs open-block enforcement vs user-channel insufficient alert dispatch** (align naming with Phase 2/3 stable keys where applicable).

### Schedule snapshot fetch resilience (`get_ibkr_schedule_snapshot`)
- **D-03:** On schedule snapshot fetch/evaluation failure: implement **bounded retries** (count/backoff — implementation detail). After retries are exhausted, behave **fail-safe toward blocking risk-increasing opens** consistent with **REQUIREMENTS N2** and Phase 2 synthetic-insufficient semantics (**02-CONTEXT** exception→block policy).
- **D-04:** **Do not** introduce **reuse of last-good schedule snapshots / TTL cache** in this milestone — user chose **simplified** behavior: **retry-only**, then fail-safe (no stale snapshot path).

### Rollout / config switches
- **D-05:** Keep rollout **simple**: **deployment-wide** controls via **environment variables or global config** are sufficient; **no requirement** for per-strategy phased feature toggles or multi-tier rollout matrices in Phase 4.
- **D-06:** **Full rollout** when shipping is acceptable from a product-process perspective; optional **single global kill-switch / master disable** for emergencies remains **Claude's discretion** (exact flag names and default-on vs default-off posture).

### False blocks / tuning acceptance
- **D-07:** For “reduce false blocks,” Phase 4 acceptance focuses on **full regression suite green** plus **documented operational boundaries** (known limitations, when false blocks may still occur); **fine-grained production threshold tuning** may be deferred beyond this milestone unless discovered blockers force otherwise.

### Claude's Discretion
- Retry budget, backoff shape, and logging of retry attempts vs final failure classification.
- Exact field names beyond D-02 minimal set; kill-switch naming and default posture (enforce vs shadow) if any shadow mode is introduced.
- Whether to extract shared test fixtures per ROADMAP carryover (LOWER_LEVELS stubs) — recommended but not user-locked.

### Folded Todos

_(none — `todo match-phase` returned no matches)_

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and Phase 4 roadmap
- `.planning/ROADMAP.md` — Phase 4 objective, tasks, exit criteria; carryover on typed metadata constants, optional `timezone_trusted`, shared fixtures, false insufficient/sufficient tuning.
- `.planning/REQUIREMENTS.md` — N2 fail-safe; N3 observability event names; consistency expectations.

### Locked prior-phase contracts
- `.planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md` — sufficiency contract; schedule failure fail-safe baseline (**D-04** Phase 1).
- `.planning/phases/02-open-signal-guard-in-execution-path/02-CONTEXT.md` — guard placement, exception→synthetic insufficient, structured logs split vs Phase 3 user alerts.
- `.planning/phases/03-alerting-and-user-decision-support/03-CONTEXT.md` — user alert path, dedup keys, N3 `ibkr_insufficient_data_alert_sent`.

### Implementation anchors
- `backend_api_python/app/services/live_trading/ibkr_trading/ibkr_schedule_provider.py` — `get_ibkr_schedule_snapshot` (retry/failure handling scope per **D-03/D-04**).
- `backend_api_python/app/services/data_sufficiency_service.py` — orchestration / exception contract intersection with Phase 2 guard façade.
- `backend_api_python/app/services/signal_executor.py` — execution-path guard integration for regression guarantees.
- `backend_api_python/app/services/data_sufficiency_logging.py` — structured events for observability (**D-01/D-02** alignment).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Structured logging helpers** emitting `ibkr_data_sufficiency_check`, `ibkr_open_blocked_insufficient_data`, `ibkr_insufficient_data_alert_sent` — extend consistently for operational rates per **D-01/D-02**.
- **`get_ibkr_schedule_snapshot`** — central seam for **D-03** retry wiring without adding snapshot-cache semantics per **D-04**.

### Established Patterns
- Phase 2/3 split: **machine audit** logs vs **user-facing** alerts — observability work must not blur these boundaries.
- Fail-safe defaults already assumed for evaluation failures mapped to synthetic insufficient outcomes.

### Integration Points
- Schedule provider + sufficiency orchestration + `SignalExecutor` guard — retries and logging must remain bounded and diagnosable under load.

</code_context>

<specifics>
## Specific Ideas

- User prefers **log-first observability** (no mandated Prometheus stack for this milestone).
- User simplified schedule handling to **bounded retry only**, explicitly **rejecting TTL reuse of old schedule snapshots** for Phase 4.
- User prefers **simple rollout**: deployment-level controls, **no elaborate phased-per-strategy requirement**; full rollout is acceptable.
- User selected **acceptance style D**: regressions pass + documentation of boundaries; deep threshold tuning can wait.

</specifics>

<deferred>
## Deferred Ideas

- **TTL cache of last-good IBKR schedule snapshot** — explicitly deferred by user for simplicity (**D-04**).
- **Per-strategy rollout toggles** — not required for Phase 4 (**D-05**); revisit if ops later need finer blast-radius control.

### Reviewed Todos (not folded)

_(none)_

</deferred>

---

*Phase: 04-hardening-and-rollout-safety*
*Context gathered: 2026-04-18*
