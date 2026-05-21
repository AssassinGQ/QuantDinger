# Architecture Research

**Domain:** QuantDinger — Cross-sectional (NQ100) strategy integration (brownfield)
**Researched:** 2026-04-13
**Confidence:** HIGH for existing code paths (repo inspection); MEDIUM for NQ100 scrape source choice (not yet implemented)

## Standard Architecture

### System Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         Clients & batch jobs                                │
├────────────────────────────────────────────────────────────────────────────┤
│  Vue 2 UI          │  scripts/cross_sectional/*.py (REST + optional DB)    │
└──────────┬─────────┴───────────────────────┬─────────────────────────────────┘
           │                               │  Bearer /api/auth/login
           │ HTTP                          │  GET /api/indicator/kline (paginated)
           ▼                               ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                    Flask API (backend_api_python/app)                       │
├────────────────────────────────────────────────────────────────────────────┤
│  routes/          indicator (kline), backtest, strategy, scheduler         │
│  services/        KlineService, BacktestService, scheduler_service        │
│  strategies/      SingleSymbolStrategy, CrossSectionalStrategy, factory    │
└──────────┬───────────────────────────────────────────────────────────────────┘
           │
           ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  PostgreSQL                                                                 │
│  qd_kline_points / qd_kline_cache / qd_kline_ranges  — bar storage        │
│  qd_market_symbols — tradable symbol catalog (per market)                  │
│  [NEW] universe constituent snapshots — NQ100 effective membership history │
└────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `KlineService` + `kline_fetcher` | Single-symbol OHLCV; DB-first then upstream | Existing; feeds `/api/indicator/kline` and `BacktestService._fetch_kline_data` |
| `BacktestService` | Per-symbol indicator execution + `_simulate_trading` | `app/services/backtest.py`; REST: `routes/backtest.py` |
| `CrossSectionalStrategy` + `run_cross_sectional_indicator` | Multi-symbol `data: {symbol: df}` → scores/rankings via user indicator code | `app/strategies/cross_sectional*.py` — **already integrated** with executor path |
| `scheduler_service` | APScheduler: kline sync, pluggable `register_scheduled_job` | Extend for periodic NQ100 scrape |
| `scripts/cross_sectional/nq100_cross_sectional.py` | Offline grid search; login + paginated kline pull | Prototype of standalone script pattern |

## Recommended Project Structure (v2.0 additions)

```
backend_api_python/app/
├── routes/
│   └── universe.py              # NEW: GET constituents, history (optional admin POST refresh)
├── services/
│   ├── nq100_constituent_service.py   # NEW: scrape → normalize → persist snapshots
│   └── cross_sectional/               # NEW package: reusable factor math (optional)
│       ├── __init__.py
│       ├── factors.py                 # pure pandas/numpy factor defs (shared with scripts)
│       └── panels.py                  # align dates, survivorship helpers
├── models/  (or existing models file)
│   └── universe_snapshot.py     # NEW: SQLAlchemy model for index membership rows
└── strategies/
    ├── cross_sectional.py       # EXISTING — keep; may call shared factor helpers
    └── cross_sectional_indicator.py  # EXISTING exec() sandbox; optional thinner wrapper

scripts/cross_sectional/
├── nq100_cross_sectional.py     # EXISTING — heavy search; refactor imports from app.* shared lib
└── README.md                    # optional: env vars, DSN vs REST
```

### Structure Rationale

- **`services/cross_sectional/`:** Pure Python (no Flask request context) so the same factor/panel code runs inside `BacktestService`, executor-driven strategies, and CLI scripts without duplication.
- **`routes/universe.py` + DB snapshots:** Constituent history is authoritative server-side data; scripts and future automation read one API instead of hardcoded lists.
- **Keep `strategies/cross_sectional*.py`:** Already wired through `create_strategy()`; new work augments data sources and backtest correctness, not a parallel strategy system.

## Architectural Patterns

### Pattern 1: Server-owned universe + client pull (REST)

**What:** NQ100 membership and effective dates live in PostgreSQL; HTTP API returns “as of date” constituents and optional change log.
**When to use:** Default for QuantDinger — aligns with existing auth, logging, and single cache path for klines.
**Trade-offs:** (+) consistent with Docker deployment; (−) bulk backtests need pagination or a batch export endpoint if REST becomes the bottleneck.

### Pattern 2: Shared library + thin routes

**What:** Scrape/normalize/factor/panel code in importable modules; Flask routes only parse/validate and call services.
**When to use:** Always — matches existing `StrategyService`, `KlineService` style.
**Trade-offs:** (+) testable without HTTP; (−) requires discipline to avoid circular imports (keep factors free of Flask).

### Pattern 3: Scheduled refresh (APScheduler)

**What:** Register `register_scheduled_job("nq100_constituent_refresh", ...)` alongside `kline_sync` in `app/tasks/__init__.py` pattern.
**When to use:** NQ100 rebalances quarterly; daily/weekly job is enough.
**Trade-offs:** (+) reuses existing scheduler infra; (−) long-running scrape should be idempotent and logged.

## Data Flow

### Request Flow (standalone script → kline cache)

```
Script: login → Bearer token
    → GET /api/indicator/kline?market=USStock&symbol=X&timeframe=1D&limit=&before_time=
    → KlineService.get_kline → qd_kline_points (read/merge) → upstream fetch → writeback
    → JSON rows → pandas panel in script
```

### Cross-sectional live/strategy path (existing)

```
Executor → DataHandler (multi-df) → InputContext["data"] = {sym: df}
    → run_cross_sectional_indicator(code, data, trading_config)
    → scores / rankings → generate_cross_sectional_signals → orders
```

### Key Data Flows

1. **Constituent refresh:** External source (NASDAQ/Wikipedia/API TBD) → `nq100_constituent_service` → **new table** rows `(index_id, symbol, effective_from, effective_to|null, source, scraped_at)` — **not** JSON-only, so queries like “members on date T” are indexed and auditable.
2. **Cross-sectional backtest (new/extended):** Universe snapshots × `qd_kline_points` for each symbol → aligned panel → factor engine → rank → portfolio returns with **explicit T+1 and halt rules** (pitfall fixes).

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|-------------------------|
| Single developer / one machine | Monolith + PostgreSQL + existing `qd_kline_points` indexes; script CSV cache under `scripts/cross_sectional/cache/` for repeat runs |
| Repeat large grids (5k+ backtests) | Precompute daily return panel (Parquet on NAS or temp table); optional `GET /api/.../export` bulk bar range for trusted users |
| 100+ symbols × 1D × ~10y | ~250k bars/symbol-tier — feasible in Postgres with `(market, symbol, interval_sec, time_sec)` indexes; avoid N+1 HTTP: batch DB read in script mode or server-side panel builder |

### Scaling Priorities

1. **First bottleneck:** HTTP per-symbol loops — mitigate with direct read-only DB URL for batch jobs *or* a dedicated export service method.
2. **Second bottleneck:** Repeated factor computation — memoize panels on disk (JSONL checkpoint already in script) or shared Parquet.

## Anti-Patterns

### Anti-Pattern 1: Hardcoded universe in production paths

**What people do:** Keep `NQ100_UNIVERSE` only in `scripts/` as the source of truth.
**Why it's wrong:** Survivorship and rebalance correctness require historical membership; static lists bias results.
**Do this instead:** DB snapshots + API; script falls back to API, keeps CSV only as cache.

### Anti-Pattern 2: Duplicating cross-sectional backtest inside `BacktestService.run()` without a dedicated code path

**What people do:** Force multi-symbol logic into single-symbol `run()` loops.
**Why it's wrong:** `BacktestService.run` is built around one `df` and per-symbol indicator execution (`_execute_indicator` on one frame — see `app/services/backtest.py`).
**Do this instead:** New method or `CrossSectionalBacktestService` that builds panels, applies pitfall rules, and optionally shares factor helpers with `run_cross_sectional_indicator` semantics.

### Anti-Pattern 3: JSON blob-only constituent history

**What people do:** One JSON file per day in the repo.
**Why it's wrong:** Hard to query “who was in the index on 2023-06-15”, no concurrent access, weak audit trail.
**Do this instead:** Relational rows or at least a single table with normalized dates; JSON optional as scrape staging before upsert.

## Integration Points

### Answers to milestone questions

#### 1) NQ100 constituent management — where it lives

| Layer | New vs modified | Recommendation |
|-------|-----------------|----------------|
| Model | **New** | Table e.g. `qd_index_constituents` (or `qd_universe_membership`) with index key `NASDAQ100`, symbol, effective dates |
| Service | **New** | `Nq100ConstituentService`: fetch, parse, diff, upsert |
| Route | **New** | `GET /api/universe/nq100?as_of=YYYY-MM-DD`, `GET .../history` under `routes/universe.py` (blueprint registered in `routes/__init__.py`) |
| Schedule | **New job** | `register_scheduled_job` + manual trigger route mirroring `/api/scheduler` patterns |

#### 2) Constituent history snapshots — storage

| Option | Verdict |
|--------|---------|
| **PostgreSQL rows (recommended)** | Queryable, concurrent-safe, fits existing migration style (`migrations/*.sql`) |
| JSON in DB | OK for raw scrape payload *in addition to* normalized rows, not as sole store |
| CSV in repo | Dev-only; script cache already uses `scripts/cross_sectional/cache/` for kline — acceptable for **derived** caches, not authoritative membership |

#### 3) Cross-sectional factor engine — module vs standalone

| Approach | Verdict |
|----------|---------|
| **Backend module** (`app/services/cross_sectional/` + optional thin strategy glue) | **Recommended:** same code for API backtest, automation, and `scripts/` via `PYTHONPATH` or package install |
| Standalone package only | Rejected for v2.0 — duplicates deployment and version drift |

Interaction with kline/indicator APIs: factors consume **panels** built from `KlineService` / DB — not a new kline table. User-defined cross-sectional **indicators** still go through `run_cross_sectional_indicator` (`exec` sandbox); **library factors** are imported helpers used when building panels or generating default indicator templates.

#### 4) Standalone backtest script — placement and backend interaction

| Topic | Recommendation |
|-------|----------------|
| **Placement** | Keep under `scripts/cross_sectional/` (already matches repo convention); add shared imports from `app.services.cross_sectional` |
| **Auth** | **REST:** `POST /api/auth/login` → `Authorization: Bearer <token>` on `/api/indicator/kline` (implemented in `nq100_cross_sectional.py`) |
| **Direct DB** | **Optional** for trusted batch jobs: read-only connection to `qd_kline_points` bypasses HTTP overhead — use same DSN as backend (`env`), never write from script except local cache files |
| **Both** | Use REST when populating cache from live API; use DB direct only after security review |

#### 5) Suggested build order (dependencies)

1. **DB + API for NQ100 membership** — downstream needs correct universe for survivorship-aware joins.
2. **Kline coverage for universe** — ensure `USStock` symbols sync/backfill (existing scheduler + `scripts/backfill_kline_history.py` patterns).
3. **Shared factor/panel library** — pure functions + tests; refactor script to import them.
4. **Backtest pitfall audit & implementation** — touch `BacktestService` single-symbol paths and add **cross-sectional** backtest path (panels, T+1, halts); see “Backtest pitfall audit” below.
5. **Wire cross-sectional backtest to API** (optional in v2.0 if scope is script-only per PROJECT.md — confirm; PROJECT says backend + script).
6. **Heavy grid search script** — last; depends on correct panels and metrics.

#### 6) Large data volume (100+ symbols × daily × years)

- **Storage:** Existing `qd_kline_points` is the right sink; composite index supports range scans per symbol.
- **Compute:** Build **daily** panels in pandas in chunks (symbol batches), persist checkpoint (script already uses JSONL).
- **API:** Prefer **bounded** `limit` + `before_time` pagination (script pattern) or server-side “panel build” job for repeated research.
- **Optional materialization:** Nightly job writing a **Parquet** daily panel for NQ100 to speed research — product decision, not required for MVP.

### Backtest pitfall audit — code paths to review

| Concern | Where to look | Notes |
|---------|----------------|-------|
| Single-symbol backtest | `app/services/backtest.py` — `run`, `_fetch_kline_data`, `_simulate_trading` | Survivorship: data only for symbols still in DB — universe table + delisted bars policy |
| REST entry | `app/routes/backtest.py` — `run_backtest` | Params for future `strategyType=cross_sectional` if exposed |
| Cross-sectional **live** path | `app/strategies/cross_sectional.py`, `cross_sectional_indicator.py`, `DataHandler` (multi-df) | Confirms ranking **execution** is separate from backtest pitfall fixes |
| Script prototype | `scripts/cross_sectional/nq100_cross_sectional.py` | Monthly rebalance logic — align with “signal day close → next open” when porting to service |
| Kline integrity | `app/services/kline.py`, `kline_fetcher.py` | Stale/missing bars → halts |

**Engine location:** Primary backtest engine for single-symbol is **`BacktestService`** in `app/services/backtest.py`. Cross-sectional **research** engine for v2.0 should be a **new service module** (or clearly named methods) that reuses kline loading primitives but **does not** pretend to be a second `run()` with one `df`.

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| NQ100 source (web/API) | HTTP client in `Nq100ConstituentService` | Rate limits + User-Agent; store raw response hash for idempotency |
| Existing market data | `KlineService` / data sources | Unchanged contract for USStock |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Universe API ↔ Kline sync | Indirect | Scheduler may add symbols to watchlists or document “ensure these symbols synced” |
| Factor library ↔ `run_cross_sectional_indicator` | Import | Library builds `scores`; user code can still `exec` for custom combine |
| Scripts ↔ `app` | `PYTHONPATH=backend_api_python` or editable install | Same codebase, no fork |

## New vs modified components (explicit)

| Component | New | Modified |
|-----------|-----|----------|
| Constituent table + migration | ✓ | |
| `Nq100ConstituentService`, scrape | ✓ | |
| `routes/universe.py` | ✓ | `routes/__init__.py` |
| APScheduler job for refresh | ✓ | `app/tasks/__init__.py` (registration) |
| `app/services/cross_sectional/` factor/panel lib | ✓ | |
| `BacktestService` or new CS backtest service | | ✓ (pitfalls + API) |
| `scripts/cross_sectional/nq100_cross_sectional.py` | | ✓ (imports shared lib, optional API for universe) |
| `CrossSectionalStrategy` / factory | | Maybe ✓ (only if wiring new factor helpers) |

## Sources

- Repository: `backend_api_python/app/services/backtest.py`, `app/routes/backtest.py`, `app/strategies/cross_sectional*.py`, `app/services/scheduler_service.py`, `scripts/cross_sectional/nq100_cross_sectional.py`, `migrations/init.sql` (`qd_kline_points`, `qd_market_symbols`)

---
*Architecture research for: QuantDinger v2.0 cross-sectional integration*
*Researched: 2026-04-13*
