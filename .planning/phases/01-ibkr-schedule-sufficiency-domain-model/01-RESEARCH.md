# Phase 1: IBKR schedule + sufficiency domain model - Research

**Researched:** 2026-04-16 `[VERIFIED: local filesystem + local environment]`  
**Domain:** IBKR trading-session-aware data sufficiency domain model for Python backend `[VERIFIED: .planning/ROADMAP.md]`  
**Confidence:** HIGH `[VERIFIED: codebase inspection + official docs + local test run]`

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** `DataSufficiencyResult` uses a strong-typed schema rather than a minimal dynamic payload. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- **D-02:** The schema must include stable top-level fields for downstream guard/alert consumers (not only nested diagnostics payloads). `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- **D-03:** `reason_code` uses fine-grained taxonomy (not coarse buckets). `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- **D-04:** Schedule fetch/parse failure is fail-safe: open/add should be considered blocked by downstream guard; close/reduce remains allowed in later phases. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- **D-05:** Phase 1 output should carry explicit schedule-failure reason for downstream decisions. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- **D-06:** Strategy-side contract remains bars-first: strategy declares required `timeframe + bars`. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- **D-07:** Sufficiency threshold uses hard rule (`available_bars < required_bars` => insufficient), no tolerance window in this milestone. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- **D-08:** Session/trading-day interpretation is framework responsibility (not strategy responsibility). `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- **D-09:** `trading_hours` and `df_validator` (data sufficiency validator) are peer components, not merged into one module. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- **D-10:** A shared utility layer may be extracted for common concerns (time/session normalization, cache/fuse helpers, schedule normalization primitives). `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- **D-11:** For this phase, prefer wrapping/reusing existing `trading_hours` behavior behind adapter-facing interfaces rather than replacing it immediately. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`

### Claude's Discretion
- Naming selection between `df_filter` vs `df_validator` vs `data_sufficiency_validator`. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- Exact typed field names in `DataSufficiencyResult` as long as D-01/D-02/D-05 are preserved. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- Utility module layout for shared helpers. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`

### Deferred Ideas (OUT OF SCOPE)
- Full replacement of `trading_hours` with a new implementation can be evaluated after guard/alert pipeline is stable. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- Optional future support for tolerance-based thresholds is deferred; this milestone locks hard-threshold policy. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
</user_constraints>

## Project Constraints (from CLAUDE.md)

- No project-local `CLAUDE.md` exists in the repo root, so no additional repo-specific directives were discovered beyond workspace/global instructions. `[VERIFIED: repo root glob for CLAUDE.md returned no matches]`
- No project-local `.claude/skills/` or `.agents/skills/` directory exists, so there are no repo-specific skill conventions to honor in this phase. `[VERIFIED: repo root glob for .claude/skills/*/SKILL.md and .agents/skills/*/SKILL.md returned no matches]`

## Summary

Phase 1 should be planned as a pure domain/modeling phase that introduces a typed sufficiency contract, a broker-facing IBKR schedule adapter, and a deterministic evaluator that converts `{required timeframe + bars}` plus cached/available K-line coverage into stable reason-coded outcomes. The existing codebase already separates broker-fetching from pure session logic in `trading_hours.py`, and it already centralizes K-line coverage/range behavior in `kline_fetcher.py`; the plan should preserve those boundaries rather than invent a new session engine. `[VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py] [VERIFIED: backend_api_python/app/services/kline_fetcher.py]`

