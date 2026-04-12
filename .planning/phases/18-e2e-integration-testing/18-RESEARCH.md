# Phase 18: E2E & integration testing - Research

**Researched:** 2026-04-12  
**Domain:** Pytest integration/E2E (Flask `test_client`), IBKR client mocking, qualify-cache behavior verification, Vue 2 + Jest unit tests  
**Confidence:** HIGH (codebase + runtime versions verified); MEDIUM on exact helper module split (discretion)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **后端 E2E 补全范围**: 全面覆盖 — qualify cache + cancel 场景 + error path + USStock/HShare 交叉验证  
- **Qualify cache E2E**（详细）: Cache hit 不重复 `qualifyContractsAsync`; cache miss; TTL 过期后重新 qualify; 不同 `market_type` TTL 独立（Forex vs USStock vs Metals 等）; IBKR 重连不清缓存; Invalidation（qualify 失败/异常后缓存项移除）  
- **限价单 cancel**: DAY 过期取消 + `filled=0` → `mark_order_failed`，无 position; DAY 过期取消 + `filled>0` → 写入 filled portion 的 position  
- **Error path E2E**: Qualify 失败（Error 200 No security definition）; 合约无效（post-qualify validation）; 限价 `price <= 0`（reject，不 enqueue）  
- **USStock/HShare**: 两个市场都加 market + limit E2E full chain（mock IBKR）  
- **文件组织**: 按主题拆分新文件（qualify cache / cancel+error / cross-market）; **`test_forex_ibkr_e2e.py` 保持不变**  
- **前端 HTTP E2E**: pytest Flask `test_client()` — **不用** Playwright/Cypress；真实 Flask app + 路由；mock DB/IBKR/通知；策略 CRUD + batch create  
- **Vue**: Jest 补几个 wizard 组件单元测试  
- **基础设施**: 共享 Flask app fixture → `conftest.py`; mock helpers → `tests/helpers/`（从 smoke/E2E 提取）  
- **验收**: TRADE-05/06 + TEST-02 + qualify cache E2E 全覆盖; **1023+ 后端测试全部 green（严格回归）**

### Claude's Discretion

- 具体文件命名和测试类组织  
- Mock helper 模块结构（单文件 vs 多文件）  
- Flask app fixture 实现细节  
- USStock/HShare E2E 场景选择  
- Vue Jest 组件选择与断言深度  
- Error path 具体错误码/消息断言  

### Deferred Ideas (OUT OF SCOPE)

- Playwright 浏览器 E2E  
- Docker-compose 黑盒集成测试  
- 前端 strategy 编辑界面 snapshot  
- 覆盖率数字门槛  

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRADE-05 | 贵金属 E2E（mock IBKR）qualify → order → callback | 现有 `test_uc_sa_e2e_xagusd_open_close_full_chain`、`test_e2e_metals_limit_xauusd` 模式；`secType=CMDTY` + `_make_qualify_for_pair(..., sec_type="CMDTY")` |
| TRADE-06 | 限价单 E2E：正常成交 + 部分成交 + 取消 | `test_e2e_forex_limit_*`、`test_e2e_limit_partial_fill_then_filled`；取消需覆盖 `_on_order_status` 中 `Cancelled` + `filled>0` / `filled<=0` 分支（见 `client.py` 503–508） |
| TEST-02 | 前端 HTTP E2E — wizard→API round-trip | **按 CONTEXT**: Flask `test_client` 调用 `strategy_bp`（`/api/strategies/create`、`PUT /api/strategies/update?id=`、`DELETE /api/strategies/delete?id=`、`POST /api/strategies/batch-create`），非浏览器 |

**Note:** `.planning/ROADMAP.md` Phase 18 成功标准第 3 条仍写 “Playwright”；**以本 CONTEXT 为准**（Flask `test_client` only）。

</phase_requirements>

## Summary

Phase 18 在已有 **~1039 条** pytest 用例（本机 `pytest --collect-only`）和密集 E2E 样板（`test_forex_ibkr_e2e.py`）之上，补齐 **qualify 缓存**、**取消/错误路径**、**USStock/HShare 全链**，并把 **策略 HTTP 集成测试** 与 **mock 提取** 工程化。后端链路的 established pattern 是：`PendingOrderWorker._execute_live_order` → 真实 `StatefulClientRunner` / `IBKRClient`，仅 mock `ib_insync`、DB 写路径、通知；Flask 侧用最小 app 注册 `strategy_bp`、`url_prefix='/api'`、`g.user_id`，并对 `login_required` 打桩后 `reload(strategy)`。

