# Feature Research

**Domain:** Cross-sectional equity strategy backtesting (NASDAQ 100 universe) on QuantDinger  
**Researched:** 2026-04-13  
**Confidence:** MEDIUM–HIGH for equity factor/portfolio practice; HIGH for Nasdaq governance dates below; MEDIUM for “perfect” historical NQ100 membership without a vendor

## Feature Landscape

### Table Stakes (Users Expect These)

Features quants assume exist for **credible** cross-sectional equity backtests. Missing these makes results hard to defend or replicate.

| Feature | Why Expected | Complexity | QuantDinger dependency |
|---------|--------------|------------|------------------------|
| **Point-in-time (PIT) investable universe** | Rankings must use only names that were index members **as of** each date; otherwise membership injects look-ahead. | MEDIUM | New: **NQ100 scrape/cache + dated snapshots** in PostgreSQL. Uses existing DB; not covered by single-symbol K-line alone. |
| **Cross-sectional factor computation per rebalance** | A “factor” is a comparable score per name on a calendar (e.g. month-end); built from data available before the trade decision. | MEDIUM | **Reuses** per-symbol K-line + indicator pipeline; adds **cross-sectional join** (date × symbol) after universe filter. |
| **Signal vs execution timing (no same-bar lookahead)** | Convention: signal using information through **close of T** → executable fills **next session** (often **open of T+1**). | MEDIUM | **Extends** existing backtest timing; PROJECT.md targets **T+1 open** execution. |
| **Survivorship-aware price history** | Delisted names must remain in historical panels for periods they traded. | MEDIUM | **Reuses** PostgreSQL K-line storage; requires **policy** not to drop delisted symbols from backtest panels and queries. |
| **Halts / limit-up-down handling policy** | If a name cannot trade, “fill at open” is invalid. | MEDIUM | New **microstructure policy module**; order automation exists for live IBKR but backtest path needs explicit rules. |
| **Portfolio construction from ranks** | Turn scores into weights (long-only, long-short, neutral variants). | LOW–MEDIUM | New **portfolio builder** on top of factor outputs; separate from single-asset backtest loop. |
| **Rebalancing schedule** | Strategy defined by turnover calendar (weekly / monthly / …). | LOW | Parameter to factor + execution engine; ties to **T+1** and cost assumptions. |
| **Standard performance metrics** | Comparable reporting to papers, peers, and internal grids. | LOW | New or consolidated **metrics** module for equity curves (see *Standard metrics* below). |
| **Reproducible batch / grid script** | Matrix of parameters without GUI (research workflow). | LOW | **Standalone script** calling factor engine + portfolio + metrics; aligns with v2.0 scope (no cross-sectional Vue UI). |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | QuantDinger dependency |
|---------|-------------------|------------|------------------------|
| **Dynamic NQ100 ingest + server cache + versioned snapshots** | Auditable “what was the NQ100 on date *D*” if snapshots are stored; reduces manual CSV drift. | MEDIUM | New ingestion + tables/API; **complements** K-line symbol coverage checks. |
| **Explicit factor combination library** | Faster research: winsorize → z-score → equal or weighted blend → rank composites. | MEDIUM | Builds on **factor registration**; optional reuse of indicator primitives per symbol. |
| **Grid / brute-force search with reporting discipline** | Explore factor subsets × top-N × rebalance freq; differentiator if results report **IS vs OOS** or walk-forward, not only best in-sample Sharpe. | MEDIUM | Script-only; depends on **metrics** + compute budget; methodological guardrails are partly **process**, partly **harness** (deferred P2). |
| **Integration with existing K-line + PostgreSQL + strategy stack** | One platform from data to signals; avoids duplicate data silos. | LOW–MEDIUM | **Core reuse:** K-line API/DB, symbols; **not** live cross-sectional automation in v2.0 (per PROJECT.md). |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Pick “best Sharpe” from a huge in-sample grid** | Find optimal parameters. | **Overfitting**; inflated Sharpe. | Nested CV, holdout window, walk-forward; pre-register “production” params before final test. |
| **Same-bar execution (signal and fill on same close)** | Simpler code. | **Look-ahead** vs realistic US equity execution. | **T+1 open** (or explicit auction model) per PROJECT.md. |
| **Current NQ100 membership applied to all history** | Easiest implementation. | **Survivorship + membership look-ahead.** | **PIT membership** + retained delisted history. |
| **Daily rebalancing for every experiment** | Maximum responsiveness. | Turnover, costs, estimate noise dominate. | Start **monthly/weekly**; add daily only with **explicit cost model**. |
| **Full sector-neutral optimization in v2.0** | Match institutional portfolios. | Needs reliable **sector taxonomy + history** (GICS changes); heavier optimization. | **Sector demean** of z-scores first; defer optimizer. |
| **Live cross-sectional IBKR automation in v2.0** | Trade the book. | Borrow, capacity, slicing; out of scope. | **Backtest + research script** first (PROJECT.md). |

