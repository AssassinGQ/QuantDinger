# External Integrations

**Analysis Date:** 2026-04-09

## APIs & External Services

**Market & reference data:**
- **Finnhub** — Company/profile and related REST usage (e.g. `app/services/symbol_name.py`); API key via `FINNHUB_API_KEY` (see `app/utils/config_loader.py`).
- **Yahoo Finance (yfinance)** — Equity and macro series; timeouts via `YFINANCE_TIMEOUT`.
- **AkShare** — China and multi-market data; `AKSHARE_TIMEOUT`.
- **Tiingo** — Optional OHLC/fundamental data; `TIINGO_API_KEY`, `TIINGO_TIMEOUT`.
- **CCXT** — Unified crypto exchange APIs; defaults and proxy via `CCXT_DEFAULT_EXCHANGE`, `CCXT_TIMEOUT`, `CCXT_PROXY` (also fed from `run.py` proxy normalization).

**Brokerage / execution:**
- **Interactive Brokers** — `ib_insync` for TWS/IB Gateway; connection settings use env such as `IBKR_HOST`, `IBKR_PORT` (see tests and live trading modules under `app/services/live_trading/`).
- **MetaTrader 5** — Optional on Windows (`requirements-windows.txt`); not bundled in Linux images.

**LLM / AI analysis (env-driven in `config_loader.py`):**
- **OpenRouter** — `OPENROUTER_API_KEY`, model and URL settings.
- **OpenAI** — `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`.
- **Google Gemini** — `GOOGLE_API_KEY`, `GOOGLE_MODEL`.
- **DeepSeek** — `DEEPSEEK_API_KEY`, base URL, model.
- **xAI Grok** — `GROK_API_KEY`, base URL, model.
- Provider selection: `LLM_PROVIDER`; model list JSON: `AI_MODELS_JSON`.

**Search (news/research):**
- **Google Custom Search / Bing** — `SEARCH_PROVIDER`, `SEARCH_GOOGLE_API_KEY`, `SEARCH_GOOGLE_CX`, `SEARCH_BING_API_KEY`, `SEARCH_MAX_RESULTS`.
- **Tavily** — `TAVILY_API_KEYS` (optional package commented in `requirements.txt`).
- **Bocha** — `BOCHA_API_KEYS` (Chinese search optimization).
- **SerpAPI** — `SERPAPI_KEYS` (optional package commented in `requirements.txt`).

**Security & identity:**
- **Cloudflare Turnstile** — Bot protection; `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` (`app/services/security_service.py`).
- **Google OAuth (login)** — Enabled when `GOOGLE_CLIENT_ID` is set (`security_service.py`); additional OAuth-related env may appear alongside registration flags.

**Notifications (outbound):**
- **SMTP** — Email: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS`, `SMTP_USE_SSL` (`app/services/signal_notifier.py`).
- **Twilio** — SMS: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`.
- **Discord** — Incoming webhook URLs configured in user notification targets (HTTP POST to `discord.com/api/webhooks/...`).
- **Generic HTTPS webhooks** — User-configured URLs with optional Bearer token and HMAC signing (`SIGNAL_WEBHOOK_SIGNING_SECRET` for signing secret override).

**Internal / same-cluster:**
- `INTERNAL_API_KEY` — Authenticates internal or privileged API usage (`get_internal_api_key()` in `app/utils/config_loader.py`).

**Exchange REST (strategy/config):**
- Strategy code may call configurable exchange HTTP bases (e.g. contract/symbol discovery in `app/services/strategy.py`); treat as deployment-specific exchange HTTP APIs, not a single third-party SDK name.

## Data Storage

**Databases:**
- **PostgreSQL** — Primary deployment: `DATABASE_URL` (e.g. `postgresql://user:pass@host:5432/dbname`), `DB_TYPE=postgresql` in Compose. Connection pooling in `app/utils/db_postgres.py`; public API in `app/utils/db.py`.
- **SQLite** — Some code paths still branch on `DB_TYPE` defaulting to `sqlite` in `app/services/data_handler.py` for schema introspection (`PRAGMA` vs `information_schema`). Production Compose path expects PostgreSQL; `app/utils/db.py` documents PostgreSQL-only unified interface.

**File storage:**
- Local filesystem under `backend_api_python/logs`, `backend_api_python/data` (mounted in `docker-compose.yml`). No cloud object storage SDK detected in core requirements.

**Caching:**
- Application-level caching toggled via env (`ENABLE_CACHE` in `config_loader.py`); no Redis/Memcached package in `requirements.txt`.

## Authentication & Identity

**Auth Provider:**
- **Custom** — JWT (`PyJWT`), bcrypt-hashed passwords, session/user tables in PostgreSQL (`app/services/user_service.py`, `security_service.py`).
- **Optional Google OAuth** — When `GOOGLE_CLIENT_ID` is configured.
- **Demo mode** — `IS_DEMO_MODE` read in `run.py` for read-only behavior when enabled.

## Monitoring & Observability

**Error Tracking:**
- Not detected as a dedicated SaaS (e.g. Sentry) in core `requirements.txt`.

**Logs:**
- File and level driven by `LOG_LEVEL`, `LOG_DIR`, `LOG_FILE`, rotation settings in `app/config/settings.py` and `app/utils/logger.py`.

## CI/CD & Deployment

**Hosting:**
- **Docker Compose** — Local/production-style orchestration (`docker-compose.yml`).
- **Nginx** — Static frontend and reverse proxy to Flask backend in container network.

**CI Pipeline:**
- Not detected at repository root in this analysis (no `.github/workflows` confirmation in this pass).

## Environment Configuration

**Required for typical Docker stack:**
- `DATABASE_URL` / `POSTGRES_*` — Database (Compose sets defaults).
- `SECRET_KEY` — Should be set for non-dev deployments (`app/config/settings.py` default is placeholder).

**Commonly used optional vars (non-exhaustive):**
- Data: `FINNHUB_API_KEY`, `CCXT_*`, `TIINGO_API_KEY`, proxy `PROXY_URL` or `PROXY_PORT`.
- AI: `OPENROUTER_API_KEY` or provider-specific keys, `LLM_PROVIDER`.
- Security: `INTERNAL_API_KEY`, Turnstile keys, rate limits (`SECURITY_*`, `VERIFICATION_CODE_*`).
- Ops: `STRATEGY_MAX_THREADS`, `STRATEGY_TICK_INTERVAL_SEC`, `LOG_LEVEL`, `ENABLE_REGISTRATION`.

**Secrets location:**
- **`backend_api_python/.env`** — Intended for secrets; file may be absent in repo and is mounted in Compose for development (`docker-compose.yml` volume). **Do not commit secrets.**

## Webhooks & Callbacks

**Incoming:**
- No universal public webhook receiver catalogued here; signal notification flows may expose routes under Flask blueprints in `app/routes/` (verify specific paths when integrating). Health endpoint used by Docker: `GET /api/health` on backend.

**Outgoing:**
- User-configured **webhooks** and **Discord** URLs from notification settings (`app/services/signal_notifier.py`).
- **SMTP** and **Twilio** for email/SMS as above.

---

*Integration audit: 2026-04-09*
