# 代码结构分析

**分析日期:** 2026-04-22

## 目录布局

```text
QuantDinger/
├── backend_api_python/           # Flask 后端：API、策略运行时、调度、数据接入
│   ├── app/                      # 业务主代码（routes/services/strategies/utils/tasks）
│   ├── tests/                    # 后端测试
│   ├── migrations/               # PostgreSQL 初始化 SQL
│   ├── run.py                    # 后端进程入口
│   └── requirements.txt          # Python 依赖
├── quantdinger_vue/              # Vue2 前端：页面、路由、状态、API 封装
│   ├── src/                      # 前端主代码
│   ├── tests/                    # 前端测试
│   ├── vue.config.js             # devServer 与构建配置
│   └── package.json              # 前端依赖与脚本
├── docs/                         # 项目文档与截图
├── scripts/                      # 仓库级脚本与数据处理脚本
└── .planning/codebase/           # codebase map 文档输出目录
```

## 目录职责

**`backend_api_python/app/routes`:**
- 目的: API 接口边界层（Blueprint）。
- 包含: `strategy.py`、`ibkr.py`、`auth.py`、`scheduler.py`、`market.py` 等。
- 关键文件: `backend_api_python/app/routes/__init__.py` 统一注册路由与 URL 前缀。

**`backend_api_python/app/services`:**
- 目的: 业务编排与领域实现层。
- 包含: 策略管理、交易执行、调度、用户与安全、IBKR/MT5/交易所客户端。
- 关键文件: `backend_api_python/app/services/trading_executor.py`、`backend_api_python/app/services/scheduler_service.py`、`backend_api_python/app/services/live_trading/ibkr_trading/client.py`。

**`backend_api_python/app/strategies`:**
- 目的: 策略抽象与运行器实现。
- 包含: 策略工厂、策略类型、runner 工厂与各 runner。
- 关键文件: `backend_api_python/app/strategies/factory.py`、`backend_api_python/app/strategies/runners/factory.py`。

**`backend_api_python/app/data_sources`:**
- 目的: 市场数据源抽象、限流、缓存、熔断。
- 包含: `DataSourceFactory`、`circuit_breaker.py`、`rate_limiter.py`、`data_manager.py`。
- 关键文件: `backend_api_python/app/data_sources/__init__.py`。

**`backend_api_python/app/utils`:**
- 目的: 基础设施与横切能力（DB、JWT、日志、工具函数）。
- 关键文件: `backend_api_python/app/utils/db.py`、`backend_api_python/app/utils/auth.py`。

**`backend_api_python/app/tasks`:**
- 目的: 插件式定时任务入口与任务定义。
- 关键文件: `backend_api_python/app/tasks/__init__.py`、`backend_api_python/app/tasks/kline_sync.py`、`backend_api_python/app/tasks/nq100_universe_sync.py`。

**`quantdinger_vue/src/views`:**
- 目的: 页面级业务组件，按功能模块组织。
- 包含: `dashboard`、`indicator-analysis`、`trading-assistant`、`broker-dashboard`、`portfolio`、`settings` 等。

**`quantdinger_vue/src/api`:**
- 目的: 前端 API 适配层；将页面动作映射到后端 `/api/*`。
- 关键文件: `quantdinger_vue/src/api/strategy.js`、`quantdinger_vue/src/api/ibkr.js`、`quantdinger_vue/src/api/login.js`。

**`quantdinger_vue/src/store`:**
- 目的: 全局状态管理（用户、权限、应用设置）。
- 关键文件: `quantdinger_vue/src/store/index.js`、`quantdinger_vue/src/store/modules/user.js`、`quantdinger_vue/src/store/modules/async-router.js`。

**`quantdinger_vue/src/router`:**
- 目的: 路由实例与动态路由生成。
- 关键文件: `quantdinger_vue/src/router/index.js`、`quantdinger_vue/src/router/generator-routers.js`、`quantdinger_vue/src/config/router.config.js`。

## 关键文件位置

**后端入口:**
- `backend_api_python/run.py`: 进程入口，创建 Flask app 并启动本地服务。
- `backend_api_python/app/__init__.py`: 应用工厂，负责启动期初始化与钩子执行。

**后端核心逻辑:**
- `backend_api_python/app/routes/strategy.py`: 策略增删改查 + 启停 + 交易记录读取。
- `backend_api_python/app/routes/ibkr.py`: IBKR 连接、下单、看板与查询接口。
- `backend_api_python/app/services/trading_executor.py`: 策略线程生命周期管理。
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py`: IBKR 客户端与事件回调核心。
- `backend_api_python/app/services/scheduler_service.py`: APScheduler 调度与同步任务组织。

**后端认证与安全:**
- `backend_api_python/app/routes/auth.py`: 登录、注册、OAuth、验证码流程。
- `backend_api_python/app/utils/auth.py`: JWT 签发/验证与装饰器。
- `backend_api_python/app/services/user_service.py`: 用户鉴权、密码哈希、角色权限。

**后端测试:**
- `backend_api_python/tests/test_ibkr_order_callback.py`: IBKR 回调/成交/拒单闭环测试。

**前端入口与网关:**
- `quantdinger_vue/src/main.js`: Vue 根实例、路由、状态、i18n 启动。
- `quantdinger_vue/src/permission.js`: 路由守卫与登录态恢复。
- `quantdinger_vue/src/utils/request.js`: axios 请求/响应拦截器。
- `quantdinger_vue/vue.config.js`: 本地开发代理（`/api` -> `http://localhost:5000`）。

