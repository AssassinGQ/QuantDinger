# Codebase Structure

**Analysis Date:** 2026-04-09

## Directory Layout

```
QuantDinger/
├── backend_api_python/          # Flask API (Python 3.12 in Dockerfile)
│   ├── run.py                   # Entry: create_app(), dev server
│   ├── gunicorn_config.py       # Production WSGI settings
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── app/                     # Application package
│   │   ├── __init__.py          # create_app(), singletons, startup hooks
│   │   ├── config/              # Settings (e.g. settings.py)
│   │   ├── routes/              # Flask blueprints (API)
│   │   ├── services/            # Business logic & integrations
│   │   ├── strategies/          # Strategy implementations & runners
│   │   ├── data_sources/        # Market data, cache, rate limits
│   │   ├── tasks/               # Scheduled task plugins (kline_sync, etc.)
│   │   └── utils/               # db, auth, logging, http helpers
│   ├── migrations/              # init.sql + numbered SQL migrations
│   ├── tests/                   # pytest tests
│   ├── scripts/                 # Operational scripts
│   ├── logs/                    # Runtime logs (mounted in Docker)
│   └── data/                    # App data (mounted in Docker)
├── quantdinger_vue/             # Vue 2 SPA + Ant Design Pro
│   ├── src/
│   │   ├── main.js              # Vue bootstrap
│   │   ├── App.vue
│   │   ├── api/                 # REST client modules per domain
│   │   ├── views/               # Page components by feature
│   │   ├── router/              # Hash router + dynamic routes
│   │   ├── store/               # Vuex modules
│   │   ├── components/        # Shared UI
│   │   ├── utils/               # axios wrapper (request.js), helpers
│   │   ├── config/              # router.config.js, etc.
│   │   ├── locales/             # i18n
│   │   └── permission.js        # Route auth guard
│   ├── public/
│   ├── deploy/
│   │   └── nginx-docker.conf    # Prod API proxy to backend:5000
│   ├── vue.config.js            # Dev server proxy /api → :5000
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml           # postgres + backend + frontend
├── scripts/                     # Repo-level helper scripts (IBKR tests, etc.)
├── docs/                        # Project documentation
└── wip/                         # Work-in-progress notes (e.g. strategy plans)
```

## Directory Purposes

**`backend_api_python/app/routes/`:**

- Purpose: One module per API area; exports a `Blueprint` registered in `backend_api_python/app/routes/__init__.py`.
- Key files: `health.py`, `auth.py`, `user.py`, `strategy.py`, `indicator.py`, `kline.py`, `backtest.py`, `market.py`, `settings.py`, `credentials.py`, `portfolio.py`, `dashboard.py`, `ibkr.py`, `mt5.py`, `global_market.py`, `community.py`, `fast_analysis.py`, `scheduler.py`, `ai_chat.py` (imported in `register_routes`).

**`backend_api_python/app/services/`:**

- Purpose: Domain logic, long-running executors, broker adapters, LLM, billing, etc.
- Subfolders: `live_trading/` (IBKR, MT5, crypto, uSMART, EF, order normalization, runners).

**`backend_api_python/app/strategies/`:**

- Purpose: Strategy types and `runners/` for execution loops; `factory.py` constructs implementations from DB config.

**`backend_api_python/migrations/`:**

- Purpose: `init.sql` defines core tables (`qd_users`, `qd_strategies_trading`, credits, K-line cache tables, etc.); numbered `*.sql` files apply incremental changes (run manually or via ops process as documented in `migrations/README.md` if present).

**`quantdinger_vue/src/api/`:**

- Purpose: Thin axios wrappers grouping endpoints (`login.js`, `strategy.js`, `market.js`, `credentials.js`, …).

**`quantdinger_vue/src/views/`:**

- Purpose: Feature pages (e.g. `dashboard/`, `indicator-analysis/`, `trading-assistant/`, `broker-dashboard/`).

## Key File Locations

**Entry Points:**

- `backend_api_python/run.py` — WSGI `app` for gunicorn; `main()` for Flask dev.
- `quantdinger_vue/src/main.js` — Vue app mount.
- `docker-compose.yml` — Orchestrates postgres, backend (`5000`), frontend (`8888:80`).

**Configuration:**

- `backend_api_python/app/config/settings.py` — Flask/JWT and host settings (referenced from `run.py`, `auth.py`).
- `quantdinger_vue/vue.config.js` — Webpack, `@$` → `src`, dev proxy.
- Environment: `.env` loaded in `run.py` (do not commit secrets); Docker passes `DATABASE_URL`, ports via `docker-compose.yml`.

**Core Logic:**

- `backend_api_python/app/__init__.py` — App factory and lifecycle.
- `backend_api_python/app/services/trading_executor.py` — Strategy execution (referenced from routes and startup).
- `backend_api_python/app/utils/db.py` — DB connection API.

**Frontend ↔ API boundary:**

- `quantdinger_vue/src/utils/request.js` — Shared axios instance and interceptors.
- `quantdinger_vue/deploy/nginx-docker.conf` — Production `/api/` proxy.

## Naming Conventions

**Files (backend):**

- Route modules: `snake_case.py` matching feature (`strategy.py`, `fast_analysis.py`).
- Services: `snake_case.py` (`user_service.py`, `trading_executor.py`).

**Files (frontend):**

- Views: often `index.vue` inside feature folders; components in `components/` subfolders.
- API modules: `kebab-case` or domain name (`fast-analysis.js` vs `global-market.js`).

**Database:**

- Table names prefixed with `qd_` in `migrations/init.sql` (e.g. `qd_users`, `qd_strategies_trading`).

## Where to Add New Code

**New REST API surface:**

- Add a blueprint module under `backend_api_python/app/routes/`, implement handlers, then register in `backend_api_python/app/routes/__init__.py` with a consistent `/api/...` prefix.

**New business logic:**

- Add or extend a service in `backend_api_python/app/services/`; keep routes thin.

**New strategy type:**

- Implement `IStrategyLoop` in `backend_api_python/app/strategies/`, wire in `backend_api_python/app/strategies/factory.py` and any DB/config expectations.

**Schema changes:**

- Add a new numbered SQL under `backend_api_python/migrations/` and update `init.sql` if fresh installs must include the change.

**New frontend screen:**

- Add route entries in `quantdinger_vue/src/config/router.config.js` (and dynamic route logic if role-based), add view under `quantdinger_vue/src/views/`, add API helpers in `quantdinger_vue/src/api/`.

**Shared frontend HTTP calls:**

- Prefer new functions in `quantdinger_vue/src/api/` using the shared `request` from `quantdinger_vue/src/utils/request.js`.

## Special Directories

**`backend_api_python/logs/`, `backend_api_python/data/`:**

- Purpose: Persistent runtime output; bind-mounted in `docker-compose.yml`.

**`quantdinger_vue/dist/`:**

- Purpose: Webpack build output; generated, typically not hand-edited.

**`.planning/`:**

- Purpose: Planning and codebase map documents for tooling; includes `codebase/` maps.

---

*Structure analysis: 2026-04-09*
