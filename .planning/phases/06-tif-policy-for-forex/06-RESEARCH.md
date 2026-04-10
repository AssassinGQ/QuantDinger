# Phase 6: TIF policy for Forex - Research

**Researched:** 2026-04-10  
**Domain:** IBKR TWS API time-in-force (IOC/DAY/GTC) for spot FX (CASH / IDEALPRO), `IBKRClient._get_tif_for_signal`  
**Confidence:** HIGH (API docs + codebase); MEDIUM (venue-specific edge cases — confirm in paper as planned)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **所有 Forex 信号统一使用 `"IOC"`**（不区分 open/close/add/reduce）。
- **美股（USStock）**：open → DAY, close → IOC — **不改**。
- **港股（HShare）**：open → DAY, close → DAY — **不改**。
- **不加 TIF fallback**；IB 拒单走现有 `_handle_reject`。
- **`_get_tif_for_signal` 签名不变**（已有 `market_type`）。

### Claude's Discretion

- Forex 分支代码位置（方法顶部 early return 或 elif）。
- 测试类命名、参数化 vs 独立用例。

### Deferred Ideas (OUT OF SCOPE)

- 美股/港股 open 改 IOC（后续 phase）。
- IOC 被拒后自动改 DAY 重试。
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **EXEC-03** | `_get_tif_for_signal` 有 Forex 专属分支，根据 paper 验证结果设定正确的 TIF（DAY/IOC/GTC） | 用户锁定 **Forex → IOC**；IBKR Campus 文档：**MKT** 订单在 TWS API 中与 **IOC** 一致；**Market** 订单 **Products** 含 **CASH**（现货外汇）。实现上在 `_get_tif_for_signal` 内对 `market_type == "Forex"` **early return `"IOC"`** 即可满足 EXEC-03；paper 验证用于确认运行时拒单率与成交行为可接受（STATE.md 已标记关注点）。 |
</phase_requirements>

## Summary

Interactive Brokers’ **IBKR Campus** order-types documentation states that, for the **TWS API**, **“MKT Orders only support ‘IOC’”** (general constraint section), while the **Market** order type lists **Products: … CASH …** (spot FX alongside STK, FUT, etc.). That combination is sufficient to treat **IOC on `MarketOrder` for `secType=CASH` (IDEALPRO spot FX)** as **first-class API behavior**, not an unsupported combination. Your codebase already passes `tif` into `ib_insync.MarketOrder` / `LimitOrder`; Phase 6 only changes the string returned for Forex.

**Partial fills:** IOC is defined as execute immediately what is available and **cancel the rest**. The IB **order status** stream can show **partial fill then cancellation**; your event path already treats **`Cancelled` with `filled > 0`** as a fill scenario (`TestEventCallbacks.test_on_order_status_cancelled_with_fill_triggers_handle_fill`), which matches typical IOC partial-fill semantics.

**Implementation placement:** A **`market_type == "Forex"` branch at the top** of `_get_tif_for_signal` is the right pattern: it avoids entangling Forex with the existing `is_close` / HShare rules, matches the user decision (“all Forex signals → IOC”), and keeps non-Forex behavior identical without reordering the rest of the method.

**Use cases UC-T1–T8 / UC-E1–E3:** They **cover** all eight Forex signal types in `_FOREX_SIGNAL_MAP` and three non-Forex regressions. Optional gap: document **`signal_type` missing/empty** — today `place_*` uses `str(kwargs.get("signal_type", ""))`; after the Forex branch, **Forex + empty `signal_type` still yields IOC**, whereas non-Forex empty `signal_type` stays on the “open” path (DAY). If callers always pass `signal_type` for automated trading, this is informational only.

**Primary recommendation:** Implement **`if market_type == "Forex": return "IOC"`** as the first check in `_get_tif_for_signal`; extend tests so **`TestTifDay`** (or a dedicated Forex TIF test) asserts **`tif == "IOC"`** for Forex `place_market_order` / `place_limit_order` with mocked IB; keep **full `pytest tests/`** green (REGR-01). Retain **paper-account spot checks** for EXEC-03 acceptance, per IBKR’s own note that paper execution is simulated.

## Standard Stack

### Core

| Library / surface | Version | Purpose | Why Standard |
|-------------------|---------|---------|--------------|
| **ib_insync** | (project `requirements`) | `MarketOrder` / `LimitOrder` with `tif=` | Already used; maps to TWS API `Order` |
| **IBKR TWS API semantics** | Campus docs (current) | Valid `tif` for `MKT` / `LMT` | Authoritative for reject vs accept |

### Supporting

| Item | Purpose |
|------|---------|
| **`pytest`** | Existing `backend_api_python/tests/test_ibkr_client.py` patterns (`_make_client_with_mock_ib`, `TestTifDay`) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| IOC for all Forex | DAY for opens only | Conflicts with locked decision; IOC matches API doc emphasis on MKT + IOC |
| Custom TIF fallback | None | User explicitly deferred; adds risk and branching |

