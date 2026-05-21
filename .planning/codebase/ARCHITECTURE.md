# 架构分析

**分析日期:** 2026-04-22

## 模式概览

**整体模式:** 前后端分离 + 分层服务架构（Vue SPA + Flask API + 策略线程执行器 + 调度器）

**关键特征:**
- 前端采用 Vue 2 单页应用，路由守卫与动态路由控制权限，业务请求统一走 `axios` 拦截器（`quantdinger_vue/src/main.js`、`quantdinger_vue/src/permission.js`、`quantdinger_vue/src/utils/request.js`）。
- 后端采用 Flask Application Factory，启动期统一完成路由注册、数据库初始化、工作线程启动与任务注册（`backend_api_python/app/__init__.py`、`backend_api_python/app/routes/__init__.py`）。
- 交易运行面使用“路由/服务 + 运行时执行器”双轨：CRUD 与控制接口在 `routes`，实时循环在 `services/trading_executor.py` 与 `strategies/runners/*`。

## 分层设计

**接入层（HTTP/路由层）:**
- 目的: 接收请求、做参数与权限边界、返回统一 JSON。
- 位置: `backend_api_python/app/routes/`。
- 包含: `strategy.py`、`ibkr.py`、`auth.py`、`scheduler.py`、`market.py` 等 21 个蓝图模块。
- 依赖: `app/services/*`、`app/utils/auth.py`、`app/utils/db.py`。
- 被谁使用: 前端 `quantdinger_vue/src/api/*.js`，以及外部调用方。

**应用服务层（业务编排层）:**
- 目的: 承载业务规则、交易编排、数据拉取、权限/安全/邮件等领域逻辑。
- 位置: `backend_api_python/app/services/`。
- 包含: 策略服务 `strategy.py`、执行器 `trading_executor.py`、调度服务 `scheduler_service.py`、IBKR 客户端 `live_trading/ibkr_trading/client.py`、用户服务 `user_service.py`。
- 依赖: 数据源 `app/data_sources/*`、策略运行器 `app/strategies/*`、数据库访问 `app/utils/db.py`。
- 被谁使用: `app/routes/*`、启动钩子 `app/__init__.py`、任务插件 `app/tasks/*`。

**策略运行层（Runtime/Execution）:**
- 目的: 将策略配置转成可运行循环，并驱动信号产出与执行。
- 位置: `backend_api_python/app/strategies/` 与 `backend_api_python/app/services/trading_executor.py`。
- 包含: 策略工厂 `strategies/factory.py`、Runner 工厂 `strategies/runners/factory.py`、不同策略与 Runner 实现。
- 依赖: `DataHandler`、`SignalExecutor`、`PriceFetcher`、`load_strategy`。
- 被谁使用: `TradingExecutor.start_strategy()`、启动恢复流程 `restore_running_strategies()`。

**基础设施层（DB/认证/日志/调度）:**
- 目的: 提供数据库连接、JWT 认证、日志、定时任务与插件任务注册。
- 位置: `backend_api_python/app/utils/`、`backend_api_python/app/tasks/`、`backend_api_python/app/services/scheduler_service.py`。
- 包含: `utils/db.py`（统一 PostgreSQL 接口）、`utils/auth.py`（JWT + 装饰器）、`tasks/__init__.py`（插件任务注册入口）。
- 依赖: PostgreSQL、APScheduler、环境变量配置。
- 被谁使用: 全部后端业务模块。

**前端状态与网关层:**
- 目的: 管理 token/用户态、动态路由、API 网关与错误处理。
- 位置: `quantdinger_vue/src/store/`、`quantdinger_vue/src/router/`、`quantdinger_vue/src/utils/request.js`。
- 包含: `store/modules/user.js`、`store/modules/async-router.js`、`router/index.js`、`permission.js`。
- 依赖: `src/api/*.js` 的接口封装与后端 `/api/*`。
- 被谁使用: `src/views/*` 页面组件。

## 关键调用链

