---
phase: 01
reviewers: [gemini, claude, opencode]
reviewed_at: 2026-04-17T00:00:00Z
plans_reviewed:
  - 01-01-PLAN.md
  - 01-02-PLAN.md
  - 01-VALIDATION.md
---

# Cross-AI Plan Review — Phase 01（RE-REVIEW）

> **说明：** 这是对 **已修订** 的 `01-01-PLAN.md` / `01-02-PLAN.md`（以及作为验收基线的 `01-VALIDATION.md`）的第二轮交叉评审输出。
>
> **CLI 可用性：** 本轮实际调用了 `gemini`、`claude`、`opencode`。环境中 **`codex` CLI 不可用**（因此 `--all` 无法包含 Codex）。

## Consensus Summary（本轮）

- **总体结论：** 三条评审一致认为 Phase 1 的拆分（类型/适配器 vs 纯校验器 + 结构化日志 + orchestration）是 **一致且可测试** 的，并且 **Phase 2/3 的职责没有明显回渗**（尤其是 `signal_executor.py` 不改动、Phase 1 只做分类与可观测性）。
- **相比上一轮 review 的“收敛点”：** 纯校验器（无 logging）、单点发射 orchestration、禁止 `trading_hours` 私有导入、秒级 `effective_lookback` / `missing_window`、以及更硬的验收/静态字符串检查，普遍被认为 **显著降低了架构腐化与不可测试性风险**。
- **仍残留的主要分歧/风险（需要执行期盯紧）：**
  - **`compute_available_bars_from_kline_fetcher` 与真实 `kline_fetcher.get_kline` 行为对齐**：Gemini 评为 **LOW**；Claude 评为 **MEDIUM**（建议在 Plan02 的集成路径用更“像生产”的 mock/或后续 Phase2 用真实路径补齐）；OpenCode 评为 **HIGH→整体 MEDIUM**（核心担忧是“mock 边界能过单测，但抓不到集成漂移”）。
  - **验收里“函数名必须完全匹配”的刚性**：Claude 指出可能造成 **流程摩擦**（建议计划前言补充“改名不减覆盖即可”的原则）；OpenCode/Gemini 未强烈反对，但这是一个 **工程治理** 层面的注意点。
  - **时间框→秒映射表/舍入策略、以及 `timezone_fallback` 与 `schedule_status` 的组合语义**：OpenCode 提出需要 **更明确的版本化常量/文档**；Claude 也建议补一个 **`next_session_open_utc` 的独立用例**（不只在 fuse 过渡里间接覆盖）。
- **综合风险评级（人工汇总，非简单平均）：** **LOW～MEDIUM**。设计边界与测试策略整体成熟；最大不确定性集中在 **kline 计数语义与生产路径一致性**，建议在实现/Phase2 交接时作为显式跟踪项。

---

## Gemini Review（原文）

# Phase 1 Plan Review: IBKR Schedule + Sufficiency Domain Model

This review covers the **updated** implementation plans (`01-01-PLAN.md` and `01-02-PLAN.md`) for Phase 1. The plans have been revised to incorporate feedback regarding component boundaries, typed contracts, and strict avoidance of private API coupling.

## 1. Summary
The decomposition of Phase 1 into a typed contract wave followed by a pure validation and orchestration wave is highly coherent and follows senior engineering standards. By separating the **Schedule Adapter** (facts about the market) from the **Sufficiency Validator** (pure logic comparing requirements to facts), the system gains high testability and prevents the "logic leak" often seen in broker integrations. The inclusion of a dedicated **Orchestration Service** to handle logging ensures the validator remains a pure function, which is critical for deterministic risk-gating. The plans are low-risk and strictly adhere to the milestone's "fail-safe" and "observability" requirements.

## 2. Strengths
*   **Strict Boundary Enforcement:** The "no private imports" constraint for `trading_hours.py` (verified via static string checks in tests) prevents brittle coupling to the existing fuse logic.
*   **Pure Logic Validator:** Using dependency injection (`get_kline_callable`) for the bar-counting helper ensures the validator can be exhaustively unit-tested without DB or network side effects.
*   **Deterministic Precedence:** Task 1 in Plan 02 explicitly defines the precedence order for reason codes (e.g., `unknown_schedule` before `missing_bars`), which is vital for consistent user alerting in Phase 3.
*   **Seconds-Based Semantics:** Normalizing `effective_lookback` and `missing_window` to `float` (seconds) provides an unambiguous metric that simplifies downstream diagnostic logic and alert generation.
*   **Fail-Safe Observability:** Capturing `timezone_resolution` (explicit vs fallback) and `schedule_failure_reason` ensures that when a "fail-closed" block occurs, the logs provide immediate root-cause evidence.

