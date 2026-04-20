---
phase: "03"
reviewers: [gemini, claude, codex, coderabbit, opencode]
reviewed_at: "2026-04-18T13:25:00Z"
plans_reviewed:
  - 03-01-PLAN.md
  - 03-02-PLAN.md
prompt_notes: "Prompt assembled at review time (~48k) with both PLAN bodies + CONTEXT/RESEARCH/REQUIREMENTS; temp copy removed after run. Gemini blocked on interactive auth; Codex/CodeRabbit absent from PATH."
---

# Cross-AI Plan Review — Phase 3

**Scope:** `03-01-PLAN.md`, `03-02-PLAN.md`, plus `03-CONTEXT.md`, `03-RESEARCH.md` excerpts and REQUIREMENTS (R4/R5/N3/N4) in the review prompt.

**Tooling:** `gemini` / `claude` / `opencode` on PATH; `codex` / `coderabbit` missing. `--all` → all **available** CLIs were invoked where non-interactive completion was possible.

---

## Gemini Review

**Status:** Not completed — headless run blocked on interactive auth (`Opening authentication page in your browser. Do you want to continue? [Y/n]:`). Output file was ~78 bytes; process terminated.

**Action:** Complete Gemini CLI login in an interactive terminal, then re-run `/gsd/review --phase 3 --gemini` if a Gemini-only pass is needed.

---

## Codex Review

**Status:** Skipped — `codex` CLI not installed (`command -v codex` → missing).

---

## CodeRabbit Review

**Status:** Skipped — `coderabbit` CLI not installed (`command -v coderabbit` → missing).

---

## Claude Review

*(Claude Code `claude --print "$(cat /tmp/gsd-review-prompt-3.md)"`; first line of raw capture was a stdin timing warning from the tool — review body begins below.)*

### Summary

The plans correctly implement the Phase 3 alerting boundary: user-channel notifications fire only at the exact block moment (D-01), use `SignalNotifier` with cooldown dedup per composite key, mirror Phase 2 stable payload fields, and emit the N3 `ibkr_insufficient_data_alert_sent` event. The Wave 1 / Wave 2 split is logical (core impl → tests). However, there is one **breaking gap**: adding N3 functions to `data_sufficiency_logging.py` in Task 2 will fail the existing Phase 2 sentinel test `test_logging_module_does_not_define_phase3_alert_event`, and no task in either wave removes or updates that assertion.

### Strengths

- **Correct trigger boundary**: All three tasks hook at the right seam — immediately after `emit_ibkr_open_blocked_insufficient_data` and before `return False`, satisfying D-01.
- **Dedup design is sound**: Process-local `dict` + `time.monotonic()` with composite key `(strategy_id, symbol, reason_code.value, exchange_id)` correctly isolates all four dimensions per D-03/D-04.
- **Notification config fallback**: Task 3 explicitly resolves `_notification_config` from ctx first, then DB via `load_notification_config`, matching D-08 and existing runner patterns.
- **N3 event kept co-located**: Adding `ibkr_insufficient_data_alert_sent` to `data_sufficiency_logging.py` (alongside existing `ibkr_data_sufficiency_check` / `ibkr_open_blocked_insufficient_data`) preserves observability co-location.
- **Threat model covers T-03-01/T-03-02/T-03-03** with concrete mitigations (no raw exceptions in extra, try/except swallowing, no URL logging in webhooks).
- **Task 4 carryover docstring** correctly addresses the ROADMAP Phase 3 carryover bullets for `stale_prev_close` and `market_closed_gap` operator copy without over-engineering.

### Concerns

#### 1. `test_logging_module_does_not_define_phase3_alert_event` Will Fail (HIGH)

The existing test at `test_data_sufficiency_logging.py:200-204` asserts `"ibkr_insufficient_data_alert_sent" not in src` for `data_sufficiency_logging.py`. Task 2 of `03-01-PLAN.md` adds exactly those symbols to that file. **No task in either wave removes or updates this assertion.** Full suite `pytest backend_api_python/tests -q` will exit non-zero after Wave 1 Task 2 until the sentinel is revised (e.g. in `03-02` Task 2).

#### 2. Signal type constant naming inconsistency (MEDIUM)

Align the module constant name (`IBKR_INSUFFICIENT_USER_ALERT_SIGNAL_TYPE` vs alternatives) with what tests import/patch.

#### 3. `strategy_name` may be empty (MEDIUM)

Prefer `strategy_ctx.get("_strategy_name") or load_strategy_name(strategy_id)` (or equivalent) instead of defaulting to `""` for all call paths.

#### 4. `direction` for flat alerts (LOW)

Clarify in the plan that `direction` is cosmetic when `signal_type` is the dedicated insufficient alert family and `_signal_meta` treats it as a neutral signal event.

### Suggestions

1. Add an explicit sub-step in `03-02-PLAN` Task 2 to update or replace `test_logging_module_does_not_define_phase3_alert_event` now that Phase 3 owns that symbol.
2. Standardize `signal_type` constant + test imports.
3. Use `load_strategy_name` fallback when `_strategy_name` is absent.
4. Document flat-case `direction` behavior relative to `SignalNotifier._signal_meta`.