Qualify 缓存在 `IBKRClient._qualify_contract_async`：`time.monotonic()` + TTL（`IBKR_QUALIFY_TTL_FOREX_SEC` / `USSTOCK` / `HSHARE`；**Metals 与 Forex 共用 `IBKR_QUALIFY_TTL_FOREX_SEC`**），异常与空 qualify 会 `_invalidate_qualify_cache`；`_on_connected` / `_on_disconnected` **不** 触碰 `_qualify_cache`（重连不清缓存的验证点）。

**Primary recommendation:** 新 E2E 文件按 CONTEXT 主题拆分；用 **`patch` / 受控 `time.monotonic` side_effect** 和 **`qualifyContractsAsync` 调用计数** 断言缓存行为；HTTP E2E 单独模块只测路由契约与 `StrategyService` 的 mock 交互；先把共享 fixture/helpers 落地再写新用例，避免复制 `test_forex_ibkr_e2e.py` 中的导入/打桩顺序陷阱。

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 9.0.2 (verified `python -c "import pytest"`) | 后端测试运行器 | 项目已用；collection 1039 tests |
| Flask | 2.3.3 (`requirements.txt`) | `app.test_client()` HTTP 集成 | 与生产一致 |
| unittest.mock | stdlib | `MagicMock`, `patch` | 现有 E2E/Smoke 一致 |
| Jest | 27.5.1 (`quantdinger_vue`, `@vue/cli-plugin-unit-jest`) | Vue 单元测试 | 与 `vue-cli-service test:unit` 一致 |
| @vue/test-utils | ^1.3.x (lock 1.3.6) | 挂载 Vue2 组件 | 与现有 `frnt-01` 一致 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|-------------|-------------|
| Vue CLI | ~5.0.8 | `npm run test:unit` | Wizard Jest 测试 |
| ib_insync | >=0.9.86 | 类型/Contract | 真实代码路径；测试里用 mock 模块 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Flask test_client | Playwright | **Deferred by CONTEXT** — CI 简单；不测真实浏览器 |
| 单一大 E2E 文件 | 按主题拆分 | CONTEXT 要求拆分，降低合并冲突与认知负担 |

**Version verification (registry / runtime):**

```bash
cd backend_api_python && python -c "import pytest; print(pytest.__version__)"
cd quantdinger_vue && npm ls jest @vue/test-utils
```

## Architecture Patterns

### Recommended layout (Phase 18)

```
backend_api_python/tests/
├── conftest.py              # + shared Flask app fixture, re-exports helpers
├── helpers/                 # NEW: ibkr_mocks.py (or split), patched_records, etc.
├── test_forex_ibkr_e2e.py   # UNCHANGED per CONTEXT
├── test_e2e_qualify_cache_ibkr.py    # NEW (example name — discretion)
├── test_e2e_limit_cancel_errors_ibkr.py
├── test_e2e_cross_market_usstock_hshare.py
└── test_strategy_http_e2e.py           # Flask test_client CRUD + batch
```

### Pattern 1: Worker-driven IBKR E2E

**What:** 与现有一致 — 直接调用 `PendingOrderWorker()._execute_live_order(...)`，`patch("...create_client", return_value=ibkr_client)`。  
**When:** TRADE-05、TRADE-06 的“全链”断言（placeOrder、回调、partial、cancel）。  
**Example (existing):**

```212:241:backend_api_python/tests/test_forex_ibkr_e2e.py
@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_uc_sa_e2e_forex_full_chain(
    mock_load_cfg,
    mock_failed,
    mock_sent,
    _mock_notify,
    patched_records,
    ...
):
    ...
    with patch(
        "app.services.pending_order_worker.create_client",
        return_value=ibkr_client,
    ):
        w = PendingOrderWorker()
        w._execute_live_order(...)
```

### Pattern 2: Qualify cache assertions

**What:** `_qualify_contract_async` 使用 `_qualify_cache` 与 `time.monotonic()`（见下）。  
**How to test without flakiness:**

