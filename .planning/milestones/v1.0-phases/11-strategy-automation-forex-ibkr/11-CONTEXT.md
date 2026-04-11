# Phase 11: Strategy automation (Forex + IBKR) - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

策略可通过配置 `market_category=Forex` + `exchange_id=ibkr-paper/ibkr-live` 触发 Forex 自动交易。后端全链路从 API → signal → pending → worker → IBKRClient 执行畅通。

**Requirement:** RUNT-03

**Key finding from code scout:** Phase 1–10 已完成 IBKRClient 的 Forex 核心能力（symbol、contract、signal mapping、TIF、market order、qty alignment、RTH、fills/positions）。`factory.py` 已有 `ibkr-paper`/`ibkr-live` → `IBKRClient` 映射，`PendingOrderWorker` 全链路已连通。Phase 11 的重点在于：
1. API 层策略配置校验（防止不合法的 exchange_id + market_category 组合）
2. 全链路 E2E 集成测试（从 Flask API 入口到 mock IBKR 执行）
3. Mock IBKR Paper smoke test（模拟完整 qualify → placeOrder → fill → position 回调流程）

</domain>

<decisions>
## Implementation Decisions

### 决策 1: 全链路 E2E 集成测试（Flask API 入口）

- **入口层级**: 从 Flask test_client 发起 API 请求，验证 API → signal → PendingOrderEnqueuer → PendingOrderWorker → factory.create_client → StatefulClientRunner.execute → IBKRClient.place_market_order 完整路径
- **Mock 范围**: mock 所有外部依赖 — ib_insync（连接、qualify、placeOrder、事件回调）+ 数据库 + 通知系统，测试完全自包含
- **信号覆盖**: 四种基本信号 — open_long / close_long / open_short / close_short
- **Stock 回归**: 包含一个 USStock 全链路回归用例，确保 Forex 改动不影响股票链路
- **测试文件**: 新建 `test_forex_ibkr_e2e.py`，独立的端到端测试文件

### 决策 2: Mock IBKR Paper Smoke Test

- **设计**: 自动化 pytest smoke test，IBKR Paper 客户端是 **mock 模拟**的（模拟 IBKR Paper 返回行为），不连接真实 IBKR 环境
- **模拟深度**: mock ib_insync 层，模拟完整的 qualify → placeOrder → fill 事件 → position 事件 → PnL 事件回调流程
- **覆盖货币对**: EURUSD（主要直盘）、GBPJPY（交叉盘）、XAGUSD（贵金属）
- **验证点**: 每个 pair 的 open + close 完整循环，验证 fills/positions/PnL 数据一致性

### 决策 3: API 层策略配置校验

- **校验时机**: 策略创建/编辑（API 保存时），不等到运行时才拦截
- **实现方式**: 在 `BaseStatefulClient` 上加 `@staticmethod` — 各子类继承实现 `validate_market_category_static(market_category)`，内部检查 `market_category in cls.supported_market_categories` 的类属性
- **路由逻辑**: factory.py 加静态函数 `validate_exchange_market_category(exchange_id, market_category)` → 根据 exchange_id 找到对应 client 类 → 调用其静态校验方法
- **API 集成**: 策略 CRUD 的 service 层（`strategy.py`）在保存时调用该校验函数，不合法组合直接返回错误
- **现有运行时校验保留**: `PendingOrderWorker` 中的实例方法 `validate_market_category` 不变，作为双重防护

### Claude's Discretion

- E2E 测试中 Flask app fixture 的具体构建方式
- mock 的粒度（patch 点选择）
- `validate_market_category_static` 的精确方法签名和类继承层次
- smoke test 中 fill/position/PnL 事件的模拟时序

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 策略配置与路由
- `backend_api_python/app/services/live_trading/factory.py` — `create_client` exchange_id → client 映射；`_create_ibkr_client` paper/live 分支
- `backend_api_python/app/services/pending_order_worker.py` — `_execute_live_order` 全链路入口；`validate_market_category` 调用点
- `backend_api_python/app/services/exchange_execution.py` — `load_strategy_configs` 读取 exchange_config/market_category
- `backend_api_python/app/services/pending_order_enqueuer.py` — `enqueue_pending_order` / `execute_exchange_order` 入队逻辑

