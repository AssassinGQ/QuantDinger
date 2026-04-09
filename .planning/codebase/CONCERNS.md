# Codebase Concerns

**Analysis Date:** 2026-04-09

## Tech Debt

**Oversized modules (hard to review and risky to change):**
- `backend_api_python/app/services/backtest.py` (~3856 lines) — backtest engine, signal handling, and position logic in one file; regressions are costly to catch without narrower modules or golden tests.
- `backend_api_python/app/routes/global_market.py` (~1778 lines) — many external data sources and caching paths in one route module.
- `backend_api_python/app/routes/settings.py` (~1318 lines) — large settings surface mixed with API wiring.
- `backend_api_python/app/services/portfolio_monitor.py` (~1284 lines) — long-running monitor logic in one place.

**Configuration vs implementation drift:**
- `Config.CORS_ORIGINS` in `backend_api_python/app/config/settings.py` reads `CORS_ORIGINS` / addon config, but the app registers CORS with `CORS(app)` and no `origins=` in `backend_api_python/app/__init__.py`. The documented “comma-separated origins” setting does not appear to constrain browser origins at the Flask-CORS layer.
- `get_internal_api_key()` in `backend_api_python/app/utils/config_loader.py` loads `INTERNAL_API_KEY` (also listed in `backend_api_python/env.example` and `backend_api_python/app/routes/settings.py`). No route or middleware in `backend_api_python/app/` was found that validates this key for service-to-service calls — likely incomplete or dead configuration surface.

**Dual database / compatibility paths:**
- `backend_api_python/app/services/data_handler.py` mixes SQLite-oriented `PRAGMA` / `ALTER TABLE ... IF NOT EXISTS` with PostgreSQL-oriented patterns; migration and behavior differences increase the chance of subtle bugs when `DB_TYPE` changes.

**User-supplied code execution:**
- Indicator and strategy code paths use `exec()` (e.g. `backend_api_python/app/utils/safe_exec.py`, `backend_api_python/app/services/backtest.py`, `backend_api_python/app/strategies/single_symbol_indicator.py`, `backend_api_python/app/routes/indicator.py`). `safe_exec_code` is not a true sandbox: it limits time (Unix main thread only) and optional memory via `SAFE_EXEC_ENABLE_RLIMIT`, but executed code shares the API process and can access the same Python environment as the server.

## Known Bugs

**IBKR commission / event ordering (documented in tooling):**
- `scripts/ibkr_commission_test.py` logs a confirmed scenario where `commissionReport` can fire after simulated context removal, causing commission loss in that test harness. Production `backend_api_python/app/services/live_trading/ibkr_trading/client.py` should be reviewed if commission accounting still depends on event ordering.

**Sparse inline issue markers:**
- Repository-wide `TODO` / `FIXME` / `HACK` / `XXX` in application source (excluding debug log strings) were not found in a routine scan; issue tracking likely lives outside the repo. Do not assume absence of markers means absence of issues.

## Security Considerations

**Default and weak credentials (must change in production):**
- `backend_api_python/app/config/settings.py`: default `SECRET_KEY` (`quantdinger-secret-key-change-me`), `ADMIN_PASSWORD` (`123456`), and related admin env defaults — unsafe if env is not set.
- `docker-compose.yml`: default `POSTGRES_PASSWORD` (`quantdinger123`) and embedded connection string defaults — rotate for any non-local deployment.
- `backend_api_python/app/services/user_service.py` `ensure_admin_exists()` uses `ADMIN_USER` / `ADMIN_PASSWORD` / `ADMIN_EMAIL` from env with defaults (`admin`, `admin123`, `admin@example.com`) when the user table is empty.

**Network exposure:**
- `docker-compose.yml` binds Postgres and backend API to `127.0.0.1` (good for local). The `frontend` service publishes `8888:80` on all interfaces (`0.0.0.0`), unlike the backend — broader LAN exposure of the static UI unless firewall rules exist.

**JWT and cookies:**
- `backend_api_python/app/utils/auth.py` uses HS256 with `Config.SECRET_KEY`; strength depends entirely on deployment env. Frontend `quantdinger_vue/src/utils/request.js` uses `withCredentials: true` — ensure cookie/session expectations match backend CORS and same-site policy when changing origins.

**SQL construction:**
- Dynamic SQL with f-strings appears where identifiers are fixed (e.g. `backend_api_python/app/services/analysis_memory.py` `WHERE` / `LIMIT` clauses). User-controlled fragments are not obviously interpolated into raw SQL in the reviewed paths; `backend_api_python/app/services/user_service.py` `list_users` builds `WHERE` with parameterized `LIKE` placeholders — acceptable pattern. Continue to avoid string-concatenating unvalidated user input into SQL.

