# Phase 04: Market category & worker gate - Research

**Researched:** 2026-04-10  
**Domain:** QuantDinger 后端 Python — `IBKRClient.supported_market_categories`、`PendingOrderWorker` 实盘路径、`pytest`/`unittest.mock` 集成测试  
**Confidence:** HIGH（代码路径与行号以仓库当前版本为准）；生态通用结论为 MEDIUM（pytest 官方行为）

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- `IBKRClient.supported_market_categories`（`client.py` 行 102）从 `frozenset({"USStock", "HShare"})` 改为 `frozenset({"USStock", "HShare", "Forex"})`
- 只改这一行，`validate_market_category` 是基类方法（`base.py` 行 148-157），自动对 `"Forex"` 返回 `(True, "")`
- **不改** `PendingOrderWorker` 代码——它已经调用 `client.validate_market_category(market_category)`（`pending_order_worker.py` 行 358），只要 frozenset 包含 Forex 就自动通过
- `test_exchange_engine.py::test_ibkr_forex_rejected` **翻转**为 `test_ibkr_forex_ok`（方法名、`assert not ok` → `assert ok`、去掉仅失败分支用到的 `msg`）
- `test_ibkr_supported_categories` 更新 frozenset 断言
- **新增** PendingOrderWorker 集成测试：mock 完整 live 处理链路，验证 Forex 不被 category 门拒绝、非法 category 仍拒绝
- mock：`create_client`、`records.mark_order_failed`、通知等
- MT5 回归：不额外加 MT5 测试，依赖全量套件

### Claude's Discretion
- PendingOrderWorker 集成测试的具体 mock 实现方式
- 测试放在 `test_exchange_engine.py` 还是新建 `test_pending_order_worker.py`
- 集成测试中需要 mock 多少个依赖

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|---------------|------------------|
| CONT-04 | `IBKRClient.supported_market_categories` 包含 `"Forex"`；`PendingOrderWorker` 经 `validate_market_category` 放行 | 唯一生产代码改动点为 `client.py:102`；worker 在 `_execute_live_order` 内 `create_client` 之后调用 `validate_market_category`（见下文行号）；测试覆盖 UC-1..UC-6 + REGR-01 |
</phase_requirements>

## Summary

本阶段在架构上延续既有模式：**市场品类允许列表**挂在各 `BaseStatefulClient` 子类的 `supported_market_categories` 上，由基类 `validate_market_category` 统一实现互斥校验；**待成交工单 worker** 在成功 `create_client` 且客户端为 `BaseStatefulClient` 时调用该校验。当前仓库中 **不存在** 名为 `_process_one_live_order` 的方法；实盘逻辑集中在 **`PendingOrderWorker._execute_live_order`**（`pending_order_worker.py` 259-457 行）。将 `"Forex"` 加入 `IBKRClient.supported_market_categories` 后，IBKR 路径上除单元测试外 **未发现** 其他硬编码 “拒绝 Forex” 的分支；`pending_order_worker` 中对品类的额外拒绝仅针对 **AShare/Futures** 与 **加密货币所白名单**，与 IBKR+Forex 无冲突。

**Primary recommendation:** 只改 `IBKRClient.supported_market_categories` 一行；用 **`pytest` + `unittest.mock.patch`** 直调 `_execute_live_order`，`patch` `load_strategy_configs`、`create_client`、`get_runner`、`records.mark_order_*`、`_notify_live_best_effort`，避免真实 DB/TWS；新建 **`test_pending_order_worker.py`** 承载 UC-4/UC-5，与 `test_exchange_engine` 的纯 client 断言分层。

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.10+（项目约束） | 运行时 | 与 `backend_api_python` 一致 |
| pytest | 9.x（环境实测 `pip show pytest` → 9.0.2） | 测试运行器 | 仓库已全量使用；`tests/conftest.py` 共享 fixtures |
| unittest.mock | 标准库 | `patch` / `MagicMock` | 与 `test_dedup_retry_on_failure.py` 一致，无需额外依赖 |

### Supporting

