---
phase: 17-forex-limit-orders-automation
verified: 2026-04-12T12:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Optional — liquid Forex session on paper Gateway (4004): place DAY limit and observe PartiallyFilled sequence"
    expected: "Cumulative filled non-decreasing; filled + remaining ≈ totalQuantity; DB snapshot updates without duplicate trades until terminal"
    why_human: "17-02-PLAN Task 3 checkpoint; Sunday RTH block confirms routing only, not partial-fill lifecycle"
---

# Phase 17: Forex limit orders & automation — Verification Report

**Phase goal:** Full limit-order execution: REST/automation parity, minTick prices, partial fills, and runner/worker support.

**Verified:** 2026-04-12T12:00:00Z

**Status:** **passed** (9/9 aggregated `must_haves.truths` from 17-01 / 17-02 / 17-03 plans)

**Re-verification:** No — initial verification (no prior `*-VERIFICATION.md` in phase directory).

**Note:** `gsd-tools verify artifacts/key-links` did not parse YAML `must_haves` from these PLAN files (tool reported missing frontmatter keys); verification was performed by direct code and test inspection.

---

## Goal Achievement

### Observable truths (must_haves)

| # | Source | Truth | Status | Evidence |
|---|--------|-------|--------|----------|
| 1 | 17-01 | Forex/automation limit path uses LimitOrder TIF **DAY** (no per-signal override) | ✓ VERIFIED | `_get_tif_for_signal` returns `"DAY"` when `order_type=="limit"`; `place_limit_order` uses that when `time_in_force is None` (`client.py` ~170–191, 1363–1364) |
| 2 | 17-01 | Limit price snapped to **minTick** (BUY floor, SELL ceil) | ✓ VERIFIED | `_snap_limit_price_to_mintick` + `place_limit_order` path (`client.py` ~1040–1046, 1423–1425) |
| 3 | 17-01 | REST limit orders can request **IOC / DAY / GTC** via body | ✓ VERIFIED | `place_limit_order` validates whitelist; `ibkr.py` passes `time_in_force` when `timeInForce` key present (~234–236); default DAY when omitted |
| 4 | 17-02 | **PartiallyFilled** → cumulative overwrite of `filled` / `remaining` (not incremental) | ✓ VERIFIED | Branch calls `records.update_pending_order_fill_snapshot`; Chinese anchor comment present (`client.py` ~471–498) |
| 5 | 17-02 | **filled** non-decreasing expectation + **filled+remaining** epsilon vs **totalQuantity** | ✓ VERIFIED | `last_reported_filled`, `_ORDER_QTY_EPS_ABS` / `_ORDER_QTY_EPS_REL`, warnings `non_monotonic_filled`, `filled_plus_remaining` (`client.py` ~31–33, 113, 475–489) |
| 6 | 17-02 | Positions / strategy trades only on **terminal** fills, not each partial | ✓ VERIFIED | PartiallyFilled returns after snapshot **before** `_handle_fill`; Filled/Cancelled paths invoke `_handle_fill` (`client.py` ~471–512); `test_ibkr_order_callback.py` `TestPartiallyFilledSnapshot` |
| 7 | 17-03 | Strategy `trading_config.live_order` can enqueue **limit** + computed limit price | ✓ VERIFIED | `signal_executor.py` ~380–414 with `pip_size_for_forex_symbol`, `execute_exchange_order(..., order_type=..., limit_price=...)` |
| 8 | 17-03 | **StatefulClientRunner** calls `place_limit_order` when `order_type==limit` and price &gt; 0 | ✓ VERIFIED | `stateful_runner.py` ~76–101; tests `test_stateful_runner_execute.py` (`ibkr_limit_price_required`) |
| 9 | 17-03 | **PendingOrderWorker** passes **price** + **order_type** into **OrderContext** | ✓ VERIFIED | `pending_order_worker.py` ~373–414 (`lim_px`, `ot_live`, `payload["order_type"]`); tests `test_pending_order_worker.py` |

**Score:** 9/9 truths verified.

---

### Required artifacts

