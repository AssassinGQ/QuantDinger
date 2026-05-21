# Stack Research

**Domain:** Cross-sectional equity strategies (NQ100 universe, factor panels, grid-search backtests) on existing QuantDinger stack  
**Researched:** 2026-04-13  
**Confidence:** HIGH for library versions (PyPI JSON verified 2026-04-13); MEDIUM for scrape reliability (site HTML/ToS change without notice)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-------------------|
| **beautifulsoup4** | `>=4.14,<5` | Parse HTML tables/pages (Wikipedia, Nasdaq-style listings) | De facto standard for static HTML; pairs with existing `requests`; no browser for server-rendered tables. PyPI latest **4.14.3**. |
| **lxml** | `>=6.0,<7` | Fast XML/HTML parser backend for Beautiful Soup | Speed + robust parsing; wheels on Linux/WSL; BS4 performs better with a fast parser than pure `html.parser`. PyPI latest **6.0.4**. |
| **pandas** | `>=1.5.0` (current floor); target `>=2.2,<4` after QA; PyPI latest **3.0.2** | Multi-asset panels (date × symbol), factor columns, merges for T+1 / rebalances | Already in `backend_api_python/requirements.txt`. Cross-sectional work benefits from 2.2+ APIs and performance; **do not** jump to pandas 3.x without running the full backend test suite (breaking changes vs 1.5/2.x). |
| **numpy** | Pulled by pandas; floor `>=1.26,<3` compatible with pandas pin; PyPI latest **2.4.4** | Vectorized factor math, returns, ranking | Explicit floor avoids ancient wheels; align numpy major with chosen pandas wheel set. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **requests** | `>=2.28` (existing) | HTTP GET for public index constituent pages | Default path; already used in backend and `scripts/cross_sectional/nq100_cross_sectional.py`. |
| **tenacity** | `>=8.2,<10` | Retries with backoff for flaky scrape endpoints | When sources return 429/5xx intermittently. PyPI latest **9.1.4**. |
| **filelock** | `>=3.15,<4` | Cross-process locks for checkpoint / JSONL append | When grid search uses multiple processes and one file records progress. PyPI latest **3.25.2**. |
| **joblib** | `>=1.4,<2` | `Parallel` + optional `Memory` for embarrassingly parallel backtests | Familiar API for numpy/pandas-heavy workers; optional disk cache for repeated factor builds. PyPI latest **1.5.3**. |
| **pandas_market_calendars** | `>=5.0,<6` (optional) | NYSE/Nasdaq **sessions** — next valid open after signal close | **Recommended** once you encode “signal at D close → trade at **next session** open” with holidays/halts; avoids hand-maintained holiday lists. PyPI latest **5.3.2**. Often used with `exchange_calendars` under the hood. |
| **httpx** | `>=0.27,<1` (optional) | Async-capable HTTP if scrape + fetch pipelines unify | Only if you add async batching; otherwise stay on `requests` to minimize dependencies. PyPI latest **0.28.1**. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **pytest** (existing) | Unit tests for HTML parsers + factor / calendar alignment | Fixtures: saved HTML snippets; **no live network in CI** for scrapers. |
| **stdlib `concurrent.futures`** | `ProcessPoolExecutor` / `ThreadPoolExecutor` | Prefer first for grid search — zero new dependencies. |
| **`OMP_NUM_THREADS=1`** (env) | Limit BLAS thread explosion | When using multiprocessing + numpy/pandas together to avoid oversubscription. |

## Installation

```bash
# Backend — add to backend_api_python/requirements.txt (or extras file for “cross_sectional”)
pip install "beautifulsoup4>=4.14,<5" "lxml>=6.0,<7" "tenacity>=8.2,<10"

# Optional: parallel grid search + safe checkpointing
pip install "joblib>=1.4,<2" "filelock>=3.15,<4"

# Optional: US equity session calendar for T+1 / next-open logic
pip install "pandas-market-calendars>=5.0,<6"

# Pandas/numpy upgrades — run full backend tests before merging
# pip install "pandas>=2.2,<4" "numpy>=1.26,<3"
# For pandas 3.x / numpy 2.x: evaluate release notes + test matrix separately
```

Standalone script under `scripts/cross_sectional/` should use the **same** pinned versions as the backend once the milestone locks versions.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| BS4 + lxml | **pandas.read_html** | Quick one-offs; less control over malformed tables — OK for exploration, fragile as sole production parser. |
| `requests` | **httpx** / **aiohttp** | Many concurrent third-party fetches; still respect rate limits and terms of use. |
| `joblib.Parallel` | **multiprocessing.Pool** | Zero extra deps; more boilerplate for chunking and error propagation. |
| **PostgreSQL tables** for constituents + optional disk CSV | **Redis** | Multi-instance hot cache or pub/sub; v2.0 does not require Redis if DB + short-lived in-process cache suffice. |
| **pandas DataFrame panels** | **Polars** / **xarray** | Very large universes or explicit 3-D labeled arrays; adds migration cost — revisit if profiling shows pandas as bottleneck. |
| **pandas_market_calendars** | Manual US holiday list + **pandas.tseries.offsets.BDay** | Simpler if you only need weekdays and accept wrong behavior around full-market holidays; not recommended for production-grade T+1. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **Scrapy** | Heavy framework for periodic single-URL/table jobs | `requests` + BS4 + APScheduler (already in stack) |
| **Selenium / Playwright** for NQ100-only lists | CI/runtime cost unless targets require JS rendering | Plain HTTP + HTML parse first; add browser automation only after proving static HTML is insufficient |
| **Replacing Flask or PostgreSQL** | Out of project constraints | Keep API and SQLAlchemy/psycopg2 patterns |
| **Dask / Ray** for initial grid search | Operational complexity; NQ100 × thousands of combos typically fits one machine RAM | `joblib` or `ProcessPoolExecutor`; scale out only when profiling demands it |
| **Celery** as mandatory | v2.0 is backend + script; no distributed queue requirement | APScheduler + cron for constituent refresh |

