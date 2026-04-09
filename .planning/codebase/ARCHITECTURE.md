# Architecture

**Analysis Date:** 2026-04-09

## Pattern Overview

**Overall:** Three-tier web application with a **Flask REST API** backend, **Vue 2 + Ant Design Pro** SPA frontend, and **PostgreSQL** persistence. Deployment uses **Docker Compose** (postgres, backend, nginx-served frontend). The backend follows a **layered service architecture**: HTTP blueprints → service classes → database / external data / strategy runners.

**Key Characteristics:**

- **Application factory** for Flask (`create_app` in `backend_api_python/app/__init__.py`) with CORS, optional demo-mode middleware, and startup hooks (workers, strategy restore, scheduled tasks).
- **Blueprint-based API** with URL prefixes grouped by domain (`/api/auth`, `/api/strategies`, `/api/indicator`, etc.); registration centralized in `backend_api_python/app/routes/__init__.py`.
- **Singleton-style long-running services** for trading execution and pending orders, exposed via getters on the app package (`get_trading_executor`, `get_pending_order_worker` in `backend_api_python/app/__init__.py`).
- **Frontend** uses **hash-mode Vue Router**, **Vuex** for state, **axios** with `baseURL: '/'` and dev proxy / production nginx proxy to the backend.

## Layers

**HTTP / API (Flask Blueprints):**

- Purpose: HTTP routing, request parsing, auth decorators, JSON responses (`code` / `msg` / `data` pattern in many endpoints).
- Location: `backend_api_python/app/routes/` (e.g. `strategy.py`, `auth.py`, `indicator.py`, `market.py`, `health.py`).
- Contains: Route handlers, thin orchestration, calls into services.
- Depends on: `app.services.*`, `app.utils.auth`, `app.utils.db`, `app` package singletons, occasionally `app.data_sources`.
- Used by: Browser and any API clients; health checks hit `backend_api_python/app/routes/health.py` (`/`, `/health`, `/api/health`).

**Domain / Application Services:**

- Purpose: Business logic—strategies, backtests, users, billing, LLM, live trading brokers, K-line sync, schedulers.
- Location: `backend_api_python/app/services/` (large surface area; subpackages include `live_trading/` for IBKR, MT5, crypto CCXT adapters, uSMART, EF, etc.).
- Contains: Service classes and modules (e.g. `StrategyService`, `TradingExecutor`, `scheduler_service`).
- Depends on: `app.utils.db`, `app.strategies`, `app.data_sources`, config, loggers.
- Used by: Route blueprints and startup hooks in `create_app`.

**Strategies & Runners:**

- Purpose: Pluggable trading logic—single-symbol, cross-sectional, regime-weighted variants; runners execute loops from DB-backed config.
- Location: `backend_api_python/app/strategies/` (`factory.py`, `base.py`, `runners/`, per-strategy modules).
- Contains: `IStrategyLoop` implementations, `load_and_create` / `create_strategy` in `backend_api_python/app/strategies/factory.py`.
- Depends on: DB-loaded config via `strategy_config_loader`, services for execution.
- Used by: `TradingExecutor` and related services.

**Data Access:**

- Purpose: PostgreSQL access via connection helpers (no heavy ORM layer in the surveyed paths; SQL in services and migrations).
- Location: `backend_api_python/app/utils/db.py` (re-exports), `backend_api_python/app/utils/db_postgres.py`.
- Schema: Initialized by `backend_api_python/migrations/init.sql` (Docker mounts this for first-time DB init); incremental SQL files in `backend_api_python/migrations/` (e.g. `005_qd_kline_ranges.sql`, `008_indicator_strategy_group.sql`).

**External Market Data:**

- Purpose: K-line and market data with caching, rate limiting, circuit breakers, multi-source routing.
- Location: `backend_api_python/app/data_sources/` (`factory.py`, `data_manager.py`, `cache_manager.py`, etc.).

**Background & Scheduling:**

- Purpose: APScheduler-registered jobs; plugin entry in `backend_api_python/app/tasks/__init__.py` (e.g. `kline_sync`).
- Location: `backend_api_python/app/tasks/`, `backend_api_python/app/services/scheduler_service.py`.

**Frontend Application:**

- Purpose: SPA UI, routing, API clients wrapping REST endpoints.
- Location: `quantdinger_vue/src/` — `views/`, `api/*.js`, `store/`, `router/`, `utils/request.js`.
- Depends on: Backend only via HTTP (`/api/...`).

