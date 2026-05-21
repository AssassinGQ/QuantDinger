# Project Research Summary

**Project:** QuantDinger — v2.0 Cross-Sectional Strategy  
**Domain:** Cross-sectional equity strategies (NASDAQ 100 universe, factor panels, grid-search backtests) on the existing QuantDinger brownfield stack  
**Researched:** 2026-04-13  
**Confidence:** MEDIUM–HIGH (stack versions PyPI-verified; scrape reliability and pre-snapshot NQ100 history are medium-confidence)

## Executive Summary

QuantDinger v2.0 adds **credible cross-sectional equity backtesting** on the NQ100 universe: point-in-time membership, cross-sectional factors and portfolio construction, and execution-realistic simulation (T+1 open after signal at prior close, halt/limit policy). Experts build this as **server-owned universe history** (PostgreSQL snapshots, not static lists), **shared factor/panel libraries** importable from API and scripts, and a **dedicated portfolio backtest path** separate from single-asset `BacktestService.run()` semantics.

The recommended approach is: **beautifulsoup4 + lxml + requests** (with optional **tenacity**, **filelock**, **joblib**) for ingest; **pandas/numpy** aligned with existing floors (upgrade pandas 2.2+ only after full test suite); optional **pandas_market_calendars** for next-session open after US holidays; **APScheduler** for periodic constituent refresh; **no** Scrapy/Selenium for simple table scrapes, **no** Dask/Ray/Celery for initial grid search. Constituent data lands in **normalized tables** (`index_definition`, snapshot/event rows) with indexes for `(index_id, as_of_date)` lookups; scripts consume **API and/or read-only DB** with CSV cache as derived cache only.

**Key risks:** (1) **Survivorship and membership look-ahead** if “today’s NQ100” drives history — mitigate with PIT snapshots, delisted bar retention, and auditable scrape metadata. (2) **Same-bar lookahead** if close-based signals fill on the same bar — mitigate with explicit signal vs execution timestamps, trading-calendar-aware shifts, and unit tests. (3) **Calendar and panel alignment** across symbols — use a reference equity calendar and avoid blind `shift(1)` on merged panels. (4) **Scrape fragility** — mitigate with retries, optional raw HTML storage, and **no** live network in CI (golden HTML fixtures).

## Key Findings

### Recommended Stack

Research favors **minimal, proven** dependencies on top of the existing Flask + PostgreSQL + pandas stack. **beautifulsoup4 (≥4.14,<5)** with **lxml (≥6,<7)** is the default HTML parsing path; **requests** stays the HTTP client unless async batching justifies **httpx**. **tenacity** handles flaky endpoints; **filelock** protects checkpoint/JSONL under parallel workers; **joblib** or stdlib **ProcessPoolExecutor** covers grid search — set **`OMP_NUM_THREADS=1`** when combining multiprocessing with BLAS-backed numpy/pandas. **pandas_market_calendars** is recommended once “next session open” must respect NYSE/Nasdaq holidays. **Do not** jump to pandas 3.x without running the full backend test suite; pin **numpy** consistently with the chosen pandas wheel set.

**Core technologies:**
- **beautifulsoup4 + lxml:** Parse static HTML constituent tables — de facto standard; fast parser backend; no browser for server-rendered tables.
- **pandas + numpy:** Date × symbol panels, factors, ranks — already in stack; cross-sectional work benefits from modern pandas APIs; upgrade deliberately.
- **PostgreSQL + SQLAlchemy:** Authoritative constituent history and “as of” queries — same patterns as `qd_kline_points`; no new database product.

Detailed pins, alternatives (Polars, httpx, Redis), and integration notes: [STACK.md](./STACK.md).

### Expected Features

Credible cross-sectional backtests require **PIT investable universe**, **per-rebalance cross-sectional factors**, **signal vs execution separation (T+1 open)**, **survivorship-aware price history**, **halt/limit policy**, **portfolio construction from ranks**, **rebalancing schedule**, **standard metrics**, and a **reproducible batch/grid script**. Differentiators include **dynamic NQ100 ingest with versioned snapshots**, **explicit factor combination (winsorize → z-score → blend)**, and **disciplined grid search** (guard against pure in-sample Sharpe mining). **Defer** live cross-sectional IBKR automation, full sector-neutral optimization, and A-share rules to later milestones; **avoid** same-bar execution, current universe on all history, and unconstrained “best Sharpe” grids without holdout/walk-forward discipline.

