# Phase 4: Hardening and rollout safety - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `04-CONTEXT.md`.

**Date:** 2026-04-18
**Phase:** 04-hardening-and-rollout-safety
**Areas discussed:** Observability, Schedule fallback, Rollout switches, False-block acceptance

---

## Observability

| Option | Description | Selected |
|--------|-------------|----------|
| Structured logs primary | Aggregate rates from unified log fields; no new metrics server | ✓ |
| Dedicated metrics exporter | HTTP metrics endpoint / Prometheus-style | |
| Hybrid | Logs + counters | |
| Implementation picks surface | Meet exit criteria only | |

**User's choice:** Structured logs as primary operational surface; minimal aggregation dimensions (`reason_code`, `exchange_id`, event kind).

**Notes:** Clarified that “Prometheus habit” referred to optional industry pattern; codebase today has no established Prometheus stack.

---

## Schedule snapshot failure policy

| Option | Description | Selected |
|--------|-------------|----------|
| Strict fail-safe, no cache | | |
| Last-good snapshot + TTL | | |
| Bounded retry then fail-safe | Retry without stale snapshot reuse | ✓ |
| Retry + TTL cache | | |
| Defer detail | | |

**User's choice:** Simplified model — **bounded retry** on `get_ibkr_schedule_snapshot` failures; **no last-good snapshot TTL cache** for this milestone; after retries exhausted, fail-safe per N2 / Phase 2 semantics.

**Notes:** Discussed misclassification risks (transient API failure vs stale calendar cache). User initially considered caching because trading calendars change rarely; ultimately preferred simplicity over TTL caching.

---

## Rollout / config switches

**User's choice (natural language):** Prefers **full rollout** without elaborate phased complexity — document as **deployment-level env/global configuration** sufficient; **no mandatory per-strategy staged toggles**.

---

## False blocks / tuning acceptance

| Option | Description | Selected |
|--------|-------------|----------|
| Tests/fixtures only | | |
| Env tunables | | |
| Tests + tunables | | |
| Regression + documented boundaries | | ✓ |
| Defer to PLAN | | |

**User's choice:** **D** — regression passes + documented boundaries; fine threshold tuning can follow later.

**Notes:** Explained “reduce false blocks” as reducing incorrect open-blocks when data was effectively sufficient.

---

## Claude's Discretion

- Retry budgets/backoff; optional global kill-switch naming and defaults.

## Deferred Ideas

- Per-strategy phased rollout toggles — explicitly out of scope for Phase 4 context.
- Schedule TTL cache — user declined for this milestone.
