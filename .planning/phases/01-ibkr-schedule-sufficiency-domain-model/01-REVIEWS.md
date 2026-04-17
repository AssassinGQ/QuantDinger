---
phase: 1
reviewers:
  - gemini
  - claude
  - opencode
skipped:
  - codex: CLI 未安装（`command -v codex`）
  - coderabbit: CLI 未安装（`command -v coderabbit`）
reviewed_at: "2026-04-17T06:06:50Z"
plans_reviewed:
  - 01-01-PLAN.md
  - 01-02-PLAN.md
notes:
  - "Claude CLI 启动时出现 stdin 警告（3s 内未收到管道数据），其输出可能混合了工作区代码状态与计划文本；请以计划文件与仓库事实为准交叉验证。"
---

# Cross-AI Plan Review — Phase 1

## Gemini Review

# Implementation Plan Review: Phase 1 (IBKR Schedule + Sufficiency Domain Model)

This review covers `01-01-PLAN.md` (Contract & Adapter) and `01-02-PLAN.md` (Validator & Logging) for the IBKR data-sufficiency risk gate.

## 1. Summary
The plans provide a robust and architecturally sound foundation for the IBKR sufficiency risk gate. By splitting the work into a typed contract phase and a pure logic/orchestration phase, the implementation ensures that the data-sufficiency domain is clearly defined before it is integrated into the execution path. The strategy of reusing existing `trading_hours.py` logic through a thin adapter is a high-signal decision that maintains consistency with current session checks while improving observability via structured logging.

## 2. Strengths
- **Clean Architectural Boundaries:** The separation of the `IBKRScheduleProvider` (adapter) from the `DataSufficiencyValidator` (pure logic) strictly adheres to decision `D-09` and ensures that classification logic is not coupled to broker-specific parsing.
- **Strongly Typed Contract:** The use of `Enum` and `dataclass` for `DataSufficiencyResult` and its diagnostics (Task 1, Plan 01) provides the "machine-stable" interface required for later guard and alerting phases.
- **Side-Effect Isolation:** The validator in Plan 02 is designed to be pure (no I/O or logging), making it highly testable and resistant to regression. Orchestration is correctly handled in a separate `DataSufficiencyService`.
- **Comprehensive Test Specifications:** The inclusion of exact `def test_*` names and detailed use cases (e.g., "cross_day_session", "fuse_transition", "precedence_unknown_schedule_over_missing_bars") ensures that implementation will be anchored to the requirements.
- **Observability Alignment:** Task 2 in Plan 02 directly addresses `N3` by defining a structured logging payload that excludes raw broker blobs, reducing noise while maintaining auditability.

## 3. Concerns
- **Mock Drift Risk (MEDIUM):** Plan 02 Task 1 uses a mocked `get_kline` callable to count available bars. While the plan mentions mirroring `LOWER_LEVELS` aggregation, there is a risk that the mock's simplified counting might diverge from `kline_fetcher.py`'s real-world behavior (e.g., handling of partial bars or inclusive/exclusive boundaries). This is partially mitigated by the deferred "real-path" tests in Phase 2.
- **Staleness Threshold Ambiguity (LOW):** The validator includes `stale_prev_close` in its precedence list, but the specific "how stale is too stale" threshold is deferred to Phase 3. In Phase 1, the validator might lack a concrete threshold to trigger this reason code unless a temporary default is used.
- **`con_id` Fuse Side Effects (LOW):** Since `trading_hours` uses a global `_fuse_until` dictionary keyed by `con_id`, the adapter's use of `is_rth_check` will trigger/update this fuse. While expected, this means a sufficiency check for one strategy could "fuse" the check for another strategy sharing the same contract if the market is detected as closed.

## 4. Suggestions
- **Staleness Logic:** In `DataSufficiencyValidator`, explicitly document or implement a simple "fallback" threshold for `stale_prev_close` (e.g., > 2 * timeframe duration) so that the reason code can be exercised in Phase 1 integration tests even before Phase 3 policy is finalized.
- **Epsilon in Tests:** Ensure that the "epsilon" used for float comparisons in `test_effective_lookback_seconds_boundary` is standardized (e.g., `1e-6`) across all new test files to prevent flaky results on different architectures.
- **Aggregation Mocking:** In `test_aggregation_1h_from_5m_mocked_get_kline`, ensure the mock data explicitly includes "boundary" timestamps (exactly on the hour) to verify the integer bar count is precise.

## 5. Risk Assessment
**Overall Risk: LOW**