The highest-value planning decision is to make Phase 1 produce a canonical, serializable `DataSufficiencyResult` that later phases can consume without re-deriving any broker/session facts. That result should carry stable top-level booleans/codes plus machine-readable diagnostics like `required_bars`, `available_bars`, `effective_lookback`, `missing_window`, `schedule_status`, and symbol/timeframe/session metadata. This matches the locked decisions, the functional output contract in `R1`, and the observability requirement in `N3`. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md] [VERIFIED: .planning/REQUIREMENTS.md]`

The main implementation risk is not parsing IBKR hours itself; that part already exists and has passing unit coverage. The real risk is planning an evaluator that accidentally re-implements `kline_fetcher` semantics, mixes open/add blocking policy into Phase 1, or emits free-form reasons that later guards/alerts cannot rely on. The plan should therefore keep Phase 1 focused on deterministic classification plus structured logging and unit test-case specifications for each reason-code edge case. `[VERIFIED: backend_api_python/tests/test_trading_hours.py] [VERIFIED: .planning/ROADMAP.md] [VERIFIED: user prompt]`

**Primary recommendation:** Reuse `trading_hours.py` as the schedule truth source behind a new adapter interface, keep sufficiency evaluation as a separate pure validator module, and standardize all outputs around a typed `DataSufficiencyResult` with stable fine-grained `reason_code` values. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md] [VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py]`

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | `3.11.14` `[VERIFIED: local environment]` | Runtime for backend services and tests `[VERIFIED: local environment]` | Already installed and used by current repo commands/tests `[VERIFIED: local environment]` |
| `ib_insync` | `0.9.86 installed`, requirement `>=0.9.86` `[VERIFIED: local environment] [VERIFIED: backend_api_python/requirements.txt]` | Source of IBKR `ContractDetails.timeZoneId` and `liquidHours` data shape `[CITED: https://ib-insync.readthedocs.io/_modules/ib_insync/contract.html]` | Matches the current codebase’s IBKR integration and official `ContractDetails` model `[VERIFIED: backend_api_python/requirements.txt] [CITED: https://ib-insync.readthedocs.io/_modules/ib_insync/contract.html]` |
| `pytz` | `2025.2` `[VERIFIED: local environment]` | Current timezone normalization primitive in `trading_hours.py` `[VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py]` | Already used in production code and tests, so Phase 1 should not introduce a second timezone abstraction `[VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py] [VERIFIED: backend_api_python/tests/test_trading_hours.py]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | `9.0.2` `[VERIFIED: local environment]` | Unit-test framework for domain-model and edge-case testing `[VERIFIED: local environment]` | Use for reason-code mapping, boundary conditions, and adapter failure-path tests `[VERIFIED: .planning/ROADMAP.md] [VERIFIED: .planning/REQUIREMENTS.md]` |
| `unittest.mock` / `MagicMock` | stdlib `[VERIFIED: Python 3.11 stdlib]` | Mock broker details, DB/data fetch seams, and logger sinks `[VERIFIED: backend_api_python/tests/test_trading_hours.py] [VERIFIED: backend_api_python/tests/test_signal_executor.py]` | Use when testing pure evaluator logic without hitting IBKR or storage layers `[VERIFIED: backend_api_python/tests/test_trading_hours.py]` |
| Python `logging` | stdlib `[VERIFIED: Python 3.11 stdlib]` | Structured contextual logging via `extra` / `LoggerAdapter` `[CITED: https://docs.python.org/3.11/library/logging.html]` | Use for `ibkr_data_sufficiency_check` decision logs and later event fan-out correlation `[VERIFIED: .planning/REQUIREMENTS.md] [CITED: https://docs.python.org/3.11/library/logging.html]` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Reusing current `trading_hours.py` adapter boundary `[VERIFIED: codebase]` | Rebuild session parsing around `ContractDetails.liquidSessions()` `[CITED: https://ib-insync.readthedocs.io/_modules/ib_insync/contract.html]` | Official parser exists, but current repo already has timezone mapping, fail-closed behavior, and fuse semantics with tests, so replacement is higher-risk and explicitly deferred. `[VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py] [VERIFIED: backend_api_python/tests/test_trading_hours.py] [VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]` |
| Free-form dict payload `[VERIFIED: CONTEXT.md prohibits it]` | Pydantic/dataclass schema `[ASSUMED]` | Either typed approach can work, but the locked requirement is “strong-typed schema”; exact implementation type remains planner discretion unless existing project conventions dictate one. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]` |

**Installation:** No new package is required for Phase 1 if implementation stays within the existing backend stack. `[VERIFIED: backend_api_python/requirements.txt] [VERIFIED: current codebase modules already exist]`

## Architecture Patterns

### Recommended Project Structure

```text
backend_api_python/app/services/
├── live_trading/ibkr_trading/
│   ├── trading_hours.py              # existing IBKR session truth source
│   └── [new]_schedule_provider.py    # adapter around current schedule/session behavior
├── [new]_data_sufficiency_validator.py   # pure sufficiency evaluator
├── [new]_data_sufficiency_types.py       # typed result contract / reason-code enum
└── [new]_data_sufficiency_logging.py     # optional helper if log payload assembly becomes noisy
```

This structure preserves the existing “broker-facing adapter + pure service logic” split already used by `trading_hours.py` and `signal_executor.py`. `[VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py] [VERIFIED: backend_api_python/app/services/signal_executor.py]`

### Pattern 1: Broker Adapter Over Existing Session Logic

**What:** Add a thin `IBKRTradingSessionProvider` abstraction that fetches or accepts IBKR contract/session details, then delegates session normalization/parsing to existing `trading_hours` logic. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md] [VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py]`

