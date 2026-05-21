# Pitfalls Research

**Domain:** Adding cross-sectional (multi-asset, universe-ranked) strategy backtesting to an existing single-asset quantitative platform (QuantDinger: `qd_kline_points`, `/api/indicator/backtest`, v2.0 NQ100-focused milestone)  
**Researched:** 2026-04-13  
**Confidence:** **HIGH** for look-ahead / pandas alignment mechanics and standard quant bias categories; **MEDIUM** for numeric magnitudes (survivorship %, slippage bps) — these vary sharply by universe, horizon, and implementation; **MEDIUM–LOW** for halt/limit detection from OHLC alone (heuristic, venue-specific).

---

## Critical Pitfalls

### Pitfall 1: Survivorship bias — “current universe” and live-listed-only histories

**Severity:** **CRITICAL** (can inflate Sharpe/CAGR by large amounts; user-cited **~5–10%** for “current index only” vs full history is plausible for **index-like** strategies; academic/industry summaries show **much larger** gaps for small-cap or high-turnover selection — do not treat 5–10% as a universal bound).

**What goes wrong:** Backtests use **today’s** NQ100 (or “currently listed”) tickers and pull full OHLCV only for survivors. Delisted names never enter losses, bankruptcy gaps, or forced exits → **upward-biased** returns and **understated** risk.

**Why it happens:** Single-asset pipelines already have per-symbol `qd_kline_points`; adding a “universe” often starts as **a static list of symbols** from a vendor screen. Historical **adds/drops** and **delisting dates** are extra data products — easy to defer “until later.”

**How to avoid:**

- Maintain **point-in-time (PIT) membership**: for each rebalance date `t`, know which tickers **were** in the investable universe at `t` using **as-of** rules, not future knowledge.
- Persist **historical constituent snapshots** (effective date ranges or event rows: `symbol`, `enter_date`, `exit_date`, `reason`). Source: index vendor / exchange **official** files where possible; scraping is OK for NQ100 if **versioned** and **auditable**.
- **Include delisted symbols** in the price DB **through** delisting (or last trade) so strategies cannot “forget” failed names.
- In code, **filter universe before** factor computation for date `t`, using only IDs that were members **at or before** `t` per your membership table — never `symbols = current_nq100()`.

**Code patterns to avoid:**

```python
# BAD: universe frozen to "who exists in DB today"
symbols = [r.symbol for r in db.query("SELECT DISTINCT symbol FROM qd_kline_points")]

# BAD: using merge/join on calendar without PIT membership
factors = prices[prices.symbol.isin(NQ100_TICKERS_2026)]
```

**Warning signs:** Backtest CAGR **jumps** when you restrict start date to “after all symbols have data”; no delisted tickers in DB; universe size **constant** over decades; performance **improves** when you **remove** a “data cleanup” that dropped thin symbols.

**Phase to address:** **Data + NQ100 snapshot pipeline** (constituent store + ingestion of delisted history) **before** trusting any cross-sectional performance metrics.

---

### Pitfall 2: Look-ahead / future function — signal at **T close** executed at **T close**

**Severity:** **CRITICAL**.

**What goes wrong:** Rank or signal from **day T**’s **close** (or OHLCV known only after the close) is used to **trade at T’s close** or to **weight the portfolio for T’s return**. That embeds information not available when the market was open — **classic lookahead**.

**Why it happens:** Vectorized backtests often compute `signal = f(close)` and then `returns * position` on the **same row**. Single-asset `/api/indicator/backtest` may implicitly assume **next-bar** execution; multi-asset codepaths reintroduce the bug if not explicitly modeled.

**How to avoid (T+1 open execution, user requirement):**

