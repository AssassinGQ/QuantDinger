# Phase 3: Alerting and user decision support - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

When IBKR live execution blocks **open/add** due to data insufficiency (Phase 2 guard), deliver **user-visible** notifications through each strategy’s existing **`notification_config`** channels, with **cooldown/deduplication** so operators are not spammed. Alert payloads MUST carry **position context** and **close/hold decision support** where a position exists (REQUIREMENTS R4/R5). Emit structured observability **`ibkr_insufficient_data_alert_sent`** (N3) on the user-channel path, distinct from Phase 2’s **`ibkr_data_sufficiency_check`** / **`ibkr_open_blocked_insufficient_data`** machine audit trail (**02-CONTEXT** D-09/D-10). No new frontend decision UI (REQUIREMENTS out of scope).

</domain>

<decisions>
## Implementation Decisions

### Trigger vs Phase 2 logs — **User: block_only**
- **D-01:** User-channel insufficient **alerts** MUST trigger **only** when the execution path **actually blocks** open/add enqueue (same business moment as **`ibkr_open_blocked_insufficient_data`** / guard outcome), **not** on every per-tick `sufficient == false` evaluation alone.
- **D-02:** Phase 2 structured logs remain the authoritative **machine** trace for evaluation vs block; Phase 3 user alerts are **downstream** of the block decision and reuse sufficiency/blocked-open context for message body.

### Cooldown and deduplication — **User: strategy_symbol_reason_exchange + 5m**
- **D-03:** Dedup/cooldown composite key: **`strategy_id` + `symbol` + `reason_code` + `exchange_id`** (`ibkr-paper` / `ibkr-live` from strategy exchange config), so different symbols, reasons, or modes do not suppress each other incorrectly.
- **D-04:** Default cooldown window: **5 minutes** per composite key (unless overridden later by config — exact override surface is Claude’s discretion).
- **D-05:** Within an active cooldown window for a key, **suppress duplicate user-channel alerts** for repeated blocks; structured logging behavior stays governed by Phase 2 (no requirement to duplicate user alerts for every blocked tick).

### Copy and severity (R5) — **User: warn_no_close_hold + emphasize**
- **D-06:** **No open position:** use **warning** severity, explain that open/add was blocked and why; **do not** include explicit “please decide close vs hold” wording (avoids implying a position exists).
- **D-07:** **Open position exists:** use **warning** and **explicitly highlight “有持仓 / 当前有仓”** in **title or first line**, plus payload/position summary; message MUST satisfy R5: **explicitly ask the user to decide close vs hold** (no default auto-close).

### Channels and payload shape — **User: signal_notifier + mirror_keys**
- **D-08:** Send user insufficient alerts through **`load_notification_config`** + **`SignalNotifier.notify_signal`** (same channel routing as existing signal notifications), not a browser-only side path.
- **D-09:** User-visible **`payload` / structured fields** SHOULD **mirror stable keys** from the Phase 2 blocked-open / sufficiency logging contract (**`_execution_mode`**, **`exchange_config.exchange_id`**, reason/diagnostics-aligned fields per **02-CONTEXT** / **02-REVIEWS.md** R-03), **plus** a short human-readable summary for email/webhook readability.
- **D-10:** When documenting operator-facing text, follow **02-CONTEXT** / ROADMAP guidance: reference **`strategy_ctx["_execution_mode"]`** and **`exchange_config.exchange_id`** as implemented — avoid ambiguous bare `execution_mode` prose.

### Observability (N3)
- **D-11:** Emit **`ibkr_insufficient_data_alert_sent`** when a user-channel insufficient alert **passes dedup/cooldown** and is **dispatched** (or when dispatch is attempted — exact “success vs attempt” granularity is Claude’s discretion; prefer **one event per logical alert emission** after cooldown, with attempted channels noted in payload).

### Claude's Discretion
- Override surface for cooldown (global default vs `notification_config` extension) and in-memory dedup store implementation (process-local vs shared).
- Exact `notify_signal` parameter mapping (`signal_type` string for this alert family, `extra` vs `payload` split) as long as D-08/D-09 hold.
- Whether `ibkr_insufficient_data_alert_sent` fires on “all channels failed” vs “at least one succeeded” (D-11 granularity).

