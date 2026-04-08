<!-- GSD:project-start source:PROJECT.md -->
## Project

**QuantDinger - IBKR 数据源**

为 `exchange_id = ibkr-live` 的交易策略提供原生 IBKR 数据源，从 Interactive Brokers API 获取 K线和实时报价，替代当前使用的 yfinance/Finnhub。

**Core value**: 实盘交易策略使用与实际下单同一数据源，确保数据一致性。

### Constraints

- **技术**: 使用 ib_insync 库连接 IBKR Gateway
- **IBKR Gateway**: 需要本地运行 IBKR Gateway 或 IBKR 账户
- **兼容性**: 支持多种市场类型（架构设计）
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.x - Backend API, data processing, trading algorithms
- JavaScript (ES6+) - Frontend web application
- Vue 2.6.14 - Frontend framework
- HTML5/CSS3 - Frontend markup and styling
- Less - CSS preprocessor for theming
## Runtime
- Python 3.x (Flask web server)
- Node.js (Vue CLI for frontend build)
- Docker - Containerized deployment
- Python: pip (requirements.txt)
- Node.js: Yarn (yarn.lock)
- Version: Lockfiles present (yarn.lock, package-lock.json)
## Frameworks
- Flask 2.3.3 - Web framework
- APScheduler 3.10.0 - Task scheduling
- SQLAlchemy 2.0.0 - ORM
- Flask-CORS 4.0.0 - Cross-origin support
- Vue 2.6.14 - UI framework
- Vue Router 3.5.3 - Client-side routing
- Vuex 3.6.2 - State management
- Ant Design Vue 1.7.8 - UI component library
- Jest (via Vue CLI) - Unit testing
- pytest - Python unit testing
- Vue CLI 5.0.8 - Frontend build tooling
- Webpack 5.105.0 - Module bundler
- Gunicorn - WSGI server for Flask
- Babel - JavaScript transpilation
## Key Dependencies
- ib_insync 0.9.86 - Interactive Brokers trading integration
- ccxt 4.0.0 - Crypto exchange unified API
- yfinance 0.2.18 - Yahoo Finance data
- finnhub-python 2.4.18 - Finnhub stock data
- akshare 1.12.0 - Chinese market data
- pandas 1.5.0 - Data analysis
- psycopg2-binary 2.9.9 - PostgreSQL driver
- SQLAlchemy 2.0.0 - Database ORM
- PyJWT 2.8.0 - JWT authentication
- bcrypt 4.1.0 - Password hashing
- requests 2.28.0 - HTTP client
- echarts 6.0.0 - Charting library
- lightweight-charts 5.0.8 - Financial charts
- klinecharts 9.8.0 - K-line charts
- viser-vue 2.4.8 - Data visualization
- axios 0.26.1 - HTTP client
- tavily-python 0.3.0 (optional) - AI search
- google-search-results 2.4.0 (optional) - Web search
## Configuration
- Environment variables in `.env` files
- Configuration loaded via `app/utils/config_loader.py`
- Config classes use metaprogramming for dynamic property resolution
- `backend_api_python/env.example` - Environment template
- `backend_api_python/app/config/` - Configuration modules
- `quantdinger_vue/vue.config.js` - Vue CLI configuration
- `quantdinger_vue/babel.config.js` - Transpilation settings
- `quantdinger_vue/jest.config.js` - Test configuration
- `docker-compose.yml` - Multi-service orchestration
- `backend_api_python/Dockerfile` - Backend container image
- `quantdinger_vue/Dockerfile` - Frontend container image
## Platform Requirements
- Python 3.x with pip
- Node.js 14+ with Yarn
- Redis server (for caching)
- PostgreSQL 16 (for production data)
- Docker and Docker Compose
- Docker containers (Ubuntu-based images)
- PostgreSQL database (hosted or containerized)
- Redis cache server
- Gunicorn for Flask serving
- Nginx (optional, for frontend reverse proxy)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- snake_case: `price_fetcher.py`, `signal_processor.py`, `market.py`
- Test files: `test_price_fetcher.py`, `test_runners.py`
- snake_case: `fetch_current_price`, `get_price_fetcher`, `process_signals`
- Private functions: prefixed with underscore `_wait_for_next_tick`, `_dedup_key`
- snake_case: `price_cache`, `market_category`, `current_price`
- Constants: UPPER_CASE with underscores: `PRICE_CACHE_TTL_SEC`, `DEFAULT_USER_ID`
- PascalCase: `PriceFetcher`, `SignalDeduplicator`, `KlineService`
- Abstract base classes: `BaseStrategyRunner`
- Type hints using Python typing module: `Optional[float]`, `Dict[str, Any]`, `List[Dict]`
## Code Style
- No explicit formatter configured; follows PEP 8 conventions
- Indentation: 4 spaces
- Maximum line length: not strictly enforced but reasonable (~100-120 chars)
- Pylint: `# pylint: disable=protected-access` comments used in tests
- Type hints: Used extensively with `typing` module
- One class or logical unit per file
- Related services grouped in `/app/services/`
- Routes in `/app/routes/`
- Strategies in `/app/strategies/`
- Data sources in `/app/data_sources/`
## Import Organization
- No explicit aliases configured; uses relative app imports
## Error Handling
- Try/except with broad `Exception` catching for non-critical failures
- Returns `None` on failure: `return None` or `(None, [])`
- Uses logger for non-critical errors: `logger.warning()`
- Guard clauses for early returns when validation fails
- Functions return `None` or empty collections when operations fail
- Tuple returns use `(None, [])` for "no result" cases
## Logging
- Use logger.warning for non-critical failures (e.g., price fetch failure)
- Use logger.error for critical failures
- Include contextual data: `"Failed to fetch price for %s:%s: %s"`
## Comments
- Explain complex logic and edge cases
- Document function purpose in docstrings (Google-style or basic)
- Comment test cases for clarity
- Basic docstrings on public methods: `"""Get current price..."""`
- Args/Returns sections in key functions
- Chinese comments in test files for test intent: `# 测试环境变量解析失败时的 fallback 逻辑`
- English comments in test methods: `# Should return cached price without calling get_ticker`
## Function Design
- Functions tend to be medium-sized with clear single responsibilities
- Complex logic broken into helper functions
- Use type hints for all parameters
- Default values for optional parameters: `market_category: str = "Crypto"`
- Explicit return types with type hints
- Return None for failure states: `-> Optional[float]`
## Module Design
- Use explicit imports: `from app.services.price_fetcher import PriceFetcher`
- Singleton pattern for services: `get_price_fetcher()`, `get_signal_deduplicator()`
- `__init__.py` in each package for package-level imports
- Submodules explicitly imported in package `__init__.py`
## Class Design
- Explicit `__init__` with dependency injection
- Initialize caches and locks in `__init__`
- Abstract base classes for strategy runners: `BaseStrategyRunner(ABC)`
- Use `@abstractmethod` for methods that must be implemented
- Thread-safe singletons with locks: `SignalDeduplicator`
- In-memory caches with TTL: `PriceFetcher._price_cache`
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Flask application factory pattern (`create_app()` in `/home/workspace/ws/QuantDinger/backend_api_python/app/__init__.py`)
- Blueprint-based API routing with centralized route registration
- Service layer for business logic (trading execution, data handling, market analysis)
- Data source abstraction layer for multi-market data providers
- Singleton pattern for critical services (TradingExecutor, PendingOrderWorker)
- Event-driven background task scheduling
## Layers
- Purpose: Centralize environment-based settings and secrets
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/config/`
- Contains: Settings, API keys, database, data sources, cache configuration
- Depends on: Environment variables and .env files
- Used by: All application components
- Purpose: Expose HTTP endpoints for frontend and external clients
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/`
- Contains: Flask blueprints (auth, market, strategy, portfolio, ibkr, mt5, etc.)
- Depends on: Services layer for business logic
- Used by: Flask app through centralized registration in `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/__init__.py`
- Purpose: Core trading execution, data processing, and analysis
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/services/`
- Contains: TradingExecutor, SignalExecutor, DataHandler, Backtest, LiveTrading modules
- Depends on: Data sources and database utilities
- Used by: Routes, Strategy runners, Background tasks
- Purpose: Unified interface for fetching market data from multiple providers
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/`
- Contains: BaseDataSource abstract class, implementations for crypto (Binance, Bybit, etc.), forex, futures, stocks
- Depends on: External APIs and rate limiting/circuit breaker utilities
- Used by: Services layer for market data
- Purpose: Execute trading strategies with configurable parameters
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/strategies/runners/`
- Contains: BaseRunner, SingleSymbolRunner, CrossSectionalRunner, RegimeRunner
- Depends on: TradingExecutor and DataHandler
- Used by: TradingExecutor for strategy execution
- Purpose: Persistence, caching, logging, authentication
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/utils/`
- Contains: DB utilities, cache management, auth, logging
- Used by: All layers
- Purpose: Vue.js SPA dashboard for trading management
- Location: `/home/workspace/ws/QuantDinger/quantdinger_vue/src/`
- Contains: Components, views, store (Vuex), router, API clients
## Data Flow
## Key Abstractions
- Purpose: Create appropriate data source based on market type and exchange
- Examples: `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/factory.py`
- Pattern: Factory pattern with registry of supported data sources
- Purpose: Define contract for all market data providers
- Examples: `/home/workspace/ws/QuantDinger/backend_api_python/app/data_sources/base.py`
- Pattern: Abstract base class with interface for get_kline(), get_ticker()
- Purpose: Manage live strategy threads and trade execution
- Examples: `/home/workspace/ws/QuantDinger/backend_api_python/app/services/trading_executor.py`
- Pattern: Singleton with thread pool management, configurable max threads
- Purpose: Execute strategy logic with market data
- Examples: `/home/workspace/ws/QuantDinger/backend_api_python/app/strategies/runners/`
- Pattern: Strategy pattern for different strategy types
## Entry Points
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/run.py`
- Triggers: Python execution (`python run.py`) or Gunicorn (`gunicorn -c gunicorn_config.py "run:app"`)
- Responsibilities: Load environment, create Flask app, start background services, register routes
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/__init__.py` (`create_app()`)
- Triggers: Called from run.py
- Responsibilities: Initialize Flask, CORS, database, register blueprints, start portfolio monitor, pending order worker, restore running strategies
- Location: `/home/workspace/ws/QuantDinger/backend_api_python/app/routes/__init__.py`
- Triggers: Called from create_app()
- Responsibilities: Import and register all blueprint routes with URL prefixes
- Location: `/home/workspace/ws/QuantDinger/quantdinger_vue/src/main.js`
- Triggers: Frontend build/dev server
- Responsibilities: Initialize Vue app, router, store, load global components
## Error Handling
- Global exception handling with centralized logging
- Demo mode middleware blocks state-changing operations
- Rate limiting and circuit breaker patterns for external API resilience
- Graceful degradation with fallback mechanisms
- Exception classes for specific error types (RateLimitError in data sources)
- Database transaction rollback on errors
- Health check endpoints for system status
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
