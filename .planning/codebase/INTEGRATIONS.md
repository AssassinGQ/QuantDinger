# External Integrations

**Analysis Date:** 2026-04-22

## APIs & External Services

**交易执行与券商/交易所:**
- Interactive Brokers (IBKR) - 实盘/仿真交易接入（证据：`backend_api_python/app/services/live_trading/ibkr_trading/client.py`）
  - SDK/Client: `ib_insync`
  - Auth: `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`, `IBKR_ACCOUNT` 及 live 变体（定义见 `backend_api_python/env.example`）
- MetaTrader 5 (可选) - 外汇交易接入（证据：`backend_api_python/app/services/live_trading/mt5_trading/client.py`）
  - SDK/Client: MetaTrader5 Python 库（Windows-only 注释）
  - Auth: MT5 账户参数（由策略配置/连接配置传入）
- Crypto Exchanges (Binance/OKX/Bitget/Bybit/Coinbase/Kraken/Kucoin/Gate/Bitfinex 等) - 加密交易执行（证据：`backend_api_python/app/services/live_trading/crypto_trading/`）
  - SDK/Client: `ccxt` + 自定义 REST 客户端
  - Auth: 交易所 key/secret（由策略交易配置提供）

**市场数据与信息服务:**
- Finnhub - 美股报价/公司信息（证据：`backend_api_python/app/data_sources/us_stock.py`、`backend_api_python/app/services/symbol_name.py`）
  - SDK/Client: `finnhub-python`
  - Auth: `FINNHUB_API_KEY`
- Yahoo Finance - 通用行情回退源（证据：`backend_api_python/app/data_sources/us_stock.py`、`backend_api_python/app/data_sources/cn_stock.py`）
  - SDK/Client: `yfinance`
  - Auth: 无
- Tiingo - 外汇相关数据链路（证据：`backend_api_python/app/data_sources/forex.py`）
  - SDK/Client: `requests`
  - Auth: `TIINGO_API_KEY`
- Eastmoney / Tencent - A/H 股行情（证据：`backend_api_python/app/data_sources/cn_stock.py`）
  - SDK/Client: `requests`
  - Auth: 无
- 搜索引擎聚合（Bocha/Tavily/SerpAPI/Google CSE/Bing/DuckDuckGo）- 新闻与研究上下文（证据：`backend_api_python/app/services/search.py`）
  - SDK/Client: `requests`，可选 `tavily`、`serpapi`
  - Auth: `BOCHA_API_KEYS`, `TAVILY_API_KEYS`, `SERPAPI_KEYS`, `SEARCH_GOOGLE_API_KEY`, `SEARCH_GOOGLE_CX`, `SEARCH_BING_API_KEY`

**LLM 与 AI:**
- OpenRouter / OpenAI / Google Gemini / DeepSeek / xAI Grok / MiniMax - AI 分析与对话调用（证据：`backend_api_python/app/services/llm.py`）
  - SDK/Client: `requests`
  - Auth: `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, `GROK_API_KEY`, `MINIMAX_API_KEY`

**身份与安全服务:**
- Cloudflare Turnstile - 人机校验（证据：`backend_api_python/app/services/security_service.py`）
  - SDK/Client: `requests`
  - Auth: `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`
- Google OAuth / GitHub OAuth - 第三方登录（证据：`backend_api_python/app/services/oauth_service.py`、`backend_api_python/app/routes/auth.py`）
  - SDK/Client: `requests`
  - Auth: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`

**消息与通知服务:**
- SMTP 邮件 - 策略通知（证据：`backend_api_python/app/services/signal_notifier.py`）
  - SDK/Client: `smtplib`
  - Auth: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`
- Twilio SMS - 短信通知（证据：`backend_api_python/app/services/signal_notifier.py`）
  - SDK/Client: `requests` 调 Twilio REST
  - Auth: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`
- Telegram Bot / Discord Webhook / Generic Webhook - 出站通知（证据：`backend_api_python/app/services/signal_notifier.py`）
  - SDK/Client: `requests`
  - Auth: Telegram bot token、Webhook token/HMAC secret（变量名见通知配置与 `SIGNAL_WEBHOOK_SIGNING_SECRET`）

## Data Storage

**Databases:**
- PostgreSQL（主路径）- 连接池与 SQL 适配（证据：`backend_api_python/app/utils/db_postgres.py`、`docker-compose.yml`）
  - Connection: `DATABASE_URL`（Compose 中由 `POSTGRES_*` 组装）
  - Client: `psycopg2-binary`（以及 `SQLAlchemy` 依赖存在）
- SQLite 兼容路径（非默认主路径）- 由 DB 抽象层兼容（证据：`backend_api_python/app/utils/db.py`、`backend_api_python/app/config/database.py`）

**File Storage:**
- Local filesystem only
  - 后端持久目录：`backend_api_python/logs`、`backend_api_python/data`（证据：`docker-compose.yml`）

**Caching:**
- 进程内缓存开关 + 可选 Redis 配置项
  - 开关配置：`ENABLE_CACHE`（证据：`backend_api_python/app/utils/config_loader.py`）
  - Redis 配置字段存在：`REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB`（证据：`backend_api_python/app/config/database.py`）

## Authentication & Identity

**Auth Provider:**
- Custom（JWT + 用户库）为主（证据：`backend_api_python/app/routes/auth.py`、`backend_api_python/app/utils/auth.py`、`backend_api_python/app/services/user_service.py`）
  - Implementation: Bearer Token + token_version 单端登录失效机制
- OAuth（Google/GitHub）为可选增强登录（证据：`backend_api_python/app/services/oauth_service.py`）

## Monitoring & Observability

**Error Tracking:**
- Not detected（未检测到 Sentry/Datadog 类 SDK，证据：`backend_api_python/requirements.txt`）

**Logs:**
- Python 文件日志 + 轮转配置（证据：`backend_api_python/app/config/settings.py`、`backend_api_python/app/utils/logger.py`）

## CI/CD & Deployment

**Hosting:**
- Docker Compose 容器化部署（证据：`docker-compose.yml`）
- 前端 Nginx 反向代理 + 静态托管（证据：`quantdinger_vue/Dockerfile`、`quantdinger_vue/deploy/nginx-docker.conf`）

**CI Pipeline:**
- GitHub Actions 基础检查（Python 语法/import + 前端 lint）（证据：`.github/workflows/basic-ci.yml`）

## Environment Configuration

**Required env vars:**
- 核心：`DATABASE_URL`, `SECRET_KEY`, `PYTHON_API_HOST`, `PYTHON_API_PORT`（证据：`backend_api_python/env.example`、`backend_api_python/app/config/settings.py`）
- OAuth 回调前端地址：`FRONTEND_URL`（证据：`backend_api_python/app/services/oauth_service.py`）

**Secrets location:**
- `backend_api_python/.env`（由 `backend_api_python/run.py` 启动时加载）
- `quantdinger_vue/.env*`（前端多环境配置文件存在，仅记录存在性）

## Webhooks & Callbacks

**Incoming:**
- OAuth 回调入口（证据：`backend_api_python/app/routes/auth.py`）
  - `/api/auth/oauth/google/callback`
  - `/api/auth/oauth/github/callback`

**Outgoing:**
- 通知出站：通用 Webhook / Discord / Telegram / Twilio / SMTP（证据：`backend_api_python/app/services/signal_notifier.py`）

---

*Integration audit: 2026-04-22*