| Library | When to Use |
|---------|-------------|
| `ib_insync` | 仅真实 IBKR 连接；本阶段集成测试应 **避免** 实例化完整 `IBKRClient()` 连接 TWS |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 直调 `_execute_live_order` | 只测 `validate_market_category` 单元 | 不满足 CONT-04 / UC-4、UC-5 对 worker 链路的要求 |
| 真实 DB | `patch` `records.*` | 慢、脆；与现有 `test_dedup_retry_on_failure` 风格一致 |

**Version verification (pytest):**

```bash
cd backend_api_python && python3 -m pip show pytest | grep ^Version
# 实测: Version: 9.0.2
```

**Installation:** 依赖已在 `backend_api_python/requirements.txt`；测试额外仅需 pytest（通常 dev 已装）。

## Architecture Patterns

### Established pattern: frozenset + 基类校验

```148:157:backend_api_python/app/services/live_trading/base.py
    def validate_market_category(self, market_category: str) -> Tuple[bool, str]:
        if not self.supported_market_categories:
            return True, ""
        if market_category in self.supported_market_categories:
            return True, ""
        return False, (
            f"{self.engine_id} only supports "
            f"{', '.join(sorted(self.supported_market_categories))}, "
            f"got {market_category}"
        )
```

IBKR 允许列表当前为：

```101:102:backend_api_python/app/services/live_trading/ibkr_trading/client.py
    engine_id = "ibkr"
    supported_market_categories = frozenset({"USStock", "HShare"})
```

（Phase 实施时改为包含 `"Forex"`。）

### Live 路径：`create_client` → `validate_market_category` → `get_runner` → `pre_check` → `execute`

**品类校验唯一入口（Stateful 客户端）：**

```340:371:backend_api_python/app/services/pending_order_worker.py
        client = None
        try:
            client = create_client(exchange_config, market_type=market_type)
        except Exception as e:
            records.mark_order_failed(order_id=order_id, error=f"create_client_failed:{e}", **_dedup_kw_live)
            ...
            return

        if isinstance(client, BaseStatefulClient):
            ok, cat_err = client.validate_market_category(market_category)
            if not ok:
                records.mark_order_failed(order_id=order_id, error=cat_err, **_dedup_kw_live)
                ...
                return
```

**要点：**

- `market_category` 来自 **`load_strategy_configs(strategy_id)["market_category"]`**（默认 `"Crypto"`），不是 payload 首选字段（见 `exchange_execution.load_strategy_configs`）。
- **`create_client` 失败** 与 **品类失败** 可通过 `mark_order_failed` 的 `error` 字符串区分：
  - 客户端创建失败：`error` 前缀为 **`create_client_failed:`**（344 行）。
  - 品类失败：`'error': cat_err`，内容为基类生成的 **`ibkr only supports ... got <category>`**（无 `create_client_failed` 前缀）。

### Recommended test structure

**直调 `_execute_live_order`**（公开方法、含完整分支），不要误用文档中的别名 `_process_one_live_order`（仓库中 **不存在**）。

为到达 `validate_market_category` 且避免 DB/网络：

| 依赖 | Mock 策略 |
|------|-----------|
| `load_strategy_configs` | 返回 dict：`market_category` 为 `Forex` 或 `Crypto`，`exchange_config` 含 `"exchange_id": "ibkr-paper"` |
| `create_client` | 返回 `IBKRClient.__new__(IBKRClient)`（无 `__init__`、不连 TWS），或返回自定义 `BaseStatefulClient` 子类实例 |
| `get_runner` | 返回 mock：`pre_check` → `PreCheckResult(ok=True)`，`execute` → `ExecutionResult(success=True, ...)`，避免真实 `place_market_order` / `is_market_open` |
| `records.mark_order_failed` / `mark_order_sent` | `patch` 后断言调用次数与 `error` 参数 |
| `_notify_live_best_effort` / `console_print` | 可选 patch，降噪 |

**UC-5（Crypto 被拒）** 仅需真实 `validate_market_category`：`IBKRClient.__new__(IBKRClient)` + 改 `supported_market_categories` 后 Crypto 仍不在集合内即可；**不必** 调用 `get_runner`。

**UC-4（Forex 过门）** 需在品类通过后仍不触发其他失败：必须用 mock runner 或跳过真实 `pre_check`/`execute`（见下节 Pitfall）。

### Anti-Patterns to Avoid