- **Define two timestamps:** `signal_time` = calendar **T** (after close); `execution_time` = **T+1** **open** (or first bar of next session).
- **Returns attribution:** portfolio return for the interval after the rebalance should use **open-to-open** or explicitly: position decided at T close → earns **T+1** return from open (and intraday if modeled), **not** T’s close→close while using T’s signal without lag.
- **Pandas discipline:**
  - Build signals on a **date index** aligned to **close** data; create `execution_signal = signal.shift(1)` on **trading** bars (not calendar days if sessions differ — see Pitfall 4).
  - Alternatively: `signal` at end of day `T` joins to **next** row’s **open** price for fills — use `merge_asof` with **backward** direction on a unified event timeline, or **reindex** to a **next-trading-day** map per symbol.
- **Never** use `shift(-1)` on prices to “fix” returns — that often **moves** labels backward and creates **subtle** leakage.

**Code patterns to avoid:**

```python
# BAD: same-bar trade
pos = rank_factor.iloc[t]
ret = close.pct_change().iloc[t] * pos  # uses close[t] known after ranking

# BAD: shift confusion on mixed calendars
signal.shift(1)  # without per-symbol trading calendar → wrong days for some stocks
```

**Warning signs:** Sharpe **drops a lot** when you switch from “close execution” to “next open”; walk-forward **train/test** gap is tiny (overfitting + leakage); intraday strategies show **impossible** fills at close prices.

**Phase to address:** **Cross-sectional backtest engine** core (execution model + return stacking), with **unit tests** that fail if signal date == fill date for close-derived factors.

---

### Pitfall 3: Halt / limit-up / limit-down — untradable rebalance days

**Severity:** **HIGH** for A-shares / hard limits; **MEDIUM** for US large-cap (limits rare but halts exist).

**What goes wrong:** On rebalance day, the model **assumes** full execution at open (or VWAP). In reality: **cannot buy** at limit-up (no liquidity at cap); **cannot sell** at limit-down. Cash can remain **uninvested**; sell failures leave **unintended** overweight — **not** the same as frictionless top-N weights.

**Why it happens:** OHLCV-only backtests lack **order book** and **auction state**. Teams approximate with **close price** execution, which **double-counts** knowing the full day’s range.

**How to avoid (heuristics — validate per market):**

- **Limit touch:** For markets with explicit limit rules (e.g. A-share **±10%/±20%**): compare `close` (or `open`) to **previous close** × (1 ± limit). If **high == low == limit price** and **volume** is collapsed vs median → **likely** limit-locked (heuristic, not proof).
- **Halt:** **volume == 0** (or missing bar) with **stale** last close → **no trade** that day; carry position or cash rules explicitly (“if no open print, skip fill”).
- **US stocks:** use **halt** datasets for production realism; for MVP, **at minimum** detect **zero-volume** bars and **optional** gap rules (open beyond prior close band) as **soft** flags.
- **Portfolio rule:** If buy fails → **cash**; if sell fails → **hold** overweight until next liquid session (user requirement — encode as **explicit state**, not implicit NaN→0).

**Code patterns to avoid:**

```python
# BAD: always fill at open
fill_px = open.loc[t, sym]

# BAD: drop row → pretend symbol didn't exist (survivorship + wrong weighting)
if not tradable: universe.remove(sym)
```

**Warning signs:** 100% **fill** rate on names with obvious **one-tick** all-day bars; simulation **never** holds cash on rebalance; A-share backtest **matches** theory **too well**.

**Phase to address:** **Execution / microstructure layer** in cross-sectional backtest (after base T+1 engine exists).

---

### Pitfall 4: Calendar misalignment — different sessions, missing bars, corporate actions

**Severity:** **HIGH**.

**What goes wrong:** A single **pandas DateTimeIndex** for “the market” is applied to **all** symbols. **HALF trading days**, **IPOs**, **suspensions**, and **different market holidays** (later: HK/US mix) cause **wrong** `shift(1)`, **mis-merged** panels, and **phantom** returns.

**Why it happens:** Single-asset backtest has **one** series; multi-asset **panel** work needs **per-symbol** valid trading sets or an **explicit** master calendar with **masking**.