**When to use:** Whenever sufficiency logic needs to answer “what counts as the current trading day/session for this IBKR symbol/timeframe?” without embedding broker-specific parsing into the validator. `[VERIFIED: .planning/REQUIREMENTS.md]`

**Example:**

```python
# Source: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py
def is_rth_check(contract_details, server_time_utc, con_id=0, symbol="?", now=None) -> bool:
    tz = _resolve_tz(contract_details.timeZoneId or "UTC")
    sessions = parse_liquid_hours(contract_details.liquidHours or "", tz)
    if not sessions:
        logger.error("No liquidHours sessions parsed for %s, fail-closed", symbol)
        return False
```

The planning implication is to expose richer schedule state than a bare boolean, but to source that state from this existing parsing boundary. `[VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py]`

### Pattern 2: Pure Sufficiency Evaluator Over Normalized Inputs

**What:** Keep the validator pure: it should accept normalized inputs such as `required_bars`, `available_bars`, `timeframe`, session/trading-day status, and coverage metadata, then return `DataSufficiencyResult` without performing IBKR API calls or DB writes. `[VERIFIED: D-09 peer-component decision] [VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py uses pure logic pattern]`

**When to use:** For all Phase 1 classification code and almost all unit tests. `[VERIFIED: .planning/ROADMAP.md]`

**Example:** Existing tests already treat `trading_hours` as pure logic with mocked contract details; Phase 1 should emulate this style for sufficiency cases. `[VERIFIED: backend_api_python/tests/test_trading_hours.py]`

### Pattern 3: Reuse K-line Coverage Semantics, Do Not Duplicate Fetch Policy

**What:** Normalize strategy lookback into a required time window, then measure available coverage using the same storage/fallback semantics already centralized in `kline_fetcher.py` (`qd_kline_ranges`, `MAX_GAP`, lower-timeframe aggregation, on-demand fetch fallback). `[VERIFIED: backend_api_python/app/services/kline_fetcher.py]`

**When to use:** When converting `{timeframe, bars}` into `effective_lookback`, `available_bars`, and `missing_window`. `[VERIFIED: .planning/REQUIREMENTS.md]`

**Example:**

```python
# Source: backend_api_python/app/services/kline_fetcher.py
LOWER_LEVELS = {
    "1D": ["4H", "1H", "5m", "1m"],
    "1H": ["5m", "1m"],
}

def _aggregate_bars(bars_1m, interval_sec):
    ...
```

The planning implication is that sufficiency should classify against already-supported aggregation/range semantics instead of assuming a naive one-bar-per-natural-interval model. `[VERIFIED: backend_api_python/app/services/kline_fetcher.py]`

### Anti-Patterns to Avoid

- **Do not merge validator and session provider into one module:** This directly contradicts locked decision `D-09`. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
- **Do not encode `reason_code` as log text or human prose:** Later guards/alerts require stable machine-consumable top-level fields. `[VERIFIED: D-02/D-03/D-05 in CONTEXT.md]`
- **Do not implement open/add blocking in Phase 1:** Phase 1 only defines deterministic classification; enforcement belongs to Phase 2. `[VERIFIED: .planning/ROADMAP.md]`
- **Do not replace `kline_fetcher` range/fallback logic with ad hoc bar counting:** Current repo already tracks coverage windows and lower-timeframe aggregation. `[VERIFIED: backend_api_python/app/services/kline_fetcher.py]`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IBKR session string parsing | New custom `liquidHours` parser from scratch | Existing `parse_liquid_hours()` and timezone helpers in `trading_hours.py` | Already tested across US/HK/Forex, lunch breaks, cross-day sessions, and fuse behavior. `[VERIFIED: backend_api_python/tests/test_trading_hours.py]` |
| IBKR session/day truth source | A second parallel “market hours” engine | Adapter over `trading_hours.is_rth_check()` plus extracted normalization helpers | Avoids divergence between current execution-time session logic and new sufficiency logic. `[VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py]` |
| Data coverage window logic | Manual calendar math for each timeframe | Existing K-line storage/range/aggregation semantics in `kline_fetcher.py` | Repo already models `MAX_GAP`, same-layer range hits, lower-level aggregation, and fallback fetch behavior. `[VERIFIED: backend_api_python/app/services/kline_fetcher.py]` |
| Structured logging plumbing | Custom logger framework | Python `logging` `extra` / `LoggerAdapter` | Official logging supports contextual attributes without changing the logger API. `[CITED: https://docs.python.org/3.11/library/logging.html]` |