The plan is low-risk because it avoids "big bang" refactoring and instead builds a layer on top of existing, verified logic. The strict enforcement of pure-logic boundaries and the high level of detail in the test specifications significantly reduce the likelihood of integration issues in Phase 2.

---
**Reviewer Note:** The plans are ready for implementation. The phased approach correctly prioritizes the domain model, ensuring that the "truth" of data sufficiency is established before enforcement begins.

---

## Claude Review

Warning: no stdin data received in 3s, proceeding without it. If piping from a slow command, redirect stdin explicitly: < /dev/null to skip, or wait longer.
Now I have a complete picture of both plans and all implementations. Let me write my review.

---

## Plan Review — Phase 01 (Plans 01 + 02)

### Summary

Both plans are thorough, well-scoped, and correctly preserve the phase boundary between domain modeling (Plan 01) and classification + logging (Plan 02). The implementation is largely sound with one significant parameter-ordering bug in the service-to-validator call path, plus a few minor issues noted below.

---

### Strengths

**Plan 01 — Contract + Adapter**
- Clean split: types in `data_sufficiency_types.py`, adapter in `ibkr_schedule_provider.py`, reusing only public `trading_hours` symbols.
- `schedule_unknown` is properly distinguishable from `schedule_known_closed` — the core Phase 1 contract requirement.
- Timezone fallback semantics are documented in the adapter docstring (RE-REVIEW carryover item fulfilled).
- All required test names are present; the `test_no_trading_hours_private_imports` static check is a good Trust Boundary enforcement.
- `TIMEFRAME_SECONDS_MAP` mirrors `kline_fetcher's` `TIMEFRAME_SECONDS` correctly via `app.data_sources.base`.

**Plan 02 — Validator + Logging + Service**
- Validator is genuinely pure — no `logging`, no I/O imports, no `kline_fetcher` imports. The import boundary is correct and verified by acceptance criteria.
- Deterministic precedence chain (`unknown_schedule` → `stale_prev_close` → `market_closed_gap` → `missing_bars` → `sufficient`) is explicit in code and covered by tests.
- `compute_available_bars_from_kline_fetcher` correctly mirrors `kline_fetcher's` `LOWER_LEVELS` aggregation chain and documents the Phase 2 drift concern.
- `emit_ibkr_data_sufficiency_check` is called exactly once per orchestration path (verified by `test_emit_once_per_call` and `test_evaluate_entrypoint_calls_emit_once`).
- Float epsilon comparisons (`< 1e-6`) used throughout for `effective_lookback` and `missing_window`.

---

### Concerns

**HIGH — Bug: `market_category` passed where `market` expected in service call**

`data_sufficiency_service.py:50-56` passes positional args to `compute_available_bars_from_kline_fetcher`:
```python
available = compute_available_bars_from_kline_fetcher(
    market_category,   # ← first positional arg
    symbol,
    timeframe,
    required_bars,
    before_time_utc,
    get_kline_callable,
)
```

But `compute_available_bars_from_kline_fetcher's` signature is:
```python
def compute_available_bars_from_kline_fetcher(
    market: str,       # ← named "market"
    symbol: str,
    timeframe: str,
    required_bars: int,
    before_time_utc: Optional[int],
    get_kline_callable: Callable[..., List[dict]],
) -> int:
```

`market_category` values like `"USStock"` would be bound to `market` and `symbol` to `timeframe` — a type mismatch (`str` vs `int`) that would raise `TypeError` at call time. The function body never actually uses `market` (only `lower_sec` lookup uses `TIMEFRAME_SECONDS_MAP`), so this silently does the wrong thing: `symbol` is interpreted as `timeframe` and `timeframe` as `required_bars`. The aggregation chain would likely return an incorrect bar count or fall through to the default path.

**Impact:** Both integration tests (`test_adapter_to_service_emits_ibkr_data_sufficiency_check` and `test_evaluate_entrypoint_calls_emit_once`) use `before_time_utc=None` with `symbol="SPY"`, which partially masks the bug because `before_time_utc=None` skips the `before_time` conditional in `compute_available_bars_from_kline_fetcher`. However, the wrong-argument issue still corrupts internal logic. Fix: use named keyword argument `market=market_category`.

---

**MEDIUM — `FreshnessMetadata.stale_prev_close` threshold is trivially permissive**