**How to avoid:**

- Use a **reference calendar** (e.g. US equities **NYSE** sessions for NQ100) for **rebalance decisions**; map each symbol’s available bars with **`reindex(..., method=None)`** + **forward-fill only where economically justified** (often **no** fill for returns — use **missing = no trade**).
- For **multi-day** momentum windows: require **min** count of valid observations, not just `window=20` on **calendar** rows.
- **Corporate actions:** for **close-to-close** return consistency, **adjust** prices or use **total return** sources; unadjusted OHLC + splits → **factor** and **P&L** bugs.

**Warning signs:** `shift(1)` on a **merged** panel lines up **different** stocks’ “yesterday”; frequent **NaN** explosion after `pivot`; **identical** weights across **unequal** listing histories without **intentional** padding.

**Phase to address:** **Data alignment utilities** + **factor engine** (same phase as first real multi-asset factors).

---

### Pitfall 5: Factor bugs — wrong window, double-counting **close**, release-time confusion

**Severity:** **HIGH**.

**What goes wrong:** **Off-by-one** in rolling windows; using **split-adjusted** prices for one leg and **raw** for another; **annual** vs **trading** day counts; fundamentals **reported** date vs **available** date (PIT issue for future work).

**Why it happens:** Copy-paste from **single** ticker notebooks; **rolling().mean()** defaults include **current** bar — confirm whether **signal at T** is allowed to include **T**’s close in the window or only **T-1** and earlier per your **signal convention**.

**How to avoid:**

- Document **inclusive/exclusive** window endpoints; write **golden** tests: hand-computed 5-bar momentum on toy data.
- For price-based factors: **explicit** `min_periods`**,** and **rank** only on symbols with **valid** inputs on that date.
- If mixing **close** signal with **next open** trade, factors should use information **available at signal time** only.

**Warning signs:** First valid signal appears **earlier** than economically possible; factor **correlates** implausibly with **same-day** return.

**Phase to address:** **Factor registration + computation** phase with **unit tests** per factor.

---

### Pitfall 6: Cross-sectional rank — NaNs, ties, tiny cross-sections

**Severity:** **MEDIUM–HIGH** (more **bugs** than **philosophy**).

**What goes wrong:** `rank()` with default **average** ties **blends** identities; **NaN** propagation drops names silently; on early dates **only 30** valid NQ100 names → **unstable** deciles.

**Why it happens:** `pandas` defaults don’t match portfolio intent; **missing** data treated as **worst** vs **neutral** changes outcomes.

**How to avoid:**

- Choose **`method`**: `first`, `dense`, or `average` **consciously**; for portfolio construction, **ties** often need **random tie-break** or **pro-rata** — document choice.
- **Explicit NaN policy:** `dropna()` vs **fill** (dangerous for factors); often **rank only among valid** names and **exclude** rest from allocation.
- Enforce **minimum** universe size **K** for ranking; else **skip** rebalance.

**Warning signs:** Portfolio **weight** sums **≠ 1** after custom rank logic; **duplicate** ranks create **duplicate** weights without normalization.

**Phase to address:** **Ranking / portfolio construction** module + tests for NaN/ties.

---

### Pitfall 7: Ignoring transaction costs, market impact, and index **reconstitution** frictions

**Severity:** **MEDIUM** for NQ100 monthly **factor** strategies (often **not** dominant vs bias bugs); still **required** for honest absolute performance.

**What goes wrong:** **Zero-cost** backtest **overstates** net returns; **rebalance** into **index adds** on **announcement** vs **effective** date confuses **implementation** shortfall.

**Why it happens:** First milestone focuses on **bias** fixes; costs are “TODO.”

**How to avoid:**