## Data Flow

**Browser → API (development):**

1. Vue app issues axios requests to `baseURL: '/'` paths under `/api/...` (`quantdinger_vue/src/utils/request.js`).
2. Webpack dev server proxies `/api` to `http://localhost:5000` (`quantdinger_vue/vue.config.js` `devServer.proxy`).

**Browser → API (Docker / production):**

1. Nginx serves static files from the frontend image and proxies `/api/` to the backend service (`quantdinger_vue/deploy/nginx-docker.conf`: `proxy_pass http://backend:5000/api/`).
2. Compose wires `frontend` → `backend` on `quantdinger-network` (`docker-compose.yml`).

**Authenticated requests:**

1. Login flows obtain JWT; token stored client-side (`quantdinger_vue/src/store/`, `storage`); axios sends credentials as configured (`withCredentials: true` in `quantdinger_vue/src/utils/request.js`).
2. Backend `app.utils.auth` validates JWT, sets `g.user_id` / role where `@login_required` is used (see `backend_api_python/app/routes/strategy.py`).

**Strategy execution:**

1. CRUD and control endpoints under `strategy_bp` (`backend_api_python/app/routes/strategy.py`) call `StrategyService` and `get_trading_executor().start_strategy(...)` (and related).
2. `TradingExecutor` runs strategy loops; live trading delegates to broker-specific code under `backend_api_python/app/services/live_trading/`.

**Demo mode:**

- When `IS_DEMO_MODE=true`, `before_request` in `backend_api_python/app/__init__.py` blocks mutating methods and sensitive GET prefixes unless whitelisted.

**State Management (frontend):**

- Vuex modules (`quantdinger_vue/src/store/modules/`) hold user and dynamic routes; `permission.js` gates routes and loads user info before `GenerateRoutes`.

## Key Abstractions

**Flask app factory:**

- `create_app()` in `backend_api_python/app/__init__.py` — wires CORS, DB init, demo middleware, `register_routes`, startup tasks.

**Route registration:**

- `register_routes(app)` in `backend_api_python/app/routes/__init__.py` — single place listing all blueprints and URL prefixes.

**Strategy factory:**

- `create_strategy` / `load_and_create` in `backend_api_python/app/strategies/factory.py` — maps `cs_strategy_type` strings to `IStrategyLoop` implementations.

**DataSourceFactory:**

- `backend_api_python/app/data_sources/factory.py` — entry for market data resolution (imported from routes such as `strategy.py`).

**DB connection context:**

- `get_db_connection` from `backend_api_python/app/utils/db.py` — used throughout services for raw SQL.

**Trading executor singleton:**

- `get_trading_executor()` in `backend_api_python/app/__init__.py` — shared runner for restored and user-started strategies.

## Entry Points

**Backend process:**

- **Local / container default:** `backend_api_python/run.py` — loads `.env`, builds `app = create_app()`, runs Flask dev server when `__main__` (`backend_api_python/run.py`).
- **Gunicorn (production option):** `gunicorn -c gunicorn_config.py "run:app"` per comment in `backend_api_python/run.py`; config in `backend_api_python/gunicorn_config.py`.

**Frontend build:**

- **Dev:** `npm` scripts (port **8000** in `quantdinger_vue/vue.config.js`).
- **Prod:** multi-stage Docker build outputs static assets to nginx (`quantdinger_vue/Dockerfile`).

**Database:**

- Postgres container runs `migrations/init.sql` on first init (`docker-compose.yml` volumes).

## Error Handling

**Strategy:** Route handlers commonly wrap logic in `try/except`, log with `get_logger`, return JSON with `code: 0` and HTTP 500 on failure (pattern in `backend_api_python/app/routes/strategy.py`). Startup hooks catch errors and log without always failing the process (`create_app` portfolio monitor, task registration).

**Client:** Axios `errorHandler` in `quantdinger_vue/src/utils/request.js` handles 401 (clear storage, redirect to hash login), 403 demo messaging.

## Cross-Cutting Concerns

**Logging:** `app.utils.logger` (`setup_logger`, `get_logger`) used across routes and services.

**Validation:** Request payloads validated inline in route handlers and services; no separate validation layer surfaced in the surveyed files.

**Authentication:** JWT in `backend_api_python/app/utils/auth.py`; `@login_required` on protected routes; optional demo global lock in `create_app`.

---

*Architecture analysis: 2026-04-09*