### 策略 CRUD（API 层校验集成点）
- `backend_api_python/app/services/strategy.py` — `create_strategy` / `update_strategy`
- `backend_api_python/app/routes/strategy.py` — HTTP API 端点

### IBKR 客户端
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `IBKRClient`、`supported_market_categories`、`place_market_order`、事件回调
- `backend_api_python/app/services/live_trading/base.py` — `BaseStatefulClient.validate_market_category`、`supported_market_categories` 类属性

### Runner
- `backend_api_python/app/services/live_trading/runners/stateful_runner.py` — `StatefulClientRunner.pre_check` / `.execute`

### 现有测试（复用模式）
- `backend_api_python/tests/test_ibkr_client.py` — ib_insync mock 模式（`_make_mock_ib_insync`、`_make_client_with_mock_ib`）
- `backend_api_python/tests/test_exchange_engine.py` — `validate_market_category` 测试
- `backend_api_python/tests/test_pending_order_worker.py` — PendingOrderWorker mock 模式（Phase 4 加的）

### 项目文档
- `.planning/REQUIREMENTS.md` — RUNT-03
- `.planning/ROADMAP.md` — Phase 11 成功标准

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_make_mock_ib_insync()` / `_make_client_with_mock_ib()` — 成熟的 ib_insync mock 基础设施
- `_always_rth` autouse fixture — RTH bypass
- Phase 4 的 PendingOrderWorker 集成测试 — mock `create_client` + `records` 模式
- `IBKROrderContext` — fill 上下文结构
- Flask `app.test_client()` — 现有 route 测试已有 fixture 模式

### Established Patterns
- `factory.create_client(exchange_config, market_type=...)` — exchange_id 路由
- `BaseStatefulClient.supported_market_categories` = `frozenset` 类属性
- `PendingOrderWorker` 通过 `isinstance(client, BaseStatefulClient)` 选择 runner
- `exchange_config` 是 JSON 字符串存 DB，运行时 `json.loads` + `resolve_exchange_config` merge credentials

### Integration Points
- `factory.py` — exchange_id → client class 映射（已支持 ibkr-paper/ibkr-live）
- `strategy.py` service — 策略保存时的校验插入点
- `pending_order_worker.py` — `_execute_live_order` → `create_client` → `get_runner` → `execute`
- `signal_executor.py` — 信号产出 → enqueue，传递 `_market_category`

### Key Finding
- 从代码路径分析，Phase 1–10 的积累已使 Forex + IBKR 自动交易链路在后端**功能上完整**
- Phase 11 的价值在于：(a) 前置配置校验防错；(b) E2E 测试证明链路端到端可靠；(c) mock smoke test 验证 IBKR Paper 场景

</code_context>

<specifics>
## Specific Ideas

- E2E 测试中，IBKR Paper 的行为应模拟真实 IBKR Paper 的返回：qualify 成功（设置 conId/localSymbol）、placeOrder 返回 Trade 对象、随后触发 orderStatus → fill → position → pnl_single 事件回调序列
- 三个货币对的 smoke test：EURUSD（EUR.USD, conId=12087792）、GBPJPY（GBP.JPY）、XAGUSD（XAGUSD）— 每个执行 open_long + close_long 完整循环
- `validate_exchange_market_category` 应覆盖所有 stateful clients（IBKR、MT5、usmart、eastmoney），非 stateful 的 crypto 交易所可以沿用现有 `_EXCHANGE_MARKET_RULES` 逻辑或跳过

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 11-strategy-automation-forex-ibkr*
*Context gathered: 2026-04-11*