### Risk Assessment

**Overall: MEDIUM** — Phase 2 sentinel test gap is a predictable full-suite failure after Wave 1 Task 2 until Wave 2 adjusts tests; fix is localized with no architectural change.

---

## OpenCode Review

*(OpenCode `opencode run -` with stdin prompt; model banner: MiniMax-M2.5. ANSI control sequences stripped in this section.)*

### Review Summary

The Phase 3 plans are well-structured and correctly identify the integration point, component reuse strategy, and dedup logic. Several **HIGH**-priority concerns around dependency injection and data availability at the hook point should be resolved before implementation.

### Strengths

1. **Correct integration point** — Hook after `emit_ibkr_open_blocked_insufficient_data` (D-01 block-only alerts).
2. **Proper component reuse** — `SignalNotifier.notify_signal` (D-08) and `load_notification_config` fallback.
3. **Dedup design** — Composite key with 5-minute cooldown (D-03/D-04).
4. **Copy handling** — Flat vs positioned distinction with **有持仓** requirement.
5. **Observability separation** — N3 event downstream of block decision vs Phase 2 logs.

### Concerns

**HIGH**

1. **Notification config at hook** — Verify `notification_config` is actually available before the early `return False`; if today it is only resolved later on the success path, the insufficient branch must explicitly load config (plan already hints this; executor code path must be verified against **current** `signal_executor.py`).

2. **Position data for R5** — Confirm `current_positions` (or `DataHandler` lookup) is available and correct at the hook for payload building.

3. **SignalNotifier lifecycle** — Clarify instantiate-per-call vs shared instance relative to other executor paths.

**MEDIUM**

4. **Thread safety** — Process-local dedup dict may need a `threading.Lock` under multi-threaded strategy execution.

5. **Missing `reason_code` isolation test** — Add coverage that different `reason_code` values do not incorrectly share cooldown (D-03).

6. **Empty `notification_config`** — Define behavior: skip user alert with warning, do not crash.

**LOW**

7. **Module constant** for `signal_type` string.

8. **Flat alert `direction`** — Special-case or document as cosmetic for directionless notifier rendering.

### Suggestions

1. Explicit config load in insufficient branch (snippet suggested in review).
2. Add `threading.Lock` around dedup store mutations.
3. Add `reason_code` isolation test in `test_ibkr_insufficient_user_alert.py`.
4. Define module-level `signal_type` constant in `ibkr_insufficient_user_alert.py`.
5. Verify position API on `DataHandler` (or equivalent) at hook.

### Risk Assessment

**MEDIUM** — Architecture matches CONTEXT; remaining risks are implementation clarifications (config, positions, concurrency) before coding.

---

## Consensus Summary

多评审源一致认为：计划在 **D-01 阻断点挂钩**、**SignalNotifier + notification_config**、**四元组冷却键** 与 **N3 事件与 Phase 2 日志分离** 上与 `03-CONTEXT.md` 一致，阶段目标可达。**Claude** 与 **OpenCode** 均给出 **MEDIUM** 总风险；最高优先的共同问题是：在 `data_sufficiency_logging.py` 中落地 `ibkr_insufficient_data_alert_sent` 会与现有关键测试 `test_logging_module_does_not_define_phase3_alert_event` 冲突，**必须在执行/重规划时显式更新该测试**（建议在 `03-02` 的 logging 测试任务中写明）。OpenCode 额外强调 **线程安全**、**空通知配置** 与 **`reason_code` 维度的 dedup 单测**；Claude 强调 **`_strategy_name` 回退** 与 **`signal_type` 常量命名一致性**。

### Agreed Strengths

- 阻断瞬间与 Phase 2 `ibkr_open_blocked_insufficient_data` 对齐，符合 D-01。
- Dedup 维度与 5 分钟冷却符合 D-03/D-04。
- 使用 `SignalNotifier` + `load_notification_config` 符合 D-08。

### Agreed Concerns（高优先级）

| 主题 | 说明 |
|------|------|
| Phase 2 哨兵测试 | `test_logging_module_does_not_define_phase3_alert_event` 禁止在 `data_sufficiency_logging.py` 出现 Phase 3 符号；与 03-01 Task 2 直接冲突，全量 pytest 会在实现 Task 2 后失败，除非更新测试。 |
| 执行路径细节 | `notification_config` / 持仓数据在 `return False` 分支是否已可用，需对照当前 `signal_executor.py` 实装核对（OpenCode HIGH）。 |

### Divergent Views

- **并发**：OpenCode 建议对 dedup 字典加锁；Claude 未单独列为 HIGH — 可在实现时按实际执行线程模型决定（若 `SignalExecutor` 单线程 per strategy 可降级）。
- **Gemini**：未完成评审，无法纳入与 Gemini 的“分歧”对比。

---

**下一步：** 将上述共识并入计划 → `/gsd/plan-phase 3 --reviews`
