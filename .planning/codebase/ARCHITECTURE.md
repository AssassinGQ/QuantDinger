# Architecture

**Analysis Date:** 2026-04-08

## Pattern Overview

**Overall:** Layered Flask Architecture with Service-Oriented Design

**Key Characteristics:**
- Flask application factory pattern (`create_app()` in `/home/workspace/ws/QuantDinger/backend_api_python/app/__init__.py`)
- Blueprint-based API routing with centralized route registration
- Service layer for business logic (trading execution, data handling, market analysis)
- Data source abstraction layer for multi-market data providers
- Singleton pattern for critical services (TradingExecutor, PendingOrderWorker)
- Event-driven background task scheduling

## Layers

**Configuration Layer:**
- Purpose: Centralize environment-based settings and secrets
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/config/`
- Contains: Settings, API keys, database, data sources, cache configuration
- Depends on: Environment variables and .env files
- Used by: All application components

**Route/API Layer:**
- Purpose: Expose HTTP endpoints for frontend and external clients
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/`
- Contains: Flask blueprints (auth, market, strategy, portfolio, ibkr, mt5, etc.)
- Depends on: Services layer for business logic
- Used by: Flask app through centralized registration in `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/__init__.py`

**Service/Business Logic Layer:**
- Purpose: Core trading execution, data processing, and analysis
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/services/`
- Contains: TradingExecutor, SignalExecutor, DataHandler, Backtest, LiveTrading modules
- Depends on: Data sources and database utilities
- Used by: Routes, Strategy runners, Background tasks

**Data Source Layer:**
- Purpose: Unified interface for fetching market data from multiple providers
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/`
- Contains: BaseDataSource abstract class, implementations for crypto (Binance, Bybit, etc.), forex, futures, stocks
- Depends on: External APIs and rate limiting/circuit breaker utilities
- Used by: Services layer for market data

**Strategy/Runner Layer:**
- Purpose: Execute trading strategies with configurable parameters
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/strategies/runners/`
- Contains: BaseRunner, SingleSymbolRunner, CrossSectionalRunner, RegimeRunner
- Depends on: TradingExecutor and DataHandler
- Used by: TradingExecutor for strategy execution

**Database/Utility Layer:**
- Purpose: Persistence, caching, logging, authentication
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/utils/`
- Contains: DB utilities, cache management, auth, logging
- Used by: All layers

**Frontend Layer:**
- Purpose: Vue.js SPA dashboard for trading management
- Location: `/home/workspace/ws/QuantDinger/quantdinger_vue/src/`
- Contains: Components, views, store (Vuex), router, API clients

## Data Flow

**API Request Flow:**

1. Client sends HTTP request to Flask endpoint
2. Route handler (blueprint) validates request
3. Route calls appropriate service method
4. Service layer executes business logic
5. Service calls data source for market data
6. Service processes data and executes trades if needed
7. Response returned through service → route → client

**Trading Execution Flow:**

1. Strategy runner signals buy/sell opportunity
2. TradingExecutor receives signal
3. SignalExecutor validates against risk rules
4. Price fetcher gets current market price
5. Order normalizer prepares exchange-specific order
6. Exchange execution service submits order to broker (IBKR, Binance, MT5, etc.)
7. Result stored in database and returned to client

**Background Task Flow:**

1. Scheduled task registered on app startup
2. Task scheduler (APScheduler) triggers at configured intervals
3. Task fetches/syncs market data, updates indicators
4. Tasks can auto-start strategies based on config

## Key Abstractions

**Data Source Factory:**
- Purpose: Create appropriate data source based on market type and exchange
- Examples: `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/factory.py`
- Pattern: Factory pattern with registry of supported data sources

**Base Data Source:**
- Purpose: Define contract for all market data providers
- Examples: `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/base.py`
- Pattern: Abstract base class with interface for get_kline(), get_ticker()

**Trading Executor:**
- Purpose: Manage live strategy threads and trade execution
- Examples: `/home/workspace/ws/QuantDinger/backend_api_python/app/services/trading_executor.py`
- Pattern: Singleton with thread pool management, configurable max threads

**Strategy Runner:**
- Purpose: Execute strategy logic with market data
- Examples: `/home/workspace/ws/QuantDinger/backend_api_python/app/strategies/runners/`
- Pattern: Strategy pattern for different strategy types

## Entry Points

**Backend API Entry:**
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/run.py`
- Triggers: Python execution (`python run.py`) or Gunicorn (`gunicorn -c gunicorn_config.py "run:app"`)
- Responsibilities: Load environment, create Flask app, start background services, register routes

**Flask App Factory:**
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/__init__.py` (`create_app()`)
- Triggers: Called from run.py
- Responsibilities: Initialize Flask, CORS, database, register blueprints, start portfolio monitor, pending order worker, restore running strategies

**Route Registration:**
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/__init__.py`
- Triggers: Called from create_app()
- Responsibilities: Import and register all blueprint routes with URL prefixes

**Vue.js Entry:**
- Location: `/home/workspace/ws/QuantDinger/quantdinger_vue/src/main.js`
- Triggers: Frontend build/dev server
- Responsibilities: Initialize Vue app, router, store, load global components

## Error Handling

**Strategy:**
- Global exception handling with centralized logging
- Demo mode middleware blocks state-changing operations
- Rate limiting and circuit breaker patterns for external API resilience
- Graceful degradation with fallback mechanisms

**Patterns:**
- Exception classes for specific error types (RateLimitError in data sources)
- Database transaction rollback on errors
- Health check endpoints for system status

## Cross-Cutting Concerns

**Logging:** Uses custom logger utility (`app/utils/logger.py`) with configurable levels and file output

**Validation:** Request validation in route handlers, input sanitization for security

**Authentication:** JWT-based auth with user service, password hashing, session management

**CORS:** Configured via Flask-CORS with environment-based allowed origins

---

*Architecture analysis: 2026-04-08*