`_caller_reports_stale_prev_close` in `data_sufficiency_validator.py:104-109` returns `True` for any `prev_close_age_seconds >= 1.0`. This means 1-second-old prev close triggers `stale_prev_close`. The plan defers threshold policy to Phase 3, so the placeholder is technically correct — but no test exercises the boundary near the threshold. `test_stale_prev_close` uses `3600.0` seconds, far from the `>= 1.0` edge. Consider adding a test at `0.999` to document the Phase 3 tightening expected behavior.

---

**MEDIUM — `resolve_time_zone_id_for_schedule` is not re-exported in `trading_hours` `__all__`**

The RE-REVIEW carryover says the adapter should use only public `trading_hours` symbols. `resolve_time_zone_id_for_schedule` is not in `__all__` (if one exists) or is a private-ish helper. The adapter imports it directly. This is a minor coupling concern but not a functional bug — the function is public in the `trading_hours` module namespace and is correctly reused.

---

**LOW — Missing `test_cross_day_session` in Plan 02 acceptance criteria**

The validator test `test_cross_day_session` exists in `test_data_sufficiency_validator.py:180-190` and is listed in Plan 02 use cases, but is absent from the acceptance criteria checklist. Coverage is preserved (the test exists and runs), so the plan's governance rule ("renaming or splitting for clarity is allowed when the same scenario remains covered") is satisfied — but the omission from acceptance criteria is an inconsistency.

---

**LOW — `test_stale_prev_close` never asserts `sufficient=False`**

`test_stale_prev_close` in `test_data_sufficiency_validator.py:85-100` asserts `r.reason_code.value == "stale_prev_close"` but never checks `r.sufficient is False`. Given the implementation sets `sufficient=False` for this reason code, this is a test coverage gap, not a bug — but the acceptance criteria do not require this assertion.

---

### Suggestions

1. **Fix the `market_category` / `market` parameter bug** in `data_sufficiency_service.py:50`: change to `market=market_category,` as a keyword argument to make the contract explicit and prevent silent positional binding errors.

2. **Add boundary test for stale threshold**: `test_stale_prev_close_boundary` using `prev_close_age_seconds=0.999` (should NOT trigger stale) and `prev_close_age_seconds=1.0` (should trigger) to document Phase 3 threshold expectations.

3. **Add `r.sufficient is False` assertion** to `test_stale_prev_close` to match the pattern used in other insufficiency tests (`test_missing_bars`, `test_unknown_schedule`, etc.).

4. **Clarify RE-REVIEW carryover compliance in acceptance criteria**: add `test_cross_day_session` explicitly to Plan 02's acceptance criteria list to eliminate the minor gap between use cases and checklist.

5. **Verify `resolve_time_zone_id_for_schedule` is a stable public symbol**: check `trading_hours.__all__` (if defined) to confirm the adapter's import is a supported public API, not an implementation detail subject to renaming.

---

### Risk Assessment

**Overall Risk: MEDIUM**

The `market_category` parameter bug is the only HIGH concern — it would cause a runtime `TypeError` in production and corrupt sufficiency decisions in the orchestration path. All other concerns are MEDIUM or LOW and are either deferred design decisions (stale threshold), documentation inconsistencies, or minor test coverage gaps.

The phase boundary is well preserved: Plan 01 correctly avoids execution blocking, Plan 02 correctly keeps the validator pure. The typed contracts and reason taxonomy are complete and correct. Once the parameter bug is fixed, the phase is ready for Phase 2 integration.

---

**Recommendation**: Fix the `market_category` → `market` keyword argument in `data_sufficiency_service.py` before marking Phase 1 complete. All other issues are non-blocking but should be addressed for completeness.

---

## Codex Review