**调用链 1：策略启动（前端 -> 后端 -> 执行线程）**
1. 前端页面触发 `startStrategy(id)`，发送 `POST /api/strategies/start`（`quantdinger_vue/src/api/strategy.js`）。
2. `strategy_bp.start_strategy` 做用户归属校验与状态更新（`backend_api_python/app/routes/strategy.py`）。
3. 路由调用 `get_trading_executor().start_strategy(strategy_id)`（`backend_api_python/app/__init__.py`、`backend_api_python/app/services/trading_executor.py`）。
4. 执行器加载策略配置 `load_and_create`，再通过 `create_runner` 选择运行器并进入 `runner.run(...)`（`backend_api_python/app/strategies/factory.py`、`backend_api_python/app/strategies/runners/factory.py`）。

**调用链 2：IBKR 下单与回调落库（前端 -> API -> 客户端事件驱动）**
1. 前端调用 `src/api/ibkr.js`（页面主要位于 `quantdinger_vue/src/views/broker-dashboard/index.vue`）访问 `/api/ibkr/order`。
2. `ibkr_bp.place_order` 解析 broker 模式，委派 `IBKRClient.place_market_order/place_limit_order`（`backend_api_python/app/routes/ibkr.py`）。
3. `IBKRClient` 通过 `TaskQueue` 把 ib_insync 调用提交到专用事件循环线程，避免阻塞 Flask/策略线程（`backend_api_python/app/services/live_trading/ibkr_trading/client.py`）。
4. 回报事件 `_on_order_status` 分发到 `_handle_fill/_handle_reject`，再调用 `app.services.live_trading.records` 更新订单、成交和持仓（同文件 + `backend_api_python/app/services/live_trading/records.py`）。
5. 测试覆盖围绕该回调与落库路径展开（`backend_api_python/tests/test_ibkr_order_callback.py`）。

**调用链 3：认证与动态权限路由（登录态闭环）**
1. 前端 `permission.js` 在路由切换时检查 `ACCESS_TOKEN`，必要时触发 `store.dispatch('GetInfo')`（`quantdinger_vue/src/permission.js`）。
2. 请求层自动注入 `Authorization` 与语言头，统一处理 401/403（`quantdinger_vue/src/utils/request.js`）。
3. 后端 `auth.py` 登录后签发 JWT，JWT 由 `utils/auth.py` 校验并注入 `g.user_id/g.user_role`（`backend_api_python/app/routes/auth.py`、`backend_api_python/app/utils/auth.py`）。
4. 前端根据角色生成并注入动态路由（`quantdinger_vue/src/store/modules/async-router.js`、`quantdinger_vue/src/router/generator-routers.js`）。

**调用链 4：定时同步（启动钩子 -> 调度服务 -> 插件任务）**
1. 应用启动时执行 `register_all_tasks()`（`backend_api_python/app/__init__.py`、`backend_api_python/app/tasks/__init__.py`）。
2. 调度能力统一收口在 `scheduler_service.py`，包括 `register_scheduled_job/start_task/stop_task`（`backend_api_python/app/services/scheduler_service.py`）。
3. 手动触发路径通过 `POST /api/scheduler/kline-sync` -> `run_kline_sync_once()`，周期触发由 APScheduler job 驱动（`backend_api_python/app/routes/scheduler.py`）。

## 状态管理

**前端状态:**
- 全局状态集中在 Vuex（`quantdinger_vue/src/store/index.js`）。
- 用户态与 token 持久化在 `store`（localStorage）插件（`quantdinger_vue/src/store/modules/user.js`）。
- 动态路由状态在 `store/modules/async-router.js`，路由实例通过 `resetRouter()` 重建（`quantdinger_vue/src/router/index.js`）。

**后端状态:**
- 进程内单例状态：`_trading_executor`、`_pending_order_worker`（`backend_api_python/app/__init__.py`）。
- 运行中策略线程表：`TradingExecutor.running_strategies`（`backend_api_python/app/services/trading_executor.py`）。
- 交易与用户状态持久化在 PostgreSQL，通过 `get_db_connection` 访问（`backend_api_python/app/utils/db.py`）。

