---
phase: 01
reviewers:
  - claude
  - opencode
skipped:
  - gemini: 非交互环境卡在 OAuth 浏览器确认（`Opening authentication page... [Y/n]`），未完成调用
  - codex: CLI 未安装（`command -v codex`）
  - coderabbit: CLI 未安装（`command -v coderabbit`）
reviewed_at: "2026-04-18T01:22:32Z"
plans_reviewed:
  - 01-01-PLAN.md
  - 01-02-PLAN.md
notes:
  - "OpenCode 首轮输出在终端被截断（约 43 行）；未成功完成第二轮补全（长时间无输出后已终止）。"
  - "Claude 使用 `claude -p \"$(cat ...)\" --permission-mode dontAsk`；首行 stdin 警告为 CLI 提示，可忽略。"
---

# Cross-AI Plan Review — Phase 1

## Gemini Review

**状态：** 未完成。

Gemini CLI 在本环境中启动后提示 `Opening authentication page in your browser. Do you want to continue? [Y/n]:`，非交互会话无法自动确认，审查未产生模型输出。请在已登录/已配置凭证的终端重试，或查阅 [Gemini CLI](https://github.com/google-gemini/gemini-cli) 文档配置无头/CI 认证。

---

## Claude Review

### Review: 01-01-PLAN.md & 01-02-PLAN.md

### Summary

Both plans are well-structured and correctly scoped. Plan 01 has been substantially delivered (types + adapter exist; tests still pending) and establishes a clean component boundary. Plan 02 adds the pure validator, structured logging, and orchestration service on top of Plan 01's contracts with appropriate separation of concerns — keeping the validator side-effect free, isolating log emission to orchestration, and properly documenting Phase 1 vs Phase 2 responsibilities around `get_kline` drift.

---

### Strengths

**Plan 01:**

- Typed contracts with stable top-level fields and fine-grained reason taxonomy match all locked decisions (D-01 through D-05)
- Adapter correctly reuses only public `trading_hours` symbols (`parse_liquid_hours`, `is_rth_check`, `resolve_time_zone_id_for_schedule`) with no private-underscore coupling
- Explicit `server_time_utc` parameter on public entrypoint enables fully deterministic test injection
- `timezone_resolution="fallback_utc"` + `schedule_failure_reason="timezone_id_unresolved"` dual-field handling correctly distinguishes "parsed but not trusted" from "completely unknown"
- RE-REVIEW items (TIMEFRAME_SECONDS_MAP, con_id in diagnostics, timezone fallback warning, fallback+schedule_known_* semantics) are all addressed

**Plan 02:**

- Validator purity enforced: no `logging`, no `kline_fetcher` import, no side effects — only `data_sufficiency_types` as dependency
- Deterministic precedence ordering: `unknown_schedule` > `stale_prev_close` > `market_closed_gap` > `missing_bars` > `sufficient`
- `get_kline_callable` injected at runtime (not imported), enabling clean mocking at the callable boundary without forking `kline_fetcher` internals
- `build_ibkr_data_sufficiency_check_payload` (pure) separated from `emit_ibkr_data_sufficiency_check` (side effect) — correct design
- `FreshnessMetadata` properly optional; defaults to not emitting `stale_prev_close` when absent — matches deferred Phase 3 threshold semantics
- Integration test properly flags LOWER_LEVELS mock fidelity caveat and defers real-path drift checks to Phase 2 per ROADMAP carryover

---

### Concerns

**Plan 01 — MEDIUM:**

- `test_adapter_does_not_mutate_trading_hours_cache` appears in use_cases and the acceptance criteria list mentions it via the broader adapter test file, but the exact function name is not enumerated in the acceptance criteria text the way other tests are. Verify this test gets written since it guards cache mutation side effects.

**Plan 02 — LOW:**

- `test_adapter_to_service_emits_ibkr_data_sufficiency_check` is listed in Task 3 acceptance criteria but named `test_adapter_to_service_emits_ibkr_data_sufficiency_check` in the `<verify>` block vs `adapter_to_service_emits_ibkr_data_sufficiency_check` in the action text. Minor naming inconsistency; confirm exact name before implementation.
- Exception handling for `get_kline_callable` raising is documented to propagate (not silently mask as zero bars), which is correct, but the exact re-raise vs wrapped behavior in the orchestrator is not specified. This is acceptable since Phase 1 doesn't implement blocking — but Phase 2 must define the contract for what the orchestrator does with the raised exception (maps to insufficient? re-raises to runner?).

**Plan 02 — INFORMATIONAL:**

- `test_get_kline_raises_documented_behavior` only covers that the exception propagates per the documented contract; it doesn't specify what the orchestrator does downstream. This is intentional (Phase 3 territory) but leaves a gap where a real `get_kline` failure in Phase 2 integration testing might surprise. Worth adding a ROADMAP Phase 2 carryover item to explicitly define the failure contract.

---

### Suggestions

1. **Clarify exception contract in orchestrator:** Add a docstring to `evaluate_ibkr_data_sufficiency_and_log` (or the service entrypoint) stating whether a `get_kline_callable` exception results in re-raise or maps to a specific insufficiency outcome. Phase 2 can tighten this, but the intent should be documented now.

2. **Confirm `test_adapter_does_not_mutate_trading_hours_cache` is written:** The test file `test_ibkr_schedule_provider.py` doesn't exist yet per Wave 0 gaps. Ensure this specific test (calling `clear_cache()` before/after adapter calls and asserting deterministic outputs) is included when that file is created.

3. **Add Phase 2 carryover for real-path `get_kline` drift:** The ROADMAP carryover mentions this but it isn't explicitly tracked as a Phase 2 task. Consider adding a ROADMAP Phase 2 item: "Real-path `get_kline` alignment: add at least one contract/integration test comparing `compute_available_bars_from_kline_fetcher` against real `kline_fetcher.get_kline` behavior for representative `(market, symbol, timeframe, limit)` tuples."

---

### Risk Assessment

**Overall: LOW**

- Plans correctly respect phase boundaries; no execution blocking in Phase 1, no alert dispatch in Phase 2
- All locked decisions (D-01 through D-11) are honored and traceable to implementation
- Validator purity prevents accidental logging side effects polluting the classifier
- Adapter reuses only public seams from `trading_hours`; no private API coupling risk
- Float assertions use epsilon; timezone fallback semantics are correctly dual-field; `FreshnessMetadata` is properly optional
- Phase 2 correctly defers real `kline_fetcher` integration drift testing per ROADMAP carryover
- Main residual risk is that the Wave 0 test files haven't been created yet, but the implementation files they test have been delivered correctly

---

## Codex Review

*（`codex` CLI 未安装，未执行审查。）*

---

## CodeRabbit Review

*（`coderabbit` CLI 未安装；且 CodeRabbit 面向 git diff，本命令未调用。）*

---

## OpenCode Review

*（首轮输出被截断；以下为已捕获的 Markdown 正文，不含控制台的 ANSI 转义序列。）*

# Phase 1 Plan Review

## Summary

Both plans are well-structured and correctly implement the Phase 1 domain model boundary: typed sufficiency contracts, IBKR schedule adapter, deterministic classification, and structured logging. The plans preserve the locked decisions (D-01 through D-11) and phase separation — execution blocking and alerting are appropriately deferred to later phases. The main risks are around incomplete `FreshnessMetadata` definition and potential gaps in `market_category` handling.

---

## Plan 01-01 Assessment

### Strengths

- **Typed contract fidelity**: Correctly implements `DataSufficiencyResult` with stable top-level fields per D-01/D-02
- **Fine-grained reason taxonomy**: Exact reason codes (`missing_bars`, `stale_prev_close`, `market_closed_gap`, `unknown_schedule`) per D-03
- **Schedule failure explicitness**: `schedule_unknown` vs `schedule_known_closed/open` distinction per D-04/D-05
- **Adapter reuses existing code**: Correctly wraps `trading_hours.py` public API instead of reimplementing (D-09/D-10/D-11)
- **Timeframe normalization**: Includes documented `TIMEFRAME_SECONDS_MAP` with seconds-based `effective_lookback` per D-06/D-07
- **Test naming governance**: Clear acceptance criteria with exact test function names

### Concerns

1. **`FreshnessMetadata` not defined** — The review_carryover references `FreshnessMetadata` for stale_prev_close but it's not in the types definition. **Severity: MEDIUM** — Will cause downstream validator issues.

2. **`market_category` field usage unclear** — The types include `market_category` but no explicit derivation logic in the plan. **Severity: LOW** — May be passed through unchanged; needs documentation.

3. **`con_id` propagation path** — Plan mentions copying `con_id` through diagnostics but no explicit test verifies this from adapter → validator → logging. **Severity: LOW** — Test coverage gap.

### Suggestions

- Add explicit `FreshnessMetadata` dataclass definition to `data_sufficiency_types.py` in Task 1
- Document in module docstring how `market_category` is derived/passed through
- Add test case `test_con_id_propagates_through_diagnostics` to verify field flow

---

## Plan 01-02 Assessment

### Strengths

- **Pure validator boundary**: Correctly isolated — no logging, no I/O imports

*（输出在此处截断；若需完整 OpenCode 段落，请在本地对较短分块提示重试 `opencode run`。）*

---

## Consensus Summary

综合 **Claude** 与 **OpenCode（部分）** 的可读输出，对 Phase 1 两份计划（`01-01-PLAN.md`、`01-02-PLAN.md`）的共识如下。

### Agreed Strengths

- 阶段边界清晰：Phase 1 聚焦类型契约、IBKR 日程适配、纯分类与结构化日志，不提前做开仓拦截与告警派发。
- 组件拆分合理：`trading_hours` 公共 API 适配、`DataSufficiencyResult` 稳定字段、纯校验器与编排/日志副作用分离。
- 可测试性设计强：注入 `server_time_utc`、`get_kline_callable`、明确 precedence 与大量具名 `test_*` 锚点。
- 与 ROADMAP 中 Phase 2 的「真实 `get_kline` 路径 / mock 漂移」承托一致（计划内已多次指向后续阶段）。

### Agreed Concerns（优先处理）

1. **编排层在 `get_kline_callable` 异常时的契约**（Claude：LOW～INFORMATIONAL）：传播异常本身已写清，但 orchestrator 是否捕获、映射为某种 `reason_code`、或向上抛出，应在服务入口 docstring 或 Phase 2 任务中写死，避免 Phase 2 集成时行为分歧。
2. **测试与验收措辞的严密性**（Claude MEDIUM）：`test_adapter_does_not_mutate_trading_hours_cache` 在正文验收列表中的显式程度弱于其它用例名，实施时需确保不遗漏。
3. **跨层字段的可观测闭环**（OpenCode LOW + 与 Claude 重叠）：`con_id` 等诊断字段从适配器经结果到日志的断言可加强（可选新增用例名供实施参考）。

### Divergent Views

- **`FreshnessMetadata` 归属**：OpenCode 认为应在 **Plan 01** 的 `data_sufficiency_types.py` Task 1 就定义；当前 `01-02-PLAN.md` 的 review_carryover 明确将 `FreshnessMetadata` 放在 **Plan 02**（类型或校验器旁）并约束「缺省不因缺失元数据误判 `stale_prev_close`」。**结论**：以计划文件为准（Plan 02 引入）；若实施中发现类型模块更利于复用，可在同一 PR 中在 `data_sufficiency_types.py` 增加定义并同步更新 Plan 01 验收列表，避免「OpenCode 所指缺口」与「Plan 02 已规划」长期不一致。

---

## 后续用法

将本文件作为输入继续打磨计划：

```text
/gsd-plan-phase 1 --reviews
```

临时文件：`/tmp/gsd-review-prompt-01.md`（提示词）、`/tmp/gsd-review-claude-01.md`（Claude 原始 tee）可在确认无误后手动删除。
