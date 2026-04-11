# Phase 05: Signal-to-side mapping (two-way FX) - Research

**Researched:** 2026-04-10  
**Domain:** Strategy signal → `buy`/`sell` mapping for IBKR Forex vs equities; `BaseStatefulClient` API evolution  
**Confidence:** HIGH (code + IB API docs); MEDIUM (exact `market_category` string casing in production configs)

## Summary

Phase 05 implements **EXEC-02**: extend `map_signal_to_side` with `*, market_category: str = ""`, pass `OrderContext.market_category` from `StatefulClientRunner.execute`, and teach **IBKRClient** to use the same eight-signal table as **MT5Client** when `market_category == "Forex"`, while keeping the existing **short-signal rejection** for non-Forex IBKR use cases (stocks). The mapping **open_short→sell, close_short→buy** (and add/reduce short) matches **IB spot FX mechanics**: orders use **`action` BUY or SELL** on the pair ([TWS API `Order` / basic orders](https://interactivebrokers.github.io/tws-api/classIBApi_1_1Order.html)); there is no equity-style short locate—**selling the base vs buying the base** is expressed as SELL vs BUY.

**Primary recommendation:** Implement Option A as locked: update the abstract method on `BaseStatefulClient`, thread `market_category` from the runner, implement the Forex branch in `IBKRClient` only, and add `*, market_category: str = ""` to **MT5Client**, **EFClient**, and **USmartClient** (ignore the parameter). Update IBKR tests for the new Chinese error string and add table-driven Forex coverage plus one runner-level test (UC-R1).

<user_constraints>
## User Constraints (from 05-CONTEXT.md)

### Locked Decisions

- Extend `BaseStatefulClient.map_signal_to_side` with **keyword-only** `*, market_category: str = ""`.
- **Semantic alignment:** `market_category` matches `OrderContext.market_category` (e.g. `"Forex"`, `"USStock"`).
- **Runner:** `client.map_signal_to_side(ctx.signal_type)` → `client.map_signal_to_side(ctx.signal_type, market_category=ctx.market_category or "")` (or equivalent strip).
- **All `BaseStatefulClient` subclasses** update signatures in Phase 5; non-IBKR implementations **ignore** `market_category` (behavior unchanged vs single-arg).
- **Backward compatibility:** default `market_category=""` preserves current IBKR behavior (short signals still raise unless `market_category="Forex"`).
- **Signal set for Forex:** align with MT5 — eight signals including `add_short` / `reduce_short`.
- **Forex mapping table:** as in CONTEXT (open/add/reduce long + four short-side signals).
- **Non-Forex:** if `"short" in signal_type`, `ValueError` with explicit copy e.g. `"IBKR 美股/港股不支持 short 信号: {signal_type}"`; update tests that match the old English message.
- **Forex:** do not reject merely because of `"short"` in the name; reject only if not in map (`Unsupported signal_type`).

### Claude's Discretion

- Internal structure of `_SIGNAL_MAP` (split dicts vs merge) and test class naming (`TestIBKRSignalMapping` vs `TestIBKRSignalMappingForex`).

### Deferred Ideas (OUT OF SCOPE)

- (None additional; items previously deferred are now in scope per CONTEXT.)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXEC-02 | `map_signal_to_side` supports Forex two-way (`open_long`→BUY, `close_long`→SELL, `open_short`→SELL, `close_short`→BUY) | Forex branch + MT5-aligned table; IB uses BUY/SELL on spot FX ([TWS API orders](https://interactivebrokers.github.io/tws-api/order_submission.html)) |
</phase_requirements>

## Standard Stack

### Core

| Library / artifact | Version | Purpose | Why Standard |
|--------------------|---------|---------|--------------|
| Python | 3.10+ (per project) | Runtime | Repo backend |
| `pytest` | project lockfile | Unit tests | Existing `tests/` |
| `ib_insync` | project dep | IBKR API wrapper | `IBKRClient` already uses `MarketOrder(action=...)` |

**Installation:** (no new packages for this phase)

**Version verification:** N/A — no new dependencies.

## Architecture Patterns

### Recommended flow

1. **`base.py`:** Change abstract `map_signal_to_side(self, signal_type: str, *, market_category: str = "") -> str`.
2. **`stateful_runner.py`:** Pass `market_category=ctx.market_category or ""` into `map_signal_to_side` (optional: `.strip()` on category for robustness — see pitfalls).
3. **`IBKRClient.map_signal_to_side`:** If `market_category.strip() == "Forex"` (recommend matching CONTEXT exactly first; see pitfalls), use full eight-signal map; else existing long-only map + `"short" in sig` guard + new Chinese message.
4. **Other engines:** `MT5Client`, `EFClient`, `USmartClient` — add `*, market_category: str = ""`, unused.

### Pattern: Keyword-only context for backward compatibility

**What:** Only-keyword `market_category` avoids accidental positional misuse and keeps old call sites valid.

**When to use:** Extending shared runner-facing APIs without breaking tests that call `map_signal_to_side("open_long")`.

**Example:**

```python
def map_signal_to_side(self, signal_type: str, *, market_category: str = "") -> str:
    ...
```

### Anti-patterns to avoid

- **Branching on `market_type` inside `map_signal_to_side` for IBKR:** Runner already passes `market_type` to `place_market_order`; signal mapping should follow locked **`market_category`** from strategy context, not re-derive from payload (avoids split-brain if configs diverge).
- **Reusing `"short" in sig` for Forex:** Would block legitimate `open_short`; Forex must take the table path first when category is Forex.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IB order side | Custom semantics | `action` **BUY** / **SELL** via existing `place_market_order` | IB API contract; already implemented |
| Eight-signal meanings | New naming | Same keys as `MT5Client._SIGNAL_MAP` | Single mental model across engines |

**Key insight:** The “short” vocabulary is **strategy-level**; IBKR execution remains standard BUY/SELL on the IDEALPRO pair.

## Common Pitfalls

### Pitfall 1: `market_category` string mismatch (`"forex"` vs `"Forex"`)

**What goes wrong:** Strategy or DB stores lowercase; `market_category == "Forex"` fails; short signals hit the equity rejection path.

**Why it happens:** `pending_order_worker` sets `market_category = str(cfg.get("market_category") or "Crypto").strip()` without normalizing case.

**How to avoid:** Either document **exact** `"Forex"` for IBKR Forex strategies, or normalize in `map_signal_to_side` with `market_category.strip().lower() == "forex"` for the Forex branch (user discretion — not locked either way).

**Warning signs:** Tests pass with literal `"Forex"`; production orders still get `ibkr_unsupported_signal` for shorts.

### Pitfall 2: Runner passes category only from `ctx.market_category`

**What goes wrong:** If some code path built `OrderContext` with empty `market_category` but put `"Forex"` in `payload`, `execute` today still resolves `market_type` for orders from a **fallback chain** (`ctx.market_category or payload...`), but **`map_signal_to_side` would only receive the kwarg from `ctx.market_category`** unless you align them.

**Why it happens:** Asymmetry between lines 64–70 (`market_type` for order) vs planned mapping call.

**How to avoid:** Rely on **worker** path: `OrderContext(..., market_category=market_category, ...)` is populated from strategy config ([`pending_order_worker.py`](../../../backend_api_python/app/services/pending_order_worker.py) ~374–381). For Forex, ensure strategy `market_category` is set to `Forex`. Optionally extend runner to pass the same merged string for mapping as for `market_type` — **out of scope unless you discover a real caller that omits `ctx.market_category`**.

### Pitfall 3: Tests matching substring `"short"`

**What goes wrong:** `pytest.raises(..., match="short")` still passes after message change.

**Why it happens:** Loose match hides regression in exact user-facing copy.

**How to avoid:** Use `match=` on the **new** Chinese substring as in UC-E1/E2.

## Code Examples

### IBKRClient Forex branch (illustrative)

```python
def map_signal_to_side(self, signal_type: str, *, market_category: str = "") -> str:
    sig = (signal_type or "").strip().lower()
    cat = (market_category or "").strip()
    if cat == "Forex":
        side = _FOREX_SIGNAL_MAP.get(sig)  # 8 keys, same as MT5
        if side is None:
            raise ValueError(f"Unsupported signal_type for IBKR: {signal_type}")
        return side
    if "short" in sig:
        raise ValueError(f"IBKR 美股/港股不支持 short 信号: {signal_type}")
    side = self._SIGNAL_MAP.get(sig)
    ...
```

### Runner call site

```python
action = client.map_signal_to_side(
    ctx.signal_type,
    market_category=(ctx.market_category or "").strip(),
)
```

(Source: [`stateful_runner.py`](../../../backend_api_python/app/services/live_trading/runners/stateful_runner.py) `execute`.)

## Use Case Validation

### Coverage vs proposed UC-F1–F6, UC-E1–E3, UC-R1, REGR-01

| UC | Verdict | Notes |
|----|---------|-------|
| UC-F1–F4 | **Complete** | Core Forex long/short open/close mapping. |
| UC-F5–F6 | **Complete** | Matches MT5 and locked table. |
| UC-E1–E2 | **Complete** | Default and explicit non-Forex category; message must match implementation exactly. |
| UC-E3 | **Complete** | Regression for long-only path without kwarg. |
| UC-R1 | **Recommended** | No existing `StatefulClientRunner` unit test in `tests/test_runners.py` (that file covers **strategy** runners). Add a focused test under `tests/` that mocks `IBKRClient.map_signal_to_side` or uses a stub client — validates wiring **once**. |
| REGR-01 | **Complete** | Full `pytest tests/` gate. |

### Edge cases **not** explicitly listed — add to plan if you want belt-and-suspenders

| Scenario | Expected behavior | Priority |
|----------|-----------------|----------|
| UC-F7 | `add_long` / `reduce_long` with `market_category="Forex"` → buy / sell | **Should** match table (already in locked mapping; UC-F1–F6 don’t name them — add two rows in table-driven test or accept PARAMETRIZE over all eight). |
| UC-E4 | `open_short` + `market_category="HShare"` | Same ValueError as UC-E2 (message says 港股). |
| UC-E5 | Unknown signal + `market_category="Forex"` (e.g. `foo_short`) | `"short" in sig` → if not in map, **Unsupported** (not the 美股/港股 message). Current design: Forex path uses map first; unknown key → `Unsupported signal_type`. |
| UC-E6 | `market_category=" forex "` (spaces) | Strip → treat as Forex if you normalize; **document** if strict equality only. |

**Verdict:** Proposed UCs are **sufficient for v1** if table-driven tests include **all eight** Forex keys (not only six “short-side” rows). Naming “six Forex short signals” in CONTEXT is shorthand; **add_long/reduce_long** must stay correct for Forex.

## Change Reasonableness

### Option A (extend base + runner)

| Criterion | Assessment |
|-----------|--------------|
| Minimal diff | **Yes** — one abstract signature, one call site, four subclasses, IBKR logic. |
| Correct layering | **Yes** — `OrderContext` already carries `market_category`; worker sets it from strategy config. |
| Alternative (only IBKR overload) | **Rejected** — would break LSP / abstract contract and invite inconsistent overrides. |

### Error message + test updates

| Criterion | Assessment |
|-----------|--------------|
| Reasonable | **Yes** — aligns UX with Chinese codebase and clarifies scope (US/HK equities vs Forex). |
| Test churn | **Expected** — `TestIBKRSignalMapping.test_short_rejected` / `test_close_short_rejected` and any `match=` on old English string. **Also grep** the repo for the old message: `IBKR stock trading does not support short signals`. |

### Subclass impact (complete inventory)

**Confirmed subclasses of `BaseStatefulClient` (repo grep):**

| Class | File | Action |
|-------|------|--------|
| `IBKRClient` | `ibkr_trading/client.py` | Implement Forex table + new message |
| `MT5Client` | `mt5_trading/client.py` | Add kwarg only (ignore) |
| `EFClient` | `ef_trading/client.py` | Add kwarg only; returns `"sale"` unchanged |
| `USmartClient` | `usmart_trading/client.py` | Add kwarg only; keep short rejection |

**No additional subclasses found** beyond these four.

### Runner safety / backward compatibility

- **Call site:** Adding a keyword argument with default is **source-compatible** for any external caller that only passes `signal_type`.
- **Behavior:** Default `market_category=""` preserves IBKR equity path — **safe**.
- **`pre_check`:** Uses `_is_close_signal` including `close_short`; for Forex, close-short is valid — **RTH skip for close signals still applies** (no change required for Phase 5).

## IBKR spot Forex: “bidirectional” / short-style flows

| Question | Answer | Confidence |
|----------|--------|------------|
| Does spot FX use BUY and SELL for both directions? | **Yes** — IB order `action` is BUY or SELL for the contract ([TWS API `Order`](https://interactivebrokers.github.io/tws-api/classIBApi_1_1Order.html)). | HIGH |
| Is equity “short sale” locate required for IDEALPRO pairs? | **No** — not the same product as stock shorting; you sell or buy the pair per margin rules. | HIGH (market structure) |
| Can accounts be restricted from FX or from selling? | Possibly — **permissions / margin** are account-level; mapping correctness ≠ guarantee of fill. | MEDIUM (ops) |

**Mapping correctness:** For a pair quoted as BASE.QUOTE (IB `Forex` / IDEALPRO), strategy naming **open_short → SELL** and **close_short → BUY** is consistent with **selling base / buying base** language used across FX platforms and matches **MT5Client** in this repo.

## State of the Art

| Old approach | Current approach | Impact |
|--------------|------------------|--------|
| IBKR `map_signal_to_side` rejects any `"short"` substring | Category-aware Forex table | Unblocks EXEC-02 |
| Generic English error | Explicit 美股/港股 copy | Clearer operator debugging |

**Deprecated/outdated:** Treating IBKR Forex like single-stock equity for signal gating.

## Open Questions

1. **Normalize `market_category` case for Forex?**  
   - What we know: Worker uses raw strategy string.  
   - What’s unclear: Whether all configs use exact `"Forex"`.  
   - Recommendation: Table tests use `"Forex"`; add one optional test for `"forex"` if normalization is implemented.

2. **Runner should merge `market_category` from payload when `ctx.market_category` is empty?**  
   - What we know: `execute` already merges for `market_type` only.  
   - Recommendation: **Defer** unless integration tests show a gap.

## Validation Architecture

> `workflow.nyquist_validation` is enabled in `.planning/config.json`.

### Test framework

| Property | Value |
|----------|-------|
| Framework | `pytest` |
| Config file | none (implicit) — see `tests/conftest.py` |
| Quick run | `cd backend_api_python && python -m pytest tests/test_exchange_engine.py -q --tb=line` |
| Full suite | `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` |

### Phase requirements → test map

| Req ID | Behavior | Test type | Automated command | File exists? |
|--------|----------|-----------|-------------------|--------------|
| EXEC-02 | Forex eight-signal mapping | unit/parametrize | `pytest tests/test_exchange_engine.py -k IBKR -q` | Extend existing |
| EXEC-02 | Non-Forex short rejection message | unit | same file | Update `match=` |
| EXEC-02 | Runner passes `market_category` | unit | `pytest tests/... -k stateful` (new) | ❌ Wave 0 — add test module or extend `test_exchange_engine` |

### Sampling rate

- **Per task commit:** targeted pytest for touched files + IBKR mapping tests.
- **Phase gate:** full `tests/` per REGR-01.

### Wave 0 gaps

- [ ] `StatefulClientRunner.execute` + `OrderContext(market_category="Forex", signal_type="open_short")` → mock client records `map_signal_to_side` kwargs or assert resulting `side` — covers UC-R1.
- [ ] Parametrize all **eight** Forex signals for IBKR (includes `add_long`, `reduce_long`).

## Sources

### Primary (HIGH confidence)

- [TWS API: `Order` / action](https://interactivebrokers.github.io/tws-api/classIBApi_1_1Order.html) — BUY/SELL for orders.
- [TWS API: Placing orders](https://interactivebrokers.github.io/tws-api/order_submission.html) — order submission flow.
- Repo: `MT5Client._SIGNAL_MAP`, `IBKRClient.map_signal_to_side`, `StatefulClientRunner.execute`, `pending_order_worker` `OrderContext` construction.

### Secondary (MEDIUM confidence)

- [IBKR Campus: IdealPro glossary](https://www.interactivebrokers.com/campus/glossary-terms/idealpro/) — IDEALPRO = spot FX venue (terminology only).

### Tertiary (LOW confidence)

- Web search snippets on margin — use account permissions checklist in ops, not blocking for mapping implementation.

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — no new deps.
- Architecture: **HIGH** — aligns with existing `OrderContext` and worker.
- Pitfalls: **MEDIUM** — `market_category` casing is the main real-world gap.
- IBKR FX “short”: **HIGH** for API mechanics; **MEDIUM** for account eligibility.

**Research date:** 2026-04-10  
**Valid until:** ~30 days (stable domain); re-check if IBKR changes FX order API.