**Key insight:** The hard part in this domain is not the raw parsing; it is keeping session truth, data-coverage truth, and downstream reason-code truth consistent across later guard and alert phases. Reusing current seams is lower risk than building “cleaner” replacements now. `[VERIFIED: codebase inspection] [VERIFIED: roadmap phase split]`

## Common Pitfalls

### Pitfall 1: Natural-Day Assumptions Leak Into Trading-Day Logic

**What goes wrong:** Planning counts missing bars using wall-clock days instead of IBKR session/trading-day boundaries. `[VERIFIED: R2 requires IBKR trading-day awareness]`  
**Why it happens:** A bars-first strategy contract is easy to misread as “just multiply timeframe by bars”. `[VERIFIED: D-06/D-08 in CONTEXT.md]`  
**How to avoid:** Normalize lookback in the framework using IBKR session/day context, not in the strategy. `[VERIFIED: D-08 in CONTEXT.md]`  
**Warning signs:** Code computes sufficiency from `now - bars * timeframe` without consulting schedule/provider output. `[VERIFIED: requirement-to-design analysis]`

### Pitfall 2: Schedule Failure Gets Flattened Into Generic False

**What goes wrong:** All failures become `sufficient=False` with no stable failure reason. `[VERIFIED: D-05 requires explicit schedule-failure reason]`  
**Why it happens:** Existing `is_rth_check()` returns `False` on parse failure, so a naive wrapper may lose the distinction between “closed” and “unknown schedule”. `[VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py]`  
**How to avoid:** The adapter should surface schedule status explicitly, such as `schedule_known`, `session_open`, and `schedule_failure_reason`, before the validator maps them to `reason_code`. `[VERIFIED: design synthesis from codebase + requirements]`  
**Warning signs:** Tests only assert boolean sufficiency and never assert `reason_code`. `[VERIFIED: roadmap exit criteria require reason-code tests]`

### Pitfall 3: Phase 1 Accidentally Implements Phase 2 Policy

**What goes wrong:** The validator starts deciding whether orders are blocked instead of only classifying sufficiency. `[VERIFIED: phase split in ROADMAP.md]`  
**Why it happens:** Requirement `R3` is nearby, but Phase 1 objective is domain model + adapter only. `[VERIFIED: .planning/ROADMAP.md]`  
**How to avoid:** Return deterministic result plus diagnostics now; consume it in execution path later. `[VERIFIED: .planning/ROADMAP.md]`  
**Warning signs:** Plan tasks mention `SignalExecutor` mutation or order-path conditionals in Phase 1. `[VERIFIED: phase boundary analysis]`

### Pitfall 4: Reason Codes Become Too Coarse for Alerting

**What goes wrong:** One generic code like `insufficient_data` makes alert text and later policy branching ambiguous. `[VERIFIED: D-03 fine-grained taxonomy]`  
**Why it happens:** Coarse codes seem simpler in Phase 1. `[VERIFIED: common design risk analysis]`  
**How to avoid:** Plan explicit cases at minimum for `missing_bars`, `unknown_schedule`, `market_closed_gap`, and `stale_prev_close` because those are already called out in requirements/discussion or adjacent code. `[VERIFIED: .planning/REQUIREMENTS.md] [VERIFIED: backend_api_python/app/strategies/runners/single_symbol_runner.py]`  
**Warning signs:** Diagnostics explain nuance but top-level `reason_code` does not. `[VERIFIED: D-02/D-03 in CONTEXT.md]`

## Code Examples

