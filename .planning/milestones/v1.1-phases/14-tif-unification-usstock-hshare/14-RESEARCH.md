# Phase 14: TIF unification (USStock/HShare) - Research

**Researched:** 2026-04-11  
**Domain:** IBKR Time-in-Force policy for US equities vs Hong Kong (SEHK) equities; pytest matrix testing  
**Confidence:** HIGH (IBKR primary source on SEHK + IOC); MEDIUM (MKT+IOC on SEHK not live-tested in this repo)

## Summary

Phase 14 aligns **USStock** open-signal TIF with Forex (**IOC**), keeps behavior explicit for **HShare**, and locks policy behind an **8×3 automated TIF matrix** (INFRA-02). The production decision point is `IBKRClient._get_tif_for_signal` in `backend_api_python/app/services/live_trading/ibkr_trading/client.py`; both `place_market_order` and `place_limit_order` pass its `tif` into `ib_insync` orders.

The **critical research question** was whether **SEHK / Hong Kong-listed stocks** actually support **IOC** on Interactive Brokers, because the current docstring claims *“Hong Kong stocks do not support IOC orders”* with no cited source.

**Finding (HIGH confidence):** Interactive Brokers publishes an official **“Exchanges For Order Type”** page for **IOC** that explicitly lists **Hong Kong Stock Exchange (SEHK)** under Asia/Pacific. That is direct vendor documentation that IOC is available for routing to SEHK—not a forum post. IB’s general IOC page also states that availability is **exchange- and product-specific** and that not every checkbox combination applies; the exchange list is the authoritative narrowing for “where IOC is supported.” Separately, third-party exchange connectivity documentation for HKEX (Trading Technologies) lists **IOC** among HKEX **Time-in-Force** restrictions for supported native order types, which corroborates exchange-level TIF support (MEDIUM confidence—vendor TT, not IB).

**Concrete recommendation:** **Adopt IOC for HShare for all signal types** (open/close/add/reduce), matching Forex/USStock policy, **unless** you later observe **IBKR order rejection** in paper/live for a specific **order type × TIF** pair (e.g. rare edge case). Update the docstring to **remove** the incorrect “HK does not support IOC” claim and **replace** it with a citation to IB’s IOC exchange list (and optional note that IOC does not support “fill outside RTH” per IB’s TIF help—same caveat as other markets). **Conservative fallback** (CONTEXT): if implementation/testing ever shows IB rejects IOC on SEHK, keep **DAY** for HShare and document the rejection text—CONTEXT already allows “uncertain → DAY.”

