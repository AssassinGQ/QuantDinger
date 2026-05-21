# Phase 18: E2E & integration testing - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Phase Boundary

End-to-end and integration test coverage for metals trading, limit orders, qualify cache, and frontend HTTP strategy operations. Covers TRADE-05 (metals E2E), TRADE-06 (limit order E2E), TEST-02 (frontend HTTP E2E). Scope includes shared test infrastructure improvements (fixture extraction, Flask app factory).

</domain>

<decisions>
## Implementation Decisions

### 后端 E2E 补全范围
- **全面覆盖**: qualify cache + cancel 场景 + error path + USStock/HShare 交叉验证
- **Qualify cache E2E**（Phase 13 延期需求，详细覆盖）:
  - Cache hit 不重复调用 `qualifyContractsAsync`
  - Cache miss 正常 qualify
  - TTL 过期后重新 qualify
  - 不同 market_type TTL 独立（Forex vs USStock vs Metals）
  - IBKR 重连不清缓存
  - Invalidation（qualify 失败/异常后缓存项被移除）
- **限价单 cancel 场景**:
  - DAY 过期取消 + `filled=0` → mark_order_failed，无 position
  - DAY 过期取消 + `filled>0` → 写入 filled portion 的 position
- **Error path E2E**:
  - Qualify 失败（Error 200 No security definition）
  - 合约无效（post-qualify validation 拒绝）
  - 限价 `price <= 0`（reject，不 enqueue）
- **USStock/HShare 交叉验证**: 两个市场都加 market + limit E2E full chain（mock IBKR）

### 文件组织
- **拆分新文件**: 不再全堆在 `test_forex_ibkr_e2e.py`
- 按主题拆分: qualify cache E2E、cancel/error E2E、USStock/HShare cross-market E2E 各自独立文件
- 现有 `test_forex_ibkr_e2e.py` 保持不变（已有的 Forex/Metals E2E 不动）

### 前端 HTTP E2E
- **工具**: pytest Flask `test_client()` — 不用浏览器，不需要 Playwright/Cypress
- **后端**: 真实 Flask app + 真实路由/blueprint，mock DB（psycopg2）、ib_insync、邮件通知等外部依赖
- **覆盖范围**: 策略完整 CRUD + 多币种对批量创建
  - `POST /api/strategies/create` — Forex+IBKR 策略创建 round-trip
  - `PUT` 策略编辑 round-trip
  - `DELETE` 策略删除
  - 批量创建（多 symbol）
- **Vue 组件单元测试**: Jest 补几个 wizard 相关组件测试（不需要浏览器）
- **CI/CD 约束**: 不引入复杂浏览器依赖

### 测试基础设施
- **共享 Flask app fixture**: 加到 `conftest.py`，所有 E2E 测试复用（真实 Flask app factory + mock DB）
- **Mock helper 提取**: 从 `test_ibkr_forex_paper_smoke.py` 和 `test_forex_ibkr_e2e.py` 提取共用 helper 到 `tests/helpers/` 模块:
  - `_FakeEvent` / `_wire_ib_events` / `_fire_callbacks_after_fill`
  - `_make_qualify_for_pair` / `_make_ibkr_client_for_e2e`
  - `patched_records` context manager
- 现有测试文件更新为 import 共享 helper（不改变测试逻辑）

### 验收标准
- **TRADE-05**: Metals E2E（mock IBKR）exercises qualify → order → callback end-to-end — 至少一个 pass
- **TRADE-06**: Limit order E2E 覆盖 normal fill + partial fill + cancel — 至少一个 pass
- **TEST-02**: 前端 HTTP E2E（Flask test_client）策略 CRUD round-trip — 至少一个 pass
- **Qualify cache E2E**: hit/miss/TTL/invalidation/重连 全覆盖
- **回归守护**: 全套 1023+ 现有后端测试 green（**严格**: 任何现有测试失败即不算完成）
- **Vue 单元测试**: 至少几个 wizard 组件 Jest 测试 pass

### Claude's Discretion
- 具体文件命名和测试类组织
- Mock helper 提取后的模块结构（`tests/helpers/ibkr_mocks.py` vs 多文件）
- Flask app fixture 的具体实现（`app_factory` vs `create_test_app`）
- USStock/HShare E2E 的具体场景选择（open/close cycle vs 单向 + 检查）
- Vue Jest 测试的具体组件选择和测试深度
- Error path E2E 的具体错误码和消息断言

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 现有 E2E / Smoke 测试（模式参考）
- `backend_api_python/tests/test_forex_ibkr_e2e.py` — 主要 E2E 套件：Forex/Metals market+limit chain, partial fill, automation TIF。Flask app 创建模式、mock 策略、patched_records 模式
- `backend_api_python/tests/test_ibkr_forex_paper_smoke.py` — Smoke 套件：`_FakeEvent`、`_wire_ib_events`、`_make_qualify_for_pair`、`_fire_callbacks_after_fill` helper；EURUSD/GBPJPY/XAGUSD cycle
- `backend_api_python/tests/test_ibkr_client.py` — `_make_mock_ib_insync()`、`_make_client_with_mock_ib()`、`_make_trade_mock()` IBKR mock 核心

