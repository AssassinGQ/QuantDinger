# Phase 2: Open-signal guard in execution path - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `02-CONTEXT.md`.

**Date:** 2026-04-18
**Phase:** 2 — Open-signal guard in execution path
**Areas discussed:** Exception contract; Guard ordering; Observability (Phase 3 boundary); Concurrency/testing

---

## Gray area selection

**User's choice:** Discuss all four areas initially (“全部”); later locked choices **1A 2B 4A** with observability **3** discussed separately, finalized as **3A**.

---

## 1) Kline / orchestration exception contract

| Option | Description | Selected |
|--------|-------------|----------|
| A | Fail-safe: synthesize insufficient + bounded diagnostics; block open/add | ✓ |
| B | Log and re-raise | |
| C | Mixed schedule vs kline | |

**User's choice:** **1A**

---

## 2) Guard injection point and ordering

| Option | Description | Selected |
|--------|-------------|----------|
| A | After AI filter and amount > 0, before enqueue | |
| B | Sufficiency **before** `_check_ai_filter` (after state machine) | ✓ |
| C | Executor + worker double gate | |

**User's choice:** **2B** — save AI work when data already insufficient; single choke in `SignalExecutor.execute`.

---

## 3) Observability (Phase 2 vs Phase 3)

**Discussion:** User asked how options conflict with Phase 3; explanation covered dedup/duplicate user noise and audit clarity.

| Option | Description | Selected |
|--------|-------------|----------|
| A | Dual structured logs: `ibkr_data_sufficiency_check` + `ibkr_open_blocked_insufficient_data`; **no** `persist_notification` | ✓ |
| B | A + `persist_notification` for blocked opens | |
| C | Single sufficiency log only | |
| D | A + metrics hook (optional future) | |

**User's choice:** **3A** — minimizes overlap with Phase 3 R4 alerting; Phase 3 owns user-facing channels and dedup.

---

## 4) Concurrency and testing

| Option | Description | Selected |
|--------|-------------|----------|
| A | Per-signal evaluation, no cache; ≥1 execution-path `get_kline` alignment test in Phase 2 | ✓ |
| B | Defer alignment test | |

**User's choice:** **4A**

---

## Claude's Discretion

- Naming of new reason code, guard helper module, `target_weight` boundary handling — see `02-CONTEXT.md`.

## Deferred Ideas

- Second-line enqueue/worker guard; cross-signal caching — see `02-CONTEXT.md` deferred section.

---

## Supplement (2026-04-18): review + planning handoff

Cross-AI output was recorded in **`02-REVIEWS.md`**. Actionable consensus was merged into **`02-CONTEXT.md`** as **§ Review-derived planning checklist (R-01–R-09)** so planners/implementers do not rely on this chat-only log.

**ROADMAP** Phase 2 now has a short pointer (**Cross-AI review follow-ups**) to those items.

**Note:** This log remains human-facing audit trail; **`02-CONTEXT.md`** is the agent-facing source for `/gsd-plan-phase 2 --reviews`.