### Folded Todos

_(none — `todo match-phase` returned no matches)_

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope
- `.planning/ROADMAP.md` — Phase 3 objective, tasks, exit criteria; carryover bullets on `stale_prev_close`, large `missing_window` / `market_closed_gap` operator copy, and Phase 2→3 payload naming.
- `.planning/REQUIREMENTS.md` — R4 (alert contents), R5 (close/hold support, no auto-close), N3 (`ibkr_insufficient_data_alert_sent`), N4 tests.
- `.planning/PROJECT.md` — Milestone intent for alerting and decision support.

### Prior phase decisions
- `.planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md` — Sufficiency contract, reason codes, fail-safe policy.
- `.planning/phases/02-open-signal-guard-in-execution-path/02-CONTEXT.md` — Guard placement, exception→synthetic insufficient, dual structured logs only in Phase 2, `_execution_mode` / `exchange_id` gate, no `persist_notification` in Phase 2.
- `.planning/phases/02-open-signal-guard-in-execution-path/02-REVIEWS.md` — R-02/R-03/R-04 and payload schema checklist for mapping to Phase 3.

### Implementation anchors
- `backend_api_python/app/services/live_trading/records.py` — `load_notification_config`.
- `backend_api_python/app/services/signal_notifier.py` — `SignalNotifier.notify_signal`, channel dispatch (`_notify_browser`, `_notify_webhook`, etc.).
- `backend_api_python/app/services/data_handler.py` — `persist_notification` (legacy/helper path; Phase 3 primary path per **D-08** is `SignalNotifier`).
- `backend_api_python/app/services/signal_executor.py` — Guard / block site to hook alert emission **after** block decision (**D-01**).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`load_notification_config(strategy_id)`** — loads JSON `notification_config` from `qd_strategies_trading`.
- **`SignalNotifier.notify_signal`** — routes browser / webhook / email (and other configured channels) from the same config shape used by `SignalRunner`.
- **`DataHandler.persist_notification`** — direct DB insert to `qd_strategy_notifications` with fixed `"browser"` channel in one overload; `SignalNotifier._notify_browser` writes `channels` as joined list — Phase 3 should prefer **notifier** path per **D-08**.

### Established Patterns
- Live order path uses runners with `notification_config` resolved from context or DB.
- Phase 2 tests assert Phase 2 code does **not** call `persist_notification` / `ibkr_insufficient_data_alert_sent` in the guard-only scope (`test_data_sufficiency_logging.py`); Phase 3 adds these **without** weakening Phase 2 boundaries.

### Integration Points
- Primary: immediately after **open/add block** decision in **`SignalExecutor.execute`** (or thin helper called from there), with access to strategy id, symbol, `exchange_config`, sufficiency result, and position snapshot for payload (**D-07/D-09**).

</code_context>

<specifics>
## Specific Ideas

- User explicitly chose: **block-only** user alerts; dedup key **strategy + symbol + reason + exchange**; **5 min** default cooldown; **warning** without close/hold text when flat; **warning + prominent 有持仓** when positioned; **`SignalNotifier`** path; **mirror Phase 2 stable keys** in user payload.

</specifics>

<deferred>
## Deferred Ideas

- **ROADMAP Phase 3 carryover — `stale_prev_close`:** operator-facing staleness thresholds and how `FreshnessMetadata` maps to alert copy — fold into planning/tasks; threshold **tuning** may still overlap Phase 4.
- **ROADMAP — large `missing_window` / `market_closed_gap`:** document expected wall-clock semantics in operator copy (may be partly Phase 3 docs/copy, partly runbook).
- **REQUIREMENTS out of scope:** new frontend decision UI; forced auto-close policy changes.

### Reviewed Todos (not folded)

_(none)_

</deferred>

---

*Phase: 03-alerting-and-user-decision-support*
*Context gathered: 2026-04-18*