## Feature Dependencies

```
[NQ100 PIT universe + snapshots]
    └──requires──> [Constituent scrape / ingest + PostgreSQL cache]
        └──requires──> [Historical bar panel including delisted tickers — K-line retention policy]

[Cross-sectional factor engine]
    └──requires──> [Aligned multi-symbol bars — existing K-line layer]
    └──requires──> [Per-date cross-section: universe ∩ available prices]

[Execution-realistic backtest]
    └──requires──> [T+1 open fills from signal at prior close]
    └──requires──> [Halt/limit policy module]
    └──enhances──> [Existing backtest / simulation services where single-asset logic differs]

[Grid search script]
    └──requires──> [Factor engine + portfolio constructor + metrics]
    └──conflicts──> [Unbounded search without reporting bias — mitigate with methodology + optional P2 harness]
```

### Dependency Notes

- **PIT NQ100 requires constituent history:** Rankings on past date *D* must use membership known as of *D* (or prior published effective date). Snapshots from first deployment forward + optional vendor/historical backfill; **“ground truth” history is vendor- or reconstruction-dependent** (see *NQ100 constituents*).

- **Cross-sectional engine requires multi-symbol alignment:** Depends on **K-line fetch + PostgreSQL** for each symbol; join on **trade date** after universe filter and liquidity screens.

- **Survivorship fix requires data retention:** Depends on **not purging** delisted symbols’ bars (or importing bias-free history).

- **Grid search vs statistical hygiene:** Software can emit many runs; **credibility** depends on train/test discipline—not only code.

### QuantDinger integration (summary)

| Existing capability | Role in v2.0 |
|---------------------|--------------|
| K-line API + PostgreSQL storage | Per-symbol inputs to cross-sectional factors; must include delisted names when present. |
| Single-asset indicators / backtesting | Building blocks for per-name series; cross-sectional layer is **new** (rank, neutralize, combine). |
| Strategy CRUD, signals, IBKR execution | **Not** extended for live cross-sectional in v2.0; future milestone. |

## MVP Definition

Aligned with `.planning/PROJECT.md` **v2.0 Cross-Sectional Strategy** (backend + script; NQ100 only; no cross-sectional live automation).

### Launch With (v2.0)

- [ ] **NQ100 dynamic constituent ingestion + cached API + historical snapshots** — foundational for PIT universe.
- [ ] **Backtest correctness:** survivorship-aware panel, **T+1 open** execution, halt/limit policy — matches core value in PROJECT.md.
- [ ] **Factor registration + cross-sectional rank/score pipeline** — minimal factor set (e.g. momentum, vol, volume) to validate architecture.
- [ ] **Standalone script:** grid over factor combinations × top-N; exports **standard metrics** — validates research loop without frontend.

### Add After Validation (v2.x)

- [ ] **IC / IR** and simple **Fama–MacBeth**-style diagnostics — when factor research needs stronger stats.
- [ ] **Walk-forward / rolling** evaluation — when grid search shows unstable parameters.
- [ ] **Transaction cost + slippage** — when frequency rises or approaching live.

### Future Consideration (v3+)