## 3. Concerns
*   **Kline Aggregation Drift (LOW):** While the plan instructs the validator to mirror `LOWER_LEVELS` aggregation intent, there is a minor risk of drift if `kline_fetcher.py` logic changes in the future. 
    *   *Mitigation:* The plan uses a mocked `get_kline` return in tests to verify the counting logic, ensuring the validator's interpretation of "available bars" is at least internally consistent.
*   **`missing_window` during Market Gaps (LOW):** If a market is closed for a weekend, the `missing_window` in seconds might be large, even if only a few bars are actually missing. 
    *   *Mitigation:* This is acceptable for Phase 1; the goal is to report the data shortfall in a standard unit (seconds). The `reason_code` (`market_closed_gap`) provides the necessary context.

## 4. Suggestions
*   **Diagnostics Boundedness:** In `DataSufficiencyDiagnostics`, consider explicitly including the `con_id` used for the check to facilitate easier correlation between sufficiency logs and the underlying `trading_hours` fuse state.
*   **Timezone Fallback Warning:** Ensure the `fallback_utc` resolution metadata triggers a `logger.warning` in the orchestration layer (or the adapter) to alert operators that a symbol's timezone mapping might be missing from `_TZ_MAP`.

## 5. Risk Assessment: LOW
The plan is exceptionally well-structured. It avoids "God object" patterns by splitting types, adapters, and validators. The risk of regression is minimized by requiring the full backend test suite to remain green after each wave. The clear separation of concerns ensures that Phase 1 stays within its "domain modeling" boundary, leaving execution enforcement and complex alerting for the subsequent phases.

**Verdict: APPROVED.** The plans are ready for execution.

---

## Claude Review（原文）

# Cross-AI Plan Review: Phase 01 (Updated)

## Summary

Both plans are substantially improved over the prior review cycle. The decomposition into **types (Plan 01) → validator + logging + orchestration (Plan 02)** is coherent and maps cleanly to the phase boundary. The explicit no-private-imports constraint on the adapter, the pure-validator/no-logging constraint, and the single-emission orchestration invariant together form a defensible architecture. The main residual risks are moderate: (1) the aggregation helper could drift from real `kline_fetcher` lower-level aggregation semantics without integration-level verification, and (2) the very rigid exact-test-function-name acceptance criteria risk becoming a compliance burden rather than a quality signal. Both are manageable.

---

## Strengths

1. **Clean component separation** — Plan 01 owns types + adapter; Plan 02 owns pure classifier, logging helper, and orchestration service. The phase boundary (no `signal_executor` mutation) is explicit and tested.

2. **Fail-safe schedule ambiguity preserved** — The `schedule_unknown` vs `schedule_known_closed` distinction is now a first-class typed field (`IBKRScheduleStatus`), not collapsed into a bare boolean. The adapter explicitly surfaces `timezone_resolution="fallback_utc"` and `schedule_failure_reason="timezone_id_unresolved"` for malformed inputs.

3. **Pure validator constraint is enforced** — Plan 02 Task 1 explicitly forbids `logging` imports and the `ibkr_data_sufficiency_check` event name in the validator, keeping side effects in orchestration. The acceptance criteria check this with static string checks.

4. **Deterministic precedence is explicit** — `unknown_schedule > stale_prev_close > market_closed_gap > missing_bars > sufficient` ordering prevents ambiguity in downstream guard branching.

5. **Aggregation helper correctly scoped** — `compute_available_bars_from_kline_fetcher` is described as calling `get_kline` and counting bars (not reimplementing `_aggregate_bars`), which avoids forking `kline_fetcher` internals.

6. **Single-emission invariant** — Plan 02 Task 3 requires integration tests to assert exactly-one `emit_ibkr_data_sufficiency_check` call per evaluation path.

7. **No private API coupling** — The adapter explicitly cannot import `trading_hours._*` names, forcing it to compute next-session information from public `parse_liquid_hours` outputs.

8. **Static string acceptance criteria are comprehensive for type existence** — Checking for exact class names, exact enum values, and forbidden substrings gives downstream code strong guarantees about the contract surface.

---

## Concerns

### MEDIUM: Aggregation helper drift from real `kline_fetcher` behavior

**Location:** Plan 02, Task 1 — `compute_available_bars_from_kline_fetcher`