Verified patterns from current code and official sources:

### Existing Fail-Closed Session Parsing

```python
# Source: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py
tz = _resolve_tz(contract_details.timeZoneId or "UTC")
sessions = parse_liquid_hours(contract_details.liquidHours or "", tz)
if not sessions:
    logger.error("No liquidHours sessions parsed for %s, fail-closed", symbol)
    return False
```

This is the correct source seam for Phase 1 schedule truth. `[VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py]`

### Existing Stable Notification/Reason Naming Pattern

```python
# Source: backend_api_python/app/strategies/runners/single_symbol_runner.py
notifier.notify_signal(
    strategy_id=int(strategy_id),
    signal_type="risk_data_stale_prev_close",
    extra={"status": "warning", ...},
)
```

This shows the repo already benefits from stable machine-readable reason-like identifiers instead of free-form prose. `[VERIFIED: backend_api_python/app/strategies/runners/single_symbol_runner.py]`

### Official Structured Logging Context Pattern

```python
# Source: https://docs.python.org/3.11/library/logging.html
logger.info("sufficiency evaluated", extra={
    "event": "ibkr_data_sufficiency_check",
    "symbol": symbol,
    "timeframe": timeframe,
    "reason_code": reason_code,
})
```

Python logging officially supports `extra` to populate `LogRecord` attributes with user-defined fields. `[CITED: https://docs.python.org/3.11/library/logging.html]`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Natural-day or naive timeframe math `[ASSUMED]` | Broker-session-aware classification using IBKR `timeZoneId` + `liquidHours` `[CITED: https://ib-insync.readthedocs.io/_modules/ib_insync/contract.html]` | Current requirement baseline for this milestone `[VERIFIED: .planning/REQUIREMENTS.md]` | Planning must treat session/day semantics as first-class input, not a later enhancement. `[VERIFIED: R2]` |
| Message-only logs `[ASSUMED]` | Context-rich logs via `extra` / `LoggerAdapter` `[CITED: https://docs.python.org/3.11/library/logging.html]` | Supported in Python stdlib today `[CITED: https://docs.python.org/3.11/library/logging.html]` | Phase 1 can emit machine-parseable sufficiency decision logs without new infra. `[CITED: https://docs.python.org/3.11/library/logging.html]` |

**Deprecated/outdated:**
- Treating all `False` session outcomes as equivalent is outdated for this milestone because the roadmap and requirements require reason-coded deterministic outputs. `[VERIFIED: .planning/ROADMAP.md] [VERIFIED: .planning/REQUIREMENTS.md]`

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A `dataclass` or enum-backed typed schema is the likely best fit for `DataSufficiencyResult`, though the exact mechanism is still open. | Standard Stack | Low; planner can swap to another typed construct without changing phase goals. |
| A2 | The “old approach” in this repo or earlier design thinking was closer to natural-day / naive timeframe math. | State of the Art | Low; does not change the recommended implementation, only historical framing. |
| A3 | Message-only logs are the main legacy baseline being improved on. | State of the Art | Low; Phase 1 still benefits from structured fields either way. |

## Open Questions (RESOLVED)

1. **Resolved: `DataSufficiencyResult` must encode schedule state separately from sufficiency state.** `[VERIFIED: design synthesis from CONTEXT.md + plan review]`
   - Decision: keep a typed intermediate adapter result with explicit schedule fields such as `schedule_status`, `session_open`, and bounded failure metadata, then map that into the final `DataSufficiencyResult`. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-01-PLAN.md]`
   - Why: `is_rth_check()` currently collapses parse failure and “outside RTH” to `False`, but D-04/D-05 require explicit schedule-failure semantics for downstream fail-safe behavior. `[VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py] [VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md]`
   - Execution implication: Plan 01 owns the typed schedule adapter contract, and Plan 02 consumes `schedule_status` as a first-class input rather than inferring schedule truth from `reason_code + diagnostics`. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-01-PLAN.md] [VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-02-PLAN.md]`

