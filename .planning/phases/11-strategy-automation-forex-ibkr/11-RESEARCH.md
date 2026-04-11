# Phase 11: Strategy automation (Forex + IBKR) - Research

**Researched:** 2026-04-11  
**Domain:** Flask API validation, pytest integration/E2E mocking, IBKR event simulation  
**Confidence:** HIGH for codebase gaps; MEDIUM for ib_insync event ordering (verify against project `IBKRClient` handlers)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **Full-chain E2E integration tests from Flask API entry point**  
   - Flask `test_client` → API → signal → `PendingOrderEnqueuer` → `PendingOrderWorker` → `factory.create_client` → `StatefulClientRunner.execute` → `IBKRClient.place_market_order`.  
   - Mock all external dependencies: `ib_insync` + DB + notifications.  
   - Four signal types: `open_long` / `close_long` / `open_short` / `close_short`.  
   - One USStock regression case.  
   - New file: `test_forex_ibkr_e2e.py`.

2. **Mock IBKR Paper smoke test**  
   - Mock `ib_insync` simulating full Paper behavior: qualify → `placeOrder` → fill → position → PnL callbacks.  
   - Pairs: EURUSD, GBPJPY, XAGUSD; each pair runs open + close full cycle.

3. **API-layer strategy config validation**  
   - `@staticmethod` on `BaseStatefulClient` for market-category validation without instantiation.  
   - `factory.py`: `validate_exchange_market_category(exchange_id, market_category)`.  
   - Strategy CRUD validates on save; illegal combinations rejected.  
   - `PendingOrderWorker` runtime validation retained as double protection.

### Claude's Discretion

- E2E Flask app fixture shape; mock patch points.  
- Exact signature and inheritance for `validate_market_category_static`.  
- Smoke test event timing/order.

### Deferred Ideas (OUT OF SCOPE)

- None per CONTEXT.md.

</user_constraints>

## Summary

Phase 11 closes **RUNT-03**: strategies configured with `market_category=Forex` and `exchange_id` in `{ibkr-paper, ibkr-live}` must drive automated execution through the existing pending-order pipeline to `IBKRClient`. Code review confirms the **runtime path is already wired**: `load_strategy_configs` → `create_client` → `BaseStatefulClient.validate_market_category` → `StatefulClientRunner` → `place_market_order` (Phases 1–10). The **gaps** are: (1) **no API-time validation** — `StrategyService.create_strategy` / `update_strategy` / `batch_create_strategies` persist arbitrary `exchange_config` without checking it against `market_category`; (2) **no automated proof** of the full chain from an HTTP entry point; (3) **no dedicated mock-IBKR smoke** that exercises qualify → order → fill → position → PnL callback ordering for multiple Forex pairs.

**Primary recommendation:** Implement `validate_exchange_market_category(exchange_id, market_category)` in `factory.py` (dispatching to per–stateful-client static validators), call it from strategy CRUD (including batch create), keep `PendingOrderWorker` instance validation unchanged, and add `test_forex_ibkr_e2e.py` plus a focused mock-Paper smoke module reusing `_make_mock_ib_insync` / `_make_client_with_mock_ib` patterns from `test_ibkr_client.py`.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RUNT-03 | Strategy with `market_category=Forex` + `ibkr-paper`/`ibkr-live` triggers Forex automation end-to-end | Runtime path confirmed; API validation + E2E + smoke tests specified as UC-SA-* below |

</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|----------------|
| Python | 3.10+ | Backend runtime | Project baseline |
| Flask | 2.3.3 (`requirements.txt`) | HTTP API + `app.test_client()` | Existing routes and tests |
| pytest | 9.x (verified locally: `pytest 9.0.2`) | Integration/unit tests | `backend_api_python/tests/` |
| unittest.mock | stdlib | Patch `create_client`, DB, notifications | Matches `test_pending_order_worker.py`, `test_ibkr_client.py` |
| ib_insync | ≥0.9.86 | IB API; mocked in tests | `requirements.txt` |

### Supporting