## 命名与组织约定

**后端文件组织:**
- 路由按业务域命名：`routes/<domain>.py`（如 `routes/portfolio.py`、`routes/community.py`）。
- 服务按能力命名：`services/<capability>.py` 或 `services/live_trading/<broker>_trading/*`。
- 运行器/策略按策略类型命名并通过工厂映射（`strategies/factory.py`、`strategies/runners/factory.py`）。

**前端文件组织:**
- 页面目录按业务模块划分，入口多为 `index.vue`（如 `views/trading-assistant/index.vue`）。
- API 层按领域拆分 `src/api/*.js`，函数名与后端动作保持语义一致（如 `startStrategy`、`getStrategyPositions`）。
- Vuex 模块化组织在 `src/store/modules/*`。

## 新增代码放置指南（可执行）

**新增后端 API（新业务域）:**
- 实现文件放在 `backend_api_python/app/routes/<new_domain>.py`。
- 在 `backend_api_python/app/routes/__init__.py` 中注册 blueprint 与 URL 前缀。
- 业务逻辑优先放在 `backend_api_python/app/services/<new_domain>.py`，路由层只做编排。

**新增交易接入（新 Broker/交易所）:**
- 放在 `backend_api_python/app/services/live_trading/<engine>_trading/`。
- 复用 `app/services/live_trading/base.py` 的客户端抽象与 `records.py` 的落库通道。
- 对外 API 入口放 `backend_api_python/app/routes/<engine>.py`。

**新增策略运行能力:**
- 策略实现放 `backend_api_python/app/strategies/`。
- 运行器放 `backend_api_python/app/strategies/runners/`。
- 在 `strategies/factory.py` 与 `strategies/runners/factory.py` 增加类型映射。

**新增定时任务:**
- 插件任务文件放 `backend_api_python/app/tasks/`。
- 在 `backend_api_python/app/tasks/__init__.py` 中纳入 `register_all_tasks()`。
- 若需要统一调度能力，走 `backend_api_python/app/services/scheduler_service.py`。

**新增前端页面:**
- 页面组件放 `quantdinger_vue/src/views/<feature>/index.vue`。
- 在 `quantdinger_vue/src/config/router.config.js` 添加路由元信息（title/icon/permission）。
- API 调用统一放 `quantdinger_vue/src/api/<feature>.js`，不要在页面中直接拼 URL。

**新增前端鉴权相关逻辑:**
- token/用户态变更放 `quantdinger_vue/src/store/modules/user.js`。
- 路由访问控制变更放 `quantdinger_vue/src/permission.js` 与 `src/store/modules/async-router.js`。

## 特殊目录说明

**`backend_api_python/logs`:**
- 用途: 后端运行日志目录。
- 生成: 是。
- 提交: 否（运行产物，通常不应提交）。

**`backend_api_python/data`:**
- 用途: 本地数据、缓存、记忆等运行数据存储。
- 生成: 是。
- 提交: 视内容而定（作为运行数据建议按需管理）。

**`quantdinger_vue/dist`:**
- 用途: 前端构建产物。
- 生成: 是。
- 提交: 通常不提交（以部署流程为准）。

---

*结构分析完成于 2026-04-22*
# Codebase Structure

**Analysis Date:** 2026-04-22

## Directory Layout

```text
QuantDinger/
├── backend_api_python/          # Flask API、策略执行、任务调度、数据落库
├── quantdinger_vue/             # Vue 2 前端（页面、路由、状态、API 调用）
├── scripts/                     # 独立脚本（数据抓取/研究/批处理）
├── docs/                        # 用户与开发文档
├── docker-compose.yml           # 容器编排（前后端与数据库）
└── .planning/codebase/          # Codebase map 文档输出目录
```

## Directory Purposes

**backend_api_python:**
- Purpose: 后端核心代码与运行环境。
- Contains: `app/` 业务代码、`migrations/` SQL 迁移、`tests/` pytest、`run.py` 入口、`requirements.txt` 依赖。
- Key files: `backend_api_python/run.py`, `backend_api_python/app/__init__.py`, `backend_api_python/app/routes/__init__.py`

**backend_api_python/app/routes:**
- Purpose: API 按业务域拆分的蓝图层。
- Contains: 鉴权、交易、回测、市场、IBKR、调度、快分析等路由模块。
- Key files: `backend_api_python/app/routes/strategy.py`, `backend_api_python/app/routes/ibkr.py`, `backend_api_python/app/routes/fast_analysis.py`

