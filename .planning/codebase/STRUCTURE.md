# Codebase Structure

**Analysis Date:** 2026-04-08

## Directory Layout

```
/home/workspace/ws/QuantDinger/
├── backend_api_python/           # Python Flask API backend
│   ├── run.py                    # Main entry point
│   ├── app/                      # Application package
│   │   ├── config/               # Configuration modules
│   │   ├── data/                 # Seed data and migrations
│   │   ├── data_sources/         # Market data provider abstraction
│   │   ├── routes/               # Flask blueprint route handlers
│   │   ├── services/             # Business logic and execution
│   │   ├── strategies/           # Trading strategy definitions
│   │   ├── tasks/                # Background scheduled tasks
│   │   └── utils/                # Utility functions
│   ├── migrations/               # Database migrations
│   ├── scripts/                  # Utility scripts
│   └── tests/                    # Unit and integration tests
├── quantdinger_vue/              # Vue.js frontend
│   ├── src/                      # Frontend source
│   ├── config/                   # Build configurations
│   ├── public/                   # Static assets
│   └── dist/                     # Production build output
└── docs/                         # Documentation and examples
```

## Directory Purposes

**Backend API Root:**
- `/home/workspace/ws/QuantDinger/backend_api_python/run.py`: Main entry point - loads .env, creates Flask app, starts services
- `/home/workspace/ws/QuantDinger/backend_api_python/app/__init__.py`: Flask application factory with startup hooks

**Configuration:**
- `/home/workspace/ws/QuantDinger/backend_api_python/app/config/settings.py`: MetaConfig-based settings (host, port, auth, logging)
- `/home/workspace/ws/QuantDinger/backend_api_python/app/config/database.py`: Redis, SQLite, Cache configuration
- `/home/workspace/ws/QuantDinger/backend_api_python/app/config/api_keys.py`: API key management
- `/home/workspace/ws/QuantDinger/backend_api_python/app/config/data_sources.py`: Market data source configuration

**Routes (API Endpoints):**
- `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/__init__.py`: Centralized route registration
- `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/auth.py`: Authentication endpoints
- `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/strategy.py`: Strategy management
- `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/market.py`: Market data queries
- `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/portfolio.py`: Portfolio management
- `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/ibkr.py`: Interactive Brokers integration
- `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/mt5.py`: MetaTrader5 integration
- `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/dashboard.py`: Dashboard data
- `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/settings.py`: User settings

**Services (Business Logic):**
- `/home/workspace/ws/QuantDinger/backend_api_python/app/services/trading_executor.py`: Real-time strategy execution engine
- `/home/workspace/ws/QuantDinger/backend_api_python/app/services/signal_executor.py`: Trade signal validation and execution
- `/home/workspace/ws/QuantDinger/backend_api_python/app/services/backtest.py`: Historical backtesting engine
- `/home/workspace/ws/QuantDinger/backend_api_python/app/services/data_handler.py`: Database operations for strategies
- `/home/workspace/ws/QuantDinger/backend_api_python/app/services/market_data_collector.py`: Market data aggregation
- `/home/workspace/ws/QuantDinger/backend_api_python/app/services/portfolio_monitor.py`: Real-time portfolio monitoring
- `/home/workspace/ws/QuantDinger/backend_api_python/app/services/pending_order_worker.py`: Pending order dispatch worker
- `/home/workspace/ws/QuantDinger/backend_api_python/app/services/live_trading/`: Live trading implementations