- **Cache hit / miss:** 同一 `IBKRClient` 实例上两次 `place_market_order`（或底层会 qualify 的路径），对 `ib.qualifyContractsAsync` 用 `wraps` 或 `side_effect` 计数；第二次在 TTL 内应 **不** 增加调用次数。  
- **TTL 过期:** `patch("app.services.live_trading.ibkr_trading.client.time.monotonic", side_effect=[t0, t0, t0 + ttl + 1, ...])` 或与 `IBKR_QUALIFY_TTL_*_SEC` 极小值配合（优先 monotonic patch，避免 sleep）。  
- **独立 TTL:** 对同一 client 分别用 `market_type` Forex vs USStock（不同 env 或默认 600s），断言 `_qualify_ttl_seconds` 行为（可单独单元式断言 + E2E 抽样）。  
- **重连不清缓存:** 调 `client._on_disconnected()` / `_on_connected()` 后检查 `client._qualify_cache` 仍保留有效 entry（与 Phase 13 设计一致）：

```583:589:backend_api_python/app/services/live_trading/ibkr_trading/client.py
    def _on_connected(self):
        logger.info("[IBKR-Event] connectedEvent — connection established")

    def _on_disconnected(self):
        logger.warning("[IBKR-Event] disconnectedEvent — connection lost")
        self._events_registered = False
        self._schedule_reconnect()
```

```928:956:backend_api_python/app/services/live_trading/ibkr_trading/client.py
    async def _qualify_contract_async(self, contract, symbol: str, market_type: str) -> bool:
        key = (symbol, market_type)
        ttl = self._qualify_ttl_seconds(market_type)
        now = time.monotonic()
        entry = self._qualify_cache.get(key)
        if entry and now < float(entry.get("expires_at", 0)):
            self._qualify_apply_snapshot_to_contract(contract, entry.get("snapshot") or {})
            return True
        ...
        try:
            qualified = await self._ib.qualifyContractsAsync(contract)
        except Exception as e:
            ...
            self._invalidate_qualify_cache(symbol, market_type)
            return False
        if len(qualified) == 0:
            self._invalidate_qualify_cache(symbol, market_type)
            return False
        ...
        self._qualify_cache[key] = {
            "expires_at": time.monotonic() + float(ttl),
            "snapshot": snapshot,
        }
```

### Pattern 3: Limit cancel → `_handle_fill` vs `_handle_reject`

**What:** `Cancelled` + `filled > 0` 仍走部分成交逻辑（fill）；`filled <= 0` 走 reject（衔接 `mark_order_failed` 路径需与 `records`/`PendingOrderWorker` mock 对齐）。

```500:508:backend_api_python/app/services/live_trading/ibkr_trading/client.py
        if status == "Filled" and filled > 0:
            self._fire_submit(lambda: self._handle_fill(ctx, filled, avg_price), is_blocking=True)
            ...
        elif status == "Cancelled" and filled > 0:
            self._fire_submit(lambda: self._handle_fill(ctx, filled, avg_price), is_blocking=True)
            ...
        elif status == "Cancelled" and filled <= 0:
            error_msgs = [e.message for e in (trade.log or []) if e.message]
            self._fire_submit(lambda: self._handle_reject(ctx, status, error_msgs), is_blocking=True)
```

### Pattern 4: Flask HTTP E2E（TEST-02）

**What:** `Flask(__name__)`, `register_blueprint(strategy_bp, url_prefix="/api")`, `before_request` 设置 `g.user_id`, `with app.test_client() as c`。  
**Routes to cover (existing):**

- `POST /api/strategies/create`
- `PUT /api/strategies/update?id=<id>`
- `DELETE /api/strategies/delete?id=<id>`
- `POST /api/strategies/batch-create`

**Mock:** `get_db_connection`（`make_db_ctx` from `conftest.py`）、`StrategyService` 或 repository 层按项目习惯 patch，避免真实 PostgreSQL。

### Pattern 5: Vue wizard Jest

**What:** 与 `quantdinger_vue/tests/unit/frnt-01-forex-ibkr-options.spec.js` 类似 — 可读入 `index.vue` 或 mount 子组件；使用 `@vue/test-utils` + Jest 27。  
**When:** 补“几个”wizard 相关测试（深度由 discretion 决定）。

### Anti-Patterns to Avoid

