# Technology Stack

**Analysis Date:** 2026-04-09

## Languages

**Primary:**
- **Python 3.12** — Backend API, services, strategies, data pipelines (`backend_api_python/`). Container base: `python:3.12-slim` in `backend_api_python/Dockerfile`.
- **JavaScript (ES5/ES6+)** — Vue 2 single-page application (`quantdinger_vue/src/`).

**Secondary:**
- **Less** — Component and global styles (`quantdinger_vue/src/**/*.less`).
- **SQL** — PostgreSQL schema and migrations (`backend_api_python/migrations/init.sql`).

## Runtime

**Backend:**
- **CPython** via `python run.py` (Flask development server with `threaded=True`) in default and Docker flows.
- **Optional production:** Gunicorn documented in `backend_api_python/run.py` comments and `backend_api_python/gunicorn_config.py` (`gunicorn -c gunicorn_config.py "run:app"`). Gunicorn is **not** listed in `backend_api_python/requirements.txt` (install separately if used).

**Frontend build:**
- **Node.js 18** — Build stage in `quantdinger_vue/Dockerfile` (`node:18-alpine`).

**Frontend production:**
- **Nginx** — Serves static `dist/` and proxies `/api/` to the backend (`quantdinger_vue/deploy/nginx-docker.conf`, `nginx:1.25-alpine` in Dockerfile stage 2).

**Package Manager:**
- **pip** — Python dependencies from `backend_api_python/requirements.txt`.
- **npm** — Frontend dependencies; Docker uses `npm install --legacy-peer-deps` (`quantdinger_vue/Dockerfile`).
- Lockfiles: `package-lock.json` may exist in `quantdinger_vue/` (not enumerated here).

## Frameworks

**Core (backend):**
- **Flask 2.3.3** — HTTP API (`app/__init__.py`, `run.py`).
- **flask-cors 4.0.0** — CORS for browser clients.
- **APScheduler ≥3.10.0** — Scheduled tasks.

**Core (frontend):**
- **Vue 2.6.x** — UI framework (`quantdinger_vue/package.json`).
- **Vue Router 3.x** — Client routing.
- **Vuex 3.x** — Application state.
- **ant-design-vue 1.7.x** — UI components.
- **@ant-design-vue/pro-layout** — Admin layout shell.

**Data & trading (backend libraries):**
- **pandas** — Tabular data.
- **SQLAlchemy ≥2.0.0** — ORM/SQL toolkit where used in codebase.
- **pymysql** — MySQL driver (legacy/compatibility paths).
- **psycopg2-binary** — PostgreSQL adapter (`app/utils/db_postgres.py`).
- **ccxt** — Cryptocurrency exchange connectivity.
- **ib_insync** — Interactive Brokers (TWS/IB Gateway).
- **finnhub-python** — Finnhub market data API client.
- **yfinance** — Yahoo Finance data.
- **akshare** — China/market data sources.
- **requests**, **PySocks** — HTTP and SOCKS proxy support.

**Security & auth (backend):**
- **PyJWT 2.8.0** — JWT tokens.
- **bcrypt** — Password hashing.
- **python-dotenv** — Load `.env` into `os.environ` (`run.py`).

**Testing (dev):**
- Backend tests use **pytest**-style patterns under `backend_api_python/tests/` (pytest not pinned in `requirements.txt`; verify local venv).
- Frontend: **Jest** via `@vue/cli-plugin-unit-jest` (`quantdinger_vue/package.json` scripts: `test:unit`).

**Build / dev (frontend):**
- **Vue CLI 5** (`@vue/cli-service` ~5.0.8), **Webpack 5**, **Babel**, **ESLint 7**, **Stylelint 14**.

## Key Dependencies

**Critical (API & product):**
- `Flask`, `flask-cors` — HTTP surface.
- `pandas`, `requests` — Data ingestion and HTTP.
- `psycopg2-binary`, `SQLAlchemy` — Persistence.
- `ccxt`, `yfinance`, `finnhub-python`, `akshare` — Market and reference data.

**Infrastructure / ops:**
- `APScheduler` — Background scheduling.
- `python-dotenv` — Configuration bootstrap.

**Optional / platform-specific:**
- `ib_insync` — Live US/HK brokerage (IBKR).
- `MetaTrader5` — Documented in `backend_api_python/requirements-windows.txt` (Windows-only; not in default Linux `requirements.txt`).

## Configuration

**Environment:**
- Primary: `backend_api_python/.env` loaded with **override=True** in `run.py`, then repo-root `.env` with **override=False**.
- Docker Compose injects `DATABASE_URL`, `DB_TYPE`, `PYTHON_API_*`, `STRATEGY_MAX_THREADS`, etc. (`docker-compose.yml`).
- Nested service config from env is assembled in `app/utils/config_loader.py` (`load_addon_config()`).

**Application settings:**
- `app/config/settings.py` — Class `Config` (host, port, debug, secrets, logging) via `PYTHON_API_HOST`, `PYTHON_API_PORT`, `PYTHON_API_DEBUG`, `SECRET_KEY`, `LOG_*`, etc.

**Frontend API base URL:**
- `quantdinger_vue/src/config/defaultSettings.js` — `PYTHON_API_BASE_URL` from `process.env.VUE_APP_PYTHON_API_BASE_URL` or default `http://localhost:5000`.
- In Docker, Nginx proxies browser `/api/` to the backend service name `backend:5000` (`quantdinger_vue/deploy/nginx-docker.conf`).

**Proxy (outbound):**
- `run.py` applies `PROXY_URL` or `PROXY_HOST`/`PROXY_PORT`/`PROXY_SCHEME` to `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `CCXT_PROXY`.

**Build:**
- `quantdinger_vue/vue.config.js` — Webpack aliases (`@$` → `src`), DefinePlugin for version/git, theme plugins.
- `quantdinger_vue/config/plugin.config.js`, `config/themePluginConfig.js` — Theme/color tooling.

## Platform Requirements

**Development:**
- Python 3.10+ per workspace docs; Docker uses 3.12.
- Node 18+ recommended for Vue CLI build (matches Dockerfile).
- PostgreSQL for full multi-user stack (or use Compose).

**Production:**
- **Docker Compose** (`docker-compose.yml`): `postgres:16-alpine`, backend image from `backend_api_python/Dockerfile`, frontend image from `quantdinger_vue/Dockerfile`.
- Backend health: `GET http://localhost:5000/api/health` (Compose healthcheck).
- Frontend health: `GET /health` on Nginx (returns 200).

---

*Stack analysis: 2026-04-09*
