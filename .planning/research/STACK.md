# Technology Stack — IBKR Forex (IDEALPRO) with ib_insync

**Project:** QuantDinger IBKR Forex milestone  
**Researched:** 2026-04-09  
**Scope:** Add IDEALPRO Forex to an existing ib_insync client that already trades US stocks (`Stock` + `SMART`) and HK shares (`Stock` + `SEHK`). Does not re-document the stock stack.

**Confidence:** **HIGH** for ib_insync `Forex` construction (verified against upstream `ib_insync/contract.py`). **MEDIUM** for IBKR operational edge cases (SMART vs IDEALPRO errors) — corroborated by IBKR basic contracts doc + community reports.

---

## Recommended Stack

### Core integration pattern

| Piece | Choice | Why |
|-------|--------|-----|
| Contract type | `ib_insync.Forex` | Maps to IBKR `secType='CASH'`; default `exchange='IDEALPRO'`. |
| Qualification | `ib.qualifyContracts(contract)` or `qualifyContractsAsync` | Resolves `conId`, `localSymbol` (often `BASE.QUOTE`, e.g. `EUR.USD`), `tradingClass`, and validates the pair exists on IDEALPRO. Same call family as stocks. |
| Orders | `MarketOrder` / `LimitOrder` | Same order objects as equities; `action`, `totalQuantity`, `tif`, `account` behave the same at the API level. |
| Connection | Existing `IB()` + TWS/Gateway | No separate Forex “stack”; same session and client id rules as current IBKR path. |

### ib_insync `Forex` — authoritative construction rules

From `ib_insync`’s `Forex` class (see Sources):

- **`Forex(pair='EURUSD')`** — `pair` must be **exactly 6 characters** (assert). Splits into `symbol='EUR'`, `currency='USD'`, `secType='CASH'`, `exchange='IDEALPRO'` (unless overridden).
- **`Forex(symbol='EUR', currency='USD', exchange='IDEALPRO')`** — explicit base/quote; omit `pair` when using this form.
- **`.pair()` method** on the contract returns concatenated `symbol + currency` (e.g. `EURUSD`).

After `qualifyContracts`, expect IB-populated fields such as **`localSymbol`** like `EUR.USD` (dot-separated), not the 6-letter concatenation — **do not assume** display format equals pre-qualification `pair` string.

### IDEALPRO vs SMART (stocks)

| | **Forex (IDEALPRO)** | **US stock (typical)** |
|--|----------------------|-------------------------|
| `secType` | `CASH` | `STK` |
| `exchange` | **`IDEALPRO`** for spot FX (ib_insync default on `Forex`) | Often **`SMART`** for smart-routed equities |
| Symbol roles | **`symbol`** = **base currency**, **`currency`** = **quote currency** | `symbol` = ticker; `currency` = trading currency |
| Routing | FX spot is **not** equity SMART routing; wrong exchange commonly yields **“Invalid destination exchange”** style errors | SMART aggregates multiple venues |

**Prescriptive rule for this codebase:** For Forex, **always** construct with `Forex(..., exchange='IDEALPRO')` (explicit or default) and **never** pass `SMART` as the FX exchange in `_create_contract`.

### Order types and fields (vs stocks)

- **`MarketOrder` / `LimitOrder`**: Same classes as US/HK stocks.
- **`totalQuantity`**: For IDEALPRO cash FX, quantity is in **units of the base currency** unless you deliberately use IB’s **cash quantity** workflow (`cashQty` on the order — optional, not required for the current “reuse `_align_qty_to_contract` + normalizer” plan).
- **`tif`**: `DAY` / `GTC` / `IOC` are valid at the API layer; **validate** against `ContractDetails.orderTypes` after qualification if you need hard guarantees. Existing `_get_tif_for_signal` uses `DAY` for opens and `IOC` for US closes — **Forex may need its own branch** (e.g. HK-style `DAY`-only if IOC is unsupported), mirroring the HShare exception already in code.
- **`outsideRth`**: Stocks use session/RTH concepts; FX is effectively **24h Mon–Fri** with maintenance windows — rely on **`ContractDetails.liquidHours` / `tradingHours`** (already used by your RTH helper) rather than equity RTH assumptions.