- **修改 `test_forex_ibkr_e2e.py` 行为** — CONTEXT 禁止挪现有用例逻辑；仅可改为 import 共享 helper。  
- **用真实浏览器跑 Phase 18** — 超出锁定方案。  
- **sleep 测 TTL** — 易 flaky；优先 monotonic patch。  
- **Hand-roll 完整 ib_insync** — 复用 `test_ibkr_client._make_mock_ib_insync` / `_make_client_with_mock_ib`。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IBKR 事件流 | 自定义最小 stub | `_FakeEvent` + `_wire_ib_events`（将迁至 `tests/helpers/`） | 与 `_register_events` 的 `+=` 语义一致 |
| Qualify Forex/Metals/STK | 每测试重写 | `_make_qualify_for_pair` / `_make_qualify_for_stock` | 已覆盖 CASH/CMDTY/STK |
| Fill 后回调顺序 | 随意调方法 | `_fire_callbacks_after_fill` | 对齐 Paper 事件顺序假设 |
| DB 连接 mock | 手写 | `make_db_ctx` + `patch("...get_db_connection", ...)` | `conftest` 已提供 |

**Key insight:** E2E 的价值在于 **真实 `IBKRClient` + 真实 Worker/Runner** 与生产一致；mock 边界应稳定在 ib/DB/通知。

## Common Pitfalls

### Pitfall 1: `login_required` / import order

**What goes wrong:** 策略路由仍带 `@login_required`，未打桩时 401 或重定向。  
**Why:** `test_forex_ibkr_e2e.py` 在 import `strategy` 前替换 `login_required` 并 `reload`。  
**How to avoid:** 共享 HTTP fixture 时复用同一顺序，或集中到一个 `tests/helpers/flask_strategy_app.py` 工厂。

### Pitfall 2: `reset_signal_deduplicator` autouse

**What goes wrong:** 测试间泄漏去重状态。  
**How to avoid:** 保持 `conftest` autouse fixture；新测试勿关闭。

### Pitfall 3: Cancel 测试未保留 `order_context`

**What goes wrong:** `_on_order_status` 早期 `ctx = self._order_contexts.pop` — 若无 ctx 直接 return。  
**How to avoid:** 先走与现有限价 E2E 相同的下单路径，再模拟 `Cancelled` 状态。

### Pitfall 4: Error 200 / qualify 失败

**What goes wrong:** 需同时触发异常或空列表以命中 `_invalidate_qualify_cache`。  
**How to avoid:** `qualifyContractsAsync` 抛错或返回 `[]`，并断言后续重试会再次调用 qualify。

### Pitfall 5: 限价 `price <= 0`

**What goes wrong:** 拒绝可能发生在 worker 或 client 多层。  
**How to avoid:** 先读 `PendingOrderWorker` / `place_limit_order` 入口，对齐实际拒绝点再断言。

## Code Examples

### Qualify TTL env（与实现一致）

```901:909:backend_api_python/app/services/live_trading/ibkr_trading/client.py
    def _qualify_ttl_seconds(self, market_type: str) -> int:
        if market_type in ("Forex", "Metals"):
            return int(os.environ.get("IBKR_QUALIFY_TTL_FOREX_SEC", "600"))
        if market_type == "USStock":
            return int(os.environ.get("IBKR_QUALIFY_TTL_USSTOCK_SEC", "600"))
        if market_type == "HShare":
            return int(os.environ.get("IBKR_QUALIFY_TTL_HSHARE_SEC", "600"))
        return 600
```

### 最小 Flask 客户端（现有）

