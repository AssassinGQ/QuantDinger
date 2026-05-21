# Phase 24: NQ100 Strategy Type - Research

**Researched:** 2026-05-20
**Domain:** Strategy inheritance, delisting policy, dynamic universe binding
**Confidence:** HIGH

## Summary

Phase 24 creates a dedicated `NQ100Strategy` class that inherits from `CrossSectionalStrategy` (via new intermediate layer `DynamicCrossSectionalStrategy`) to provide dynamic universe binding via Phase 19's PIT API and configurable delisting policy for handling index reconstitution events. The implementation follows a layered architecture where Strategy handles universe membership pool adjustments and Runner handles execution timing through a new `DelistingPolicyFilter` in the existing `FilterChain`.

**Primary recommendation:** Implement three-layer inheritance (`CrossSectionalStrategy` → `DynamicCrossSectionalStrategy` → `NQ100Strategy`), add `DelistingPolicyFilter` to existing `cross_sectional_filter_chain.py`, and validate `delisting_policy` + `force_exit_symbols` configuration in `strategy.py` routes.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**STRAT-01: Universe Dynamic Binding**
- **D-01:** Three-layer inheritance: `CrossSectionalStrategy` → `DynamicCrossSectionalStrategy` → `NQ100Strategy`
- **D-02:** `DynamicCrossSectionalStrategy` provides `get_universe_list(as_of_date: date) -> List[str]`, subclasses must implement
- **D-03:** `NQ100Strategy.get_universe_list(as_of_date)` calls Phase 19's `get_constituents_as_of(as_of_date)`
- **D-04:** Dynamic universe vs static `symbol_list` mutual exclusion: both configured → HTTP 4xx + clear msg
- **D-05:** `DynamicCrossSectionalStrategy.get_data_request()` calls `get_universe_list()` instead of static `symbol_list`

**STRAT-02: Delisting Policy Architecture**
- **D-06:** Layered architecture: Strategy layer handles universe membership pool, Runner layer handles execution timing
- **D-07:** Strategy layer: `immediate`/`delayed` → removed stocks NOT in ranking; `hold_until_signal_exit` → removed stocks IN ranking, marked `excluded_from_universe`
- **D-08:** Runner layer: `DelistingPolicyFilter` in FilterChain, detects `qd_nq100_change_events`, decides forced sell timing based on `delisting_policy.mode`
- **D-09:** `hold_until_signal_exit`: after sell signal (rank out of TopN), Runner marks excluded from universe

**Delisting Policy Configuration**
- **D-10:** Config field: `trading_config.delisting_policy = {"mode": "immediate" | "delayed" | "hold_until_signal_exit", "months": N}`
- **D-11:** `months` field valid only for `mode="delayed"`, default=3, range 1-12
- **D-12:** `mode="immediate"`: effective_date forced sell removed stock holdings
- **D-13:** `mode="delayed"`: delayed `months` months forced sell removed stock holdings

**Special Case Handling**
- **D-14:** Bankruptcy/fraud/delisting risk: live trading immediate exit (fastest sell), NOT affected by `delisting_policy`
- **D-15:** Backtest simulation: special cases assumed total loss (exit price=0), conservative approach
- **D-16:** Phase 24 only supports MANUAL marking via `trading_config.force_exit_symbols` list; auto detection deferred

**Mag7 Concentration Constraint**
- **D-17:** Phase 24 only reserves config fields: `trading_config.mag7_min_count`, `trading_config.mag7_max_weight`
- **D-18:** Current phase does NOT implement Mag7 constraint logic

**Backtest Consistency**
- **D-19:** Backtest engine and live strategy share same `trading_config.delisting_policy` config
- **D-20:** Backtest engine reuses Runner's `DelistingPolicyFilter`, does NOT implement separate logic

### Claude's Discretion
- `DynamicCrossSectionalStrategy` interface naming details
- `DelistingPolicyFilter` internal implementation structure
- `force_exit_symbols` field validation logic
- Backtest total loss assumption implementation location