| Library | Purpose | When to Use |
|---------|---------|-------------|
| MagicMock / AsyncMock | IB async qualify, events | Smoke test simulating callbacks |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Flask `test_client` | Direct Python calls to worker | Loses HTTP/auth/JSON contract; CONTEXT locks test_client path |
| Real IBKR Paper | Full mock | CONTEXT requires no live IB for smoke |

**Installation (dev):** Project does not pin `pytest` in `requirements.txt`; ensure CI/dev env has `pytest` (e.g. `pip install pytest`). Flask is already a declared dependency.

**Version verification:** `python3 -m pip show pytest` → 9.0.2 (2026-04-11). Flask pinned: `Flask==2.3.3`.

## Architecture Patterns

### Recommended Project Structure (tests)

```
backend_api_python/tests/
├── test_forex_ibkr_e2e.py          # NEW: API → … → place_market_order (mocks)
├── test_ibkr_client.py             # REUSE: _make_mock_ib_insync, _make_client_with_mock_ib
├── test_pending_order_worker.py    # REUSE: patch create_client + load_strategy_configs
└── conftest.py                     # Shared: signal dedup reset, DB mocks helpers
```

### Pattern 1: Patch at the worker import site

**What:** `@patch("app.services.pending_order_worker.create_client")` (and `load_strategy_configs`, `get_runner`, `records.*`) so the worker under test uses mocks without importing real TWS.

**When:** Unit/integration tests for `_execute_live_order` and E2E that drive the worker after API/enqueue simulation.

**Example (existing):**

```1:60:backend_api_python/tests/test_pending_order_worker.py
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.get_runner")
@patch("app.services.pending_order_worker.create_client")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_live_order_forex_passes_category_gate(
    mock_load_cfg,
    mock_create,
    ...
):
    mock_load_cfg.return_value = {
        "market_category": "Forex",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "forex",
    }
    ...
```

### Pattern 2: Minimal Flask app + blueprint for route tests

**What:** Register `strategy_bp` on a tiny `Flask(__name__)`, set `g.user_id` in `before_request`, use `with app.test_client() as c`.

**When:** E2E tests that hit real route functions with patched services (see `test_strategy_force_rebalance.py`).

### Pattern 3: Factory validation without live clients

**What:** Map `exchange_id` → client class or validator table; call a **static** method that only reads `supported_market_categories` (or explicit rules for crypto REST exchanges). Do not call `connect()`.

**When:** `create_strategy` / `update_strategy` before DB write.

### Anti-Patterns to Avoid

- **Instantiating `IBKRClient` in API validation:** pulls in connection/singleton side effects; use static validation only.
- **Duplicating `_EXCHANGE_MARKET_RULES` logic incorrectly:** worker already has crypto-only exchange sets; factory validation must stay **consistent** with `BaseStatefulClient.supported_market_categories` for IBKR/MT5/uSMART/EF.
- **E2E without patching DB:** tests become flaky and slow; CONTEXT requires full mock of DB + notifications.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IB contract qualification in tests | Custom Forex DSL | Extend `_make_mock_ib_insync` + `qualifyContractsAsync` mutation pattern | Matches real `ib_insync` in-place contract updates |
| Flask request cycle | Ad-hoc WSGI | `app.test_client()` with blueprint registration | Same as existing route tests |
| Per-exchange market rules scattered | New ad-hoc if/else in routes | Central `validate_exchange_market_category` + static methods on client classes | Single source of truth with worker |

**Key insight:** Execution semantics are already implemented; Phase 11 is **guardrails + proof**, not new trading logic.

## Common Pitfalls

### Pitfall 1: Batch create bypasses validation

**What goes wrong:** `batch_create_strategies` calls `create_strategy` in a loop; if validation is only on the HTTP route, batch path might skip it.

**Why:** Duplicate entry points.

**How to avoid:** Implement validation inside `StrategyService.create_strategy` (and ensure `update_strategy` + batch use the same helper).

### Pitfall 2: `exchange_id` casing and aliases