### Symbol format conventions (implementation checklist)

| Input style | Suggested handling |
|-------------|---------------------|
| `EURUSD` (6 letters) | Pass to `Forex('EURUSD')` or split to symbol/currency. |
| `EUR.USD` | Strip dot → `EUR` + `USD` → `Forex(symbol='EUR', currency='USD')` or normalized 6-char pair. |
| Case | Normalize to uppercase before parsing. |
| Invalid length | Not a valid `pair=` shortcut; use explicit `symbol` + `currency`. |

---

## Supporting Libraries

| Library | Role | Notes |
|---------|------|--------|
| **ib_insync** (existing) | `Forex`, `IB`, `MarketOrder`, `qualifyContracts` | No additional broker SDK. |
| **ibapi** | Not required | ib_insync bundles the needed IB API protocol; do not add `ibapi` just for Forex. |

---

## Alternatives Considered

| Alternative | Verdict |
|-------------|---------|
| Raw `Contract(secType='CASH', ...)` | Equivalent to `Forex`; **`Forex()` is clearer and matches ib_insync examples.** |
| `Stock` / `SMART` for FX | **Wrong** — wrong `secType` and exchange model. |
| Separate IB connection for Forex | Unnecessary; same TWS session handles mixed asset classes. |
| `cashQty` orders | Useful for “trade $X” UX; **out of scope** if strategies emit base-currency units like today’s stock share counts. |

---

## What NOT to Use / What NOT to Do

**When mixing Forex with existing stock code:**

1. **Do not** route Forex through `_create_contract` paths that always build `Stock(...)` — add a **`market_type == 'Forex'`** (or `market_category`) branch that returns `Forex(...)`.
2. **Do not** set `exchange='SMART'` on FX contracts for IDEALPRO spot — use **`IDEALPRO`**.
3. **Do not** reuse equity **ticker** normalization (e.g. HK `.HK` stripping) for FX pairs — use a **dedicated parser** for `EURUSD` / `EUR.USD`.
4. **Do not** assume **share** semantics for `totalQuantity` — document internally as **base currency units** for Forex positions.
5. **Do not** infer session from US equity holidays alone — use IB-returned **hours** for the CASH contract (project already aligns with contract-based RTH).
6. **Do not** silently apply **IOC** to Forex close orders until confirmed supported for your account/order types (mirror the **HShare** special case if needed).

---

## Sources

| Source | What it validates |
|--------|-------------------|
| [ib_insync `contract.py` — `Forex` class](https://github.com/erdewit/ib_insync/blob/master/ib_insync/contract.py) | `secType='CASH'`, default `exchange='IDEALPRO'`, `pair` length 6, `symbol`/`currency` split. **HIGH** |
| [ib_insync docs — homepage example `Forex('EURUSD')`](https://ib-insync.readthedocs.io/) | Official usage pattern for historical data / contracts. **HIGH** |
| [TWS API — Basic Contracts (FX Pairs)](https://interactivebrokers.github.io/tws-api/basic_contracts.html) | `Symbol` = base, `SecType` = `CASH`, `Currency` = quote, `Exchange` = `IDEALPRO`. **HIGH** (note: page banner says Campus is canonical for latest wording; structure still matches). |
| [IBKR Campus — Contracts](https://www.interactivebrokers.com/campus/ibkr-api-page/contracts/) | Supplemental official overview. **MEDIUM** |

---

## Quality gate checklist

- [x] ib_insync Forex API specifics: `Forex(pair=)` / `Forex(symbol=, currency=, exchange='IDEALPRO')`, `secType` CASH, `qualifyContracts`, same `MarketOrder`/`LimitOrder`.
- [x] IDEALPRO: explicit venue for spot FX; not SMART equity routing.
- [x] Differences from stock path: `STK`+`SMART`/`SEHK` vs `CASH`+`IDEALPRO`; base/quote vs ticker; quantity meaning.
- [x] Symbol conventions: 6-char pair, `EUR.USD` localSymbol after qualification, uppercase normalization.