### Deferred Ideas (OUT OF SCOPE)
- **Auto bankruptcy/fraud detection** — needs external data source (SEC filings/news API)
- **Mag7 constraint implementation** — reserved fields only, logic deferred
- **Other universe subclasses** (e.g., `SP100Strategy`) — pattern same, create as needed later
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STRAT-01 | NQ100Strategy inherits CrossSectionalStrategy, symbol_list dynamically bound to PIT universe API (not static trading_config) | Three-layer inheritance pattern (D-01-D-05), existing `CrossSectionalStrategy` base class, `get_constituents_as_of()` PIT API |
| STRAT-02 | Three delisting_policy modes: immediate/delayed_N_months/hold_until_signal_exit, special cases (bankruptcy/delisting risk) unconditional immediate exit | Delisting Policy architecture (D-06-D-13), `DelistingPolicyFilter` pattern, `qd_nq100_change_events` table |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11.14 | Runtime | Existing backend version |
| pytest | 9.0.2 | Testing | Existing test framework, fixture-driven patterns |
| Flask | (existing) | HTTP routes | Strategy creation API validation |

### Supporting (Project-specific)
| Module | Purpose | When to Use |
|--------|---------|-------------|
| `app.strategies.cross_sectional.py` | Base class inheritance | STRAT-01 implementation |
| `app.strategies.runners.cross_sectional_filter_chain.py` | Filter pattern | STRAT-02 DelistingPolicyFilter |
| `app.services.universe_nq100_service.py` | PIT API | `get_constituents_as_of()` integration |
| `app.services.nq100_sources.py` | Effective date shift | `resolve_shifted_execution_date()` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Three-layer inheritance | Single subclass NQ100Strategy directly inheriting CrossSectionalStrategy | Would duplicate universe binding logic for future SP100/other index strategies |
| DelistingPolicyFilter in FilterChain | Separate DelistingService module | Breaks Phase 21 execution filter chain pattern, harder to ensure backtest/live consistency |
| Runner-layer delisting handling | Strategy-layer handling only | Cannot enforce T+1 execution semantics properly |

**Installation:**
No new dependencies required — all implementation uses existing project modules.

**Version verification:** All existing modules verified by codebase inspection.

## Architecture Patterns

### Recommended Project Structure
```
backend_api_python/app/strategies/
├── cross_sectional.py               # Base class (existing)
├── dynamic_cross_sectional.py       # NEW: Intermediate layer with get_universe_list()
├── nq100_strategy.py                # NEW: NQ100-specific implementation
├── runners/
│   ├── cross_sectional_runner.py    # Existing runner (modify metadata handling)
│   └── cross_sectional_filter_chain.py  # Existing (add DelistingPolicyFilter)
```

### Pattern 1: Three-Layer Strategy Inheritance
**What:** `CrossSectionalStrategy` → `DynamicCrossSectionalStrategy` → `NQ100Strategy`
**When to use:** Any strategy requiring dynamic universe binding (NQ100, SP100, etc.)
**Example:**
```python
# Source: existing CrossSectionalStrategy pattern + CONTEXT.md D-01-D-03
class DynamicCrossSectionalStrategy(CrossSectionalStrategy):
    """Intermediate layer providing dynamic universe interface."""
    
    def get_universe_list(self, as_of_date: date) -> List[str]:
        """Subclass must implement to return constituents as of date."""
        raise NotImplementedError("Subclass must implement get_universe_list()")
    
    def get_data_request(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        current_time: float,
    ) -> DataRequest:
        """Override to use dynamic universe instead of static symbol_list."""
        trading_config = strategy.get("trading_config") or {}
        # Call subclass implementation
        symbol_list = self.get_universe_list(date.today())
        return {
            "symbol_list": symbol_list,
            "timeframe": trading_config.get("timeframe", "1D"),
            ...
        }


class NQ100Strategy(DynamicCrossSectionalStrategy):
    """NQ100-specific strategy with PIT universe binding."""
    
    def get_universe_list(self, as_of_date: date) -> List[str]:
        """Call Phase 19 PIT API."""
        from app.services.universe_nq100_service import get_constituents_as_of
        return get_constituents_as_of(as_of_date)
```

