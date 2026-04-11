# Phase 4: Market category & worker gate - Context

**Gathered:** 2026-04-09
**Status:** Ready for planning

<domain>
## Phase Boundary

The runner and pending-order pipeline accept Forex as a first-class market category end-to-end. `IBKRClient.supported_market_categories` includes `"Forex"`. `PendingOrderWorker.validate_market_category` allows Forex alongside existing categories. A Forex-marked signal is not rejected solely for category when other validations pass.

**Requirement:** CONT-04

</domain>

<decisions>
## Implementation Decisions

### supported_market_categories 修改
- `IBKRClient.supported_market_categories`（client.py 行 102）从 `frozenset({"USStock", "HShare"})` 改为 `frozenset({"USStock", "HShare", "Forex"})`
- 只改这一行，`validate_market_category` 是基类方法（base.py 行 148-157），自动对 `"Forex"` 返回 `(True, "")`
- **不改** `PendingOrderWorker` 代码——它已经调用 `client.validate_market_category(market_category)`（pending_order_worker.py 行 358），只要 frozenset 包含 Forex 就自动通过

### 现有测试翻转
- `test_exchange_engine.py::test_ibkr_forex_rejected`（行 94-96）**翻转**为 `test_ibkr_forex_ok`
  - 改方法名：`test_ibkr_forex_rejected` → `test_ibkr_forex_ok`
  - 改断言：`assert not ok` → `assert ok`
  - 删掉 `msg` 变量（成功时 msg 为空）
- `test_exchange_engine.py::test_ibkr_supported_categories`（行 66-67）更新断言匹配新的 frozenset

### PendingOrderWorker 集成测试
- **新增完整集成测试**：mock PendingOrderWorker 的 **`_execute_live_order`** 链路（仓库中无 `_process_one_live_order`）
- 验证 Forex 信号不被 category 门拒绝
- 验证非法 category（如 Crypto）仍被正确拒绝
- 需要 mock：`create_client`（返回一个带正确 `supported_market_categories` 的 IBKRClient mock）、`records.mark_order_failed`、通知系统等

### MT5 回归
- 不额外加 MT5 专用回归测试——全量测试套件已覆盖 `test_mt5_forex_ok` 和 `test_mt5_supported_categories`

### Claude's Discretion
- PendingOrderWorker 集成测试的具体 mock 实现方式
- 测试是放在 `test_exchange_engine.py` 还是新建 `test_pending_order_worker.py`
- PendingOrderWorker 集成测试中需要 mock 多少个依赖

</decisions>

<specifics>
## Specific Ideas

### 实施约束（用户明确要求）
- **每个 task 必须有明确的用例及其规格**
- **全量测试套件必须作为每个 task 的 verify 步骤的一部分**
- TDD 方法

### 测试用例全景（6 个用例 + 1 个回归）

**UC-1: supported_market_categories 包含 Forex**
- 前置：IBKRClient 类
- 断言：`"Forex" in IBKRClient.supported_market_categories`

**UC-2: validate_market_category("Forex") 返回 True**
- 前置：IBKRClient 实例
- 断言：`validate_market_category("Forex")` 返回 `(True, "")`

**UC-3: validate_market_category("Crypto") 仍被拒绝**
- 前置：IBKRClient 实例
- 断言：`validate_market_category("Crypto")` 返回 `(False, msg)`，msg 包含 "Crypto"

**UC-4: PendingOrderWorker Forex 信号不被 category 门拒绝**
- 前置：mock PendingOrderWorker 处理一个 market_category="Forex" 的订单
- 操作：`_execute_live_order` 路径执行
- 断言：不因 category 被拒（`mark_order_failed` 不因 `cat_err` 被调用）

**UC-5: PendingOrderWorker 非法 category 仍被拒绝**
- 前置：mock PendingOrderWorker 处理一个 market_category="Crypto" 的订单
- 断言：因 category 被拒（`mark_order_failed` 被调用，错误含 "Crypto"）

**UC-6: test_ibkr_supported_categories 断言更新**
- 前置：test_exchange_engine.py
- 断言：`IBKRClient.supported_market_categories == frozenset({"USStock", "HShare", "Forex"})`

**REGR-01: 全量测试套件回归**
- 操作：运行全部 ~849 个测试
- 断言：全部通过（包括 MT5 Forex 测试、USStock/HShare 回归）

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 核心实现文件
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `supported_market_categories`（行 102）
- `backend_api_python/app/services/live_trading/base.py` — `BaseStatefulClient.validate_market_category`（行 148-157），`supported_market_categories` 类属性（行 146）
- `backend_api_python/app/services/pending_order_worker.py` — `_execute_live_order` 内的 `validate_market_category` 调用（约 357-371 行，以源码为准）

### 测试文件
- `backend_api_python/tests/test_exchange_engine.py` — `TestExchangeEngineBasics::test_ibkr_supported_categories`（行 66-67）、`TestValidateMarketCategory::test_ibkr_forex_rejected`（行 94-96）、以及 USStock/HShare/Crypto/MT5 测试
- `backend_api_python/tests/test_dedup_retry_on_failure.py` — PendingOrderWorker 唯一现有测试（只测试 `_mark_failed`）

### Runner 文件（只传递 market_category，不做独立检查）
- `backend_api_python/app/services/live_trading/runners/stateful_runner.py` — `market_category` 字段传递逻辑
- `backend_api_python/app/services/live_trading/runners/signal_runner.py` — `market_category` 日志

### 先前 Phase Context
- `.planning/phases/01-forex-symbol-normalization/01-CONTEXT.md` — symbol 格式
- `.planning/phases/02-forex-contract-creation-idealpro/02-CONTEXT.md` — Forex(pair=ib_symbol) 构造
- `.planning/phases/03-contract-qualification/03-CONTEXT.md` — qualify + _validate_qualified_contract

### 项目文档
- `.planning/REQUIREMENTS.md` — CONT-04
- `.planning/ROADMAP.md` — Phase 4 成功标准

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BaseStatefulClient.validate_market_category`（base.py:148-157）：已有的通用验证方法，只检查 `market_category in self.supported_market_categories`。加 "Forex" 到 frozenset 就自动工作
- `TestValidateMarketCategory`（test_exchange_engine.py:73-105）：已有完整的 accept/reject 测试类，可复用模式
- `TestMarkFailedClearsDedupCache`（test_dedup_retry_on_failure.py）：PendingOrderWorker mock 模式参考

### Established Patterns
- frozenset 类属性声明模式（各 client 统一用 `supported_market_categories = frozenset({...})`）
- `validate_market_category` 返回 `(bool, str)` 元组
- PendingOrderWorker 用 `isinstance(client, BaseStatefulClient)` 判断是否做 category 检查

### Integration Points
- `client.py:102` — 唯一需要修改的生产代码
- `test_exchange_engine.py:67` — frozenset 断言值
- `test_exchange_engine.py:94-96` — 翻转测试
- 新的 PendingOrderWorker 集成测试需要 mock `create_client` + `records` + 通知

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 04-market-category-worker-gate*
*Context gathered: 2026-04-09*