- Model **fixed** + **proportional** cost (bps per **side**); **optional** impact model **∝** participation rate for large notionals.
- **Slippage significance (MEDIUM confidence, order-of-magnitude):** industry-style summaries often cite **single-digit to tens of bps** **one-way** for **liquid US large-cap** depending on spread/impact assumptions; **monthly** rebalance of a **diversified** NQ100 **long-only** strategy often sees **modest** drag vs **daily** HFT — **but** **concentrated** weights, **adds/deletes** around **index events**, or **illiquid** names can spike costs. **Validate** with your **actual** turnover and **assumed** bps.
- **Nasdaq-100 reconstitution (HIGH confidence on process, MEDIUM on PnL impact):** **Annual** **reconstitution** (with **December** / quadruple-witching timing per **Nasdaq** methodology materials) drives **adds/deletes**; **quarterly** activity often relates to **weight** **rebalancing** / methodology — **read** current **[NDX methodology PDF](https://indexes.nasdaq.com/docs/methodology_NDX.pdf)** for exact rules. **Index effect** (prices moving **before** effective date) is **well-documented** in academic/industry literature; **ignoring** **implementation** around **rebalance** **windows** can **overstate** achievable returns for **replication** strategies.

**Warning signs:** Net returns **≈** gross; turnover **high** but costs **zero**; big **jumps** on known **index** **event** dates with **no** slippage model.

**Phase to address:** **Backtest reporting** + **cost model** (can be Phase 2+ after unbiased engine).

---

### Pitfall 8: Integration — bolting a portfolio loop onto **single-asset** `/api/indicator/backtest` semantics

**Severity:** **HIGH** (architecture).

**What goes wrong:** **Per-symbol** backtests **look** **great**; **portfolio** aggregation **double-applies** risk-free, **mis-averages** correlations, or uses **different** **return** definitions per symbol.

**Why it happens:** API shaped around **one** **indicator** **series** **+** **one** **equity** curve; cross-sectional **needs** **panel** **state**: weights, cash, per-fill constraints.

**How to avoid:**

- **New** codepath: **panel** **engine** (script-first in v2.0 is fine) with **clear** **separation** from single-asset **endpoint** — **shared** **only** **low-level** **DB** **readers** and **corporate** **action** **helpers**.
- **One** **definition** of **portfolio** **return** (chain-linked **daily** **weights**, **cash** **drag**, **dividends** **policy**).

**Warning signs:** **Sum** of **single-name** **Sharpes** **≠** **portfolio** **risk**; **inconsistent** **date** **alignment** **across** **symbols** **in** **one** **report**.

**Phase to address:** **Cross-sectional** **backtest** **module** **design** **at** **start** **of** **implementation** (before **large** **factor** **library**).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Static “NQ100 list” JSON checked into repo | Fast prototype | Survivorship + stale universe | Never for production metrics; OK only for UI mock / dev |
| `ffill` missing prices across long gaps | Clean panel | Fake liquidity; hides halts | Rarely; if used, flag synthetic bars and exclude from trade logic |
| Single global `shift(1)` on merged data | Simple code | Wrong T+1 for some symbols | Never without calendar alignment |
| Rank with `average` ties, undocumented | Default pandas | Non-reproducible weights | Short internal tests only |
| Zero transaction costs until “later” | Faster first Sharpe | False confidence in strategy rankings | OK for relative bias A/B, not for absolute performance claims |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `qd_kline_points` | Assume equal history length per symbol | Per-symbol valid index + explicit missing-data policy |
| `/api/indicator/backtest` | Run N single-asset backtests and average | Dedicated portfolio engine with constraints |
| NQ100 membership scrape | Overwrite file without history | Versioned snapshots + immutable historical rows |
| Index vendor vs IB symbols | Miss ticker changes / share class | Symbol mapping table + tests on known adds/drops |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full vectorized panel (daily × 20y × 100+ names) | RAM spikes, slow pivot | Chunk by year; store narrow factor tables | Universe ≫100 or intraday bars |
| Repeated DB scans per rebalance | API timeouts | Preload window once per batch job | Large brute-force search grids |
| Pure Python per (date × symbol) loops | CPU hours | Batch ops, Numba, or Polars | Large parameter sweeps |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Unpickling untrusted backtest artifacts | RCE if shared | JSON or Parquet only |
| Secrets in notebooks for data APIs | Credential leak | Env vars; never commit secrets |

*Domain is offline backtesting — lower surface than live trading.*

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| One headline Sharpe without bias audit | False confidence | Report checks: survivorship mode, execution lag, cost assumptions |
| Silent drops of bad symbols | Looks clean but wrong | Log excluded names and counts |
| No RNG seed for tie-breaks | Non-reproducible runs | Fixed seed + documented tie policy |

---

## “Looks Done But Isn’t” Checklist

- [ ] **Survivorship:** Delisted names **present** through exit — verify **sample** **delisted** **tickers** **in** **DB**
- [ ] **T+1:** Signal **date** **≠** **fill** **bar** **for** **close-based** **factors** — verify **unit** **test** **on** **toy** **panel**
- [ ] **Limits/halts:** **Zero-volume** / **limit-locked** **days** **do** **not** **fill** **at** **fantasy** **prices**
- [ ] **Calendar:** **Rebalance** **shift** **uses** **trading** **calendar**, **not** **calendar** **day** **blind** **shift**
- [ ] **Factors:** **Rolling** **window** **endpoints** **match** **docs**; **min_periods** **enforced**
- [ ] **Ranks:** **NaN** / **tie** **policy** **documented** **and** **tested**
- [ ] **Costs:** At least a bps sensitivity table (even if 0 bps baseline)
- [ ] **Integration:** **Portfolio** **curve** **≠** **average** **of** **single-name** **curves**

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Survivorship bias | HIGH | Re-ingest delisted history; rebuild PIT universe; re-run studies |
| Look-ahead in pandas | MEDIUM | Freeze signal/execution schema; add regression tests; recompute |
| Bad calendar shift | MEDIUM | Centralize calendar + reindex helpers; re-run |
| Wrong tie/NaN rank policy | LOW | Fix rank API; run sensitivity checks |

---

## Pitfall-to-Phase Mapping

Suggested mapping for v2.0-style milestones (adjust to your `ROADMAP.md` phase numbers):

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Survivorship / PIT universe | Constituent + history data phase | Delisted symbol count > 0; membership changes year-over-year |
| T+1 / lookahead | Cross-sectional backtest engine phase | Deterministic tests; signal vs execution date in logs |
| Halt / limits | Execution realism phase (after core engine) | Fill rate below 100% on synthetic halt fixtures |
| Calendar / missing data | Data alignment + factor phase | No silent ffill across halts unless explicitly allowed |
| Factor window bugs | Factor library phase | Golden tests per factor |
| Rank NaN/ties | Ranking / portfolio builder phase | Property tests: weights sum to 1 (long-only) |
| Costs / reconstitution | Reporting + refinement phase | Cost sweep table; event study around index dates |
| Single-asset integration | Architecture / first vertical slice | One portfolio equity curve — not N× single-asset average |

---

## Sources

- Nasdaq NDX methodology (constituent rules, reconstitution / rebalance mechanics): [Nasdaq Global Indexes methodology_NDX.pdf](https://indexes.nasdaq.com/docs/methodology_NDX.pdf) — HIGH confidence for process description.
- Survivorship bias (impact varies widely by strategy): industry and academic literature — MEDIUM confidence for magnitude without your exact universe.
- Pandas `shift`, `merge_asof`, alignment: [pandas documentation](https://pandas.pydata.org/docs/) — HIGH confidence for API semantics.
- Transaction costs and index rebalancing (e.g. SSRN working papers) — MEDIUM confidence for specific bps without portfolio-level calibration.

---
*Pitfalls research for: Cross-sectional strategy backtesting on QuantDinger (brownfield, single-asset → multi-asset)*  
*Researched: 2026-04-13*
