# Technology Stack

**Analysis Date:** 2026-04-08

## Languages

**Primary:**
- Python 3.x - Backend API, data processing, trading algorithms
- JavaScript (ES6+) - Frontend web application
- Vue 2.6.14 - Frontend framework

**Secondary:**
- HTML5/CSS3 - Frontend markup and styling
- Less - CSS preprocessor for theming

## Runtime

**Environment:**
- Python 3.x (Flask web server)
- Node.js (Vue CLI for frontend build)
- Docker - Containerized deployment

**Package Manager:**
- Python: pip (requirements.txt)
- Node.js: Yarn (yarn.lock)
- Version: Lockfiles present (yarn.lock, package-lock.json)

## Frameworks

**Backend:**
- Flask 2.3.3 - Web framework
- APScheduler 3.10.0 - Task scheduling
- SQLAlchemy 2.0.0 - ORM
- Flask-CORS 4.0.0 - Cross-origin support

**Frontend:**
- Vue 2.6.14 - UI framework
- Vue Router 3.5.3 - Client-side routing
- Vuex 3.6.2 - State management
- Ant Design Vue 1.7.8 - UI component library

**Testing:**
- Jest (via Vue CLI) - Unit testing
- pytest - Python unit testing

**Build/Dev:**
- Vue CLI 5.0.8 - Frontend build tooling
- Webpack 5.105.0 - Module bundler
- Gunicorn - WSGI server for Flask
- Babel - JavaScript transpilation

## Key Dependencies

**Critical:**
- ib_insync 0.9.86 - Interactive Brokers trading integration
- ccxt 4.0.0 - Crypto exchange unified API
- yfinance 0.2.18 - Yahoo Finance data
- finnhub-python 2.4.18 - Finnhub stock data
- akshare 1.12.0 - Chinese market data
- pandas 1.5.0 - Data analysis

**Infrastructure:**
- psycopg2-binary 2.9.9 - PostgreSQL driver
- SQLAlchemy 2.0.0 - Database ORM
- PyJWT 2.8.0 - JWT authentication
- bcrypt 4.1.0 - Password hashing
- requests 2.28.0 - HTTP client

**UI/Charts:**
- echarts 6.0.0 - Charting library
- lightweight-charts 5.0.8 - Financial charts
- klinecharts 9.8.0 - K-line charts
- viser-vue 2.4.8 - Data visualization
- axios 0.26.1 - HTTP client

**Search & AI:**
- tavily-python 0.3.0 (optional) - AI search
- google-search-results 2.4.0 (optional) - Web search

## Configuration

**Environment:**
- Environment variables in `.env` files
- Configuration loaded via `app/utils/config_loader.py`
- Config classes use metaprogramming for dynamic property resolution

**Backend Config Files:**
- `backend_api_python/env.example` - Environment template
- `backend_api_python/app/config/` - Configuration modules
  - `api_keys.py` - API key management
  - `data_sources.py` - Data source configuration
  - `database.py` - Database and cache config
  - `settings.py` - Application settings

**Frontend Config Files:**
- `quantdinger_vue/vue.config.js` - Vue CLI configuration
- `quantdinger_vue/babel.config.js` - Transpilation settings
- `quantdinger_vue/jest.config.js` - Test configuration

**Docker:**
- `docker-compose.yml` - Multi-service orchestration
- `backend_api_python/Dockerfile` - Backend container image
- `quantdinger_vue/Dockerfile` - Frontend container image

## Platform Requirements

**Development:**
- Python 3.x with pip
- Node.js 14+ with Yarn
- Redis server (for caching)
- PostgreSQL 16 (for production data)
- Docker and Docker Compose

**Production:**
- Docker containers (Ubuntu-based images)
- PostgreSQL database (hosted or containerized)
- Redis cache server
- Gunicorn for Flask serving
- Nginx (optional, for frontend reverse proxy)

---

*Stack analysis: 2026-04-08*