- **实例化完整 `IBKRClient()`**：会启动 `TaskQueue` 并可能在 `create_client`/singleton 路径上尝试连接。
- **只测 `validate_market_category` 而声称覆盖 worker**：不满足 CONTEXT 中 UC-4/UC-5。
- **用 open 类信号且不 mock `pre_check`**：`StatefulClientRunner.pre_check` 对非 close 信号会调用 `client.is_market_open`（可能触发 IB 连接）。缓解：mock `get_runner`、或 `signal_type` 用 `close_long`/`close_short`（runner 内跳过 RTH）、或给 fake client 挂 `is_market_open = lambda *a, **k: (True, "")`。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 在 worker 里单独 if Forex | 特判分支 | 扩展 `supported_market_categories` + 基类校验 | 与用户锁定决策一致，单一真相来源 |
| 自定义断言框架 | 手写测试运行器 | pytest + mock | 与全仓 860+ 测试一致 |
| 子类化 IBKR 仅测 frozenset | 过度设计 | `IBKRClient.__new__(IBKRClient)` | 与 `test_exchange_engine.TestValidateMarketCategory` 相同技巧 |

## Common Pitfalls

### Pitfall 1: 混淆失败原因（create_client vs category）

**What goes wrong:** 断言 `mark_order_failed` 时被 `create_client` 异常误导为品类问题。  
**How to avoid:** 断言 `error`：`create_client_failed:` **对比** `ibkr only supports` / `got Crypto`。  
**Warning signs:** 测试里未 patch `create_client` 却期望品类行为。

### Pitfall 2: `load_strategy_configs` 未注入 Forex

**What goes wrong:** 默认 `market_category` 为 `"Crypto"`（`exchange_execution.py` 79 行），worker 在品类阶段仍走 Crypto 校验。  
**How to avoid:** 集成测试必须 `patch` 返回 `market_category: "Forex"`（UC-4）或保持 Crypto（UC-5）。

### Pitfall 3: `pre_check` 拉真实 IB 做 RTH

**What goes wrong:** UC-4 使用 `open_long` 且未 mock runner，`is_market_open` 连 TWS。  
**How to avoid:** mock `get_runner` 或对 fake client 固定 `is_market_open` 返回开放；或使用 close 信号跳过 RTH（见 `stateful_runner.py` 25-30 行）。

### Pitfall 4: 搜索 “Forex 拒绝” 误判

**What goes wrong:** 全仓大量 `Forex` 出现在 K 线、数据源、路由，与 IBKR 品类门无关。  
**How to avoid:** 以 `supported_market_categories` / `validate_market_category` / `ibkr only supports` 为 grep 核心；**未发现** 除 `IBKRClient.supported_market_categories` 与基类消息外的 IBKR 专用 Forex 黑名单。

## Code Examples

### 单元层（已有模式）：`__new__` 避免初始化

与当前 `test_exchange_engine.TestValidateMarketCategory` 一致：

```75:76:backend_api_python/tests/test_exchange_engine.py
    def _ibkr(self):
        return IBKRClient.__new__(IBKRClient)
```

### Worker 集成（推荐形状 — 实施时由 planner 落任务）

```python
# 概念示例：patch 边界与断言方向（非复制粘贴即运行）
from unittest.mock import MagicMock, patch

from app.services.pending_order_worker import PendingOrderWorker
from app.services.live_trading.runners.base import PreCheckResult, ExecutionResult

@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.load_strategy_configs")
@patch("app.services.pending_order_worker.create_client")
@patch("app.services.pending_order_worker.get_runner")
def test_forex_passes_category_gate(mock_runner, mock_create, mock_load_cfg, mock_sent, mock_failed):
    mock_load_cfg.return_value = {
        "market_category": "Forex",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "forex",
    }
    mock_create.return_value = IBKRClient.__new__(IBKRClient)  # 实施前需已包含 Forex于 frozenset

    runner = MagicMock()
    runner.pre_check.return_value = PreCheckResult(ok=True)
    runner.execute.return_value = ExecutionResult(success=True, exchange_id="ibkr", exchange_order_id="1")
    mock_runner.return_value = runner

    w = PendingOrderWorker()
    w._execute_live_order(order_id=1, order_row={...}, payload={...})

    for c in mock_failed.call_args_list:
        assert "ibkr only supports" not in (c[1].get("error") or "")
```