### Pattern 2: FilterChain Extension for Delisting Policy
**What:** Add `DelistingPolicyFilter` to existing `cross_sectional_filter_chain.py`
**When to use:** All cross-sectional executions requiring delisting policy handling
**Example:**
```python
# Source: existing FilterChain pattern in cross_sectional_filter_chain.py
class DelistingPolicyFilter(SignalFilter):
    """D-08: Handle delisting events from qd_nq100_change_events."""
    
    def apply(self, ctx: FilterContext) -> FilterOutcome:
        # Check if symbol has remove event with effective_date <= execution_date
        # Based on delisting_policy.mode, decide action
        delisting_policy = ctx.signal.get("delisting_policy", {})
        mode = delisting_policy.get("mode", "immediate")
        
        # Query qd_nq100_change_events for symbol's remove events
        # If mode="immediate" and execution_date >= effective_date → forced sell
        # If mode="delayed" and execution_date >= effective_date + months → forced sell
        # If mode="hold_until_signal_exit" → pass through (Strategy layer handles)
        
        return FilterOutcome(FilterAction.CONTINUE)
```

### Pattern 3: Configuration Validation in Routes
**What:** Validate `delisting_policy` and `force_exit_symbols` in strategy creation
**When to use:** POST `/api/strategies/create` and PUT `/api/strategies/update`
**Example:**
```python
# Source: existing strategy.py pattern + D-04, D-10-D-11
def validate_cross_sectional_config(trading_config: Dict[str, Any]) -> None:
    # D-04: Mutual exclusion check
    if trading_config.get("symbol_list") and trading_config.get("universe"):
        raise ValueError("symbol_list and universe are mutually exclusive")
    
    # D-10-D-11: delisting_policy validation
    policy = trading_config.get("delisting_policy", {})
    mode = policy.get("mode", "immediate")
    if mode not in ("immediate", "delayed", "hold_until_signal_exit"):
        raise ValueError(f"Invalid delisting_policy.mode: {mode}")
    if mode == "delayed":
        months = policy.get("months", 3)
        if not (1 <= months <= 12):
            raise ValueError("delisting_policy.months must be 1-12 for delayed mode")
    
    # D-16: force_exit_symbols validation
    force_exit = trading_config.get("force_exit_symbols", [])
    if not isinstance(force_exit, list):
        raise ValueError("force_exit_symbols must be a list")
```

### Anti-Patterns to Avoid
- **Anti-pattern 1:** Implementing delisting logic in Strategy layer only (violates D-06 Runner-layer responsibility for execution timing)
- **Anti-pattern 2:** Backtest engine implementing separate delisting logic (violates D-20 reuse requirement)
- **Anti-pattern 3:** Using `get_constituents_as_of(signal_date)` instead of `get_constituents_as_of(execution_date)` for execution decisions (lookahead bias)
- **Anti-pattern 4:** Allowing both `symbol_list` and `universe` config (violates D-04 mutual exclusion)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dynamic universe query | Custom SQL query logic | `get_constituents_as_of()` from Phase 19 | PIT semantics already implemented, tested |
| Execution date shifting | Custom calendar logic | `resolve_shifted_execution_date()` from Phase 21 | D-14/D-15 effective_date shift already handled |
| Filter chain pattern | New DelistingService module | Add `DelistingPolicyFilter` to existing `FilterChain` | Follows Phase 21 pattern, ensures consistency |
| Config validation | Ad-hoc validation in multiple places | Centralized in `strategy.py` route | Single validation point, clear error messages |

**Key insight:** Delisting policy handling involves execution timing (Runner layer) AND universe membership (Strategy layer). Attempting to handle both in one layer leads to semantic confusion and backtest/live inconsistency.

## Runtime State Inventory

> Phase 24 is a greenfield implementation (new classes and filter), not a rename/refactor.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — new strategy classes | None |
| Live service config | None — existing FilterChain pattern extension | None |
| OS-registered state | None | None |
| Secrets/env vars | None — no new secrets | None |
| Build artifacts | None | None |

**Nothing found in any category:** Phase 24 adds new code without modifying runtime state.

## Common Pitfalls

### Pitfall 1: Using Signal Date for Universe Query
**What goes wrong:** Querying `get_constituents_as_of(signal_date)` instead of `get_constituents_as_of(execution_date)` for execution decisions
**Why it happens:** Intuitive assumption that signal date determines universe
**How to avoid:** Runner layer uses execution_date for change event checks; Strategy layer uses signal_date for ranking pool
**Warning signs:** Backtest shows trades on stocks that were removed from index before execution_date