2. **Resolved: lookback normalization should live behind a thin coverage/count seam, not directly inside `get_kline()` usage from the pure validator.** `[VERIFIED: design synthesis from RESEARCH + plan review]`
   - Decision: Phase 1 validator remains pure and consumes normalized `required_bars`, `available_bars`, `timeframe`, `schedule_status`, and optional freshness/coverage metadata; any retrieval or coverage aggregation seam should reuse `kline_fetcher.py` semantics without embedding direct fetch orchestration in the classifier. `[VERIFIED: backend_api_python/app/services/kline_fetcher.py] [VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-02-PLAN.md]`
   - Why: `kline_fetcher.py` already owns range, gap, lower-timeframe aggregation, and fallback semantics, so duplicating those rules inside the validator would create divergence and violate the planned component boundary. `[VERIFIED: backend_api_python/app/services/kline_fetcher.py] [VERIFIED: D-09/D-10 in CONTEXT.md]`
   - Execution implication: Plan 02 may define normalization helpers or a thin coverage provider abstraction, but must not make the core classifier depend on direct broker/data-fetch side effects. `[VERIFIED: .planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-02-PLAN.md]`

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Backend implementation and tests | ✓ `[VERIFIED: local environment]` | `3.11.14` `[VERIFIED: local environment]` | — |
| `pytest` | Unit tests for reason-code mapping and edge cases | ✓ `[VERIFIED: local environment]` | `9.0.2` `[VERIFIED: local environment]` | — |
| `pylint` | Repo review/tooling parity for Python work | ✓ `[VERIFIED: local environment]` | `4.0.4` `[VERIFIED: local environment]` | — |
| `pip` | Installing any missing Python deps if needed later | ✓ `[VERIFIED: local environment]` | `25.3` `[VERIFIED: local environment]` | — |
| `ib_insync` | IBKR contract/session model integration | ✓ `[VERIFIED: local environment]` | `0.9.86` `[VERIFIED: local environment]` | None if removed; phase depends on IBKR model support. `[VERIFIED: backend_api_python/requirements.txt]` |
| `pytz` | Current timezone handling in `trading_hours.py` | ✓ `[VERIFIED: local environment]` | `2025.2` `[VERIFIED: local environment]` | No fallback needed for Phase 1 because repo already uses it. `[VERIFIED: backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py]` |

**Missing dependencies with no fallback:** None discovered for Phase 1 planning. `[VERIFIED: local environment audit]`