- [ ] **Live cross-sectional execution** on IBKR — deferred in PROJECT.md.
- [ ] **A-share cross-sectional** — different rules and data; deferred.
- [ ] **Full sector-neutral optimization** — defer until sector metadata quality is assured.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| PIT NQ100 universe + snapshots | HIGH | MEDIUM | P1 |
| Survivorship-aware historical panel | HIGH | MEDIUM | P1 |
| T+1 signal-to-execution alignment | HIGH | MEDIUM | P1 |
| Halt/limit handling policy | MEDIUM | MEDIUM | P1 |
| Core factor set + z-score / rank combination | HIGH | MEDIUM | P1 |
| Long-only top-N portfolio builder | HIGH | LOW | P1 |
| Standalone grid-search script + standard metrics | HIGH | MEDIUM | P1 |
| Long–short / simple sector-neutral | MEDIUM | MEDIUM | P2 |
| IC/IR diagnostics | MEDIUM | LOW | P2 |
| Walk-forward evaluation | MEDIUM | MEDIUM | P2 |

**Priority key:** P1 = v2.0 credibility (per PROJECT.md); P2 = after core path stable; P3 = later milestones.

## Competitor Feature Analysis

| Feature | Academic / institutional practice | Typical retail / lightweight tools | QuantDinger v2.0 approach |
|---------|-------------------------------------|--------------------------------------|---------------------------|
| Universe | CRSP/Compustat PIT; index vendors | Often “current universe” only | **NQ100 + snapshots + scrape/cache** |
| Factors | Momentum, vol, quality, FF-style | Fixed screeners | **Registered factors + scriptable combos** |
| Combination | Z-score, rank, FM regression | Fixed recipes | **Equal / weighted z-score; rank average** first |
| Execution timing | T+1 or explicit microstructure | Often simplified | **Explicit T+1 open** per PROJECT.md |
| Metrics | Sharpe, IR, IC, alphas | CAGR, drawdown | **Sharpe, Calmar, max DD, annual return, win rate** + room for IC/IR later |

## Research Q&A (maps to milestone questions)

### How cross-sectional equity strategies typically work

1. Fix **universe** and **rebalance calendar**.  
2. On each rebalance, compute **raw factor inputs** per symbol from information available **before** the trading decision (often prior close).  
3. **Cross-sectionally** clean and normalize: winsorize outliers, **z-score** within universe (and optionally neutralize by sector/size).  
4. **Combine** into a composite (equal-weighted z-scores, fixed weights, rank averages, etc.).  
5. **Construct portfolio** (long top-N, long-short, sector-neutral variants).  
6. Simulate **execution** on the next session(s) with **T+1** and **halt/limit** rules.  
7. Roll forward and compute **performance metrics**.

### Common cross-sectional factors (examples)

| Family | Typical construction (illustrative) | Notes |
|--------|-------------------------------------|--------|
| **Momentum** | 12–1 month return (12-month skip last month), or shorter horizons | Core in asset pricing; watch turnover. |
| **Reversal / short-term** | Last 1 week–1 month return (often contrarian) | Distinct from long-term momentum. |
| **Volatility** | Realized vol (e.g. 20–60d); often **long low vol** | “Low vol anomaly”; inverse-vol weighting is related. |
| **Volume / liquidity** | Dollar volume, turnover, Amihud illiquidity | Liquidity screens + signal. |
| **Mean reversion** | Distance from long MA, residual vs factor model | Often more infrastructure; pairs/cointegration heavier. |
| **Risk-adjusted** | Prior-window Sharpe/Sortino **ranked cross-sectionally** | “Quality”-adjacent; estimation noise on short windows. |

### Factor combination methods

| Method | Description | Trade-off |
|--------|-------------|-----------|
| **Equal-weight on z-scores** | Average z-scored factors (possibly after winsorize). | Simple; assumes equal marginal info. |
| **Fixed / grid weights** | Weighted sum \(\sum w_i z_i\); weights from grid search. | Flexible; overfitting risk if grid is huge without OOS discipline. |
| **Rank-based** | Average ranks or map rank to Gaussian scores | Robust to outliers; less scale-sensitive. |
| **Regression-based (e.g. Fama–MacBeth)** | Time-series of CS regressions | Stronger inference; higher build cost (P2). |

### Portfolio construction approaches

| Approach | Idea | v2.0 fit |
|----------|------|----------|
| **Long-only top-N** | Equal or score-proportional weights in top decile/N names | **P1** — matches simple mandates. |
| **Long-short** | Top vs bottom, dollar-beta-neutral | Feasible in backtest; shorting/borrow ignored or idealized unless modeled. |
| **Sector-neutral** | Demean scores by sector or constrain sector weights | Start with **demean**; full optimization **P2+** (data burden). |