*未执行：`codex` CLI 在当前环境中不可用（`--all` 已尝试）。可在安装 [OpenAI Codex CLI](https://github.com/openai/codex) 后重新运行 `/gsd/review --phase 1 --codex` 补全本节。*

---

## CodeRabbit Review

*未执行：`coderabbit` CLI 在当前环境中不可用。*

---

## OpenCode Review

> build · MiniMax-M2.5

# Plan Review: Phase 1 (01-01-PLAN.md & 01-02-PLAN.md)

## Summary

Both plans together form a coherent Phase 1 implementation for IBKR data sufficiency domain modeling. Plan 01 establishes typed contracts + IBKR schedule adapter (reusing existing `trading_hours.py`), while Plan 02 adds deterministic sufficiency classification + structured logging + orchestration. The plans correctly separate concerns and defer execution blocking to Phase 2.

---

## Plan 01-01-PLAN.md (Typed Contract + Adapter)

### Strengths

1. **Proper reuse of existing `trading_hours.py`** — Adapter correctly imports only public symbols (`parse_liquid_hours`, `is_rth_check`) rather than replacing them, per D-09–D-11.
2. **Comprehensive test coverage** — 10 explicit test scenarios covering unknown schedule, cross-day, cross-timezone, fuse transitions.
3. **Fail-safe design** — Schedule failure explicitly surfaced via `schedule_failure_reason` + `timezone_resolution`, ensuring downstream guards can fail-closed.
4. **Timeframe→seconds contract** — `effective_lookback` as float seconds is correctly specified; `TIMEFRAME_SECONDS_MAP` referenced.

### Concerns

1. **`TIMEFRAME_SECONDS_MAP` not explicitly created** — Task 1 action mentions it should be documented but doesn't show an explicit step to create it. (Severity: **MEDIUM** — Risk of inconsistency if different modules define it differently.)
2. **`FreshnessMetadata` referenced but not defined** — Task 1 mentions "optional FreshnessMetadata (or equivalent)" for staleness but Plan 01 doesn't include its definition — this is deferred to Plan 02 action but creates ambiguity. (Severity: **MEDIUM** — Plan 02 depends on a type it doesn't create.)
3. **Test naming governance slightly unclear** — Acceptance says exact `test_*` names but allows renaming "for clarity" — could lead to acceptance criteria drift. (Severity: **LOW** — Minor process risk.)

### Suggestions

- Add explicit step in Plan 01 Task 1 to create `TIMEFRAME_SECONDS_MAP` in `data_sufficiency_types.py` with documented keys.
- Clarify where `FreshnessMetadata` is defined (either in Plan 01 or make Plan 02 action explicitly create it).

---

## Plan 01-02-PLAN.md (Validator + Logging + Orchestration)

### Strengths

1. **Pure validator design** — Correctly isolates side effects; validator imports no `logging`, no `kline_fetcher`, per review_carryover.
2. **Deterministic precedence** — Explicit order: `unknown_schedule` → `stale_prev_close` → `market_closed_gap` → `missing_bars` → `sufficient`. Matches requirements.
3. **Structured logging contract** — `ibkr_data_sufficiency_check` emitted with stable fields; raw broker payloads explicitly excluded.
4. **Orchestration separation** — Service calls validator (pure) → logging (side effect), maintaining testability.

### Concerns

1. **`FreshnessMetadata` dependency unresolved** — Task 1 references `FreshnessMetadata` for staleness but Plan 02 doesn't create it either. (Severity: **HIGH** — Blocks the `test_stale_prev_close` scenario.)
2. **`get_kline` exception handling needs verification** — Review carryover says "document and implement one behavior" but task action doesn't show explicit docstring. (Severity: **MEDIUM** — Could mask insufficient data as zero bars.)
3. **Aggregation mock documentation** — Review carryover requires docstring about `LOWER_LEVELS` assumptions — verified in test but critical for Phase 2 drift detection. (Severity: **LOW** — Already addressed.)
4. **Float epsilon comparison** — Task action mentions epsilon but acceptance criteria doesn't verify it exists in tests. (Severity: **LOW** — Tests likely implement it.)

### Suggestions

- Add explicit `FreshnessMetadata` dataclass creation to Plan 02 Task 1 action.
- Add explicit docstring in `compute_available_bars_from_kline_fetcher` about exception propagation behavior.

---

## Risk Assessment

| Area | Level | Justification |
|------|-------|---------------|
| Dependency gap (`FreshnessMetadata`) | **HIGH** | Referenced in both plans but created in neither; blocks `test_stale_prev_close` scenario |
| Test execution ordering | **MEDIUM** | Plan 01 must pass before Plan 02 tests can meaningfully run |
| Scope creep | **LOW** | Plans correctly defer execution blocking to Phase 2 |
| Security (raw broker data leak) | **LOW** | Both plans explicitly exclude raw `liquidHours` from logs |
| Integration test realism | **LOW** | Mocked `get_kline` acknowledged in review_carryover |

**Overall Risk: MEDIUM**

Primary blocker: The `FreshnessMetadata` type used for stale-previous-close detection is referenced but not defined in either plan. This must be resolved before Plan 02 implementation can complete the `test_stale_prev_close` scenario.

---

## Key Recommendations

