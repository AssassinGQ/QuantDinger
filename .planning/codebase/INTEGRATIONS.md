# External Integrations

**Analysis Date:** 2026-04-08

## APIs & External Services

**Financial Data:**
- Finnhub - Real-time and historical stock market data
  - SDK: finnhub-python 2.4.18
  - Auth: FINNHUB_API_KEY env var

- Tiingo - Stock market data and fundamentals
  - SDK: (built into data source module)
  - Auth: TIINGO_API_KEY env var

- Yahoo Finance - Free market data via yfinance
  - SDK: yfinance 0.2.18
  - Auth: None (public API)

- Akshare - Chinese stock and futures data
  - SDK: akshare 1.12.0
  - Auth: None (public Chinese market data)

- CCXT - Cryptocurrency exchange unified API
  - SDK: ccxt 4.0.0
  - Supports: Binance, Coinbase, Kraken, etc.
  - Auth: Exchange-specific API keys
  - Proxy: Configurable via PROXY_* env vars

**Trading Execution:**
- Interactive Brokers (IBKR) - US/HK stock trading
  - SDK: ib_insync 0.9.86
  - Requires: TWS or IB Gateway running
  - Auth: IBKR credentials

- MetaTrader 5 (MT5) - Forex/CFD trading (optional, Windows only)
  - SDK: MetaTrader5 5.0.45
  - Not available on Linux/macOS
  - Requires: MT5 terminal

**AI & LLM Services:**
- OpenAI - GPT models for analysis
  - Auth: OPENAI_API_KEY env var

- Google Gemini - Google's AI models
  - Auth: GOOGLE_API_KEY env var

- DeepSeek - AI models
  - Auth: DEEPSEEK_API_KEY env var

- Grok (xAI) - AI models
  - Auth: GROK_API_KEY env var

- MiniMax - AI models
  - Auth: MINIMAX_API_KEY env var

- OpenRouter - LLM routing/aggregation
  - Auth: OPENROUTER_API_KEY env var

**Search Services:**
- Tavily - AI-optimized search
  - SDK: tavily-python 0.3.0 (optional)
  - Auth: TAVILY_API_KEYS env var (comma-separated for rotation)
  - Free tier: 1000 requests/month

- Bocha Search - Web search API
  - Auth: BOCHA_API_KEYS env var (comma-separated for rotation)

- SerpAPI - Google/Bing search scraping
  - SDK: google-search-results 2.4.0 (optional)
  - Auth: SERPAPI_KEYS env var
  - Free tier: 100 requests/month

## Data Storage

**Databases:**
- PostgreSQL 16 - Primary production database
  - Connection: postgresql://user:pass@host:5432/db
  - Client: psycopg2-binary 2.9.9
  - ORM: SQLAlchemy 2.0.0
  - Config: DATABASE_URL env var

- SQLite - Development database
  - File: backend_api_python/data/quantdinger.db
  - Config: SQLITE_DATABASE_FILE env var

**Caching:**
- Redis - In-memory cache and session storage
  - Connection: redis://host:port/db
  - Config via: REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB
  - Cache TTL: Configurable by data type (5s to 3600s)
  - Cache Manager: app/data_sources/cache_manager.py

**File Storage:**
- Local filesystem - K-line data, logs, market symbols
  - Location: backend_api_python/data/
  - Logs: backend_api_python/logs/

## Authentication & Identity

**Auth Provider:**
- Custom JWT-based authentication
  - Implementation: PyJWT 2.8.0
  - Tokens: Access/refresh token pattern
  - Password hashing: bcrypt 4.1.0

- OAuth integration (optional)
  - Implementation: app/services/oauth_service.py
  - Providers: Configurable via OAuth flow

**Session Management:**
- Redis-backed sessions for multi-instance deployments
- JWT tokens stored in HTTP-only cookies or Authorization header

## Monitoring & Observability

**Error Tracking:**
- Not explicitly configured (could integrate Sentry)

**Logs:**
- Python logging to files and console
- Configurable via LOG_LEVEL, LOG_DIR, LOG_FILE
- Rotating file handler: 10MB per file, 5 backup files

**Health Checks:**
- Backend: /api/health endpoint
- Frontend: /health endpoint
- Docker health checks in docker-compose.yml

## CI/CD & Deployment

**Hosting:**
- Docker Compose - Local development and production
- Backend: Flask + Gunicorn on Alpine Linux
- Frontend: Nginx on Alpine Linux (or static serving)

**CI Pipeline:**
- GitHub Actions (from .github/ directory)
- Docker build/push workflows

**Container Orchestration:**
- Docker Compose 3.8
- Services: postgres, backend, frontend
- Networks: quantdinger-network (bridge driver)

## Environment Configuration

**Required env vars:**
- DATABASE_URL - PostgreSQL connection string
- REDIS_HOST/PORT - Cache server
- SECRET_KEY - JWT signing key
- POSTGRES_DB/USER/PASSWORD - Database credentials

**Optional env vars:**
- FINNHUB_API_KEY, TIINGO_API_KEY - Market data
- OPENAI_API_KEY, GOOGLE_API_KEY, DEEPSEEK_API_KEY, GROK_API_KEY, MINIMAX_API_KEY - AI/LLM
- TAVILY_API_KEYS, BOCHA_API_KEYS, SERPAPI_KEYS - Search
- CCXT_PROXY or PROXY_URL - Network proxy for crypto APIs
- IBKR credentials - For live trading

**Secrets location:**
- backend_api_python/.env - Main configuration (gitignored)
- backend_api_python/env.example - Template for required variables
- Docker secrets (in production)

## Webhooks & Callbacks

**Incoming:**
- Trading webhooks: Configured in trading executor services
- OAuth callbacks: app/routes/auth.py handles OAuth redirects

**Outgoing:**
- Trading execution: IBKR API calls via ib_insync
- Market data fetching: HTTP requests to data providers
- AI API calls: OpenAI, Gemini, DeepSeek, etc.

---

*Integration audit: 2026-04-08*