The plan correctly says the helper must not reimplement `_aggregate_bars`. However, `kline_fetcher.py` has complex aggregation logic: it prefers 1m→5m fallback, range-hit semantics with `MAX_GAP` tolerance, and stale-tail refresh logic (see lines 513–539). The mocked-`get_kline` test (`test_aggregation_1h_from_5m_mocked_get_kline`) only verifies that a known-mocked series returns a deterministic bar count — it does not verify that the helper's bar-counting semantics match what `kline_fetcher.get_kline` would actually return for a given `(market, symbol, timeframe, limit)` call in production.

**Risk:** Later integration tests (Phase 2 guard injection) may find that the helper undercounts or overcounts vs real `get_kline` behavior, causing false insufficient/false sufficient classifications.

**Mitigation needed:** The integration test in Plan 02 Task 3 (`test_adapter_to_service_emits_ibkr_data_sufficiency_check`) should use a realistic mock of `get_kline` that mimics `LOWER_LEVELS` aggregation more faithfully, not just a flat list of bars. Alternatively, add a note that Phase 2 must add an integration test with a real `get_kline` call (or a more complete mock) to catch drift.

### MEDIUM: Over-rigid acceptance criteria may cause unnecessary churn

**Location:** Both plans — acceptance criteria specifying exact test function names

Examples:
- `test_unknown_schedule():`, `test_market_closed_gap():`, `test_cross_day_session():` (Plan 01 Task 2)
- `test_available_bars_equals_required_bars():`, `test_stale_prev_close():` (Plan 02 Task 1)

If during implementation a developer wants to split `test_unknown_schedule` into two focused cases (e.g., `test_unknown_schedule_empty_liquid_hours` + `test_unknown_schedule_garbage_segment`), the plan would require a formal amendment before the criteria can be satisfied. This is appropriate for a contract — but the acceptance criteria should distinguish **renaming for clarity** (acceptable) from **removing coverage** (not acceptable).

**Suggestion:** Add a principle to both plans: "Acceptance criteria target substantive coverage. Renaming a test function without changing the scenario under test does not invalidate the criterion, provided the new name appears in the diff."

### LOW: `effective_lookback` and `missing_window` semantics not exercisable until Plan 02

**Location:** Plan 01 Task 1 — types define these fields but no code populates them until Plan 02

`DataSufficiencyResult.effective_lookback` and `DataSufficiencyResult.missing_window` are declared in Plan 01 types but only computed in Plan 02's `data_sufficiency_validator`. The Plan 01 type tests can verify the fields exist but cannot verify correct values. This is expected (Phase 1 is domain modeling, not classification logic), but it means a whole class of bugs (wrong seconds computation, wrong field copying) won't be caught until Plan 02 — which is also when the phase regression gate runs.

**No action needed** — this is correct phase sequencing. Just note that Plan 02's test suite should explicitly assert `effective_lookback` and `missing_window` values in its boundary and missing-bars cases.

### LOW: `IBKRScheduleSnapshot.next_session_open_utc` computation not verified in isolation

**Location:** Plan 01 Task 2 — adapter computes next session but no standalone test isolates this

The adapter must compute `next_session_open_utc` from `parse_liquid_hours` outputs. The plan includes `test_fuse_transition_open_after_expiry` which exercises fuse boundary behavior, but there's no standalone test that directly asserts `next_session_open_utc` correctness for a known session schedule (e.g., HK morning/afternoon sessions, Forex Sunday 17:15 open).

**Suggestion:** Add `test_next_session_open_utc_populated()` to `test_ibkr_schedule_provider.py` with a simple known schedule where next open is unambiguous (e.g., single-session US equity, next open is next calendar day 09:30 ET).

### LOW: `timezone_resolution` and `schedule_failure_reason` values not locked as typed constants

**Location:** Plan 01 Task 1 — types define fields but not the string values

`timezone_resolution` uses literals `"explicit"` and `"fallback_utc"`, and `schedule_failure_reason` uses `"timezone_id_unresolved"` — these appear in the action text but are not declared as typed constants or validated in the type tests. If a future refactor changes these string values, type-level tests would still pass.

**No action needed for Phase 1** — this is a hardening item for a later phase. The threat model already flags T-01-02 (enum values drift).

---

## Suggestions

1. **Add a note to Plan 02 Task 1**: The aggregation mock in `test_aggregation_1h_from_5m_mocked_get_kline` should document what it assumes about `LOWER_LEVELS` behavior, so future readers understand the gap between the mocked helper and real `kline_fetcher`.