| Artifact | Expected | Status |
|----------|----------|--------|
| `backend_api_python/app/services/live_trading/ibkr_trading/client.py` | TIF, minTick snap, PartiallyFilled, invariants | ✓ Substantive (1700+ LOC module; patterns present) |
| `backend_api_python/app/routes/ibkr.py` | `timeInForce` → `place_limit_order` | ✓ Wired |
| `backend_api_python/migrations/0054_add_pending_orders_remaining.sql` | `remaining` column | ✓ Exists |
| `backend_api_python/migrations/init.sql` | `pending_orders.remaining` | ✓ Present |
| `backend_api_python/app/services/live_trading/records.py` | `update_pending_order_fill_snapshot` | ✓ Implemented |
| `backend_api_python/app/services/live_trading/forex_pip.py` | `pip_size_for_forex_symbol` | ✓ Exists |
| `backend_api_python/app/services/signal_executor.py` | `live_order` limit path | ✓ Wired |
| `backend_api_python/app/services/pending_order_enqueuer.py` | `order_type` / limit price | ✓ Wired |
| `backend_api_python/app/services/live_trading/runners/stateful_runner.py` | `place_limit_order` branch | ✓ Wired |
| `backend_api_python/app/services/pending_order_worker.py` | `OrderContext.price` | ✓ Wired |

---

### Key link verification

| From | To | Via | Status |
|------|-----|-----|--------|
| `ibkr.py` `place_order` | `IBKRClient.place_limit_order` | `time_in_force` when `timeInForce` in JSON | ✓ |
| `client._on_order_status` | `records.update_pending_order_fill_snapshot` | `pending_order_id` on PartiallyFilled | ✓ |
| `signal_executor.execute` | `PendingOrderEnqueuer.execute_exchange_order` | `order_type`, `limit_price` kwargs | ✓ |
| `PendingOrderWorker._execute_live_order` | `StatefulClientRunner.execute` | `OrderContext(price=lim_px, ...)` | ✓ |

---

### Requirements coverage (TRADE-01, TRADE-02, TRADE-03)

| ID | REQUIREMENTS.md text (abridged) | Plan claiming ID | Status | Evidence |
|----|--------------------------------|------------------|--------|----------|
| **TRADE-01** | IBKRClient Forex LimitOrder, minTick, TIF IOC/DAY/GTC | 17-01-PLAN | ✓ SATISFIED | `place_limit_order`, `_snap_limit_price_to_mintick`, tests `TestTrade01LimitMintickTif` |
| **TRADE-02** | PartiallyFilled updates remaining; no double-count | 17-02-PLAN | ✓ SATISFIED | Migration + `update_pending_order_fill_snapshot` + PartiallyFilled branch + `test_ibkr_order_callback.py` |
| **TRADE-03** | StatefulClientRunner limit; PendingOrderWorker limit price | 17-03-PLAN | ✓ SATISFIED | `forex_pip`, `signal_executor`, `stateful_runner`, `pending_order_worker` + tests |

**Documentation drift:** `.planning/REQUIREMENTS.md` still shows TRADE-02 and TRADE-03 as unchecked (lines 11–12) and the traceability table lists Phase 17 TRADE-02/TRADE-03 as **Pending** (lines 52–53). **Implementation and tests satisfy all three IDs;** updating REQUIREMENTS + traceability (and optional ROADMAP plan checkboxes 111–113) is recommended for doc/roadmap consistency, not a code gap.

**Orphaned requirements:** None — every ID appears in at least one PLAN frontmatter.

---

### Anti-patterns

| File | Pattern | Severity | Notes |
|------|---------|----------|------|
| — | `TODO` / `FIXME` in `client.py` (spot check) | — | None found in scanned trading client |

---

### Human verification (optional / non-blocking)

1. **Liquid-session paper partial fill (17-02 UC-02h)**  
   **Test:** During Forex liquid hours, connect paper Gateway (4004), POST limit with `orderType=limit`, `timeInForce=DAY`, observe `[IBKR-Event] orderStatus` for PartiallyFilled if the venue delivers partials.  
   **Expected:** Cumulative `filled` non-decreasing; `filled` + `remaining` within epsilon of `totalQuantity`.  
   **Why human:** Real IBKR event ordering; user already confirmed Sunday attempt **blocked by RTH** (expected), which validates market-closed path only.

---

### Gaps summary

**None** blocking phase goal achievement. Automated tests cited in plans exist and align with behaviors (`test_ibkr_client.py`, `test_ibkr_order_callback.py`, `test_signal_executor.py`, `test_pending_order_enqueuer.py`, `test_stateful_runner_execute.py`, `test_pending_order_worker.py`). Full suite green per user report (1023 tests).

---

_Verifier: Claude (gsd-verifier)_  
_Codebase root: QuantDinger/backend_api_python_