**Primary recommendation:** Implement **USStock `open_*` → IOC**; implement **HShare → IOC** with documentation citing [IBKR Exchanges for IOC](https://www.interactivebrokers.com/en/trading/order-type-exchanges.php?ot=ioc); extend/centralize pytest matrix **8 signals × 3 markets** on `_get_tif_for_signal` return values.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **USStock open 信号 TIF 策略**
  - USStock open 信号从 DAY 改为 **IOC** — 与 Forex 完全对齐
  - USStock close 信号保持 **IOC** — 现有行为不变
  - 静默切换，无需用户操作、无功能开关、无 warning 日志
  - 所有已有策略自动使用新 TIF 策略

- **HShare 例外处理**
  - **由 researcher 调查决定** — 当前代码注释声称"港股不支持 IOC"，但来源不确定，需要 research 阶段验证 SEHK 对 IOC 的实际支持情况
  - 如果 research 确认 HShare 支持 IOC → open/close 都改为 IOC
  - 如果 research 确认 HShare 不支持 IOC → 保持 DAY，代码注释说明原因（引用具体来源）
  - 如果不确定 → 保守策略保持 DAY
  - 无论哪种结果，都需要在代码和测试中明确记录 HShare 的 TIF 策略及其依据

- **TIF 矩阵测试**
  - 覆盖全部 **8 个信号类型** × **3 个市场**（Forex / USStock / HShare）= 24 种组合
  - 组织方式：单个 `TestTifMatrix` 类，使用 `pytest.mark.parametrize` 穷举所有组合
  - 每个组合明确断言预期的 TIF 值
  - 漂移防护：穷举矩阵测试，任何 TIF 变化都会被自动测试捕获
  - 现有的分散 TIF 测试（`TestTifForexPolicy`、`TestTifDay` 等）可以保留或由 Claude 决定是否合并

### Claude's Discretion

- HShare TIF 最终策略（基于 research 结果）
- 现有分散 TIF 测试是否合并到 `TestTifMatrix` 或保留
- `_get_tif_for_signal` 方法的具体重构方式（如需要）
- 是否为未知 market_type 添加 defensive raise

### Deferred Ideas (OUT OF SCOPE)

- **TIF fallback (IOC→DAY)** — ADV-01，v2 需求。如果 IOC 被 IBKR 拒绝，自动用 DAY 重试。本 phase 不实现。
- **HShare paper 验证** — 如果 research 无法确认 SEHK IOC 支持，后续可通过 paper 账号实际验证
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-02 | USStock open 信号 TIF → IOC（与 Forex 对齐），HShare 保持现有策略或明确记录例外，TIF 矩阵全面测试覆盖 | USStock→IOC matches CONTEXT; HShare→IOC justified by IBKR IOC/SEHK listing + tests/doc citation; matrix: parametrize 8×3 on `_get_tif_for_signal` |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | *(project env; `python -m pytest`)* | Unit tests for TIF matrix | Already used across `backend_api_python/tests/` |
| ib_insync | *(existing `requirements.txt`)* | `MarketOrder`/`LimitOrder` with `tif=` | Existing IBKR integration |

**Installation:** No new packages required for this phase unless planner adds typing/lint tooling—none identified.

**Version verification:** This phase does not introduce new npm/Python dependencies; use the repo’s existing `backend_api_python` environment.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| — | — | — | — |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Single matrix test class | Keep `TestTifDay` + `TestTifForexPolicy` only | Harder to see 24-cell policy at a glance; CONTEXT prefers one matrix class |

## Architecture Patterns

### Recommended shape

- **Single source of truth:** `_get_tif_for_signal(signal_type, market_type)` remains the only TIF policy function (already true).
- **Matrix test:** One class (e.g. `TestTifMatrix`) with `pytest.mark.parametrize` over `(signal_type, market_type)` and expected `tif`, covering all **8** signal types × **3** markets = **24** rows. Signal types must match existing tests: `open_long`, `add_long`, `close_long`, `reduce_long`, `open_short`, `add_short`, `close_short`, `reduce_short` (Forex uses the extended set; equity uses the long-only subset but the matrix still lists all 8 for Forex rows).

### Pattern: Expected TIF table driven test

**What:** Central dict or param list `(signal, market) -> "IOC"|"DAY"` used in one test.  
**When to use:** INFRA-02 drift prevention.  
**Example:**

```python
# Pattern only — align with actual policy after implementation
import pytest
from app.services.live_trading.ibkr_trading.client import IBKRClient

@pytest.mark.parametrize("signal_type,market_type,expected_tif", [
    # ... 24 rows ...
])
def test_tif_matrix(signal_type, market_type, expected_tif):
    assert IBKRClient._get_tif_for_signal(signal_type, market_type) == expected_tif
```

### Anti-patterns to avoid

- **Unsourced venue claims:** Do not repeat “HK does not support IOC” without evidence; IBKR lists SEHK under IOC exchanges (see Sources).
- **Silent policy drift:** Changing `_get_tif_for_signal` without updating the 24-cell matrix test.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Venue TIF rules | Custom inference | IBKR docs + optional paper reject log | Exchange rules change; IB documents IOC↔exchange mapping |
| Order construction | Ad-hoc TIF strings scattered | Keep `tif` only from `_get_tif_for_signal` | Already centralized in `client.py` |

## Common Pitfalls

### Pitfall 1: Stale docstring contradicting IBKR
**What goes wrong:** Comments claim SEHK cannot use IOC; planners implement DAY “by comment.”  
**Why it happens:** Legacy assumption without citation.  
**How to avoid:** Cite [IBKR IOC exchange list](https://www.interactivebrokers.com/en/trading/order-type-exchanges.php?ot=ioc) (SEHK listed).  
**Warning signs:** No URL in comment; mismatch between tests and IB help.

### Pitfall 2: IOC vs outside RTH
**What goes wrong:** IOC orders may not use “fill/trigger outside regular trading hours” (IB TIF help).  
**Why it happens:** Extended-hours expectations from US equities.  
**How to avoid:** If the product ever enables outside-RTH for HK, re-validate TIF with IB.  
**Warning signs:** IB error messages referencing TIF or session.

### Pitfall 3: Partial matrix coverage
**What goes wrong:** Only Forex or only USStock updated; HShare cells drift.  
**Why it happens:** Copy-paste from older test classes.  
**How to avoid:** Single parametrized matrix covering **24** combinations.  
**Warning signs:** Assertions scattered across classes with conflicting expectations.

## Code Examples

### Current TIF decision point (production)

```165:182:backend_api_python/app/services/live_trading/ibkr_trading/client.py
    @staticmethod
    def _get_tif_for_signal(signal_type: str, market_type: str = "USStock") -> str:
        """Get TIF (Time in Force) based on signal type and market type.

        For ``market_type == "Forex"``, all signals return ``"IOC"`` (no open/close
        distinction; aligns with IDEALPRO automation expectations).

        For non-Forex markets: non-close signals use ``"DAY"``; for close signals,
        ``"HShare"`` uses ``"DAY"`` (Hong Kong stocks do not support IOC orders);
        otherwise close uses ``"IOC"`` for pre/post-market execution.
        """
        if market_type == "Forex":
            return "IOC"
        is_close = signal_type in ("close_long", "close_short")
        if not is_close:
            return "DAY"
        if market_type == "HShare":
            return "DAY"
        return "IOC"
```

**Planner note:** After Phase 14, non-Forex policy becomes “IOC where aligned” per CONTEXT; docstring and branches update accordingly, and the parenthetical about HK **must** be replaced with evidence-based text.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| USStock open = DAY | USStock open = IOC | Phase 14 (planned) | Matches Forex automation expectations |
| HShare = DAY (unsourced) | HShare = IOC with IB citation (recommended) | Phase 14 (planned) | Removes incorrect SEHK claim |

**Deprecated/outdated:**

- Docstring line *“Hong Kong stocks do not support IOC orders”* — **contradicted** by IBKR’s IOC exchange list including **SEHK** (see Sources).

## Open Questions

1. **Does IBKR accept `MarketOrder` + `IOC` for every HK stock in practice?**
   - **What we know:** IB lists SEHK for IOC; codebase already uses `MarketOrder(..., tif="IOC")` for USStock closes. Same API path for HShare.
   - **What's unclear:** Rare symbol/session-specific rejects only show in live/paper.
   - **Recommendation:** Treat as **MEDIUM** residual risk; if any reject, capture message and revert HShare to DAY **for that path** or document broker error (CONTEXT “uncertain → DAY”).

2. **Is IOC limited to certain HK native order types at the exchange?**
   - **What we know:** TT HKEX docs emphasize **Limit** row with broad TIF support including IOC (institutional connectivity doc).
   - **What's unclear:** Exact mapping from IB “IOC” to HKEX internal order type.
   - **Recommendation:** Not needed for app logic—IBKR abstracts TIF; trust IOC on SEHK listing unless rejects occur.

## Validation Architecture

> `workflow.nyquist_validation` is enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (project standard) |
| Config file | `backend_api_python/tests/conftest.py`; no root `pytest.ini` (per Phase 13 notes) |
| Quick run command | `cd backend_api_python && python -m pytest tests/test_ibkr_client.py::TestTifMatrix -q` *(class name to match implementation)* |
| Full suite command | `cd backend_api_python && python -m pytest -q` *(~928 tests regression gate per STATE.md)* |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|----------------|
| INFRA-02 | TIF matrix 8×3 matches policy | unit | `python -m pytest tests/test_ibkr_client.py::TestTifMatrix -q` | ❌ Wave 0 — add `TestTifMatrix` |
| INFRA-02 | USStock open uses IOC | unit | Same matrix or targeted rows | Partial — update `TestTifDay`, `test_uc_e1`, `test_uc_r1` |
| INFRA-02 | HShare policy explicit | unit | Matrix rows for HShare | Partial — update `test_uc_e3`, `test_uc_r2` |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/test_ibkr_client.py -k "Tif" -q`
- **Per wave merge:** Full `python -m pytest -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_ibkr_client.py` — add `TestTifMatrix` (24 combinations) for INFRA-02
- [ ] Update/remove obsolete comments in `TestTifDay` section headers once USStock open → IOC
- [ ] Framework: existing pytest env — no install gap

## Sources

### Primary (HIGH confidence)

- [Interactive Brokers — Exchanges for order type: IOC](https://www.interactivebrokers.com/en/trading/order-type-exchanges.php?ot=ioc) — **Hong Kong Stock Exchange (SEHK)** listed under Asia/Pacific for IOC.
- [Interactive Brokers — Immediate or Cancel (IOC) order description (HK site, Chinese)](https://www.interactivebrokers.co.uk/cn/trading/orders/ioc.php) — IOC definition; notes that **not every product/exchange combination** is valid; points to exchange table for specifics.
- [Interactive Brokers Hong Kong — Time in Force for orders](https://www.interactivebrokers.com.hk/php/webhelp/Making_Trades/Create_Order_Types/timeinforce.htm) — IOC definition; **not all TIFs for all orders**; outside RTH limitation for IOC.

### Secondary (MEDIUM confidence)

- [Trading Technologies — HKEx supported order types / TIF](https://library.tradingtechnologies.com/user-setup/hke-hkex-supported-order-types.html) — Lists **IOC** among HKEX TIF restrictions (corroborates exchange-level TIF vocabulary; not IB-specific).

### Tertiary (LOW confidence)

- Web search snippets without official IB URL — **not used** as primary evidence for SEHK IOC.

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — pytest + existing IBKR client patterns unchanged structurally.
- Architecture: **HIGH** — single `_get_tif_for_signal` + matrix test is established pattern in repo.
- Pitfalls: **MEDIUM** — IBKR session/reject edge cases need runtime evidence if they appear.

**Research date:** 2026-04-11  
**Valid until:** ~30 days (IB pages stable); re-check if IBKR reformats order-type pages.