### Qualify cache 实现
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_qualify_contract_async`（缓存逻辑）、`_qualify_ttl_seconds`（per-market TTL）、`_on_connected`/`_on_disconnected`（重连不清缓存）
- `.planning/phases/13-qualify-result-caching-e2e-prefix-fix/13-CONTEXT.md` — Phase 13 缓存决策 + 延期 E2E 需求

### 限价单 + 部分成交
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `place_limit_order`、`_on_order_status`（PartiallyFilled/Cancelled 处理）
- `.planning/phases/17-forex-limit-orders-automation/17-CONTEXT.md` — Phase 17 限价单决策（DAY TIF、minTick snap、cumulative overwrite）

### 前端 API / Wizard
- `quantdinger_vue/src/api/strategy.js` — `createStrategy` → `POST /api/strategies/create`
- `quantdinger_vue/src/views/trading-assistant/index.vue` — 策略创建 wizard UI
- `backend_api_python/app/routes/__init__.py` — `register_routes` 中 blueprint 注册
- `backend_api_python/app/routes/strategy.py` — 策略 CRUD 路由

### 共享测试基础
- `backend_api_python/tests/conftest.py` — `make_db_ctx`、`reset_signal_deduplicator`
- `quantdinger_vue/jest.config.js` — Jest 配置
- `quantdinger_vue/tests/unit/frnt-01-forex-ibkr-options.spec.js` — 唯一的 Vue 测试（参考模式）

### 需求
- `.planning/REQUIREMENTS.md` — TRADE-05（Metals E2E）、TRADE-06（Limit E2E）、TEST-02（前端 HTTP E2E）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `test_forex_ibkr_e2e.py`: Flask app 创建 + `login_required` stub + `_mock_db` + `patched_records` — 可提取为共享 fixture
- `test_ibkr_forex_paper_smoke.py`: `_FakeEvent`、`_wire_ib_events`、`_make_qualify_for_pair`（CASH vs CMDTY+SMART）、`_fire_callbacks_after_fill`（orderStatus→execDetails→position→pnlSingle）— 可提取到 `tests/helpers/`
- `test_ibkr_client.py`: `_make_mock_ib_insync()` 创建完整 mock ib_insync 模块 — 可提取复用
- `conftest.py`: `make_db_ctx` — 通用 mock DB context manager

### Established Patterns
- E2E 通过 `PendingOrderWorker._execute_live_order` 驱动 full chain（不通过 HTTP）
- Flask E2E 通过 `Flask(__name__)` + `register_blueprint` 创建最小 app
- IBKR mock 通过 `MagicMock` + `patch` 隔离，`qualifyContractsAsync` 返回预设 Contract
- 测试命名: `test_uc_sa_e2e_*`（strategy automation E2E）、`test_e2e_*`（E2E 链路）

### Integration Points
- 共享 fixture 需要 `conftest.py` 级别集成（所有测试自动可用）
- Mock helper 提取需要更新现有 import（`test_ibkr_forex_paper_smoke.py`、`test_forex_ibkr_e2e.py`）
- 前端 HTTP E2E 需要 Flask test_client 调用 `strategy.py` 路由
- Vue Jest 测试需要 `@vue/test-utils` mount wizard 组件

</code_context>

<specifics>
## Specific Ideas

- Phase 13 CONTEXT 明确延期: "Phase 18 E2E 覆盖 qualify cache 场景（hit/miss/invalidation）" — 这是已承诺的需求
- 用户不希望 CI/CD 引入复杂浏览器依赖 — 所以前端 E2E 用 pytest Flask test_client 而非 Playwright
- 后端全面覆盖（cache + cancel + error + cross-market）— 用户选择最完整的方案
- 文件拆分而非继续往 test_forex_ibkr_e2e.py 堆 — 按主题独立
- Mock helper 提取到共享模块 — 新旧测试都能用，减少重复代码

</specifics>

<deferred>
## Deferred Ideas

- Playwright 浏览器 E2E（真实 UI 测试）— 如果后续需要可加，当前 pytest HTTP round-trip 足够
- Docker-compose 黑盒集成测试（真实 DB + 真实 Flask + 真实 worker）— 超出当前范围
- 前端 strategy 编辑界面的 snapshot 测试 — 留给后续
- Coverage 数字目标（如 80% 行覆盖）— 当前以场景覆盖为准，不设数字门槛

</deferred>

---

*Phase: 18-e2e-integration-testing*
*Context gathered: 2026-04-12*