### Pitfall 2: Missing Delisting Event Query
**What goes wrong:** `DelistingPolicyFilter` doesn't query `qd_nq100_change_events` table properly
**Why it happens:** Assuming change events are pre-loaded in metadata
**How to avoid:** Filter must query database for `event_type='remove'` AND `effective_date <= execution_date`
**Warning signs:** Removed stocks not being sold on effective_date in `immediate` mode

### Pitfall 3: hold_until_signal_exit Universe Tracking
**What goes wrong:** Strategy layer doesn't track `excluded_from_universe` status for removed stocks in `hold_until_signal_exit` mode
**Why it happens:** Assuming FilterChain handles all delisting logic
**How to avoid:** D-07: Strategy layer marks removed stocks as `excluded_from_universe`, D-09: Runner updates after sell signal
**Warning signs:** Removed stocks continue appearing in rankings indefinitely

### Pitfall 4: Backtest vs Live Config Mismatch
**What goes wrong:** Backtest engine uses hardcoded delisting config instead of `trading_config.delisting_policy`
**Why it happens:** Separating backtest and live strategy configuration
**How to avoid:** D-19/D-20: Both use same config, same `DelistingPolicyFilter`
**Warning signs:** Backtest shows different behavior than live for same config

### Pitfall 5: Force Exit Symbols Not Checked in Runner
**What goes wrong:** `force_exit_symbols` only checked at strategy creation, not during execution
**Why it happens:** Assuming validation is sufficient
**How to avoid:** Runner's `DelistingPolicyFilter` must check `force_exit_symbols` list at each execution
**Warning signs:** Manually marked bankruptcy stocks not immediately sold in live trading

## Code Examples

Verified patterns from existing codebase:

### CrossSectionalStrategy Base Class Pattern
```python
# Source: backend_api_python/app/strategies/cross_sectional.py
class CrossSectionalStrategy(IStrategyLoop):
    def get_data_request(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        current_time: float,
    ) -> DataRequest:
        trading_config = strategy.get("trading_config") or {}
        symbol_list = trading_config.get("symbol_list", [])
        # ...returns DataRequest dict
```

### FilterChain Pattern for Adding Filters
```python
# Source: backend_api_python/app/strategies/runners/cross_sectional_filter_chain.py
class FilterChain:
    def __init__(self, filters: List[SignalFilter]):
        self.filters = filters

    def run(self, ctx: FilterContext) -> FilterOutcome:
        for filter_unit in self.filters:
            outcome = filter_unit.apply(ctx)
            if outcome.action != FilterAction.CONTINUE:
                return outcome
        return FilterOutcome(FilterAction.ACCEPT, signal=ctx.signal)

# Usage in CrossSectionalRunner._filter_phase21_signals:
chain = FilterChain([
    CashMnaForcedExitFilter(),
    TradabilityFilter(),
    MissingMarketRowPassThroughFilter(),
    LiquidityVolumeFilter(),
    ExecutionPriceFilter(),
    # NEW: DelistingPolicyFilter() will be added here
])
```

### qd_nq100_change_events Table Schema
```sql
-- Source: backend_api_python/migrations/0055_qd_nq100_universe.sql
CREATE TABLE IF NOT EXISTS qd_nq100_change_events (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    event_type VARCHAR(16) NOT NULL,  -- 'add' or 'remove'
    effective_date DATE NOT NULL,
    source VARCHAR(64) NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_qd_nq100_change_events_event_type CHECK (event_type IN ('add', 'remove'))
);
```