**Data Sources (Market Data Providers):**
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/base.py`: Abstract base class defining data source interface
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/factory.py`: Factory pattern for creating data sources
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/crypto.py`: Cryptocurrency data (CCXT-based)
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/forex.py`: Forex data providers
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/futures.py`: Futures data
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/cn_stock.py`: Chinese stock data
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/us_stock.py`: US stock data
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/cache_manager.py`: Caching layer
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/rate_limiter.py`: Rate limiting for APIs

**Strategies:**
- `/home/workspace/ws/QuantDinger/backend_api_python/app/strategies/runners/`: Strategy execution engines
  - `base_runner.py`: Abstract base runner
  - `single_symbol_runner.py`: Single-symbol strategy execution
  - `cross_sectional_runner.py`: Cross-sectional strategy execution
  - `regime_runner.py`: Market regime detection
- `/home/workspace/ws/QuantDinger/backend_api_python/app/strategies/single_symbol.py`: Single-symbol strategy definitions
- `/home/workspace/ws/QuantDinger/backend_api_python/app/strategies/cross_sectional.py`: Cross-sectional strategy definitions

**Utilities:**
- `/home/workspace/ws/QuantDinger/backend_api_python/app/utils/logger.py`: Logging setup
- `/home/workspace/ws/QuantDinger/backend_api_python/app/utils/db.py`: Database utilities
- `/home/workspace/ws/QuantDinger/backend_api_python/app/utils/cache.py`: Redis caching utilities
- `/home/workspace/ws/QuantDinger/backend_api_python/app/utils/auth.py`: Authentication utilities

**Frontend (Vue.js):**
- `/home/workspace/ws/QuantDinger/quantdinger_vue/src/api/`: API client functions (auth, market, portfolio, strategy)
- `/home/workspace/ws/QuantDinger/quantdinger_vue/src/components/`: Reusable Vue components
- `/home/workspace/ws/QuantDinger/quantdinger_vue/src/views/`: Page-level components
- `/home/workspace/ws/QuantDinger/quantdinger_vue/src/store/`: Vuex store modules (user, permissions, router)
- `/home/workspace/ws/QuantDinger/quantdinger_vue/src/router/`: Vue Router configuration
- `/home/workspace/ws/QuantDinger/quantdinger_vue/src/utils/`: Utility functions (request, axios)
- `/home/workspace/ws/QuantDinger/quantdinger_vue/src/config/`: App configuration and router configs
- `/home/workspace/ws/QuantDinger/quantdinger_vue/src/main.js`: Vue app initialization

## Key File Locations

**Entry Points:**
- `/home/workspace/ws/QuantDinger/backend_api_python/run.py`: Python API server
- `/home/workspace/ws/QuantDinger/quantdinger_vue/src/main.js`: Vue app initialization
- `/home/workspace/ws/QuantDinger/backend_api_python/gunicorn_config.py`: Production server configuration

**Configuration:**
- `/home/workspace/ws/QuantDinger/backend_api_python/app/config/settings.py`: Main settings
- `/home/workspace/ws/QuantDinger/backend_api_python/env.example`: Environment variable template
- `/home/workspace/ws/QuantDinger/backend_api_python/app/config/database.py`: Database/cache config

**Core Logic:**
- `/home/workspace/ws/QuantDinger/backend_api_python/app/services/trading_executor.py`: Trading engine
- `/home/workspace/ws/QuantDinger/backend_api_python/app/services/signal_executor.py`: Signal processing
- `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/base.py`: Data source interface

**Testing:**
- `/home/workspace/ws/QuantDinger/backend_api_python/tests/`: Test suite directory

## Naming Conventions

**Files:**
- Python modules: snake_case (e.g., `trading_executor.py`, `data_sources.py`)
- Vue components: PascalCase (e.g., `Dashboard.vue`, `IndicatorList.vue`)
- JavaScript utilities: camelCase (e.g., `request.js`, `axios.js`)
- Configuration: snake_case (e.g., `settings.py`, `database.py`)

**Directories:**
- Backend directories: snake_case (e.g., `data_sources`, `services`, `routes`)
- Frontend directories: camelCase or kebab-case (e.g., `api`, `components`, `views`)
- Tests: snake_case with `_test.py` or `test_` prefix

**Variables and Functions:**
- Python: snake_case (e.g., `get_kline()`, `trading_executor`)
- JavaScript/Vue: camelCase (e.g., `getMarketData()`, `fetchIndicator()`)

**Types/Classes:**
- PascalCase (e.g., `TradingExecutor`, `BaseDataSource`, `Config`)

## Where to Add New Code

**New API Endpoint:**
- Primary: `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/{feature_name}.py`
- Registration: `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/__init__.py`

**New Service/Business Logic:**
- Primary: `/home/workspace/ws/QuantDinger/backend_api_python/app/services/{service_name}.py`
- Entry point: Import in route handler or strategy runner

**New Data Source:**
- Primary: `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/{source_name}.py`
- Registration: Add to factory in `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/factory.py`

**New Strategy:**
- Implementation: `/home/workspace/ws/QuantDinger/backend_api_python/app/strategies/`
- Runner: `/home/workspace/ws/QuantDinger/backend_api_python/app/strategies/runners/`
- Config: `/home/workspace/ws/QuantDinger/backend_api_python/app/strategies/strategy_config_loader.py`

**New Frontend Feature:**
- Component: `/home/workspace/ws/QuantDinger/quantdinger_vue/src/components/{ComponentName}/`
- View: `/home/workspace/ws/QuantDinger/quantdinger_vue/src/views/{ViewName}/`
- API client: `/home/workspace/ws/QuantDinger/quantdinger_vue/src/api/{feature}.js`
- Route: `/home/workspace/ws/QuantDinger/quantdinger_vue/src/router/`

**Background Task:**
- Implementation: `/home/workspace/ws/QuantDinger/backend_api_python/app/tasks/{task_name}.py`
- Registration: `/home/workspace/ws/QuantDinger/backend_api_python/app/tasks/__init__.py`

**Configuration:**
- Backend config: `/home/workspace/ws/QuantDinger/backend_api_python/app/config/{config_name}.py`
- Environment: Add to `/home/workspace/ws/QuantDinger/backend_api_python/env.example`

## Special Directories

**`backend_api_python/migrations/`:**
- Purpose: Database schema migrations
- Generated: Yes (Alembic/SQLAlchemy)
- Committed: Yes

**`backend_api_python/data/`:**
- Purpose: SQLite database file and seed data
- Generated: Yes (runtime)
- Committed: No (in .gitignore)

**`backend_api_python/logs/`:**
- Purpose: Application log files
- Generated: Yes (runtime)
- Committed: No (in .gitignore)

**`quantdinger_vue/dist/`:**
- Purpose: Production build output
- Generated: Yes (build process)
- Committed: No

**`quantdinger_vue/backup_dist/`:**
- Purpose: Backup of previous builds
- Generated: Yes
- Committed: No

---

*Structure analysis: 2026-04-08*