## State of the Art

| Old / 误解 | Current / 仓库事实 | Impact |
|------------|---------------------|--------|
| 文档写 `_process_one_live_order` | 代码为 `_execute_live_order` | 计划/测试应引用正确方法名 |
| “runner 单独拒绝 Forex” | runner 仅传递 `market_category`（`stateful_runner` / `signal_runner` grep） | 品类门仅在 client `supported_market_categories` + worker 校验 |
| 全量约 849 测试 | `pytest --collect-only` 实测 **860**（2026-04-10） | REGR-01 以当前 collect 数为准 |

## Open Questions

1. **是否将 UC-4/UC-5 放入 `test_exchange_engine.py`？**  
   - 已知：两类测试关注点不同（client vs worker）。  
   - 建议：新建 `test_pending_order_worker.py` 更清晰；若强行合并单文件会变长。  
   - 处理：按 CONTEXT「Claude's Discretion」由 planner 定稿。

## Validation Architecture

`workflow.nyquist_validation` 在 `.planning/config.json` 中为 `true` —— 本段启用。

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest（实测 9.0.2） |
| Config file | 无独立 `pytest.ini`；共享 `tests/conftest.py` |
| Quick run command | `cd backend_api_python && python -m pytest tests/test_exchange_engine.py -q` |
| Full suite command | `cd backend_api_python && python -m pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| CONT-04 / UC-1 | `Forex in IBKRClient.supported_market_categories` | unit | `python -m pytest tests/test_exchange_engine.py::TestExchangeEngineBasics::test_ibkr_supported_categories -x` | 需更新断言后 ✅ |
| CONT-04 / UC-2 | `validate_market_category("Forex")` → True | unit | `python -m pytest tests/test_exchange_engine.py::TestValidateMarketCategory::test_ibkr_forex_ok -x` | 翻转后 ✅ |
| CONT-04 / UC-3 | Crypto 仍拒 | unit | `python -m pytest tests/test_exchange_engine.py::TestValidateMarketCategory::test_ibkr_crypto_rejected -x` | ✅ |
| CONT-04 / UC-4 | Worker Forex 不因品类失败 | integration | `python -m pytest tests/test_pending_order_worker.py::... -x` | ❌ Wave 0 |
| CONT-04 / UC-5 | Worker Crypto 品类失败 | integration | 同上 | ❌ Wave 0 |
| CONT-04 / UC-6 | frozenset 断言 | unit | 同 UC-1 | 同 UC-1 |
| CONT-04 / REGR-01 | 全量绿 | suite | `python -m pytest -q` | ✅ |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/test_exchange_engine.py tests/test_pending_order_worker.py -q`（待 UC-4/5 文件加入后）
- **Per wave merge / phase gate:** `python -m pytest -q`（860 tests，2026-04-10）

### Wave 0 Gaps

- [ ] `tests/test_pending_order_worker.py` — UC-4、UC-5，覆盖 `_execute_live_order` + `patch` 表
- [ ] 确认 `test_ibkr_supported_categories` / `test_ibkr_forex_ok` 在改 `client.py:102` 后同步更新

## Sources

### Primary (HIGH confidence)

- 仓库源码：`backend_api_python/app/services/live_trading/ibkr_trading/client.py`、`base.py`、`pending_order_worker.py`、`factory.py`、`runners/stateful_runner.py`、`exchange_execution.py`
- `pytest --collect-only`：860 tests（`backend_api_python`，2026-04-10）

### Secondary (MEDIUM confidence)

- pytest 行为：`https://docs.pytest.org/` — mock/patch 惯例

### Tertiary (LOW confidence)

- 无：本阶段以代码为准，不依赖未验证的论坛结论

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — pytest 版本来自本机 `pip show`；代码路径来自 Read/Grep  
- Architecture: **HIGH** — 行号与调用顺序可追溯  
- Pitfalls: **HIGH** — 由 `pending_order_worker` / `stateful_runner` 控制流导出  

**Research date:** 2026-04-10  
**Valid until:** ~30 天（若 `pending_order_worker` 大改需重扫）

## RESEARCH COMPLETE