**Missing dependencies with fallback:** None discovered for Phase 1 planning. `[VERIFIED: local environment audit]`

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest 9.0.2` `[VERIFIED: local environment]` |
| Config file | `none detected` `[VERIFIED: search for pytest config files under backend_api_python returned no matches]` |
| Quick run command | `python3 -m pytest backend_api_python/tests/test_trading_hours.py -q` `[VERIFIED: local test run passed]` |
| Full suite command | `python3 -m pytest backend_api_python/tests -q` `[VERIFIED: pytest available locally]` |

### Phase Requirements → Test Map

No roadmap-specific requirement IDs were mapped to Phase 1, but the phase should still derive explicit test cases from the phase tasks and from `R1`, `R2`, `N1`, `N3`, and `N4`. `[VERIFIED: user prompt says no mapped IDs] [VERIFIED: .planning/REQUIREMENTS.md]`

### Sampling Rate

- **Per task commit:** Run the narrowest affected sufficiency/trading-hours test file plus any new validator test file. `[VERIFIED: existing pytest file-per-feature pattern in backend_api_python/tests/]`
- **Per wave merge:** Run all Phase-1-related unit tests including `test_trading_hours.py` and the new sufficiency-validator suite. `[VERIFIED: roadmap exit criteria require unit tests for reason-code mapping and edge cases]`
- **Phase gate:** Run the full backend test suite before `/gsd-verify-work`, per the user's stated planning preference. `[VERIFIED: user prompt]`

### Wave 0 Gaps

- [ ] Add a dedicated test file for the new sufficiency validator, likely `backend_api_python/tests/test_data_sufficiency_validator.py`. `[VERIFIED: current repo has no sufficiency validator tests]`
- [ ] Add explicit test-case specifications for every planned task, per user preference. `[VERIFIED: user prompt]`
- [ ] Add one verify task in each plan item that runs the full relevant test-case suite, per user preference. `[VERIFIED: user prompt]`
- [ ] Add adapter tests that distinguish `unknown_schedule` from “market closed but schedule known”. `[VERIFIED: D-04/D-05 + current `is_rth_check()` boolean limitation]`

## Security Domain

This phase has low direct security surface because it primarily introduces classification logic and logging, not auth/session/crypto flows. `[VERIFIED: phase scope from ROADMAP + REQUIREMENTS]`

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no `[VERIFIED: phase scope]` | — |
| V3 Session Management | no `[VERIFIED: phase scope]` | — |
| V4 Access Control | no `[VERIFIED: phase scope]` | — |
| V5 Input Validation | yes `[VERIFIED: Phase 1 accepts broker/session/data inputs]` | Validate typed fields, enum-like `reason_code`, and diagnostics payload shape at module boundaries. `[VERIFIED: D-01/D-02]` |
| V6 Cryptography | no `[VERIFIED: phase scope]` | — |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed or partial IBKR schedule data | Tampering / Reliability risk `[VERIFIED: schedule parse failure is a requirement concern]` | Fail closed for open/add decisions in downstream phases and emit explicit schedule-failure reason in Phase 1 output. `[VERIFIED: D-04/D-05]` |
| Ambiguous reason-code/log payloads | Repudiation / Observability risk `[VERIFIED: N3 + D-02/D-03]` | Stable top-level fields and structured logging with event name + reason code + required/available counts. `[VERIFIED: .planning/REQUIREMENTS.md] [CITED: https://docs.python.org/3.11/library/logging.html]` |
| Over-logging internal payloads | Information disclosure `[ASSUMED]` | Log decision metadata, not raw secrets or oversized broker payload dumps. `[ASSUMED]` |

## Sources

### Primary (HIGH confidence)

- `backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py` - existing session parsing, timezone mapping, fail-closed path, fuse behavior. `[VERIFIED: codebase]`
- `backend_api_python/app/services/kline_fetcher.py` - current K-line coverage/range/aggregation semantics. `[VERIFIED: codebase]`
- `backend_api_python/tests/test_trading_hours.py` - tested edge cases for session parsing and fuse logic. `[VERIFIED: codebase]`
- `backend_api_python/tests/test_signal_executor.py` - current unit-test style and execution-path testing conventions. `[VERIFIED: codebase]`
- `.planning/phases/01-ibkr-schedule-sufficiency-domain-model/01-CONTEXT.md` - locked decisions and phase boundaries. `[VERIFIED: local file]`
- `.planning/REQUIREMENTS.md` - functional and non-functional constraints. `[VERIFIED: local file]`
- [ib_insync contract module docs](https://ib-insync.readthedocs.io/_modules/ib_insync/contract.html) - official `ContractDetails.timeZoneId`, `tradingHours`, `liquidHours`, `liquidSessions()`. `[CITED: official docs]`
- [Python 3.11 logging docs](https://docs.python.org/3.11/library/logging.html) - official `extra`, `LogRecord`, `LoggerAdapter` behavior. `[CITED: official docs]`
- [pytest monkeypatch docs](https://docs.pytest.org/en/stable/how-to/monkeypatch.html) - official fixture-based patching and teardown behavior. `[CITED: official docs]`

### Secondary (MEDIUM confidence)

- `backend_api_python/app/strategies/runners/single_symbol_runner.py` - adjacent stable identifier pattern via `risk_data_stale_prev_close`. `[VERIFIED: codebase]`
- Local environment audit (`python3 --version`, `pytest --version`, `pylint --version`, package imports, and `python3 -m pytest backend_api_python/tests/test_trading_hours.py -q`). `[VERIFIED: local environment + local test run]`

### Tertiary (LOW confidence)

- None beyond the explicit assumptions recorded in the Assumptions Log. `[VERIFIED: research review]`

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - mostly verified from the current repo, local environment, and official docs. `[VERIFIED: codebase + shell audit + official docs]`
- Architecture: HIGH - strongly constrained by locked decisions and existing production module boundaries. `[VERIFIED: CONTEXT.md + codebase]`
- Pitfalls: MEDIUM - derived from verified constraints and code inspection, but some are predictive planning risks rather than currently failing behaviors. `[VERIFIED: requirements + codebase]`

**Research date:** 2026-04-16 `[VERIFIED: local environment]`  
**Valid until:** 2026-05-16 for repo-internal findings; re-check official docs or package versions sooner if the Phase 1 plan adds new dependencies. `[VERIFIED: research date] [ASSUMED]`