### get_constituents_as_of PIT API
```python
# Source: backend_api_python/app/services/universe_nq100_service.py
def get_constituents_as_of(as_of_date: date) -> List[str]:
    """Return sorted unique symbols that were NQ100 constituents on as_of_date."""
    with db.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(_PIT_SQL, (as_of_date,))
        rows = cursor.fetchall()
    symbols = sorted({str(row[0]).strip().upper() for row in rows})
    return symbols
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Static symbol_list in trading_config | Dynamic universe binding via PIT API | Phase 24 | Enables index-tracking strategies with automatic rebalancing |
| No delisting policy | Three configurable modes | Phase 24 | Handles index reconstitution events systematically |
| Ad-hoc backtest handling | Unified DelistingPolicyFilter for backtest and live | Phase 24 (D-19/D-20) | Ensures consistency, reduces maintenance |

**Deprecated/outdated:**
- Hardcoded NQ100 universe lists in scripts: Migrate to PIT API calls

## Assumptions Log

> All claims verified by codebase inspection. No `[ASSUMED]` claims in this research.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | All claims verified | — | — |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed.

## Open Questions

1. **DelistingPolicyFilter database query timing**
   - What we know: D-08 requires checking `qd_nq100_change_events` table
   - What's unclear: Should query happen in FilterContext construction (pre-filter) or inside filter.apply()
   - Recommendation: Query in `CrossSectionalRunner._filter_phase21_signals` before filter chain (similar to existing `market_rows`/`tradability` metadata pattern)

2. **hold_until_signal_exit excluded_from_universe tracking**
   - What we know: D-07/D-09 describe Strategy and Runner layer responsibilities
   - What's unclear: Where exactly is `excluded_from_universe` status stored and updated
   - Recommendation: Store in strategy's `status_info` JSON column (via `update_strategy_status_info`), Runner updates after sell signal

3. **Backtest total loss assumption location**
   - What we know: D-15 says special cases assumed total loss (exit price=0)
   - What's unclear: Should this be in `DelistingPolicyFilter` or separate backtest-specific handling
   - Recommendation: Add to `DelistingPolicyFilter` with backtest context flag; when `execution_mode='backtest'` and symbol in `force_exit_symbols`, set execution_price=0

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | ✓ | 3.11.14 | — |
| pytest | Testing | ✓ | 9.0.2 | — |
| PostgreSQL | qd_nq100_change_events | ✓ | (Docker) | — |
| Flask | Routes | ✓ | (existing) | — |

**Missing dependencies with no fallback:**
- None

**Missing dependencies with fallback:**
- None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `backend_api_python/tests/conftest.py` |
| Quick run command | `pytest tests/test_nq100_strategy.py -v -x` |
| Full suite command | `pytest tests/ -v --tb=short` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STRAT-01 | Three-layer inheritance | unit | `pytest tests/test_nq100_strategy.py::TestStrategyInheritance -v` | ❌ Wave 0 |
| STRAT-01 | Dynamic universe binding via PIT API | unit | `pytest tests/test_nq100_strategy.py::TestDynamicUniverseBinding -v` | ❌ Wave 0 |
| STRAT-01 | Mutual exclusion validation | unit | `pytest tests/test_nq100_strategy.py::TestConfigValidation::test_mutual_exclusion -v` | ❌ Wave 0 |
| STRAT-02 | DelistingPolicyFilter immediate mode | unit | `pytest tests/test_delisting_policy_filter.py::TestImmediateMode -v` | ❌ Wave 0 |
| STRAT-02 | DelistingPolicyFilter delayed mode | unit | `pytest tests/test_delisting_policy_filter.py::TestDelayedMode -v` | ❌ Wave 0 |
| STRAT-02 | DelistingPolicyFilter hold_until_signal_exit mode | unit | `pytest tests/test_delisting_policy_filter.py::TestHoldUntilSignalExit -v` | ❌ Wave 0 |
| STRAT-02 | force_exit_symbols handling | unit | `pytest tests/test_delisting_policy_filter.py::TestForceExitSymbols -v` | ❌ Wave 0 |
| STRAT-02 | Backtest total loss assumption | unit | `pytest tests/test_delisting_policy_filter.py::TestBacktestTotalLoss -v` | ❌ Wave 0 |
| Integration | Runner filter chain integration | integration | `pytest tests/test_cross_sectional_runner_integration.py::TestDelistingFilterChain -v` | ❌ Wave 0 |
| Integration | Strategy creation route validation | e2e | `pytest tests/test_strategy_routes.py::TestNQ100StrategyCreation -v` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_nq100_strategy.py tests/test_delisting_policy_filter.py -v -x`
- **Per wave merge:** `pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_nq100_strategy.py` — covers STRAT-01 inheritance and universe binding
- [ ] `tests/test_delisting_policy_filter.py` — covers STRAT-02 delisting policy modes
- [ ] `tests/test_cross_sectional_runner_integration.py` — covers Runner integration with new filter
- [ ] `tests/test_strategy_routes.py` — covers HTTP route validation for NQ100 strategy creation
- [ ] `tests/fixtures/phase24/` — test data fixtures (change events, delisting scenarios)
- [ ] Framework config: already exists in `conftest.py`