## Stack Patterns by Variant

**If scraping is rate-limited or unstable:**

- Wrap fetch + parse with **tenacity**; optionally persist raw HTML (blob column or file) for audit and reparse.
- Use a stable **User-Agent** and comply with **robots.txt** / site terms.

**If grid search parallelizes:**

- Single writer for **checkpoint.json** / JSONL — or **filelock** around append/rewrite.
- Avoid nested parallelism (many worker processes + multi-threaded BLAS): set `OMP_NUM_THREADS=1` (and friends) for workers.

**If fixing survivor bias, T+1, halts in software:**

- **Survivor bias:** join returns to **point-in-time** membership from DB constituent history (see schema below), not “today’s” list applied to history.
- **T+1:** rank on signal bar (e.g. close); execute on **next session open** — optional **pandas_market_calendars** for correct next open across holidays.
- **Halts / limits:** logic in backtest engine (no position change when volume=0 or rule says untradeable); optional reference data later — no extra pip package required for a minimal v2.0.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-----|
| beautifulsoup4 4.14.x | lxml 6.x | `BeautifulSoup(html, "lxml")` |
| pandas 2.2+ | numpy 1.26+ | Match wheels to Python 3.10+ images |
| pandas 3.x (if adopted) | numpy 2.x | Read pandas 3.0 release notes; re-run full test suite |
| SQLAlchemy 2.0+ (existing) | psycopg2-binary 2.9+ | New constituent tables use same engine/session |
| joblib 1.5.x | stdlib multiprocessing | `n_jobs` ≤ CPU cores; `prefer="processes"` for CPU-bound pandas work |

## Integration with QuantDinger

| Area | Integration |
|------|-------------|
| **Backend** | New modules: fetch → parse → normalize tickers → upsert DB; optional route e.g. `GET /api/.../universe/nq100` reading DB cache. Reuse existing auth if exposed. |
| **Scheduler** | **APScheduler** (already required): periodic job to refresh constituents; log `source_url`, `scraped_at`, row counts. |
| **K-line / indicators** | No breaking change to `/api/indicator/kline`; cross-sectional engine consumes the same bars as `nq100_cross_sectional.py`. |
| **Standalone script** | Keep brute-force script as thin client over API + local CSV cache; universe from DB export or API instead of hardcoded `NQ100_UNIVERSE` only. |
| **Tests** | Golden HTML for parsers; backtest tests for **calendar alignment** (month-end, next open) without network. |

## Database Schema (additions — illustrative)

No new database *product*; use existing PostgreSQL + SQLAlchemy migrations.

| Table / concept | Role |
|-----------------|------|
| **index_definition** | e.g. `NASDAQ100`, display name, data vendor |
| **index_constituent_snapshot** | `(index_id, as_of_date, symbol, source, raw_hash)` — point-in-time membership for survivor-bias-aware joins |
| **index_constituent_event** (optional) | `(index_id, symbol, effective_date, action add/remove, source)` — derived from snapshot diffs |

Indexes: `(index_id, as_of_date)`, `(symbol, as_of_date)` for lookups.

## Caching Strategy

| Layer | What to cache | TTL / invalidation |
|-------|---------------|-------------------|
| **PostgreSQL** | Authoritative constituent history + “latest” row per index | Update on successful scrape; store `scraped_at` and source metadata |
| **Application memory** | Last good list for API hot path | Minutes TTL or process lifetime |
| **Disk (script)** | Per-symbol CSV kline cache — e.g. `scripts/cross_sectional/cache/` | Time-based (e.g. 48h) as in current script |
| **HTTP** | `ETag` / `Last-Modified` if source supports | Reduces bandwidth when page unchanged |

Do **not** scrape Nasdaq/Wikipedia on every API request — batch job + DB is the right pattern.

## Sources

- PyPI JSON API — versions verified **2026-04-13**: beautifulsoup4 **4.14.3**, lxml **6.0.4**, tenacity **9.1.4**, filelock **3.25.2**, joblib **1.5.3**, httpx **0.28.1**, pandas **3.0.2**, numpy **2.4.4**, pandas_market_calendars **5.3.2**
- [https://pypi.org/project/beautifulsoup4/](https://pypi.org/project/beautifulsoup4/)
- [https://pypi.org/project/lxml/](https://pypi.org/project/lxml/)
- Project: `.planning/PROJECT.md` (v2.0 Cross-Sectional milestone)
- Reference script: `scripts/cross_sectional/nq100_cross_sectional.py` (panels, checkpoint JSONL, CSV cache)
- Existing deps: `backend_api_python/requirements.txt`

---
*Stack research for: QuantDinger v2.0 cross-sectional strategy features*  
*Researched: 2026-04-13*