## 关键抽象与边界

**Blueprint 作为 API 模块边界:**
- 以业务域分拆蓝图，如策略、IBKR、调度、认证、市场（`backend_api_python/app/routes/__init__.py`）。
- 边界规则: 路由层只做入参/鉴权/编排，不直接持有复杂运行时状态。

**Service 作为领域逻辑边界:**
- `routes/*` 通过 service 函数/类调用核心逻辑，避免业务散落到控制器（`backend_api_python/app/routes/strategy.py` -> `app/services/strategy.py` 等）。

**Client 作为外部系统边界:**
- IBKR/MT5/交易所接入均位于 `app/services/live_trading/*`，对上层暴露统一动作（连接、下单、查询、回调处理）。

## 入口点

**后端启动入口:**
- 进程入口: `backend_api_python/run.py`（创建 `app = create_app()` 并提供本地运行入口）。
- 应用工厂: `backend_api_python/app/__init__.py:create_app`（初始化 CORS、DB、路由、启动钩子）。

**前端启动入口:**
- SPA 入口: `quantdinger_vue/src/main.js`（挂载 router/store/i18n，初始化权限守卫）。
- 路由入口: `quantdinger_vue/src/router/index.js`。

## 错误处理

**策略:**
- 路由层普遍采用 `try/except` 返回 `{code,msg,data}` 结构化响应（示例：`backend_api_python/app/routes/strategy.py`、`backend_api_python/app/routes/scheduler.py`）。
- 运行时线程与回调层记录异常堆栈但保持主流程存活（`backend_api_python/app/services/trading_executor.py`、`backend_api_python/app/services/live_trading/ibkr_trading/client.py`）。

**模式:**
- 业务失败多返回 HTTP 200 + `code=0`（前端兼容），认证失败返回 401/403（`auth.py`、`utils/request.js`）。
- 前端响应拦截器统一处理 401，清理本地凭证并跳转登录页（`quantdinger_vue/src/utils/request.js`）。

## 横切关注点

**日志:**
- 后端统一使用 `get_logger`，在登录流程、调度、交易回调路径均有细粒度日志（`backend_api_python/app/utils/logger.py`、各 route/service 文件）。

**认证鉴权:**
- JWT + `login_required` 装饰器是主认证机制（`backend_api_python/app/utils/auth.py`）。
- 前端路由守卫与动态路由共同承担页面级访问控制（`quantdinger_vue/src/permission.js`）。

**数据访问:**
- 统一经 `get_db_connection()` 对接 PostgreSQL，作为服务层默认访问接口（`backend_api_python/app/utils/db.py`）。

---

*架构分析完成于 2026-04-22*
# Architecture

**Analysis Date:** 2026-04-22

## Pattern Overview

**Overall:** 前后端分离 + Flask 蓝图路由聚合 + Service/Strategy 分层 + 线程化策略执行器

**Key Characteristics:**
- Web 入口采用 Flask Application Factory，应用启动时统一完成 DB 初始化、路由注册与后台任务挂载，入口在 `backend_api_python/app/__init__.py` 与 `backend_api_python/run.py`。
- API 层以蓝图拆分业务域，聚合注册由 `backend_api_python/app/routes/__init__.py` 负责，前端经 `/api/*` 访问，开发代理定义在 `quantdinger_vue/vue.config.js`。
- 交易执行采用“数据库状态 + 内存线程池”双层模型：路由更新策略状态后调用执行器线程启动/停止，核心在 `backend_api_python/app/routes/strategy.py` 与 `backend_api_python/app/services/trading_executor.py`。

## Layers

**前端展示与状态层（Vue 2）:**
- Purpose: 页面渲染、路由守卫、权限控制、用户态缓存与 API 调用编排。
- Location: `quantdinger_vue/src/`
- Contains: `views` 页面、`router` 路由、`store` 状态、`api` 请求封装、`utils/request.js` axios 拦截器。
- Depends on: `backend_api_python` 的 `/api/*` 接口、浏览器本地存储 token。
- Used by: 最终用户浏览器访问。