1. **Add `FreshnessMetadata` creation** to Plan 02 Task 1 action with fields:
   ```python
   @dataclass
   class FreshnessMetadata:
       prev_close_timestamp_utc: datetime | None
       prev_close_age_seconds: float | None  # Optional staleness threshold
   ```

2. **Create `TIMEFRAME_SECONDS_MAP`** explicitly in `data_sufficiency_types.py`:
   ```python
   TIMEFRAME_SECONDS_MAP = {
       "1m": 60.0,
       "5m": 300.0,
       "1H": 3600.0,
       "4H": 14400.0,
       "1D": 86400.0,
   }
   ```

3. **Add missing acceptance criteria**: `test_types_import_smoke` should verify imports don't fail (already in plan but ensure it runs).

4. **Verify the complete test pipeline**: Run combined Phase 1 suite before Plan 02 work begins:
   ```bash
   python3 -m pytest backend_api_python/tests/test_data_sufficiency_types.py backend_api_python/tests/test_ibkr_schedule_provider.py backend_api_python/tests/test_trading_hours.py -q
   ```

---

## Consensus Summary

本次 `--all` 实际成功调用的外部 CLI 为 **Gemini、Claude Code（`claude -p`）、OpenCode**；**Codex** 与 **CodeRabbit** 未安装故跳过。

### Agreed Strengths（2+ 评审一致）

- **阶段边界清晰**：Plan 01 定契约与 IBKR 日程适配器，Plan 02 做纯分类、结构化日志与编排，明确不把 open/add 拦截放进 Phase 1。
- **架构分层合理**：适配器复用 `trading_hours` 公共接口；校验器保持纯函数、副作用集中在 orchestration / logging。
- **可测试性强**：用例矩阵细（含 precedence、fuse、跨日、跨时区等），并与 R1/N3 等需求对齐。
- **可观测性与安全面**：结构化事件、避免原始 `liquidHours` 进入日志契约，多份评审均认可。

### Agreed Concerns（优先处理）

1. **Mock 与真实 `get_kline` 漂移（MEDIUM）** — Gemini 明确；OpenCode 归为低风险但同属「Phase 1 单测不足以证明生产路径」类问题；与 ROADMAP Phase 2 carryover（真实路径对齐）一致。
2. **`stale_prev_close` 阈值策略留白（LOW–MEDIUM）** — Phase 3 政策前，Phase 1 需文档化占位语义与边界测试是否足够；Claude 指出 1s 占位阈值与缺少边界测例的风险。
3. **全局 fuse / `con_id` 副作用（LOW）** — Gemini：`is_rth_check` 经 `con_id` 共享 fuse 状态可能影响多策略并发语义，需在 Phase 2+ 运维或设计上心里有数。

### 与仓库事实的校准（共识段落补充）

- **Claude 所称「`market_category` 传错位置」HIGH 问题**：在当前实现中，首参即 `get_kline` 语义上的 **market**（如 `USStock`），与 `compute_available_bars_from_kline_fetcher(market, symbol, timeframe, ...)` 形参顺序一致；**更稳妥的改进**仍是使用关键字参数 `market=market_category` 提高可读性，但不宜再标为「参数错位导致 TypeError」类缺陷，除非评审明确对照了签名与调用。
- **OpenCode 所称「计划中未定义 `FreshnessMetadata`」**：作为**仅针对 PLAN 文本**的批评部分成立（可写得更显式）；若对照已实现代码，类型已在 `data_sufficiency_types` 与 Plan 02 `review_carryover` 中覆盖，则「阻塞实现」的结论应降级为「计划文档应点名落文件与验收」。

### Divergent Views

- **总体风险档位**：Gemini 评 **LOW**；Claude / OpenCode 评 **MEDIUM**（Claude 部分建立在对服务调用的误判上；OpenCode 部分建立在对计划文本与实现状态混淆上）。
- **Claude stdin 警告**：其输出可能混合「读到的仓库」与「本提示中的计划」，与 Gemini / OpenCode（主要按计划文本）不完全同质；后续重跑建议对 `claude` 使用文件重定向或官方支持的「从文件读入完整 prompt」方式，避免 3s stdin 超时。

---

## 后续

将本文件反馈进规划迭代：

```text
/gsd-plan-phase 1 --reviews
```

清理临时文件：

```bash
rm -f /tmp/gsd-review-prompt-1.md /tmp/gsd-review-gemini-1.md /tmp/gsd-review-claude-1.md /tmp/gsd-review-opencode-1.md /tmp/gsd-review-opencode-1-clean.md
```