**Installation:** No new packages required for Phase 6.

**Version verification:** N/A for new deps; confirm `ib_insync` from project lock/requirements at implementation time.

## Architecture Patterns

### Recommended change shape

**What:** First-line guard in `_get_tif_for_signal`:

```python
if market_type == "Forex":
    return "IOC"
# existing is_close / HShare / default logic unchanged
```

**When to use:** Always for Phase 6 scope (EXEC-03 + user lock-in).

**Why here:** `place_market_order` and `place_limit_order` already compute `tif = self._get_tif_for_signal(signal_type, market_type)` — no signature or call-site change.

### Anti-patterns to avoid

- **Duplicating TIF logic** in `place_market_order` / `place_limit_order` — violates DRY and EXEC-03 single place of policy.
- **Adding automatic TIF retry** — explicitly out of scope and hides real reject causes.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IB order `tif` encoding | String tables per exchange | IB-documented `tif` values on `MarketOrder`/`LimitOrder` | TWS validates; hand-rolled mappings drift from API |
| Partial-fill aggregation | Custom IOC fill merger | Existing order status + `_on_order_status` / `_handle_fill` | IB sends authoritative `filled` / `remaining` / status |

**Key insight:** Phase 6 is **policy selection** (`str`), not execution mechanics.

## Common Pitfalls

### Pitfall 1: Assuming IOC always fully fills

**What goes wrong:** Remainder cancelled; strategy expects full size.

**Why it happens:** IOC definition + thin book (illiquid pair, session gap).

**How to avoid:** Rely on existing fill/reject paths; monitor `filled` vs requested size in ops (out of scope for this single method change).

**Warning signs:** `Cancelled` with `0 < filled < order size`; `remaining > 0` before terminal state.

### Pitfall 2: Paper vs live execution

**What goes wrong:** Paper acceptance assumed identical to live.

**Why it happens:** IBKR states paper is **simulated** (Campus order-types page).

**How to avoid:** Use paper for **functional** “order accepts IOC” checks; treat slippage/reject rates on live as follow-up monitoring.

### Pitfall 3: Forex market-hours vs IOC

**What goes wrong:** Order rejected or poor fill when **market not liquid** (e.g. weekly maintenance, holiday liquidity).

**Why it happens:** Session/holiday effects, not IOC-specific logic bugs.

**How to avoid:** **RUNT-01** (Forex `is_market_open` / liquid hours) is the right layer; Phase 6 only sets TIF.

**Warning signs:** Clustered rejects at session boundaries; aligns with STATE.md “paper validation” flag.

### Pitfall 4: Tests still titled “TIF = DAY” for all cases

**What goes wrong:** `TestTifDay` name/docstring implies every test is DAY-only.

**Why it happens:** Forex will assert IOC under the same harness.

**How to avoid:** Rename or split **`TestTifForex`** / **`TestTifPolicy`** when implementing (Claude’s discretion).

## Code Examples

### Policy branch (prescriptive)

```python
@staticmethod
def _get_tif_for_signal(signal_type: str, market_type: str = "USStock") -> str:
    if market_type == "Forex":
        return "IOC"
    is_close = signal_type in ("close_long", "close_short")
    if not is_close:
        return "DAY"
    if market_type == "HShare":
        return "DAY"
    return "IOC"
```

### Existing call sites (no change required)

TIF is already threaded into orders in `client.py` (~1068–1096, ~1138–1165): `tif=tif` on `MarketOrder` / `LimitOrder`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Forex followed stock open=DAY | Forex unified IOC | Phase 6 | Fewer surprise rests on book for FX automation |

**Deprecated/outdated:** N/A for this phase.

## Use Case Validation

### Coverage vs `_FOREX_SIGNAL_MAP` / regressions

| UC | Assertion | Complete? |
|----|-----------|-------------|
| UC-T1–T8 | Eight Forex signals → `"IOC"` | **Yes** — matches `open_long`, `add_long`, `close_long`, `reduce_long`, `open_short`, `add_short`, `close_short`, `reduce_short` |
| UC-E1–E3 | USStock / HShare regressions | **Yes** — preserves open/close/HShare close behavior |
| REGR-01 | Full pytest green | **Yes** — project standard |

### Optional / edge (document for planner; not required if callers always set `signal_type`)

- **Forex + empty `signal_type`:** After the Forex branch, result is **IOC** (not DAY). Non-Forex empty remains **DAY** (non-close path).
- **HShare + Forex:** N/A — mutually exclusive `market_type`.

### IBKR behavior questions (answered)

| Question | Answer | Confidence |
|----------|--------|------------|
| Does IDEALPRO / spot FX support IOC for market orders? | **API:** Market **MKT** applies to **CASH**; TWS API doc states **MKT uses IOC** for `tif`. | **HIGH** |
| Partial fill reporting? | Partial execution then cancel remainder — use **`filled` / `remaining`** and status; codebase treats cancelled-with-fills as fill path. | **HIGH** |
| Sunday open / holiday? | Liquidity/session issues affect **fill quality and rejects**, not IOC validity; mitigate with **hours checks** (later RUNT-01). | **MEDIUM** (operational) |