**What goes wrong:** `factory._get` lowercases `exchange_id`; validation must normalize the same way before lookup.

**Why:** Mismatch causes false rejections or silent wrong client.

**How to avoid:** Normalize with `.strip().lower()` once, shared with `create_client`.

### Pitfall 3: E2E chain ambiguity (“API → signal”)

**What goes wrong:** No single public route emits arbitrary `open_long` for every strategy without going through the executor.

**Why:** Product flow is signal processor → enqueue → worker.

**How to avoid:** E2E tests may (a) POST a strategy route that triggers enqueue + mocked worker poll, or (b) call the same internal functions the route would call, **after** `test_client` proves JSON handling—document the chosen hook in PLAN (CONTEXT leaves fixture choice to discretion).

### Pitfall 4: Mock event order vs `IBKRClient` handlers

**What goes wrong:** Invoking callbacks in an order that never occurs in production, missing bugs in `_on_order_status` / `_on_exec_details` / `_on_position` / `_on_pnl_single`.

**Why:** Handlers have side effects on DB records.

**How to avoid:** Align with registration in `IBKRClient` (`orderStatusEvent`, `execDetailsEvent`, `positionEvent`, `pnlSingleEvent`) and fire mocks in a **plausible** sequence (fill → exec → position update → pnl single).

## Code Examples

### Factory + static validation (prescriptive sketch)

```python
# Conceptual — implement in factory.py / base.py per PLAN
def validate_exchange_market_category(exchange_id: str, market_category: str) -> tuple[bool, str]:
    ex = (exchange_id or "").strip().lower()
    cat = (market_category or "").strip()
    if ex in _CRYPTO_EXCHANGE_IDS:
        allowed = _EXCHANGE_MARKET_RULES.get(ex)  # mirror worker or import shared constant
        ...
    if ex in ("ibkr-paper", "ibkr-live"):
        return IBKRClient.validate_market_category_static(cat)
    if ex == "mt5":
        return MT5Client.validate_market_category_static(cat)
    ...
```

### Flask test client (from project tests)