### Detailed Test Case Specifications

#### Task 1: DynamicCrossSectionalStrategy Implementation

**Test File:** `tests/test_nq100_strategy.py`

| Test Case | Description | Input | Expected Output |
|-----------|-------------|-------|-----------------|
| `test_dynamic_strategy_requires_get_universe_list` | Verify intermediate layer raises NotImplementedError if subclass doesn't implement | `DynamicCrossSectionalStrategy()` instance, call `get_universe_list(date(2024,1,1))` | Raises `NotImplementedError` with message containing "Subclass must implement" |
| `test_dynamic_strategy_get_data_request_calls_universe_list` | Verify `get_data_request()` calls `get_universe_list()` instead of static config | Strategy with mock `get_universe_list` returning `["AAPL", "MSFT"]`, `trading_config={}` | `DataRequest["symbol_list"]` == `["AAPL", "MSFT"]` |
| `test_dynamic_strategy_inherits_from_cross_sectional` | Verify inheritance chain | Check `DynamicCrossSectionalStrategy.__bases__` | First base is `CrossSectionalStrategy` |

#### Task 2: NQ100Strategy Implementation

**Test File:** `tests/test_nq100_strategy.py`

| Test Case | Description | Input | Expected Output |
|-----------|-------------|-------|-----------------|
| `test_nq100_strategy_inherits_dynamic` | Verify inheritance chain | Check `NQ100Strategy.__bases__` | First base is `DynamicCrossSectionalStrategy` |
| `test_nq100_get_universe_list_calls_pit_api` | Verify PIT API integration | Mock `get_constituents_as_of(date(2024,3,15))` returning `["AAPL","MSFT","GOOGL"]`, call `strategy.get_universe_list(date(2024,3,15))` | Returns `["AAPL","GOOGL","MSFT"]` (sorted) |
| `test_nq100_get_universe_list_empty_result` | Handle empty PIT result | Mock `get_constituents_as_of` returning `[]` | Returns `[]` (no error raised) |
| `test_nq100_get_universe_list_db_error_handling` | Handle database errors gracefully | Mock `get_constituents_as_of` raising `Exception("DB error")` | Catches and returns `[]` or logs warning (doesn't crash) |

#### Task 3: Configuration Validation

**Test File:** `tests/test_strategy_routes.py`

| Test Case | Description | Input | Expected Output |
|-----------|-------------|-------|-----------------|
| `test_mutual_exclusion_symbol_list_and_universe` | D-04: Both configured should error | `trading_config={"symbol_list": ["AAPL"], "universe": "NQ100"}` | HTTP 400, `msg` contains "mutually exclusive" |
| `test_valid_delisting_policy_immediate` | D-12: Valid immediate mode | `delisting_policy={"mode": "immediate"}` | HTTP 200, strategy created |
| `test_valid_delisting_policy_delayed` | D-13: Valid delayed mode with months | `delisting_policy={"mode": "delayed", "months": 6}` | HTTP 200, strategy created |
| `test_invalid_delisting_policy_mode` | Invalid mode value | `delisting_policy={"mode": "invalid_mode"}` | HTTP 400, `msg` contains "Invalid delisting_policy.mode" |
| `test_delayed_mode_months_range_validation` | D-11: months out of range | `delisting_policy={"mode": "delayed", "months": 15}` | HTTP 400, `msg` contains "months must be 1-12" |
| `test_delayed_mode_missing_months_defaults_to_3` | D-11: Default months=3 | `delisting_policy={"mode": "delayed"}` (no months field) | HTTP 200, stored config has `months=3` |
| `test_force_exit_symbols_valid_list` | D-16: Valid list | `force_exit_symbols=["ENRN", "WCOM"]` | HTTP 200, strategy created |
| `test_force_exit_symbols_invalid_type` | D-16: Non-list value | `force_exit_symbols="ENRN"` (string not list) | HTTP 400, `msg` contains "must be a list" |
| `test_mag7_fields_reserved_no_validation` | D-17/D-18: Mag7 fields accepted but not implemented | `mag7_min_count=3, mag7_max_weight=0.15` | HTTP 200, fields stored but no runtime effect |

#### Task 4: DelistingPolicyFilter Implementation

**Test File:** `tests/test_delisting_policy_filter.py`

| Test Case | Description | Input | Expected Output |
|-----------|-------------|-------|-----------------|
| `test_immediate_mode_forced_sell_on_effective_date` | D-12: Immediate sell on effective_date | Signal for removed symbol, `execution_date="2024-03-18"` (equals effective_date from mock events), `mode="immediate"` | `FilterOutcome(FilterAction.ACCEPT)` with `signal.type="forced_sell"` |
| `test_immediate_mode_no_action_before_effective_date` | No forced sell before effective_date | Signal for removed symbol, `execution_date="2024-03-17"` (before effective_date="2024-03-18") | `FilterOutcome(FilterAction.CONTINUE)` |
| `test_delayed_mode_forced_sell_after_months` | D-13: Forced sell after delay period | Signal for removed symbol, `effective_date="2024-03-18"`, `execution_date="2024-06-18"` (3 months later), `mode="delayed", months=3` | `FilterOutcome(FilterAction.ACCEPT)` with `signal.type="forced_sell"` |
| `test_delayed_mode_no_action_within_delay_period` | No forced sell within delay period | Same as above but `execution_date="2024-04-15"` (within 3 months) | `FilterOutcome(FilterAction.CONTINUE)` |
| `test_hold_until_signal_exit_no_forced_sell` | D-09: No forced sell from filter | Signal for removed symbol, `mode="hold_until_signal_exit"` | `FilterOutcome(FilterAction.CONTINUE)` (Strategy layer handles ranking) |
| `test_hold_until_signal_exit_excluded_after_sell_signal` | D-09: Mark excluded after sell | Signal showing sell (close_long) for removed stock in hold_until_signal_exit mode | `FilterOutcome(FilterAction.ACCEPT)` with additional metadata marking `excluded_from_universe=True` |
| `test_force_exit_symbols_immediate_sell` | D-14/D-16: Force exit overrides policy | Signal for symbol in `force_exit_symbols=["ENRN"]`, any mode | `FilterOutcome(FilterAction.ACCEPT)` with `signal.type="forced_sell"` (immediate, no delay) |
| `test_no_change_event_for_symbol` | Symbol without remove event | Signal for symbol not in `qd_nq100_change_events` | `FilterOutcome(FilterAction.CONTINUE)` |
| `test_add_event_ignored` | Add events don't trigger forced sell | Signal for symbol with `event_type="add"` | `FilterOutcome(FilterAction.CONTINUE)` |

#### Task 5: Backtest Total Loss Handling

**Test File:** `tests/test_delisting_policy_filter.py`

| Test Case | Description | Input | Expected Output |
|-----------|-------------|-------|-----------------|
| `test_backtest_force_exit_total_loss` | D-15: Special cases total loss in backtest | Signal for `force_exit_symbols=["ENRN"]`, `execution_mode="backtest"` | `execution_price=0.0` in output signal |
| `test_live_force_exit_not_total_loss` | D-14: Live uses actual price | Signal for `force_exit_symbols=["ENRN"]`, `execution_mode="live"`, `next_open=50.0` | `execution_price=50.0` (not zero) |

#### Task 6: Runner Integration

**Test File:** `tests/test_cross_sectional_runner_integration.py`

| Test Case | Description | Input | Expected Output |
|-----------|-------------|-------|-----------------|
| `test_runner_includes_delisting_filter_in_chain` | Verify filter chain composition | Check `CrossSectionalRunner._filter_phase21_signals` chain filters | `DelistingPolicyFilter` in filter list |
| `test_runner_metadata_includes_change_events` | Verify metadata preparation | Mock strategy with `universe="NQ100"`, check metadata passed to filter chain | `metadata["change_events"]` populated with `qd_nq100_change_events` data |
| `test_runner_metadata_includes_force_exit_symbols` | Verify force exit symbols passed | Strategy with `force_exit_symbols=["ENRN"]`, check metadata | `metadata["force_exit_symbols"]` == `["ENRN"]` |
| `test_runner_metadata_includes_delisting_policy` | Verify policy passed | Strategy with `delisting_policy={"mode":"immediate"}`, check metadata | `metadata["delisting_policy"]` matches strategy config |

#### Task 7: Strategy Layer hold_until_signal_exit Tracking

**Test File:** `tests/test_nq100_strategy.py`

| Test Case | Description | Input | Expected Output |
|-----------|-------------|-------|-----------------|
| `test_strategy_excluded_from_universe_tracking` | D-07: Removed stocks still in ranking pool | Mock `get_constituents_as_of` excluding "ABCD", strategy in `hold_until_signal_exit` mode, "ABCD" has position | "ABCD" appears in `get_data_request()["symbol_list"]` |
| `test_strategy_marks_excluded_in_metadata` | D-07: Mark excluded_from_universe | Strategy `get_signals` for removed stock in `hold_until_signal_exit` mode | Signal metadata includes `excluded_from_universe=True` |

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing JWT auth (`login_required` decorator) |
| V3 Session Management | yes | Existing token verification |
| V4 Access Control | yes | Strategy ownership verification (`user_id` check) |
| V5 Input Validation | yes | `delisting_policy`, `force_exit_symbols`, `universe` config validation |
| V6 Cryptography | no | No new crypto operations |

### Known Threat Patterns for Strategy API

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Invalid configuration injection | Tampering | Validate all `trading_config` fields before persisting |
| Universe bypass (symbol_list + universe) | Tampering | D-04 mutual exclusion check with HTTP 4xx response |
| SQL injection in force_exit_symbols | Tampering | Validate list type, sanitize symbol strings before DB query |
| Unauthorized strategy modification | Information Disclosure | `user_id` ownership check in routes |

## Sources

### Primary (HIGH confidence)
- `.planning/phases/24-nq100-strategy-type/24-CONTEXT.md` — Locked decisions D-01 through D-20
- `backend_api_python/app/strategies/cross_sectional.py` — Existing base class implementation
- `backend_api_python/app/strategies/runners/cross_sectional_filter_chain.py` — FilterChain pattern
- `backend_api_python/app/services/universe_nq100_service.py` — PIT API `get_constituents_as_of()`
- `backend_api_python/migrations/0055_qd_nq100_universe.sql` — `qd_nq100_change_events` schema

### Secondary (MEDIUM confidence)
- `backend_api_python/tests/test_backtest_correctness_phase21.py` — Filter testing pattern
- `backend_api_python/tests/test_cross_sectional_portfolio_bt01.py` — Contract validation pattern
- `backend_api_python/app/routes/strategy.py` — Strategy creation route pattern

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — All modules verified by codebase inspection
- Architecture: HIGH — Inheritance and filter patterns verified in existing code
- Pitfalls: HIGH — Derived from CONTEXT.md decisions and existing Phase 21 patterns

**Research date:** 2026-05-20
**Valid until:** 2026-06-20 (30 days — stable codebase patterns)

---

## RESEARCH COMPLETE

**Phase:** 24 - NQ100 Strategy Type
**Confidence:** HIGH

### Key Findings
1. Three-layer inheritance pattern (`CrossSectionalStrategy` → `DynamicCrossSectionalStrategy` → `NQ100Strategy`) verified as compatible with existing base class
2. `DelistingPolicyFilter` addition to existing `FilterChain` pattern validated — follows Phase 21 execution filter architecture
3. PIT API `get_constituents_as_of()` already implemented in Phase 19, ready for integration
4. `qd_nq100_change_events` table schema confirmed: `event_type='add'|'remove'`, `effective_date` column available
5. Configuration validation pattern established in `strategy.py` routes — extend for mutual exclusion and delisting_policy

### File Created
`.planning/phases/24-nq100-strategy-type/24-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|-------|
| Standard Stack | HIGH | All existing modules verified by code inspection |
| Architecture | HIGH | Inheritance and filter patterns match existing implementations |
| Pitfalls | HIGH | Derived from locked decisions and tested patterns |

### Test Case Specifications Summary
- 29 unit tests covering STRAT-01 inheritance and STRAT-02 delisting policy
- 4 integration tests for Runner and route integration
- Test fixtures needed in `tests/fixtures/phase24/`

### Ready for Planning
Research complete. Planner can now create PLAN.md with task-level test case specifications as documented above.