**Must have (table stakes):**
- PIT NQ100 universe + historical snapshots — rankings must not use future membership.
- Cross-sectional factor pipeline + execution-realistic backtest (T+1 open, halts) — matches PROJECT.md core value.
- Survivorship-aware panel — delisted names remain in historical data where policy allows.

**Should have (competitive):**
- Dynamic NQ100 ingest + server cache + auditable snapshots — reduces manual list drift.
- Factor combination library and grid script with standard metrics — research velocity on-platform.

**Defer (v2+):**
- IC/IR, Fama–MacBeth-style diagnostics, walk-forward harness, transaction-cost models — after core path validates.

Full landscape, MVP checklist, and prioritization: [FEATURES.md](./FEATURES.md).

### Architecture Approach

Extend the **brownfield** monolith: new **`Nq100ConstituentService`** (scrape → normalize → upsert), **`routes/universe.py`** for `GET` constituents/history, **`app/services/cross_sectional/`** for pure pandas/numpy factors and panel alignment (no Flask in core math), and **APScheduler** job for periodic refresh. Keep existing **`CrossSectionalStrategy`** / `run_cross_sectional_indicator`; add a **distinct cross-sectional backtest service or methods** that build panels and portfolio returns — do not force multi-symbol logic into single-symbol `BacktestService.run()`. Standalone **`scripts/cross_sectional/`** should import shared app code via `PYTHONPATH` or package install. **Build order:** DB + membership API → kline coverage for universe symbols → shared factor/panel library → backtest pitfall implementation → optional API exposure → grid script last.

**Major components:**
1. **Constituent ingestion + PostgreSQL snapshots** — authoritative “who was in NQ100 on date D.”
2. **`services/cross_sectional/` (factors, panels)** — shared between backend, strategies, and scripts.
3. **Cross-sectional portfolio backtest engine** — T+1, halts, weights, one equity curve (not N× single-asset averages).

Diagrams and file layout: [ARCHITECTURE.md](./ARCHITECTURE.md).

### Critical Pitfalls

1. **Survivorship / “current universe” on history** — Persist PIT membership and include delisted symbols in bars; never filter history with today’s list only.
2. **Look-ahead (signal and fill on same close bar)** — Define `signal_time` vs `execution_time`; attribute returns to post-signal sessions; test that close-derived signals do not fill same bar.
3. **Calendar misalignment** — Use a reference US equity session calendar; avoid one global `shift(1)` on heterogeneous symbol calendars; optional **pandas_market_calendars** for next open.
4. **Halt / limit-up-down** — Heuristics from OHLCV (e.g. zero volume, limit-locked days); explicit cash vs hold rules; no fantasy fills at open when untradeable.
5. **Bolting portfolio logic onto single-asset backtest API** — New panel engine with one portfolio return definition; shared only low-level data readers.

Full list, debt patterns, and checklist: [PITFALLS.md](./PITFALLS.md).

## Implications for Roadmap

Suggested phase structure aligns with dependency order in architecture research and pitfall prevention.

### Phase 1: Universe data plane (constituents + DB + API)
**Rationale:** Every downstream join depends on correct **as-of** membership; survivor bias is fatal if deferred.  
**Delivers:** Migrations for index/snapshot tables, `Nq100ConstituentService` (fetch/parse/upsert), `GET` universe endpoints, scheduled refresh job, logging of source URL and scrape time.  
**Addresses:** PIT NQ100, dynamic ingest (FEATURES P1).  
**Avoids:** Pitfalls 1 (survivorship), hardcoded `NQ100_UNIVERSE` as sole truth (ARCHITECTURE anti-pattern 1).

### Phase 2: Kline coverage and delisted retention policy
**Rationale:** Cross-sectional panels need aligned bars **including** names that later delist.  
**Delivers:** Policy and sync/backfill alignment so universe symbols (and delisted history per policy) exist in `qd_kline_points`; document retention.  
**Addresses:** Survivorship-aware historical panel (FEATURES P1).  
**Avoids:** Pitfall 1 (live-listed-only histories).

### Phase 3: Shared cross-sectional library (factors + panels)
**Rationale:** One implementation for script, backtest, and future API; golden tests per factor.  
**Delivers:** `app/services/cross_sectional/` (factors, panel alignment, NaN/tie policy); refactor `scripts/cross_sectional/nq100_cross_sectional.py` to import shared code.  
**Addresses:** Factor registration, z-score/rank pipeline, minimum universe size K (FEATURES P1).  
**Avoids:** Pitfalls 4–6 (calendar, factor windows, rank NaNs/ties).

