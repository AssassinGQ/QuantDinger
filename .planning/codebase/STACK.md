# Technology Stack

**Analysis Date:** 2026-04-22

## Languages

**Primary:**
- Python 3.x - 后端 API 与交易执行核心，位于 `backend_api_python/`（证据：`backend_api_python/requirements.txt`、`backend_api_python/run.py`）

**Secondary:**
- JavaScript (Vue 2) - 前端控制台，位于 `quantdinger_vue/`（证据：`quantdinger_vue/package.json`）
- SQL - 数据库结构与迁移脚本，位于 `backend_api_python/migrations/`
- YAML - 容器编排与 CI，位于 `docker-compose.yml`、`.github/workflows/basic-ci.yml`

## Runtime

**Environment:**
- Python 3.12 容器运行时（证据：`backend_api_python/Dockerfile`）
- Node.js 18 构建镜像（证据：`quantdinger_vue/Dockerfile`）
- CI 中 Python 3.12 + Node.js 20（证据：`.github/workflows/basic-ci.yml`）

**Package Manager:**
- `pip`（后端依赖安装，证据：`backend_api_python/Dockerfile`、`backend_api_python/requirements.txt`）
- `npm`（前端本地安装与脚本，证据：`quantdinger_vue/package.json`）
- `yarn`（前端 CI 安装，证据：`.github/workflows/basic-ci.yml`）
- Lockfile: `quantdinger_vue/package-lock.json`（present），根目录 `package-lock.json`（present）

## Frameworks

**Core:**
- Flask 2.3.x - HTTP API 框架（证据：`backend_api_python/requirements.txt`、`backend_api_python/app/__init__.py`）
- Vue 2.6 + Vue Router + Vuex - 前端框架（证据：`quantdinger_vue/package.json`）
- Ant Design Vue 1.x - 前端 UI 组件库（证据：`quantdinger_vue/package.json`）

**Testing:**
- pytest 体系 - 后端测试目录 `backend_api_python/tests/`
- Vue CLI unit-jest - 前端单元测试（证据：`quantdinger_vue/package.json` 的 `test:unit`）

**Build/Dev:**
- Docker Compose - 本地一键部署（证据：`docker-compose.yml`）
- Vue CLI Service + Webpack 5 - 前端构建与开发（证据：`quantdinger_vue/package.json`、`quantdinger_vue/vue.config.js`）
- Nginx - 前端产物托管（证据：`quantdinger_vue/Dockerfile`）

## Key Dependencies

**Critical:**
- `ib_insync` - IBKR 交易接入（证据：`backend_api_python/requirements.txt`、`backend_api_python/app/services/live_trading/ibkr_trading/client.py`）
- `ccxt` - 加密市场数据与交易所接入（证据：`backend_api_python/requirements.txt`、`backend_api_python/app/data_sources/crypto.py`）
- `yfinance` + `finnhub-python` + `akshare` - 多市场行情数据源（证据：`backend_api_python/requirements.txt`、`backend_api_python/app/data_sources/us_stock.py`、`backend_api_python/app/data_sources/cn_stock.py`）
- `psycopg2-binary` + `SQLAlchemy` - PostgreSQL 数据访问（证据：`backend_api_python/requirements.txt`、`backend_api_python/app/utils/db_postgres.py`）
- `requests` - 对外 HTTP 调用基础库（证据：`backend_api_python/app/services/llm.py`、`backend_api_python/app/services/oauth_service.py`、`backend_api_python/app/services/search.py`）

**Infrastructure:**
- `python-dotenv` - 启动时加载 `.env`（证据：`backend_api_python/run.py`）
- `flask-cors` - CORS 处理中间件（证据：`backend_api_python/app/__init__.py`）
- `APScheduler` - 调度能力依赖（证据：`backend_api_python/requirements.txt`）

## Configuration

**Environment:**
- 统一使用环境变量驱动，模板在 `backend_api_python/env.example`
- 进程启动时优先加载 `backend_api_python/.env`，再回退仓库根 `.env`（证据：`backend_api_python/run.py`）
- 配置键映射与类型转换集中在 `backend_api_python/app/utils/config_loader.py`
- 业务配置读取入口为 `backend_api_python/app/config/settings.py`

**Build:**
- 容器与编排：`backend_api_python/Dockerfile`、`quantdinger_vue/Dockerfile`、`docker-compose.yml`
- 前端构建与代理：`quantdinger_vue/vue.config.js`
- CI 检查：`.github/workflows/basic-ci.yml`

## Platform Requirements

**Development:**
- Python 3.10+（文档约束，证据：`backend_api_python/README.md`）
- Node.js 16+（文档约束，证据：`quantdinger_vue/README.md`）
- PostgreSQL 14+（本地建议）或 Docker `postgres:16-alpine`（证据：`backend_api_python/README.md`、`docker-compose.yml`）

**Production:**
- 推荐 Docker Compose 三服务拓扑：`frontend` + `backend` + `postgres`（证据：`docker-compose.yml`）
- 前端通过 Nginx 提供静态资源，后端暴露 5000 端口 API（证据：`quantdinger_vue/Dockerfile`、`backend_api_python/Dockerfile`）

---

*Stack analysis: 2026-04-22*