## Change Reasonableness

- **Minimal surface:** One method body (`_get_tif_for_signal`) + tests; **no** new public APIs, **no** fallback engine.
- **Aligned with IB docs:** Forex **MKT** + **IOC** matches Campus **MKT / IOC** guidance and **CASH** product coverage for Market orders.
- **Consistent with integration:** Call sites already pass `market_type`; Phase 5 already routes Forex signals — no new wiring.

## Open Questions

1. **STK `MKT` + `DAY` vs global “MKT only IOC” text**
   - **What we know:** Campus states **“MKT Orders only support ‘IOC’”** for the TWS API broadly; this repo’s USStock opens use **`DAY`** and are covered by tests.
   - **What’s unclear:** Product-specific allowances in TWS vs simplified doc.
   - **Recommendation:** **Do not change USStock/HShare** in Phase 6; treat the apparent tension as **pre-existing**; Forex move to **IOC** is **safer** relative to the published MKT/IOC rule.

2. **EXEC-03 wording “DAY/IOC/GTC”**
   - **Recommendation:** Implement **IOC** for Forex per lock-in; if requirements text must be literal, update **REQUIREMENTS.md** in planning to say “Forex → IOC (validated in paper)” to avoid ambiguity.

## Validation Architecture

> `workflow.nyquist_validation` is enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | **pytest** (project standard) |
| Config file | none at repo root; `backend_api_python/tests/conftest.py` |
| Quick run command | `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -x -q --tb=line` |
| Full suite command | `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| EXEC-03 | Forex `place_market_order` / `place_limit_order` sets `tif=IOC` | unit (mock IB) | `pytest tests/test_ibkr_client.py -k Tif -x` (or new class name) | Extend existing file |
| EXEC-03 | `_get_tif_for_signal` Forex matrix | unit | `pytest tests/test_ibkr_client.py::...` | Add methods |
| REGR-01 | No regressions | suite | `pytest tests/ -x -q --tb=line` | ✅ |

### Sampling Rate

- **Per task commit:** `pytest tests/test_ibkr_client.py -x -q --tb=line` (or targeted `-k`).
- **Per wave merge / phase gate:** full `pytest tests/` per CONTEXT.

### Wave 0 Gaps

- [ ] Add/extend tests for **`tif == "IOC"`** when `market_type=="Forex"` (market and limit paths if both in scope for EXEC-03).
- None blocking framework — **pytest** and `test_ibkr_client.py` already exist.

## Sources

### Primary (HIGH confidence)

- [IBKR Campus — Order Types](https://ibkrcampus.com/ibkr-api-page/order-types/) — Sections stating **MKT orders (TWS API) use IOC**; **Market** order **Products** includes **CASH**; **Forex** / **cashQty** notes for CASH.
- [IBKR — Market orders (customer-facing)](https://www.interactivebrokers.com/en/index.php?f=602) — Linked from Campus as general Market order definition (behavioral context).

### Secondary (MEDIUM confidence)

- [TWS API — Basic Orders](https://interactivebrokers.github.io/tws-api/basic_orders.html) — Deprecated hosting but historical IB structure; superseded by Campus for maintenance.

### Tertiary (LOW confidence — operational)

- Forum / anecdotal venue liquidity — use **paper/live** monitoring rather than as spec facts.

## Metadata

**Confidence breakdown:**

- Standard stack / API IOC + CASH: **HIGH** — Campus primary.
- IDEALPRO-specific exchange rule sheet: **MEDIUM** — not separately quoted; **CASH** + IB FX routing is standard; confirm in paper.
- Pitfalls (partial fill, hours): **HIGH** — standard market mechanics + existing code paths.

**Research date:** 2026-04-10  
**Valid until:** ~30 days for API text; re-check if IBKR Campus order-types page major revision.

---

## RESEARCH COMPLETE

**Phase:** 6 — TIF policy for Forex  
**Confidence:** **HIGH** (with MEDIUM on venue-specific live edge cases)

### Key Findings

- IBKR Campus documents **MKT** + **IOC** for TWS API and lists **CASH** under **Market** products — **IOC for Forex `MarketOrder` is API-aligned**.
- **`_get_tif_for_signal` Forex-first early return** is the correct, minimal integration point; **`place_market_order` / `place_limit_order` unchanged** at call site.
- **UC-T1–T8 + UC-E1–E3** are **comprehensive** for mapped signals; optional note on **empty `signal_type`** on Forex.
- **Partial IOC fills** map to existing **cancelled-with-fill → `_handle_fill`** behavior in tests.
- **Low-liquidity / session** issues are **operational** (mitigate with RUNT-01), not blockers to IOC policy selection.

### File Created

`.planning/phases/06-tif-policy-for-forex/06-RESEARCH.md`

### Ready for Planning

Research complete. Planner can author **06-01-PLAN.md** against EXEC-03 and locked constraints.