2. **Add `test_next_session_open_utc_populated()`** to Plan 01 adapter tests — directly verify next-session computation for a known unambiguous schedule.

3. **Distinguish test-function-name refactoring as acceptable** in the plan preamble — avoid forcing formal amendment for renames that don't reduce coverage.

4. **Consider adding a `test_missing_window_zero_when_sufficient()`** in Plan 02 validator tests to explicitly exercise the `missing_window == 0.0` when sufficient rule, since this is a D-07 requirement.

5. **Flag `prev_close_stale_since` semantics for Plan 02** — the `stale_prev_close` reason code implies a freshness check, but no plan yet specifies where the stale-check threshold comes from. This is probably deferred to Phase 3 (alerting) but should be noted as an open question.

---

## Risk Assessment

**Overall: LOW**

- Phase 1 decomposition is sound and phase boundaries are respected.
- Adapter has no private API coupling, no execution-path mutation, and explicit fail-safe semantics.
- Pure validator has no logging side effects and deterministic precedence.
- Structured logging keeps raw broker payloads out of the event stream.
- Orchestration single-emission invariant is tested.

**Primary residual risk (MEDIUM)**: Aggregation helper drift from `kline_fetcher` semantics — mitigated by integration test in Plan 02 Task 3 but worth watching when Phase 2 (guard injection) exercises real data paths.

**Secondary risk (MEDIUM)**: Over-rigid exact-test-name criteria could cause unnecessary churn — addressable by adding a refactoring-disclaimer in the plan preamble.

---

## OpenCode Review（原文）

# Cross-AI Plan Review: Phase 1 (RE-REVIEW)

## Summary

This is a **re-review** of updated Phase 1 plans for the IBKR data-sufficiency domain model. The plans decompose the work into: (1) typed contract + IBKR schedule adapter, and (2) pure validator + structured logging + orchestration service. The decomposition appears well-constrained by the locked decisions (D-01 through D-11) and addresses the prior review's concerns about keeping Phase 1 focused on classification only, not execution blocking. The key risk is whether the `compute_available_bars_from_kline_fetcher` helper can stay aligned with `kline_fetcher.py` without forking its internals—a risk partially mitigated by mocking at the `get_kline` boundary.

---

## Plan 01-01 (Typed Contract + IBKR Schedule Adapter)

### Strengths

1. **Explicit separation of concerns**: Plan 01 correctly isolates contract definition (types) from the schedule adapter, honoring D-09 (peer components) and D-11 (reuse not replace `trading_hours`).

2. **Stable top-level fields**: `DataSufficiencyResult` includes required top-level fields per D-02, with `effective_lookback` and `missing_window` expressed in seconds—unambiguous per D-07.

3. **Fail-safe schedule handling**: The adapter explicitly distinguishes `schedule_unknown` from `schedule_known_closed`, addressing D-04/D-05 and the prior review's concern about schedule ambiguity.

4. **Explicit test function names**: Acceptance criteria now enumerate exact test function names, making verification objective.

5. **Adapter constraints well-specified**: No private `_` imports, explicit `server_time_utc` parameter, timezone fallback metadata, and fuse transition tests—all addressing potential drift risks.

### Concerns

1. **MEDIUM**: The `effective_lookback_seconds` and `missing_window_seconds` mapping from `{timeframe, bars}` needs deterministic in-code documentation. The plan mentions "deterministic timeframe→seconds mapping documented in-code" but doesn't specify the lookup table. If multiple timeframes are supported, this could become a source of inconsistency.

2. **LOW**: The plan requires `effective_lookback` and `missing_window` as floats (seconds), but doesn't specify rounding behavior or precision expectations. Floating-point equality in tests may be fragile.

3. **LOW**: The `timezone_fallback_metadata` use case requires `schedule_failure_reason="timezone_id_unresolved"` but the plan also says "still returning a coherent `schedule_status` based on parsed sessions" even when timezone is invalid. The interaction between `timezone_fallback` and `schedule_status` needs clarity—can you have `schedule_known_open` with a fallback timezone?

### Suggestions

1. Add a `TIMEFRAME_SECONDS_MAP` constant in `data_sufficiency_types.py` or a dedicated helper with explicit mappings for supported timeframes (e.g., `"1m": 60, "5m": 300, "1H": 3600, "1D": 86400`). Document rounding policy (e.g., floor or round-to-nearest).

2. In acceptance criteria, add a tolerance for float comparison in tests (e.g., `abs(result.missing_window - expected) < 0.001`).

