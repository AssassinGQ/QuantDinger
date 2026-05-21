# Phase 13: Qualify result caching + E2E prefix fix - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Reduce redundant IB qualify API traffic by caching `qualifyContractsAsync` results with configurable TTL. Fix E2E test API prefix drift so test routing matches production. No new trading capabilities or E2E test cases — those belong in later phases.

</domain>

<decisions>
## Implementation Decisions

### 缓存策略与 TTL
- TTL 中等时长（5-15 分钟），具体默认值 Claude 决定
- TTL 按 market 分开可配：Forex / USStock / HShare 各自独立 TTL
- Cache key 使用 `symbol + market_type` 组合
- 内存缓存（IBKRClient 实例级别），不需要外部缓存
- 失败模式安全：过期缓存数据最多导致 IBKR 拒单，不会静默执行错误交易

### 缓存失效触发
- IBKR 重连时**不清除**缓存 — conId 是全局统一的，不随 gateway 变化，TTL 自然过期足够
- 特定错误码（如 qualify 失败、合约无效）**清除对应 symbol** 的缓存条目
- 不需要手动清缓存的 API 或端点

### E2E prefix 修复
- 中等范围修复：修正 `test_forex_ibkr_e2e.py` 的 `url_prefix` 从 `/api/strategy` 改为 `/api`（匹配生产 `register_routes`），同时重构 Flask test app 创建逻辑使其更接近生产 `create_app`
- 修改后运行全部 E2E 测试确认不破坏现有用例
- 不在 Phase 13 新增 E2E 测试用例 — 新用例留给 Phase 18

### Claude's Discretion
- TTL 具体默认值（5-15 分钟范围内）
- 缓存实现方式（dict + timestamp、functools.lru_cache 变体、或自定义类）
- 需要触发缓存清除的具体 IBKR 错误码列表
- Flask test app 重构的具体方式（复用 create_app 的哪些部分）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Qualify 逻辑
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_qualify_contract_async` 方法（4 处调用点）、`_on_connected`/`_on_disconnected` 重连回调、`_create_contract` 合约创建
- `backend_api_python/tests/test_ibkr_client.py` — `TestQualifyContractForex` 测试类，qualify 行为的现有测试覆盖

### E2E 测试
- `backend_api_python/tests/test_forex_ibkr_e2e.py` — 当前 E2E 测试（prefix 漂移：注册 `/api/strategy` 应为 `/api`）
- `backend_api_python/app/routes/__init__.py` — 生产 `register_routes` 中 `strategy_bp` 注册为 `url_prefix='/api'`

### 重连机制
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_schedule_reconnect` / `_reconnect_loop` / `_on_connected` 重连链路

### 项目约束
- `.planning/REQUIREMENTS.md` — INFRA-01（qualify 缓存）、TEST-01（E2E prefix 修复）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_qualify_contract_async(contract)` — 现有 qualify 入口，缓存逻辑可在此方法内或其上层包装
- `_on_connected` / `_on_disconnected` — 重连事件钩子，可用于缓存生命周期管理（虽然本阶段不需要重连清缓存）
- `conftest.py` 中 `make_db_ctx` / `reset_signal_deduplicator` — 共享测试 fixture 模式可复用于缓存 reset

### Established Patterns
- IBKRClient 使用实例变量管理状态（`self._conid_to_symbol` 等 dict）— 缓存应遵循同样模式
- 测试使用 `unittest.mock.patch` + `MagicMock` 隔离 IBKR 依赖
- E2E 测试通过 `Flask(__name__)` + `register_blueprint` 创建最小 app

### Integration Points
- 缓存需要在 `_qualify_contract_async` 方法级别集成（所有 4 个调用点自动受益）
- E2E 测试的 Flask app 需要对齐 `backend_api_python/app/routes/__init__.py` 的 blueprint 注册

</code_context>

<specifics>
## Specific Ideas

- qualify 缓存的失败模式是安全的：过期数据只会导致 IBKR 拒单（order rejected），不会静默执行错误交易 — 这是选择中等 TTL 的依据
- conId 是 IBKR 全局统一的，不随 gateway 变化 — 这是重连不清缓存的依据
- 用户明确要求 Phase 18 的 E2E 测试应覆盖 qualify cache 命中/未命中/失效场景

</specifics>

<deferred>
## Deferred Ideas

- **Phase 18 E2E 覆盖 qualify cache 场景** — 用户要求在 Phase 18 路线图中明确标注：cache hit / cache miss / cache invalidation（错误码触发）的 E2E 测试用例
- **重连清缓存** — 当前决定不清，如果未来发现 TTL + 错误码失效不够，可在后续 phase 加入

</deferred>

---

*Phase: 13-qualify-result-caching-e2e-prefix-fix*
*Context gathered: 2026-04-11*