### Phase 4: Cross-sectional backtest engine (T+1, halts, portfolio curve)
**Rationale:** Core credibility: execution model and portfolio returns before large grid search.  
**Delivers:** New service or methods: panel → signals → **T+1 open** fills, halt/limit rules, long-only top-N weights, standard metrics module; unit tests for signal vs fill dates.  
**Addresses:** T+1, halt/limit policy, portfolio construction, metrics (FEATURES P1).  
**Avoids:** Pitfalls 2, 3, 8 (lookahead, halts, single-asset integration).

### Phase 5: Grid search script + reporting discipline
**Rationale:** Depends on correct panels and metrics; last to avoid optimizing wrong objective.  
**Delivers:** Parameter sweep (joblib/executor), checkpointing (**filelock**), exports; document IS vs OOS expectations (process + optional P2 harness).  
**Addresses:** Standalone grid script (FEATURES MVP).  
**Avoids:** Pitfall 7 (zero-cost overconfidence) — at least document cost sensitivity; anti-feature “best in-sample Sharpe only.”

### Phase Ordering Rationale

- **Universe and bars before factors:** PIT membership and bar retention define the panel; factors are meaningless on the wrong universe.  
- **Shared library before heavy backtest:** Reduces duplication and makes script and service consistent.  
- **Engine before grid:** Grid multiplies errors; pitfall mapping places survivor + T+1 engine before brute-force search.  
- **Scheduler + DB cache, not per-request scraping:** Matches STACK caching strategy.

### Research Flags

Phases likely needing deeper research or decisions during planning:
- **Phase 1 (universe ingest):** **Source selection** (Nasdaq vs Wikipedia vs vendor) — HTML/ToS changes; **robots.txt** and rate limits; optional **research-phase** on legal/operational scrape policy.
- **Phase 2 (bars):** **Historical NQ100** before first snapshot — reconstruction vs vendor; label confidence in pre-snapshot backtests.
- **Phase 4 (engine):** **Halt detection** from OHLC alone is heuristic; US vs future A-share rules differ.

Phases with standard patterns (lighter research):
- **Phase 3 (pandas factors/ranks):** Well-trodden patterns; focus on tests and documentation.
- **Phase 5 (joblib/checkpoint):** Common batch patterns; **tenacity** + **filelock** are documented stack choices.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | PyPI versions verified 2026-04-13; pandas major upgrade needs explicit QA. |
| Features | MEDIUM–HIGH | Strong alignment with equity factor practice; perfect decades-long free PIT NQ100 history is not assumed. |
| Architecture | HIGH | Grounded in repo inspection (`BacktestService`, `cross_sectional*`, scheduler, scripts). |
| Pitfalls | HIGH | Look-ahead/survivorship/calendar mechanics are standard; halt magnitudes and cost bps are context-dependent. |

**Overall confidence:** MEDIUM–HIGH

### Gaps to Address

- **Long-horizon PIT NQ100 without a vendor:** Forward snapshots + best-effort backfill; document confidence bands for early years.  
- **Official scrape/API target:** Final URL and parser tests with **frozen HTML** in CI.  
- **Pandas/numpy upgrade path:** If pinning moves to 2.2+/numpy 2.x, run full backend tests before merge.  
- **PROJECT.md scope confirmation:** Optional REST exposure for cross-sectional backtest vs script-only — align when locking ROADMAP phases.

## Sources

### Primary (HIGH confidence)
- PyPI JSON API — package versions (2026-04-13): beautifulsoup4, lxml, pandas, numpy, tenacity, filelock, joblib, pandas_market_calendars (see [STACK.md](./STACK.md)).
- Repository — `backend_api_python/app/services/backtest.py`, `app/strategies/cross_sectional*.py`, `scheduler_service`, `scripts/cross_sectional/nq100_cross_sectional.py`, migrations.
- [Nasdaq NDX methodology PDF](https://indexes.nasdaq.com/docs/methodology_NDX.pdf) — index rules and reconstitution process.
- [Nasdaq press release — Nasdaq-100 methodology consultation (2026-03-30)](https://www.nasdaq.com/press-release/nasdaq-concludes-public-consultation-nasdaq-100-indexr-methodology-2026-03-30) — effective dates for methodology change.

### Secondary (MEDIUM confidence)
- Asset pricing / industry practice — PIT universes, T+1 convention, survivorship impact ranges (strategy-dependent).
- Pandas documentation — `shift`, `merge_asof`, alignment semantics.

### Tertiary (LOW confidence)
- Specific survivorship **percentage** impact without this product’s exact universe and horizon — treat order-of-magnitude only.

---
*Research completed: 2026-04-13*  
*Ready for roadmap: yes*
