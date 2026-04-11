# Phase 10: Fills, position & PnL events — Research

**Researched:** 2026-04-11  
**Domain:** IBKR event callbacks (`ib_insync`), local DB snapshots (`records.py`), Forex vs equity portfolio semantics  
**Confidence:** HIGH for code-path and bug verification; MEDIUM for IBKR’s exact meaning of `PnLSingle.value` vs equity `marketValue` (documented as pitfall)

## Summary

Phase 10 must satisfy **RUNT-02**: fill/position/PnL callbacks handle Forex correctly for **symbol keys**, **quantities**, and **currency / secType context**. Code review shows a **single coherent failure mode**: the API layer (`get_positions`) **hardcodes** equity assumptions (`secType=STK`, `exchange=SMART`, `currency=USD`) while the DB row only stores `symbol` + numeric fields; meanwhile **`_conid_to_symbol` and `ibkr_save_position` use `contract.symbol`**, which for Forex is the **base currency** (e.g. `EUR`), not the project’s canonical **`localSymbol`** (e.g. `EUR.USD`). A third issue is **`ibkr_save_pnl` is broken at runtime** (`UnboundLocalError` / dead clamp lines referencing undefined names); existing tests never execute the real function because they patch `ibkr_save_pnl`.

The three CONTEXT.md proposals are **not a shotgun**: they cluster around **one core problem** — *persist and expose IBKR contract truth (label + secType + venue + currency) for per-conId rows keyed by `(account, con_id)`*. The **`localSymbol or symbol`** change fixes the **identifier**; the **DB columns on `qd_ibkr_pnl_single`** fix the **hardcoded `get_positions()` metadata**; the **`ibkr_save_pnl` fix** is **mandatory hygiene** in the same records module and unblocks real account-level PnL persistence (orthogonal to Forex display but same edit surface).

**Primary recommendation:** Implement **(1)** `localSymbol or symbol` for `_conid_to_symbol` + position/portfolio save paths, **(2)** add `sec_type`, `exchange`, `currency` to `qd_ibkr_pnl_single` with migration-safe `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, wire `ibkr_save_position` / `ibkr_get_positions` / `get_positions()`, **(3)** remove dead lines in `ibkr_save_pnl` and add a **direct unit test** that calls the real `ibkr_save_pnl` (mock DB only).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **DB:** `qd_ibkr_pnl_single` add columns `sec_type`, `exchange`, `currency`; `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`; `ibkr_save_position` extended; `_on_position` / `_on_update_portfolio` pass contract fields; `ibkr_get_positions` SELECT extended; `get_positions()` reads real values with fallback for legacy rows.
- **Bugfix:** `ibkr_save_pnl` — remove 3 dead lines (`position`/`avg_cost`/`value` clamps referencing undefined names); keep PnL clamps; test that no exception is raised with mock DB.
- **Symbol key:** `_conid_to_symbol` and save paths use `contract.localSymbol or contract.symbol or ""`.
- **Tests:** records mocks + callback mocks + `get_positions` mock rows; full regression of `test_ibkr_client.py` / `test_ibkr_order_callback.py`.

### Claude's Discretion

- Exact PostgreSQL `ALTER TABLE` syntax and defaults.
- `ibkr_save_position` parameter defaults for new fields.
- Test IDs and parametrization (Forex + Stock).

### Deferred Ideas (OUT OF SCOPE)

- None per CONTEXT.md.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **RUNT-02** | 成交/仓位/PnL 事件回调正确处理 Forex 合约的数据（symbol key、数量、币种） | `localSymbol` alignment + DB-backed secType/exchange/currency + `get_positions()` no longer equity-only; tests cover Forex lifecycle mocks. |
</phase_requirements>

## Standard Stack

### Core

| Library / component | Version (project) | Purpose | Why Standard |
|---------------------|-------------------|---------|--------------|
| **ib_insync** | `>=0.9.86` (`requirements.txt`) | `Contract` fields (`localSymbol`, `secType`, `exchange`, `currency`), event objects | Project’s IBKR integration layer |
| **PostgreSQL + psycopg2** | `psycopg2-binary>=2.9.9` | `qd_ibkr_pnl` / `qd_ibkr_pnl_single` snapshots | Existing `records.py` pattern |
| **pytest** | (dev stack) | Unit tests for callbacks and records | Existing `backend_api_python/tests/` |

### Supporting

| Piece | Purpose |
|-------|---------|
| `_fire_submit` / `_submit` | Thread-pool dispatch for callbacks — keep async boundary unchanged |
| `make_db_ctx` in `tests/conftest.py` | Mock DB for records tests |

### Alternatives Considered

| Instead of | Could use | Tradeoff |
|------------|-----------|----------|
| DB columns for sec/exchange/ccy | Infer Forex from `symbol` string (e.g. `EUR.USD`) in `get_positions()` only | Fragile, duplicates parsing rules, worse for FUT/OPT |
| Only `localSymbol` fix | Skip DB columns | Still wrong `secType`/`currency` in API — **fails RUNT-02 (2)** |

**Version verification:** `ib_insync>=0.9.86`, `psycopg2-binary>=2.9.9` from `backend_api_python/requirements.txt` (no separate pin file).

## Architecture Patterns

### Data flow (focused model)

```
IBKR positionEvent / updatePortfolio / pnlSingleEvent
    → client callbacks fill _conid_to_symbol + call records.ibkr_save_position
    → qd_ibkr_pnl_single (account, con_id, symbol, …, sec_type, exchange, currency)
    → get_positions() maps row → API dict (symbol, quantity, secType, exchange, currency, …)