**backend_api_python/app/services:**
- Purpose: 业务逻辑与外部集成的服务层。
- Contains: 策略执行器、数据采集、回测、交易记录、调度、LLM 分析、券商客户端。
- Key files: `backend_api_python/app/services/trading_executor.py`, `backend_api_python/app/services/scheduler_service.py`, `backend_api_python/app/services/fast_analysis.py`

**backend_api_python/app/strategies:**
- Purpose: 策略建模与运行器抽象。
- Contains: 策略工厂、策略实现、runner 工厂与各类 runner。
- Key files: `backend_api_python/app/strategies/factory.py`, `backend_api_python/app/strategies/runners/factory.py`

**backend_api_python/app/data_sources:**
- Purpose: 多市场数据源统一访问入口与技术保护层。
- Contains: 数据源工厂、限流器、缓存、熔断器、数据管理器。
- Key files: `backend_api_python/app/data_sources/__init__.py`, `backend_api_python/app/data_sources/factory.py`

**backend_api_python/app/tasks:**
- Purpose: 插件式任务定义与统一注册入口。
- Contains: 任务注册器和任务插件模块。
- Key files: `backend_api_python/app/tasks/__init__.py`, `backend_api_python/app/tasks/nq100_universe_sync.py`

**quantdinger_vue/src:**
- Purpose: 前端应用源码。
- Contains: `views/` 页面、`api/` 接口封装、`store/` Vuex、`router/` 路由、`permission.js` 守卫。
- Key files: `quantdinger_vue/src/main.js`, `quantdinger_vue/src/permission.js`, `quantdinger_vue/src/utils/request.js`

## Key File Locations

**Entry Points:**
- `backend_api_python/run.py`: 后端进程入口，负责加载环境并创建 Flask 应用。
- `backend_api_python/app/__init__.py`: 后端应用工厂，完成初始化和启动钩子。
- `quantdinger_vue/src/main.js`: 前端入口，挂载 router/store/i18n。

**Configuration:**
- `backend_api_python/env.example`: 后端环境变量模板。
- `backend_api_python/app/config/settings.py`: 后端配置读取与默认值。
- `quantdinger_vue/vue.config.js`: 前端开发代理、构建配置与别名配置。

**Core Logic:**
- `backend_api_python/app/routes/`: API 接入边界。
- `backend_api_python/app/services/`: 业务服务与编排。
- `backend_api_python/app/strategies/`: 策略与 runner 执行逻辑。
- `backend_api_python/app/services/live_trading/`: 券商/执行侧客户端与适配。

**Testing:**
- `backend_api_python/tests/`: 后端 pytest 测试（含 `test_ibkr_order_callback.py` 等）。
- `quantdinger_vue/tests/unit/`: 前端单元测试（Jest）。

## Naming Conventions

**Files:**
- 后端以 `snake_case.py` 为主，按职责命名（如 `scheduler_service.py`, `fast_analysis.py`）。
- 前端以 `kebab-case.js`/`.vue` 与目录模块名组合（如 `fast-analysis.js`, `broker-dashboard/index.vue`）。

**Directories:**
- 后端采用职责分层目录（`routes`, `services`, `strategies`, `data_sources`, `utils`）。
- 前端采用功能分层目录（`views`, `api`, `store`, `router`, `components`）。

## Where to Add New Code

**New Feature:**
- Primary code: 后端接口放 `backend_api_python/app/routes/`，业务逻辑放 `backend_api_python/app/services/`，必要时在 `backend_api_python/app/strategies/` 扩展策略域。
- Tests: 后端新增到 `backend_api_python/tests/`；前端新增到 `quantdinger_vue/tests/unit/`。

**New Component/Module:**
- Implementation: 前端页面放 `quantdinger_vue/src/views/`；跨页面通用组件放 `quantdinger_vue/src/components/`；对应接口封装放 `quantdinger_vue/src/api/`。

**Utilities:**
- Shared helpers: 后端复用工具放 `backend_api_python/app/utils/`；前端请求/通用函数放 `quantdinger_vue/src/utils/`。

## Special Directories

**backend_api_python/migrations:**
- Purpose: 数据库结构迁移 SQL。
- Generated: No
- Committed: Yes

**backend_api_python/data:**
- Purpose: 本地数据缓存/运行时数据目录（由业务服务读写）。
- Generated: Yes（运行时可能新增内容）
- Committed: 部分模板/结构可提交，运行时产物按仓库策略处理

**quantdinger_vue/dist:**
- Purpose: 前端构建产物。
- Generated: Yes
- Committed: 当前仓库中存在该目录，按现状视为已纳入版本管理

**.planning/codebase:**
- Purpose: 代码映射与规范文档，供后续规划/执行阶段直接引用。
- Generated: Yes（由映射流程生成）
- Committed: Yes（作为工程内知识资产）

---

*Structure analysis: 2026-04-22*