```29:40:backend_api_python/tests/test_strategy_force_rebalance.py
@pytest.fixture
def client_fixture():
    """Fixture to provide a test client for the Flask app."""
    app = Flask(__name__)
    app.register_blueprint(strategy_bp, url_prefix='/api/strategy')
    
    @app.before_request
    def set_g():
        g.user_id = 1
        
    with app.test_client() as c:
        yield c
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ccxt-only mental model | Stateful clients for IBKR/MT5 with `factory.create_client` | Pre–Forex work | Forex uses same worker path as equities |
| Category check only in worker | Worker + API validation | Phase 11 | Fail fast on bad config |

**Deprecated/outdated:** N/A for this phase.

## Use Case Specifications

Each use case is written for downstream PLAN/tasks: **Preconditions**, **Actions**, **Expected results / assertions**.

### A. API validation (`validate_exchange_market_category`)

| UC ID | Preconditions | Actions | Assertions |
|-------|-----------------|---------|------------|
| UC-SA-VAL-01 | Valid user payload | `create_strategy` with `market_category=Forex`, `exchange_config.exchange_id=ibkr-paper` | Success; row persisted |
| UC-SA-VAL-02 | Same | `exchange_id=ibkr-live` | Success |
| UC-SA-VAL-03 | Same | `exchange_id=mt5` | Success (MT5 supports Forex) |
| UC-SA-VAL-04 | Same | `exchange_id=binance` (or any crypto id from worker rules) | Rejected with clear error (crypto exchanges ≠ Forex category) |
| UC-SA-VAL-05 | Same | `exchange_id=ibkr-paper`, `market_category=Crypto` | Rejected (IBKR does not support Crypto as category) |
| UC-SA-VAL-06 | Existing strategy | `update_strategy` changing to illegal pair (e.g. Forex + binance) | Rejected; DB unchanged for exchange_config |
| UC-SA-VAL-07 | Batch payload | `batch_create_strategies` with `Forex:EURUSD` style symbol and `ibkr-paper` | Success per UC-SA-VAL-01 |
| UC-SA-VAL-08 | Batch payload | Forex market with incompatible exchange in `exchange_config` | Rejected or skipped with error in `failed_symbols` |

### B. Full-chain E2E (`test_forex_ibkr_e2e.py`)

| UC ID | Preconditions | Actions | Assertions |
|-------|-----------------|---------|------------|
| UC-SA-E2E-F1 | Mocks: DB, notifications, `ib_insync`; strategy row or patched `load_strategy_configs` returns Forex + ibkr-paper | Drive route or internal chain with `signal_type=open_long`, symbol EURUSD | `place_market_order` called once with BUY side; `mark_order_sent` (or equivalent) success path |
| UC-SA-E2E-F2 | Same | `close_long` | SELL side; success path |
| UC-SA-E2E-F3 | Same | `open_short` | SELL side |
| UC-SA-E2E-F4 | Same | `close_short` | BUY side |
| UC-SA-E2E-REGR | `market_category=USStock`, `ibkr-paper` | One full-chain case (e.g. `open_long` AAPL) | No regression vs current equity behavior; `place_market_order` invoked |

### C. Mock IBKR Paper smoke (qualify → order → events)

| UC ID | Preconditions | Actions | Assertions |
|-------|-----------------|---------|------------|
| UC-SA-SMK-01 | Mock IB wired for EURUSD; conId/localSymbol set after qualify | Open then close cycle (e.g. `open_long` + `close_long`) | Fill/exec/position/PnL handlers receive Forex contract fields; DB or spy calls consistent for round-trip |
| UC-SA-SMK-02 | Same for GBPJPY | Full open + close | Same as UC-SA-SMK-01 for cross pair |
| UC-SA-SMK-03 | Same for XAGUSD | Full open + close | Same for metals pair |

### D. Regression / double protection

| UC ID | Preconditions | Actions | Assertions |
|-------|-----------------|---------|------------|
| UC-SA-RT-01 | DB row illegally inserted bypassing API (simulated by old data) | `PendingOrderWorker._execute_live_order` | Still rejected at `validate_market_category` if pair is invalid |

## Gap Analysis: Does the codebase already support Forex + IBKR automation?

| Area | Supported? | Evidence | Remaining gap |
|------|------------|----------|----------------|
| `factory.create_client` for `ibkr-paper` / `ibkr-live` | Yes | `factory.py` lines 136–138 | None |
| `load_strategy_configs` includes `market_category` | Yes | `exchange_execution.load_strategy_configs` | None |
| Worker `validate_market_category` for Forex on IBKR | Yes | `test_pending_order_worker.py` UC-4 | None |
| `PendingOrderWorker` crypto exchange vs Forex | Yes | `_EXCHANGE_MARKET_RULES` blocks wrong category for crypto IDs | Extend **factory** rules for new validation (mirror semantics) |
| API save-time validation | **No** | `create_strategy` / `update_strategy` insert without `validate_exchange_market_category` | **Implement Phase 11** |
| Automated Flask → worker → `place_market_order` proof | **No** | No `test_forex_ibkr_e2e.py` | **Add tests** |
| Multi-pair mock Paper event smoke | **No** | `test_ibkr_client.py` focuses on client unit/integration, not 3-pair lifecycle smoke | **Add smoke module** |

## Risk Analysis: Static validation + factory changes

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Forgotten subclass (uSMART, EF) causes wrong default | Medium | Table-driven tests for each `exchange_id` that maps to a stateful client |
| `batch_create_strategies` skips validation | High | Single internal `_validate_strategy_exchange_market(...)` called from create + update + batch |
| Stricter validation breaks legacy bad rows | Low | Only on **create/update**; existing DB rows unchanged until edited |
| Divergence worker vs API rules | Medium | Share constants for crypto `_EXCHANGE_MARKET_RULES` or single module imported by both |

## Mock IBKR Paper: Realistic callback sequence

**Confidence:** MEDIUM — verify against `IBKRClient` event registration and handler order in `client.py`.

1. **Qualify:** `qualifyContractsAsync` mutates contract (`conId`, `secType`, `localSymbol` for Forex).  
2. **Submit:** `placeOrder` returns a `Trade` with `order`, `orderStatus`, `contract`.  
3. **orderStatus:** Transition to `Submitted` → `Filled` (or partial then filled).  
4. **execDetails:** Commission report + fills.  
5. **position:** `positionEvent` with non-zero then zero after close.  
6. **pnlSingle:** After position updates for unrealized/realized PnL paths.

Use **async** mocks where the client uses `ib.run` / async qualify (see `_make_client_with_mock_ib` async stubs in `test_ibkr_client.py`).

## Open Questions

1. **Which HTTP route constitutes the “API → signal” segment for E2E?**  
   - *What we know:* Signals normally come from `SignalExecutor` / indicators, not all strategy routes enqueue arbitrary signals.  
   - *Recommendation:* E2E may combine `test_client` POST to `create_strategy` **plus** a controlled test hook that invokes `PendingOrderWorker._execute_live_order` with a prepared `order_row`, **or** a thin test-only route (if product forbids, use internal call after verifying create returns 200). Document in PLAN.

2. **Should `validate_exchange_market_category` apply to crypto REST clients when `market_category` is Crypto?**  
   - *Recommendation:* Yes — keep parity with worker `_EXCHANGE_MARKET_RULES` for binance/okx/… ; CONTEXT allows non-stateful rules alongside static methods.

## Validation Architecture

> `workflow.nyquist_validation` is enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (~9.x) |
| Config file | Inline markers in `tests/conftest.py` (`pytest_configure`); no `pytest.ini` in repo |
| Quick run command | `cd backend_api_python && python -m pytest tests/test_forex_ibkr_e2e.py -x -q` (after file exists) |
| Full suite command | `cd backend_api_python && python -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| RUNT-03 | Forex + IBKR config drives live path | integration | `pytest tests/test_forex_ibkr_e2e.py -x` | ❌ Wave 0 |
| RUNT-03 | API rejects illegal exchange+category | unit/integration | `pytest tests/test_strategy*.py -k validate_exchange` (TBD) | ❌ Wave 0 |
| RUNT-03 | Mock Paper multi-pair smoke | integration | `pytest tests/test_ibkr_forex_paper_smoke.py -x` (name TBD) | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** Targeted `pytest` on new/changed tests.  
- **Per wave merge:** `python -m pytest tests/ -q`.  
- **Phase gate:** Full suite green before `/gsd:verify-work`.