**API 接入层（Flask Route/Blueprint）:**
- Purpose: 解析 HTTP 请求、鉴权、参数校验、调用服务层并返回统一 JSON。
- Location: `backend_api_python/app/routes/`
- Contains: 业务蓝图（如 `strategy.py`、`ibkr.py`、`fast_analysis.py`、`scheduler.py`）。
- Depends on: `app/services/*`、`app/utils/auth.py`、`app/utils/db.py`。
- Used by: 前端 axios 与外部 API 调用者。

**业务服务层（Service）:**
- Purpose: 封装交易、回测、数据采集、调度、AI 分析等核心业务逻辑。
- Location: `backend_api_python/app/services/`
- Contains: `strategy.py`、`trading_executor.py`、`scheduler_service.py`、`fast_analysis.py`、`market_data_collector.py`、`live_trading/*`。
- Depends on: 数据源层、策略层、数据库工具层、LLM 服务层。
- Used by: 路由层与启动阶段钩子。

**策略域层（Strategy/Runner）:**
- Purpose: 按策略类型实例化策略对象并绑定对应 runner，驱动交易循环。
- Location: `backend_api_python/app/strategies/`
- Contains: `factory.py`（策略工厂）、`runners/factory.py`（runner 工厂）、各类策略/runner 实现。
- Depends on: `services/data_handler.py`、`services/signal_executor.py`、数据源与交易客户端。
- Used by: `TradingExecutor` 线程循环。

**基础设施层（DataSource/DB/Auth/Scheduler）:**
- Purpose: 提供跨模块复用的技术能力（数据抓取、缓存、限流、JWT、任务调度）。
- Location: `backend_api_python/app/data_sources/`、`backend_api_python/app/utils/`、`backend_api_python/app/tasks/`
- Contains: `DataSourceFactory`、JWT 鉴权装饰器、APScheduler 任务注册与插件任务入口。
- Depends on: 第三方数据/API 客户端、PostgreSQL。
- Used by: 服务层与路由层全局复用。

## Data Flow

**Flow 1: 前端鉴权与动态路由初始化**
1. 前端启动 `quantdinger_vue/src/main.js`，加载 `quantdinger_vue/src/permission.js` 路由守卫。
2. 守卫从 `store` 读取 token（`quantdinger_vue/src/store/modules/user.js`），缺失则重定向登录。
3. 请求经 `quantdinger_vue/src/utils/request.js` 注入 `Authorization: Bearer`。
4. 后端 `login_required` 在 `backend_api_python/app/utils/auth.py` 验证 JWT 并写入 `flask.g.user_id`。
5. 用户信息返回后前端生成可访问路由并动态 `addRoute`。

**Flow 2: 策略启动链路（核心交易链）**
1. 前端调用策略启动接口（`/api/...`），路由入口在 `backend_api_python/app/routes/strategy.py`。
2. 路由校验策略归属后，先更新策略状态，再调用 `get_trading_executor().start_strategy()`。
3. `TradingExecutor` 在 `backend_api_python/app/services/trading_executor.py` 创建线程并进入 `_run_strategy_loop`。
4. 循环内通过 `app/strategies/factory.py` 的 `load_and_create()` 加载策略配置，再经 `app/strategies/runners/factory.py` 选择 runner。
5. runner 使用 `DataHandler` 与 `SignalExecutor` 推进行情处理和信号执行，状态持续写回数据库。

**Flow 3: Fast Analysis 调用链**
1. 前端调用 `quantdinger_vue/src/api/fast-analysis.js` 对应接口（蓝图 `backend_api_python/app/routes/fast_analysis.py`）。
2. 路由层鉴权后调用 `get_fast_analysis_service().analyze()`。
3. 服务层 `backend_api_python/app/services/fast_analysis.py` 通过 `market_data_collector` 汇总行情/指标/宏观/新闻。
4. 同一服务内构建强约束 prompt，调用 `LLMService` 获取结构化分析结果。
5. 结果经约束校验后写入分析记忆（`analysis_memory`），返回前端展示。