## Performance Bottlenecks

**Heavy synchronous work in the API process:**
- Large backtests and indicator execution can hold CPU and memory in the same process as HTTP handling (`backend_api_python/app/services/backtest.py`, `safe_exec` paths). Parallel strategy threads (`STRATEGY_MAX_THREADS` in `docker-compose.yml`) increase contention on a single host.

**External API fan-out:**
- `backend_api_python/app/routes/global_market.py` and `backend_api_python/app/services/market_data_collector.py` aggregate many providers; cold-cache or stampeding requests can hit provider rate limits (Finnhub, yfinance, akshare, etc.).

**Database:**
- `docker-compose.yml` sets `max_connections=512` on Postgres; many concurrent strategies and monitors can still exhaust connections if pools are not bounded consistently across `get_db_connection()` usage.

## Deprecated or Aging Dependencies

**Python (`backend_api_python/requirements.txt`):**
- Pinned `Flask==2.3.3`, `flask-cors==4.0.0`, `PyJWT==2.8.0` — should be tracked for security advisories and Flask 3.x migration when feasible.

**Frontend (`quantdinger_vue/package.json`):**
- Vue 2.6.x and Vue CLI 5 stack are in maintenance/end-of-life territory; `axios` ^0.26.1, `babel-eslint`, and older ESLint 7 align with that generation. Plan a Vue 3 + toolchain upgrade as a larger initiative, not a patch.

## Code Duplication

**Platform and exchange caveats:**
- “MT5 only on Windows” and similar notes recur across `backend_api_python/app/services/live_trading/mt5_trading/client.py`, `backend_api_python/app/services/live_trading/factory.py`, and `backend_api_python/app/routes/mt5.py` — acceptable duplication for UX/errors but easy to diverge.

**Live trading exchange clients:**
- Multiple files under `backend_api_python/app/services/live_trading/crypto_trading/` implement similar order normalization and error strings; refactors could reduce drift (e.g. Binance vs Bitget precision handling).

## Fragile Areas

**Signal-based timeouts:** `backend_api_python/app/utils/safe_exec.py` — `signal.SIGALRM` only applies on Unix and only on the main thread; Windows and worker threads effectively skip time limits.

**Bare `except:` clauses** (swallow all exceptions, harder to diagnose):
- `backend_api_python/app/services/search.py` (e.g. around lines 208, 385)
- `backend_api_python/app/services/llm.py` (e.g. around line 464)
- `backend_api_python/app/routes/global_market.py` (e.g. around lines 722, 1250)

**Startup side effects:** `backend_api_python/app/__init__.py` restores running strategies, starts portfolio monitor and pending-order worker, and registers scheduled tasks — failures are often logged but the system may run in a partially initialized state.

## Scaling Limits

- Strategy thread pool default `STRATEGY_MAX_THREADS` (e.g. 256 in `docker-compose.yml`) vs CPU cores and IBKR/ exchange connection limits.
- Single Flask process model in `backend_api_python/run.py` (`threaded=True`) — horizontal scaling requires multiple workers (e.g. gunicorn) and shared state care for strategies and monitors.

## Dependencies at Risk

- Optional Windows-only `MetaTrader5` is commented in `backend_api_python/requirements.txt`; MT5 features fail at runtime on Linux unless architecture is documented and guarded everywhere.

## Missing Critical Features

- **Frontend automated tests:** `quantdinger_vue/package.json` defines `test:unit`, but there is no meaningful suite of `*.spec.js` / test files under `quantdinger_vue/tests/` (only `tests/unit/.eslintrc.js` was present). Regressions in Vue views (e.g. trading assistant, indicator analysis) rely on manual QA.

## Test Coverage Gaps

**Backend:** `backend_api_python/tests/` has substantial coverage for IBKR, executors, and strategy runners, but large route modules (`global_market.py`, `settings.py`, `auth.py`, `user.py`) and `backtest.py` are disproportionately large relative to focused unit tests — integration or contract tests for critical API flows would reduce release risk.

**Frontend:** Effectively no unit/component test coverage in-tree; E2E is not evident in the repo layout reviewed.

## Configuration Issues

- **CORS:** Documented `CORS_ORIGINS` vs actual `CORS(app)` behavior — see Tech Debt.
- **Rate limiting:** `Config.RATE_LIMIT` exists in `backend_api_python/app/config/settings.py` and settings UI; global HTTP rate limiting via that value is not clearly wired to Flask middleware in `app/__init__.py` (Finnhub and data-source limiters are separate).
- **Logging default:** `backend_api_python/app/utils/logger.py` defaults `LOG_LEVEL` to `DEBUG` via env default — verbose logs in production if unset.

---

*Concerns audit: 2026-04-09*