### Rebalancing frequencies and trade-offs

| Frequency | Pros | Cons |
|-----------|------|------|
| **Monthly** | Common in equity factor literature; lower turnover | Slower to react |
| **Weekly** | Balance responsiveness vs noise | More turnover; needs cost awareness |
| **Daily** | Most responsive | Turnover, costs, microstructure noise dominate for typical factor signals |

### Grid search / brute-force combination patterns

- Grid over **factor subsets**, **discrete weight sets**, **top-N**, **rebalance frequency**, optional **neutralization** toggles.  
- **Risk:** many trials → **data mining**. Mitigations: **holdout**, **walk-forward**, reporting **distribution** of Sharpe across trials, fixing “production” hyperparameters before final OOS test.  
- v2.0: **scripted grid** + standard metrics; **walk-forward harness** optional P2.

### NQ100 constituent management

- **Scheduled changes:** Nasdaq-100 has a **major annual reconstitution** (typically **December**, aligned with index industry practice around “quadruple witching” week); press highlights often cite on the order of **a handful** of adds/deletes in a given year—**not** daily churn. Use **Nasdaq index notices** and methodology PDFs as the authority for exact rules and dates.  
- **Governance updates:** Nasdaq may amend methodology on a schedule (e.g. press **Mar 30, 2026** announced methodology updates **effective May 1, 2026**, with prior methodology through **Apr 30, 2026** — see [Nasdaq press release](https://www.nasdaq.com/press-release/nasdaq-concludes-public-consultation-nasdaq-100-indexr-methodology-2026-03-30)). Implementation details are communicated via **standard index notices** — product should **subscribe to notices** or poll official sources, not only annual December.  
- **Historical constituents:** There is **no single universal free API** for perfect point-in-time NQ100 membership over decades. Practical sources: **commercial index history**, **reconstruct from archived constituents + corporate actions**, or **internal snapshots from first run forward** + partial backfill. For QuantDinger v2.0, **forward snapshots + best-effort historical alignment** is a pragmatic split; label confidence in any pre-snapshot backtests.

### Standard backtest metrics (definitions to document in code)

| Metric | Typical definition | Caveat |
|--------|--------------------|--------|
| **Annual return / CAGR** | Geometric mean annualized return over window | Depends on return definition (log vs simple); **document**. |
| **Sharpe ratio** | Mean excess return / vol of returns; **annualize** with consistent \(\sqrt{k}\) rule for k periods/year | Annualization convention must be **fixed** across runs. |
| **Max drawdown** | Max peak-to-trough on cumulative equity curve | Path-dependent; use same return series as Sharpe. |
| **Calmar** | CAGR / \|max drawdown\| | Undefined or unstable if max DD ≈ 0. |
| **Win rate** | Fraction of periods (e.g. months) with positive strategy return | Can look good with fat tails; pair with **max DD** and distribution. |

Optional research-grade add-ons (P2): **information coefficient (IC)**, **information ratio**, simple **turnover** and **capacity** proxies.

## Sources

- [Nasdaq Global Indexes — NDX overview](https://indexes.nasdaq.com/Index/Overview/NDX) — index description; links to methodology PDFs and research PDFs.  
- [Nasdaq press release — Nasdaq-100 methodology consultation resolved (Mar 30, 2026)](https://www.nasdaq.com/press-release/nasdaq-concludes-public-consultation-nasdaq-100-indexr-methodology-2026-03-30) — **effective May 1, 2026**; prior methodology through **Apr 30, 2026**.  
- Nasdaq methodology PDF (e.g. `methodology_NDX.pdf` on indexes.nasdaq.com) — authoritative rules; verify current revision when implementing.  
- Asset pricing references: Fama–French factors; Jegadeesh & Titman (momentum); standard practice for **PIT** universes and **T+1** execution assumptions in US equity backtests.  
- Internal: `.planning/PROJECT.md` — v2.0 scope, T+1 alignment, survivorship/halt goals, out-of-scope items.

---
*Feature research for: Cross-sectional strategy backtesting on QuantDinger (NQ100)*  
*Researched: 2026-04-13*