**Flow 4: 启动阶段后台任务链**
1. `create_app()` 在 `backend_api_python/app/__init__.py` 完成基础初始化后进入 startup hooks。
2. 依次启动挂单 worker、组合监控、策略恢复。
3. 调用 `app/tasks/__init__.py` 的 `register_all_tasks()` 注册插件任务。
4. 插件任务统一落到 `backend_api_python/app/services/scheduler_service.py` 的 `register_scheduled_job()`。

**State Management:**
- 前端状态以 Vuex 为中心（`quantdinger_vue/src/store/index.js`），持久化依赖 `store` 本地存储。
- 后端状态以 PostgreSQL 为主，线程内运行态存在 `TradingExecutor.running_strategies` 内存映射。

## Key Abstractions

**应用工厂（Application Factory）:**
- Purpose: 统一启动顺序与全局依赖注入。
- Examples: `backend_api_python/app/__init__.py`, `backend_api_python/run.py`
- Pattern: `create_app()` 返回 Flask 实例 + 启动后钩子。

**蓝图路由聚合器（Blueprint Aggregator）:**
- Purpose: 模块化 API 边界并集中注册 URL 前缀。
- Examples: `backend_api_python/app/routes/__init__.py`, `backend_api_python/app/routes/ibkr.py`, `backend_api_python/app/routes/strategy.py`
- Pattern: 每个业务域独立 blueprint，再由 register 函数统一挂载。

**策略工厂 + Runner 工厂（Factory + Polymorphic Runner）:**
- Purpose: 用配置驱动策略与执行逻辑选择，避免路由层硬编码分支。
- Examples: `backend_api_python/app/strategies/factory.py`, `backend_api_python/app/strategies/runners/factory.py`
- Pattern: `cs_type` 映射到具体策略类与 runner 类。

**数据源工厂（DataSourceFactory）:**
- Purpose: 统一多市场数据访问能力并隔离上层业务与底层数据源。
- Examples: `backend_api_python/app/data_sources/__init__.py`, `backend_api_python/app/services/scheduler_service.py`, `backend_api_python/app/routes/strategy.py`
- Pattern: 工厂入口 + 缓存/限流/熔断器组合。

## Entry Points

**后端服务入口:**
- Location: `backend_api_python/run.py`
- Triggers: `python run.py` 或 WSGI 进程加载 `run:app`
- Responsibilities: 加载环境、创建 Flask 应用、启动 HTTP 服务。

**后端应用构建入口:**
- Location: `backend_api_python/app/__init__.py`
- Triggers: `run.py` 调用 `create_app()`
- Responsibilities: DB 初始化、管理员确保、demo 拦截、蓝图注册、后台任务启动。

**前端入口:**
- Location: `quantdinger_vue/src/main.js`
- Triggers: `npm run serve/build` 后浏览器加载
- Responsibilities: 挂载 Vue 根实例、注入 router/store/i18n、初始化全局权限与请求层。

## Error Handling

**Strategy:** 路由层兜底异常捕获 + 结构化 JSON 返回 + 统一日志记录

**Patterns:**
- API 层普遍使用 `try/except` 并返回 `{code,msg,data}`，如 `backend_api_python/app/routes/strategy.py` 与 `backend_api_python/app/routes/fast_analysis.py`。
- 服务层关键路径记录 `logger.error(..., exc_info=True)`，避免异常直接中断主服务线程，如 `backend_api_python/app/services/fast_analysis.py`、`backend_api_python/app/services/trading_executor.py`。

## Cross-Cutting Concerns

**Logging:** 通过 `app/utils/logger.py` 提供统一 logger，路由和服务均调用 `get_logger(__name__)`。
**Validation:** 路由层先做必要参数验证（如 market/symbol/strategy_id），鉴权由 `login_required` 装饰器统一执行。
**Authentication:** JWT 生成与验证在 `backend_api_python/app/utils/auth.py`，基于 Bearer Token 写入 `flask.g`。

---

*Architecture analysis: 2026-04-22*