### Wave 0 Gaps

- [ ] `tests/test_forex_ibkr_e2e.py` — covers UC-SA-E2E-*  
- [ ] API validation tests — covers UC-SA-VAL-* (file may be `test_strategy_exchange_validation.py` or colocated)  
- [ ] Mock Paper smoke test file — covers UC-SA-SMK-*  
- [ ] Optional: add `pytest` to `requirements-dev.txt` if project adopts explicit dev deps  

## Sources

### Primary (HIGH confidence)

- Repository: `backend_api_python/app/services/live_trading/factory.py`, `pending_order_worker.py`, `strategy.py`, `live_trading/base.py`  
- Repository: `backend_api_python/tests/test_ibkr_client.py`, `test_pending_order_worker.py`, `test_strategy_force_rebalance.py`

### Secondary (MEDIUM confidence)

- [Flask testing — application object](https://flask.palletsprojects.com/en/2.3.x/testing/) — `test_client()` usage aligns with Phase 11 E2E approach

### Tertiary (LOW confidence)

- ib_insync exact callback ordering for Paper — **defer to** tracing `IBKRClient` in-repo rather than external docs alone

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — versions from `requirements.txt` + local `pip show`  
- Architecture: **HIGH** — direct file reads  
- Pitfalls: **MEDIUM** — includes inferred E2E routing ambiguity  

**Research date:** 2026-04-11  
**Valid until:** ~30 days (test layout stable) unless factory/strategy signatures change materially