```78:89:backend_api_python/tests/test_forex_ibkr_e2e.py
@pytest.fixture
def client_fixture():
    """Minimal Flask app with strategy routes; g.user_id set for UC-SA-E2E API tests."""
    app = Flask(__name__)
    app.register_blueprint(strategy_bp, url_prefix="/api")

    @app.before_request
    def set_g():
        g.user_id = 1

    with app.test_client() as c:
        yield c
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ROADMAP 写 Playwright | CONTEXT 锁定 Flask HTTP E2E | Phase 18 discuss | 实施以 CONTEXT 为准 |
| 单文件堆 E2E | 按主题拆分新文件 | Phase 18 | `test_forex_ibkr_e2e.py` 冻结 |

**Deprecated/outdated:**

- 依赖 ROADMAP 字面 “Playwright” 做 Phase 18 — **与锁定决策冲突**。

## Open Questions

1. **`StrategyService` mock 粒度**  
   - What we know: HTTP 路由调用 `get_strategy_service().create_strategy` / `update_strategy` / `delete_strategy` / `batch_create_strategies`。  
   - What's unclear: 是否 patch `StrategyService` 类还是 `get_strategy_service`。  
   - Recommendation: planner 实施时选最少侵入：patch service 方法返回固定 id / success。

2. **HShare 符号与 conId**  
   - What we know: `_make_qualify_for_stock` 模式可用于 STK。  
   - What's unclear: 具体测试标的（ discretion）。  
   - Recommendation: 选与现有测试一致的 mock conId/localSymbol 风格。

3. **Vue wizard “几个”组件**  
   - What we know: 仅 `frnt-01` 风格文件读或 mount。  
   - What's unclear: 是否测 `index.vue` 子组件拆分。  
   - Recommendation: 1–2 个 mount 测试 + 可选 1 个静态断言（与 CONTEXT 一致）。

## Validation Architecture

> `workflow.nyquist_validation` is enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none (no `pytest.ini` / `pyproject` in `backend_api_python`; markers registered in `conftest.py`) |
| Quick run command | `cd backend_api_python && pytest tests/test_<module>.py::test_<name> -x --tb=short` |
| Full suite command | `cd backend_api_python && pytest` |
| Frontend unit | `cd quantdinger_vue && npm run test:unit` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| TRADE-05 | Metals qualify→order→callback | integration/E2E | `pytest tests/test_forex_ibkr_e2e.py::test_uc_sa_e2e_xagusd_open_close_full_chain -x` | ✅ |
| TRADE-06 | Limit fill / partial / cancel | integration/E2E | `pytest tests/test_forex_ibkr_e2e.py::test_e2e_limit_partial_fill_then_filled -x` (+ new cancel file) | ✅ partial / new |
| TEST-02 | Strategy HTTP CRUD + batch | integration (Flask client) | `pytest tests/test_strategy_http_e2e.py -x` | ❌ Wave 0 |
| INFRA-01 (regression) | Qualify cache | new module | `pytest tests/test_e2e_qualify_cache_ibkr.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** targeted `pytest ...::test_... -x` for touched areas  
- **Per wave merge:** `pytest` full backend + `npm run test:unit` if Vue touched  
- **Phase gate:** full backend green + CONTEXT 规定的 Jest 若干用例 pass

### Wave 0 Gaps

- [ ] `tests/helpers/*.py` — shared IBKR/Flask mocks（从 smoke/E2E 提取）  
- [ ] `conftest.py` — shared Flask app fixture（真实 factory + mocks）  
- [ ] `tests/test_strategy_http_e2e.py` — TRADE/TEST-02 HTTP 层  
- [ ] `tests/test_e2e_qualify_cache_ibkr.py`（或等价命名）— qualify cache  
- [ ] `tests/test_e2e_limit_cancel_errors_ibkr.py` — cancel + error paths  
- [ ] `tests/test_e2e_cross_market_usstock_hshare.py` — cross-market  
- [ ] `quantdinger_vue/tests/unit/*wizard*` — 至少数个 wizard Jest 测试  

## Sources

### Primary (HIGH confidence)

- `backend_api_python/tests/test_forex_ibkr_e2e.py` — E2E 样板  
- `backend_api_python/tests/test_ibkr_forex_paper_smoke.py` — smoke helpers  
- `backend_api_python/tests/test_ibkr_client.py` — `_make_mock_ib_insync`  
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — qualify cache + `_on_order_status`  
- `backend_api_python/app/routes/strategy.py` — HTTP 路由  
- `.planning/phases/18-e2e-integration-testing/18-CONTEXT.md` — 锁定决策  
- Runtime: `pytest --collect-only` → 1039 tests; `pytest.__version__` → 9.0.2  

### Secondary (MEDIUM confidence)

- Flask 2.3 `test_client` — https://flask.palletsprojects.com/en/2.3.x/testing/  

### Tertiary (LOW confidence)

- npm registry `jest` latest tag (30.x) vs project lock 27.x — **use project lock for Phase 18**

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — versions measured in repo/environment  
- Architecture: **HIGH** — matches existing tests and `client.py`  
- Pitfalls: **HIGH** — import/auth and ctx lifecycle from code  
- Qualify cache time tests: **MEDIUM** — recommend `monotonic` patch; validate in implementation  

**Research date:** 2026-04-12  
**Valid until:** ~30 days (pytest/flask 稳定栈)