```

**Cohesion:** One table (`qd_ibkr_pnl_single`) already holds **per-instrument** PnL/position aggregates (naming is historical). Adding contract metadata here is **the same aggregate row** — not a second parallel store.

### Recommended touchpoints

| Location | Change |
|----------|--------|
| `client.py` `_on_update_portfolio` | Use `localSymbol or symbol` for map + `ibkr_save_position`; pass sec/exchange/ccy from `item.contract` |
| `client.py` `_on_position` | Same for `position.contract` |
| `client.py` `_on_pnl_single` | Consumes `_conid_to_symbol` only for `symbol` string — **must** be filled by earlier events with correct key |
| `client.py` `get_positions` | Replace hardcoded `STK`/`SMART`/`USD` with DB fields + fallback |
| `records.py` | Schema ensure, `ibkr_save_position`, `ibkr_get_positions`, **`ibkr_save_pnl` bugfix** |

### Anti-patterns to avoid

- **Inferring Forex from `symbol` alone in API** without DB fields — duplicates Phase 1 logic and breaks non-Forex-like symbols.
- **Using `contract.symbol` alone for Forex labels** — breaks alignment with Phase 1 display and strategy keys.

## Architecture Review (CONTEXT.md — three proposals)

### Focused vs “shotgun”

| Criterion | Verdict |
|-----------|---------|
| **Single core problem?** | **Yes.** All three changes address **IBKR portfolio snapshot correctness**: stable symbol label (`localSymbol`), **non-equity** contract metadata for API consumers, and a **broken** `ibkr_save_pnl` in the same persistence layer. |
| **Independent one-offs?** | **No.** (1) and (3) are **tightly coupled**: `_on_pnl_single` resolves `symbol` from `_conid_to_symbol` populated by (3); `get_positions` metadata needs (1). (2) is **not Forex-feature work** but is **same module / same phase risk surface** and fixes a **production-broken** function. |

### Per-proposal necessity and risk

| # | Proposal | Necessary for RUNT-02? | Risk | Verdict |
|---|-----------|-------------------------|------|---------|
| **1** | `qd_ibkr_pnl_single` + `sec_type`/`exchange`/`currency` + `get_positions` reads DB | **Yes** for success criterion **(2)** — removes equity-only hardcoding in ```1313:1324:backend_api_python/app/services/live_trading/ibkr_trading/client.py``` | Low: additive columns, ON CONFLICT upsert extended; **must** update INSERT column list and COALESCE rules consistently | **Keep — core** |
| **2** | Remove dead lines in `ibkr_save_pnl` | **Not strictly Forex**; **yes** for correct `qd_ibkr_pnl` account row updates | Very low — delete 3 lines; add test calling real function | **Keep — mandatory bugfix** (verified: real call raises `UnboundLocalError`) |
| **3** | `localSymbol or symbol` for map + saves | **Yes** for success criterion **(1)** — Forex currently stores `"EUR"` instead of `"EUR.USD"` | Low for STK/HK (`localSymbol` == `symbol`); **tests** that assert exact map keys (e.g. `GOOGL`) unchanged if `localSymbol` unset | **Keep — core** |

### Minimal viable change set for RUNT-02

- **Cannot drop (3)** — symbol key requirement fails.
- **Cannot drop (1)** — `get_positions()` still lies about `secType`/`currency` without persisted fields (unless you re-query IB per row — **don’t hand-roll**).
- **Should not drop (2)** — leaving `ibkr_save_pnl` broken wastes `_on_pnl` and any future integration test of real DB path.

**Optional deferral (not recommended):** Move (2) to a tiny hotfix only if release process forbids mixing; functionally it should ship with Phase 10.

### Impact: existing US / HK stock paths

- **`localSymbol or symbol`:** For listed stocks, IB typically sets `localSymbol` ≈ ticker; **behavior matches current tests** if mocks set `symbol` only (both resolve to same string). Add **`localSymbol`** on mocks in new Forex tests; optionally set `localSymbol=symbol` on stock mocks for explicitness.
- **DB columns:** Legacy rows have empty new fields → **`get_positions()` fallback** to `STK`/`SMART`/`USD` preserves prior API behavior for old data.
- **`ibkr_save_position` INSERT:** New columns need defaults in SQL or Python (`''`) so partial callers remain valid.

### Future: FUT, OPT

- **`sec_type` + `exchange` + `currency`** columns are the **right granularity** — same `(account, con_id)` key works; no Forex-specific branching in schema.
- **Extension cost:** Low if all product types funnel through the same callbacks with `Contract` populated; **higher** if later instruments need fields not on `Contract` (then consider a JSON `extra` column — **out of scope**).

### More focused alternative?

- **There is no smaller coherent fix** that meets both (1) and (2) of phase success criteria without either **DB metadata** or **re-fetching ContractDetails** on every `get_positions()` call (heavy, fragile offline).

### Hidden coupling

- **Routes:** `app/routes/ibkr.py` exposes `client.get_positions()` — consumers receive `secType`/`currency`; document behavior change for Forex.
- **`sync_positions` / `get_positions_normalized`:** Uses `quantity` and `symbol` from `get_positions()`; **side** is derived from qty sign — still valid for FX **lots in base currency**; verify runners don’t assume “shares”.
- **`_handle_fill`:** Uses `ctx.symbol` from order context — **unchanged**; aligns with CONTEXT.md if order path already uses normalized Forex symbol.

## Use Case Specifications

Detailed specs for planning and verification (IDs are suggestions; planner may rename).

### UC-FP1 — Forex `localSymbol` in position event

| Field | Content |
|-------|---------|
| **ID** | UC-FP1 |
| **Description** | `_on_position` stores strategy/API-facing symbol `EUR.USD`, not base `EUR`. |
| **Preconditions** | Mock `position.contract` with `conId>0`, `secType=CASH`, `symbol=EUR`, `localSymbol=EUR.USD`, `exchange=IDEALPRO`, `currency=USD`, `position≠0`. |
| **Input** | `client._on_position(position)` |
| **Expected** | `_conid_to_symbol[conId] == "EUR.USD"`; `ibkr_save_position` called with `symbol="EUR.USD"` and new metadata args matching contract. |
| **Boundaries** | `localSymbol` missing → fallback to `symbol`; both empty → `""`. |

### UC-FP2 — Forex `updatePortfolio` map + DB

| Field | Content |
|-------|---------|
| **ID** | UC-FP2 |
| **Description** | `_on_update_portfolio` uses same label + metadata rules as `_on_position`. |
| **Input** | Mock `item` with `account`, `contract` as Forex, `position`, PnL fields. |
| **Expected** | Map key uses `EUR.USD`; `ibkr_save_position` includes `sec_type=CASH`, `exchange=IDEALPRO`, `currency=USD` (or IB-provided strings). |

### UC-FP3 — `pnlSingle` uses map for symbol

| Field | Content |
|-------|---------|
| **ID** | UC-FP3 |
| **Description** | After UC-FP1 populates map, `_on_pnl_single` saves `symbol` from map for same `conId`. |
| **Input** | `pnl_single` mock with same `conId`, numeric fields. |
| **Expected** | `ibkr_save_position(..., symbol="EUR.USD", ...)`. |
| **Boundaries** | Map empty → `symbol==""` (existing test behavior); document ordering dependency (position/portfolio before pnlSingle). |

### UC-FP4 — `get_positions` Forex metadata

| Field | Content |
|-------|---------|
| **ID** | UC-FP4 |
| **Description** | API dict exposes non-equity metadata for Forex row. |
| **Input** | `ibkr_get_positions` returns one row: `symbol=EUR.USD`, `position=10000`, `sec_type=CASH`, `exchange=IDEALPRO`, `currency=USD`, realistic PnL fields. |
| **Expected** | `result[0]["secType"]=="CASH"`, `exchange=="IDEALPRO"`, `currency=="USD"`, `quantity==10000` (base units). |
| **Boundaries** | Missing new columns → fallback `STK`/`SMART`/`USD`. |

### UC-FP5 — Stock regression (HK/US)

| Field | Content |
|-------|---------|
| **ID** | UC-FP5 |
| **Description** | US/HK row still returns `secType` STK and appropriate exchange/currency when DB holds those values. |
| **Input** | Mock row `sec_type=STK`, `exchange=SMART`, `currency=USD`, `symbol=AAPL`. |
| **Expected** | Same as today’s semantics; no accidental `CASH`. |

### UC-FP6 — `ibkr_save_pnl` executes without exception

| Field | Content |
|-------|---------|
| **ID** | UC-FP6 |
| **Description** | Real `ibkr_save_pnl` body runs with DB mocked — no `UnboundLocalError`. |
| **Input** | `make_db_ctx` + patch `get_db_connection`; call `ibkr_save_pnl(account=..., daily_pnl=1, unrealized_pnl=2, realized_pnl=3)`. |
| **Expected** | Returns `True` (or `False` only on intentional DB error), **never raises**. |

### UC-FP7 — Round-trip lifecycle (integration-style, mocks)

| Field | Content |
|-------|---------|
| **ID** | UC-FP7 |
| **Description** | Single test chains: `_on_position` → `_on_pnl_single` (optional `_on_update_portfolio`) → assert `get_positions` dict. |
| **Expected** | Symbol and metadata consistent end-to-end. |

## Don't Hand-Roll

| Problem | Don’t build | Use instead | Why |
|---------|-------------|-------------|-----|
| Forex pair parsing in `get_positions` | String heuristics for `EUR.USD` | Persist `Contract` fields from IB events | Single source of truth; matches FUT/OPT later |
| Re-qualify contract on every read | Extra `reqContractDetails` per row | Event-time persistence | Latency, rate limits, connection coupling |
| Custom symbol map separate from IB | Parallel registry | `localSymbol or symbol` + conId key | `conId` already unique |

## Common Pitfalls

### Pitfall 1: `_on_pnl_single` avgCost derivation

**What goes wrong:** `avg_cost = value / position` (see ```757:757:backend_api_python/app/services/live_trading/ibkr_trading/client.py```) is equity-style. For Forex, `position` is base size and `value` is quote notional — ratio may track an **implied price**, but is not the same as equity avg cost.

**How to avoid:** Phase 10 **does not need to “fix” FX pricing semantics** for RUNT-02 if success criteria focus on **keys and currency context**; treat as **documentation + future refinement**. Add a LOW-confidence note in verification: compare to IB TWS for one paper pair.

### Pitfall 2: Event ordering

**What goes wrong:** `_on_pnl_single` before `_on_position` → empty `_conid_to_symbol`.

**How to avoid:** Tests should either populate map first or accept empty symbol and document IB ordering; optional **backfill** from `entry` is **not** available on `PnLSingle` (no `Contract`).

### Pitfall 3: Migration on old DBs

**What goes wrong:** `CREATE TABLE IF NOT EXISTS` does not add new columns.

**How to avoid:** Explicit `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` after create, once per deploy.

### Pitfall 4: Tests that patch away the bug

**What goes wrong:** `ibkr_save_pnl` never exercised — production bug invisible.

**How to avoid:** UC-FP6 direct test of real function.

## Code Examples

### `localSymbol` label (prescriptive)

```python
# Pattern for contract label (Forex + others)
label = (getattr(contract, "localSymbol", None) or getattr(contract, "symbol", None) or "").strip()
```

### `get_positions` metadata (conceptual)

```python
sec_type = (row.get("sec_type") or "").strip() or "STK"
exchange = (row.get("exchange") or "").strip() or "SMART"
currency = (row.get("currency") or "").strip() or "USD"
```

*(Exact keys depend on `ibkr_get_positions` dict normalization — match `records.py` cursor output.)*

## State of the Art

| Old approach | Current approach | Notes |
|--------------|------------------|-------|
| Equity-only `get_positions` | DB-stored `secType`/`exchange`/`currency` | Required for Forex + scalable |
| `contract.symbol` for Forex | `localSymbol or symbol` | Aligns with Phase 1 display |

## Open Questions

1. **PnLSingle `value` semantics for Forex vs equity** — Partially documented by IB; treat display as best-effort until paper validation.
2. **Whether `updatePortfolio` or `positionEvent` wins on race** — LOW priority; last writer wins at DB layer today.

## Validation Architecture

> `workflow.nyquist_validation` is enabled in `.planning/config.json`.

### Test framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | none (markers in `tests/conftest.py`) |
| Quick run | `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -x --tb=short` |
| Full IBKR slice | `python -m pytest tests/test_ibkr_client.py tests/test_ibkr_order_callback.py -x` |

### Phase requirements → test map

| Req ID | Behavior | Test type | Automated command | Wave 0 |
|--------|----------|-----------|---------------------|--------|
| RUNT-02 | Forex symbol + metadata in callbacks/API | unit | `pytest tests/test_ibkr_client.py -k "FP or position or pnl_single or get_positions" -x` | Add new tests per UC-FP* |
| RUNT-02 | `ibkr_save_pnl` no crash | unit | `pytest tests/ -k "ibkr_save_pnl" -x` | Add `test_records_ibkr_save_pnl` if new file |

### Wave 0 gaps

- [ ] Direct **`ibkr_save_pnl`** test (mock `get_db_connection`) — UC-FP6
- [ ] **Forex** fixtures on `Contract` mocks (`localSymbol`, `secType`, …)
- [ ] Update **`test_get_positions_reads_from_database`** assertions when `secType`/`exchange`/`currency` become data-driven (optional explicit expected fields)

## Sources

### Primary (HIGH confidence)

- Repository code: `backend_api_python/app/services/live_trading/ibkr_trading/client.py`, `records.py`, `tests/test_ibkr_client.py`
- Runtime verification: `ibkr_save_pnl` raises when called (2026-04-11, local Python run)

### Secondary (MEDIUM)

- Phase CONTEXT: `.planning/phases/10-fills-position-pnl-events/10-CONTEXT.md`
- Requirements: `.planning/REQUIREMENTS.md` (RUNT-02)

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — matches repo dependencies and patterns  
- Architecture / CONTEXT evaluation: **HIGH** — grounded in line-level code review  
- IBKR numeric semantics (`value`/`position` for FX): **MEDIUM** — needs optional paper validation  

**Research date:** 2026-04-11  
**Valid until:** ~30 days (stable domain); re-check if `ib_insync` or IB API fields change  