3. Clarify the semantic: if `timezone_id` is invalid and falls back to UTC, can sessions still be considered "known"? Consider adding a secondary field like `timezone_trusted: bool` to make this explicit.

---

## Plan 01-02 (Pure Validator + Logging + Orchestration)

### Strengths

1. **Clean decomposition**: Validator stays pure (no logging imports), logging helpers are separate, and orchestration owns side effects—matching the prior review's recommendation.

2. **Precedence explicit**: The plan specifies deterministic precedence order (`unknown_schedule` → `stale_prev_close` → `market_closed_gap` → `missing_bars` → `sufficient`), addressing the prior review's concern about ambiguous classification.

3. **Mocked kline aggregation**: The `compute_available_bars_from_kline_fetcher` helper uses mocked `get_kline` return values, not forking `kline_fetcher` internals—correct per the research findings.

4. **Single-emission invariant**: Integration tests assert `emit_ibkr_data_sufficiency_check` is called exactly once per evaluation, addressing T-01-07.

5. **No Phase 2/3 leakage**: The plan explicitly keeps `signal_executor.py` untouched and avoids execution-path blocking—correct for Phase 1 scope.

### Concerns

1. **HIGH**: The `compute_available_bars_from_kline_fetcher` helper could drift from real `kline_fetcher.py` behavior if `kline_fetcher` evolves (e.g., adding new aggregation logic, changing `LOWER_LEVELS`, or modifying `MAX_GAP` handling). The plan mitigates this by mocking at the `get_kline` callable boundary, but there's no integration test that verifies the helper's behavior matches actual `kline_fetcher` outputs. Consider adding a smoke test that uses a real (or realistic mock) `kline_fetcher.get_kline` to catch drift.

2. **MEDIUM**: The plan doesn't specify how to handle the case where `get_kline` returns fewer bars than `required_bars` due to data gaps vs. genuinely missing data. The helper may need to distinguish "available bars from storage" from "coverage window completeness"—this distinction matters for `missing_window` calculation.

3. **LOW**: The `stale_prev_close` reason code requires "freshness metadata" as input, but the plan doesn't define the schema for that metadata. If callers don't provide it, what's the default behavior? This could lead to inconsistent classification.

4. **LOW**: The plan requires the validator to NOT import logging, but doesn't forbid importing other modules that might have side effects (e.g., database connections). The "pure" requirement should be more explicit about what constitutes impurity.

### Suggestions

1. Add a dedicated integration test that uses a realistic `get_kline` mock (matching `kline_fetcher.py`'s return shape) to verify the helper's bar-counting logic aligns with actual behavior.

2. Define an optional `FreshnessMetadata` input type with fields like `prev_close_timestamp: datetime | None`, `prev_close_age_seconds: float | None`, and document the default behavior when not provided.

3. Add explicit purity checks: validator must not import any module that performs I/O (database, network, filesystem). Consider adding a test that asserts `data_sufficiency_validator` has no transitive dependency on `logging`, `kline_fetcher`, or similar.

4. Document the helper's fallback behavior: if `get_kline` raises an exception, should the helper return 0 bars, raise, or use a sentinel value?

---

## Overall Risk Assessment

**Risk Level: MEDIUM**

**Justification:**

- **Phase boundary integrity**: Both plans correctly restrict Phase 1 to classification + observability, not execution blocking or alert dispatch. This is a significant improvement over prior designs that leaked Phase 2 responsibilities.

- **Type safety**: `DataSufficiencyResult` and `IBKRScheduleSnapshot` provide stable top-level fields per D-01/D-02, and the explicit test function names in acceptance criteria make verification objective.

- **Main risk**: The `compute_available_bars_from_kline_fetcher` helper could diverge from `kline_fetcher.py` behavior over time. The mocking strategy mitigates this for unit tests but doesn't catch integration drift.

- **Secondary risk**: The `effective_lookback` and `missing_window` mapping from timeframe+bars to seconds needs explicit, version-controlled lookup logic to avoid ambiguity.

---

## Overall Assessment

**Summary**: The updated plans represent a solid Phase 1 implementation that honors all locked decisions (D-01 through D-11) and addresses prior review feedback about keeping Phase 1 focused on classification, not enforcement. The decomposition into types/adapter (Plan 01) and validator/logging/orchestration (Plan 02) is coherent. Key risks are manageable: (1) kline-fetcher alignment via mocked boundary, (2) timeframe→seconds mapping via explicit lookup, (3) schedule status semantics via explicit fallback metadata.

**Acceptable for execution**: Yes, with the suggested additions to reduce drift risk and clarify edge cases.
