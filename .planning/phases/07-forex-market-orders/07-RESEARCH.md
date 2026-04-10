# Phase 7: Forex market orders — Research

**Researched:** 2026-04-10  
**Domain:** IBKR IDEALPRO Forex `MarketOrder` via `ib_insync`, integration testing with `unittest.mock`  
**Confidence:** HIGH (code + project tests + IBKR Campus excerpts); MEDIUM (broker-specific min size / live partial-fill timing)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **totalQuantity 以基础货币单位计**（如 20000 EUR），与 IBKR IDEALPRO 约定一致。
- **ForexNormalizer 只检查 > 0**，不加最小下单量拦截（与项目 Out of Scope 一致）。
- **_align_qty_to_contract 从 ContractDetails.sizeIncrement 对齐**，复用现有两层机制。
- **最小下单量由 IBKR 服务端拒单兜底**（主流货币对约 20000 基础货币）。
- **完整 mock 集成测试**：覆盖 contract 创建 → qualify → _align_qty_to_contract → MarketOrder 构造 → placeOrder 全路径。
- **三个货币对**：EURUSD（主流）+ 交叉盘（如 GBPJPY）+ 贵金属（如 XAUUSD），确保不同类型 Forex pair 都正确处理。
- **注意不要过度 mock**：测试应验证真实行为，不要 mock 过多导致只测了 mock 本身。参考现有 `TestTifDay` 和 `TestTifForexPolicy` 的 mock 粒度。
- **USStock/HShare 回归测试**：确认现有下单路径不被 Forex 改动影响。
- **部分成交（IOC）**：接受，不重试，记录实际成交量。**仓位/成交记录以 IBKR 回调为准，不按提交量记录 position**。（Phase 10 fills/position events 会深入处理回调逻辑。）
- **错误消息**：保持现有行为，已包含 `market_type`（如 `f"Invalid {market_type} contract: {symbol}"`）。
- **qty=0 优化**：当 `_align_qty_to_contract` 返回 0 时，Forex 的错误提示加上"可能是数量低于最小下单量"的相关说明。
- **周末/非交易时间**：pre_check RTH 优先拦截 + IBKR 拒单兜底。（Phase 9 会完善 Forex 24/5 RTH 逻辑。）
- **断连**：复用现有 IBKRClient 自动重连机制（最多 3 次），不需要 Forex 专门处理。

### Claude's Discretion

- 集成测试中 mock 的粒度和分层方式。
- 具体选哪个交叉盘和贵金属对做测试（建议 GBPJPY + XAUUSD）。
- 用例编号命名（延续 UC-xxx / REGR-01 惯例）。
- qty=0 时 Forex 错误消息的具体文案。

### Deferred Ideas (OUT OF SCOPE)

- **cashQty 下单方式**（按报价货币金额下单，如 "用 23000 USD 买入 EUR"）→ v2 ADV-02
- **ForexNormalizer 最小量检查** → 项目 Out of Scope，保持 IBKR 拒单兜底
- **Forex 限价单** → v2 ADV-01
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-------------------|
| **EXEC-01** | `IBKRClient.place_market_order` 可对 Forex 合约下市价单（`MarketOrder` + `totalQuantity` 基础货币单位） | 代码路径已存在；本 Phase 以**集成测试 + qty=0 文案**锁定行为；IBKR/`ib_insync` 用法见 Standard Stack 与 Code Examples |
</phase_requirements>

## Summary

`place_market_order` 对 **Forex** 与 **USStock/HShare** 共用同一入口：先 `get_normalizer(market_type).check`，再 `_get_tif_for_signal`（Forex 固定 **IOC**，Phase 6 已锁定），然后 `_create_contract` → `qualifyContractsAsync` → `_validate_qualified_contract`（`Forex`→`secType==CASH`）→ `_align_qty_to_contract`（`reqContractDetailsAsync` + `sizeIncrement` floor）→ `ib_insync.MarketOrder(..., tif=tif)` → `placeOrder`。Phase 6 paper 已验证 EURUSD 20000 买卖可行；Phase 7 的价值是**用与生产一致的 mock 粒度**把这条链写进测试，并改进 **Forex + qty 对齐为 0** 时的用户可读错误信息。

**Primary recommendation:** 新增 `TestPlaceMarketOrderForex`（或等价类名）使用现有 `_make_client_with_mock_ib()` + `@patch(..., _make_mock_ib_insync())` 模式；对每个货币对断言 `placeOrder` 的 **contract**（`secType`、`symbol`、`currency`）与 **order**（`action`、`totalQuantity`、`tif`）；对 **UC-E** 用例显式 mock `qualifyContractsAsync` 失败或 `reqContractDetailsAsync` 返回带 `sizeIncrement` 的 details，使对齐结果为 0；**不要** mock `MarketOrder` 类本身（保持构造真实）。

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **ib_insync** | `>=0.9.86`（`requirements.txt`；registry 最新 **0.9.86**） | `Forex`, `MarketOrder`, `IB.placeOrder` | 项目已选定的 IBKR 异步封装，与 TWS/Gateway 一致 |
| **Python** | 3.10+（项目约定） | typing、`asyncio`、测试 | 后端基线 |
| **pytest** | 与仓库一致 | 单元/集成测试 | 现有 `tests/test_ibkr_client.py` 已大规模使用 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **unittest.mock** (`MagicMock`, `patch`, `AsyncMock`) | 标准库 | 替换 `ib_insync` 模块与 `IB` 实例 | 所有不连真实 Gateway 的集成测试 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `totalQuantity`（基础货币） | `cashQty`（报价货币名义） | v2 ADV-02；当前阶段明确不做 |

**Installation:** 已在 `backend_api_python/requirements.txt` 中。

**Version verification:** `pip index versions ib_insync` → latest **0.9.86**（2026-04-10 检查）。

## Architecture Patterns

### Established `place_market_order` flow (Forex = same surface as equities)

**What:** 单方法内完成校验、合约、数量对齐、下单；异步 `_do()` 经 `_submit(..., timeout=15.0)` 进入 IB 线程/loop。

**When to use:** 所有市价单（Forex / 股票）统一走此路径；Runner 只调用 `place_market_order`，不分支 Forex。

**Reference implementation:**

```1063:1125:backend_api_python/app/services/live_trading/ibkr_trading/client.py
    def place_market_order(
        self, symbol: str, side: str, quantity: float,
        market_type: str = "USStock", **kwargs,
    ) -> LiveOrderResult:
        from app.services.live_trading.ibkr_trading.order_normalizer import get_normalizer
        ok, reason = get_normalizer(market_type).check(quantity, symbol)
        if not ok:
            return LiveOrderResult(success=False, message=reason, exchange_id=self.engine_id)

        signal_type = str(kwargs.get("signal_type", ""))
        tif = self._get_tif_for_signal(signal_type, market_type)

        async def _do():
            await self._ensure_connected_async()
            _ensure_ib_insync()
            contract = self._create_contract(symbol, market_type)
            if not await self._qualify_contract_async(contract):
                return LiveOrderResult(success=False, message=f"Invalid {market_type} contract: {symbol}",
                                   exchange_id=self.engine_id)
            # ... validate, align, MarketOrder, placeOrder, context ...
```

### Forex contract creation

```801:808:backend_api_python/app/services/live_trading/ibkr_trading/client.py
    def _create_contract(self, symbol: str, market_type: str):
        _ensure_ib_insync()
        ib_symbol, exchange, currency = normalize_symbol(symbol, market_type)
        if market_type == "Forex":
            return ib_insync.Forex(pair=ib_symbol)
```

### TIF policy (Phase 6 — dependency for Phase 7)

```134:151:backend_api_python/app/services/live_trading/ibkr_trading/client.py
    def _get_tif_for_signal(signal_type: str, market_type: str = "USStock") -> str:
        ...
        if market_type == "Forex":
            return "IOC"
```

### Quantity alignment

```835:862:backend_api_python/app/services/live_trading/ibkr_trading/client.py
    async def _align_qty_to_contract(self, contract, quantity: float, symbol: str) -> float:
        """Query IBKR ContractDetails for sizeIncrement and floor-align quantity."""
        ...
        aligned = math.floor(quantity / increment) * increment
```

### Runner integration

```76:90:backend_api_python/app/services/live_trading/runners/stateful_runner.py
            result = client.place_market_order(
                symbol=ctx.symbol,
                side=action,
                quantity=ctx.amount,
                market_type=market_type,
                ...
            )
```

### Recommended test structure

- **Reuse:** `_make_mock_ib_insync()`, `_make_client_with_mock_ib()`, `@patch("app.services.live_trading.ibkr_trading.client.ib_insync", ...)`（与 `TestTifForexPolicy`、`TestCreateContractForex` 一致）。
- **Assert on `client._ib.placeOrder.call_args`:** `(contract, order)`，分别检查 Forex 合约字段与 `MarketOrder` 字段。
- **Extend `_make_client_with_mock_ib` 或测试局部覆盖:** `reqContractDetailsAsync` 当前返回单个 `MagicMock()`（用于 RTH）；对 **对齐用例** 应返回带 **数值** `sizeIncrement` / `minSize` 的 object，避免 `MagicMock` 参与算术时行为不确定。

### Anti-Patterns to Avoid

- **Over-mocking:** mock 掉 `place_market_order` 或整个 `_do` — 会测不到真实调用顺序。
- **错误使用 MagicMock 作为 ContractDetails:** `float(mock.sizeIncrement)` 可能异常或非预期；对齐测试应用简单 `types.SimpleNamespace` 或显式 `float` 字段。
- **把 IOC 部分成交当成失败:** `LiveOrderResult` 在提交成功时即 `Submitted`；部分成交由事件流处理（Phase 10），本 Phase 不测成交深度。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IDEALPRO Forex 合约 | 手写 `Contract` 字典 | `ib_insync.Forex(pair=...)` | 与 `qualify` / 字段约定一致 |
| 市价单结构 | 自定义序列化 | `ib_insync.MarketOrder(action=..., totalQuantity=..., tif=...)` | IBKR Order 字段与 Gateway 一致 |
| 数量取整（Forex） | 重复实现规则 | `ForexNormalizer` + `_align_qty_to_contract` | 单一职责；对齐 IB `sizeIncrement` |

**Key insight:** 业务层已组合好块；Phase 7 是**验证组合正确**，不是新协议层。

## Common Pitfalls

### Pitfall 1: Confusing quantity denomination (base vs quote)

**What goes wrong:** 误以为 `totalQuantity` 永远是“右手货币”或美元名义。  
**Why it happens:** IBKR 文档强调 Forex 可用 `cashQty` 按第二货币名义下单，容易与 `totalQuantity` 混淆。  
**How to avoid:** 锁定项目语义 — **基础货币单位**；测试用例对 EURUSD 使用“欧元数量”类整数（如 20000）。  
**Warning signs:** 与 TWS 显示单位不一致、或与 Phase 6 paper 验证量级不一致。

### Pitfall 2: `qualify` 失败与错误消息

**What goes wrong:** 无效符号返回 `Invalid Forex contract: {symbol}`。  
**Why it happens:** `_qualify_contract_async` 返回 false。  
**How to avoid:** 集成测试断言 message 子串；不要用模糊 `assert not result.success`。

### Pitfall 3: IOC + 部分成交

**What goes wrong:** 期望 `placeOrder` 后 `filled == totalQuantity`。  
**Why it happens:** IOC 在流动性不足时可部分成交，余量取消。  
**How to avoid:** 本 Phase 只断言 **Submitted** 与订单字段；成交以回调为准（用户已锁定）。  
**Warning signs:** 在单元测试里断言 `orderStatus.filled`（当前 `place_market_order` 路径不等待该状态）。

### Pitfall 4: RTH `pre_check` 与 Forex 周末

**What goes wrong:** Runner `pre_check` 对非 close 信号调用 `is_market_open`；周末可能拦截。  
**Why it happens:** `stateful_runner.py` 对 close 跳过 RTH；open 类信号需市场开放。  
**How to avoid:** Phase 7 **客户端单测**继续 patch `is_rth_check`（文件已 `autouse`）；端到端/人工验证留给 Phase 9。  
**Warning signs:** 集成测试在周五夜间不稳定 — 应用固定时间的 `is_market_open` mock。

### Pitfall 5: 测试里 `reqContractDetailsAsync` 共享 mock

**What goes wrong:** `_align_qty_to_contract` 与 `is_market_open` 都调用 `reqContractDetailsAsync`；若全局 mock 返回无 `sizeIncrement`，对齐路径不触发 increment 逻辑。  
**Why it happens:** 单一 `_mock_details` 服务多个场景。  
**How to avoid:** 为 **UC-E 对齐为 0** 单独 patch 返回带 `sizeIncrement=25000`（示例）的 details，使 `floor(10000/25000)*25000 == 0`。

## Code Examples

### ib_insync 测试替身（项目已有）

```32:74:backend_api_python/tests/test_ibkr_client.py
def _make_mock_ib_insync():
    """Create a mock ib_insync module with necessary classes."""
    ...
    class MockForex:
        def __init__(self, pair='', exchange='IDEALPRO', symbol='', currency='', **kwargs):
            if pair:
                assert len(pair) == 6
                symbol = symbol or pair[:3]
                currency = currency or pair[3:]
            self.secType = 'CASH'
            ...
```

### Forex IOC 下单断言（项目已有 — 扩展为多货币对）

```697:704:backend_api_python/tests/test_ibkr_client.py
    @patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
    def test_forex_market_order_passes_tif_ioc(self):
        client = _make_client_with_mock_ib()
        ...
        client.place_market_order("EURUSD", "buy", 10000.0, "Forex", signal_type="open_long")
        placed_order = client._ib.placeOrder.call_args[0][1]
        assert placed_order.tif == "IOC"
```

### ForexNormalizer（仅 >0）

```7:15:backend_api_python/app/services/live_trading/order_normalizer/forex.py
class ForexNormalizer(OrderNormalizer):

    def normalize(self, raw_qty: float, symbol: str) -> int:
        return math.floor(raw_qty)

    def check(self, qty: float, symbol: str) -> Tuple[bool, str]:
        if qty <= 0:
            return False, f"Quantity must be positive, got {qty}"
        return True, ""
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Forex TIF 与股票相同（DAY/IOC 混用） | Forex 全 IOC | Phase 6 | 与 IDEALPRO 自动化预期一致；避免挂单 |
| 仅股票下单测试 | 股票 + Forex 合同与 TIF 测试 | Phase 2–6 | Phase 7 补齐 **市价单全路径** 三货币对 |

**Deprecated/outdated:** 无新增废弃 API；`cashQty` 留待 v2。

## Test Use Cases & Specifications

> 本节为 Phase 7 核心交付物：用例 ID、输入、期望、边界、mock 策略。实现时可原样迁入 `07-01-PLAN.md`。

### Mock strategy (global)

| 层次 | Mock | 不要 Mock |
|------|------|-----------|
| `ib_insync` 模块 | ✅ `@patch` 使用 `_make_mock_ib_insync()` | ❌ 不要在生产代码换 stub |
| `IB` 实例 (`client._ib`) | ✅ `qualifyContractsAsync`、`placeOrder`、`reqContractDetailsAsync`（按需） | ❌ 不要 mock `IBKRClient.place_market_order` 整体 |
| `MarketOrder` / `Forex` 类 | ✅ 测试模块内轻量类（已存在） | ❌ 不要替换成无属性的对象（会丢失断言） |
| 网络 / Gateway | ✅ 全程不连真实 IB | 真实 paper 已由 Phase 6 覆盖，本 Phase CI 不依赖 |

### Happy path — 全路径集成

| ID | 描述 | 输入参数 | 期望输出 / 断言 | 边界与备注 |
|----|------|----------|-----------------|------------|
| **UC-M1** | 主流 EURUSD 买入 | `symbol="EURUSD"`, `side="buy"`, `qty=20000`, `market_type="Forex"`, `signal_type="open_long"` | `success=True`, `status="Submitted"`, `order_id` 匹配 mock；`placeOrder` 第一参 `secType=="CASH"`，`symbol=="EUR"`, `currency=="USD"`；`totalQuantity==20000`；`tif=="IOC"` | 与 Phase 6 paper 量级一致 |
| **UC-M2** | 交叉盘 GBPJPY 卖出 | `GBPJPY`, `sell`, `50000`, `Forex`, `signal_type="open_short"` | 同上；`symbol=="GBP"`, `currency=="JPY"`；`action=="SELL"` | 验证非美元报价货币 |
| **UC-M3** | 贵金属 XAUUSD | `XAUUSD`, `buy`, `10`, `Forex` | `symbol=="XAU"`, `currency=="USD"`；`tif=="IOC"`；数量经对齐后仍 >0 | 金属在 `KNOWN_FOREX_PAIRS`；若 mock increment 为 1，则 qty 仍为 10 |

### Error / validation path

| ID | 描述 | 输入 / mock 设定 | 期望输出 | 边界 |
|----|------|------------------|----------|------|
| **UC-E1** | 无效符号 / qualify 失败 | `symbol="INVALID1"` 或 `qualifyContractsAsync` 返回 `[]` | `success=False`，`message` 含 `Invalid` 且含 `Forex` 与 symbol | 与现有 `test_invalid_contract_rejected` 模式一致，显式 `market_type="Forex"` |
| **UC-E2** | 数量对齐后为 0（Forex 文案） | `reqContractDetailsAsync` 返回 `sizeIncrement=25000`（示例），`quantity=10000` | `success=False`，`message` 含原对齐失败语义，并含 **Forex 特有可能低于最小可交易单位** 的提示（具体措辞 Claude discretion） | 需 **numeric** details，不用裸 `MagicMock` |
| **UC-E3** | normalizer 拒绝（非对齐） | `qty=0` 或负数 | `ForexNormalizer`：`Quantity must be positive`；**不**走到 `placeOrder` | `placeOrder` `call_count==0` |

### Regression

| ID | 描述 | 输入 | 期望 |
|----|------|------|------|
| **UC-R1** | USStock 行为不变 | `AAPL`, `buy`, `10`, `USStock` | `tif=="DAY"`（`TestTifDay` 已覆盖）；Phase 7 变更后仍通过 |
| **UC-R2** | HShare 仍存在 | 任选已有 HShare 测试 | 不回归 |
| **REGR-01** | 全量测试 | `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` | exit 0 |

### IOC / 部分成交（规格说明，非本 Phase 自动化重点）

| ID | 描述 | 期望行为 | 自动化 |
|----|------|----------|--------|
| **UC-I1** | IOC 部分成交 | 提交成功即 `Submitted`；成交增量来自事件 | 可选：mock `placeOrder` 返回 `Submitted` + `remaining>0` 不检查（与当前设计一致） |

## Open Questions

1. **XAUUSD / 交叉盘的 `sizeIncrement` 在实盘的典型值**  
   - What we know: 逻辑为 `floor(qty/increment)*increment`。  
   - What's unclear: 精确数值依赖 IB 返回。  
   - Recommendation: 测试中 **注入** 已知 increment，不硬依赖实盘。

2. **`reqContractDetailsAsync` 失败时是否回退为原数量**  
   - What we know: 代码在异常或 increment≤0 时 `return quantity`。  
   - Recommendation: 可选 UC：mock `reqContractDetailsAsync` 抛错 → 断言数量不抛异常且仍下单（若需文档化行为）。

## Validation Architecture

> `workflow.nyquist_validation` 为 true（`.planning/config.json`）。

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | 无独立 `pytest.ini` 检测 — 使用默认 + 仓库约定 |
| Quick run command | `cd backend_api_python && python -m pytest tests/test_ibkr_client.py -x -q --tb=line` |
| Full suite command | `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| EXEC-01 | Forex `place_market_order` 提交 `MarketOrder`，`totalQuantity` 为对齐后基础货币数量，`tif=IOC` | integration (mock IB) | `pytest tests/test_ibkr_client.py -k "PlaceMarketOrderForex or forex" -x -q --tb=line`（实现后调整 `-k`） | ❌ Wave 0 — 新增类 |
| EXEC-01 | qty 对齐为 0 时失败且 Forex 友好提示 | unit/integration | 同上 | ❌ Wave 0 |
| EXEC-01 | USStock/HShare 回归 | regression | 全量 `pytest tests/` | ✅ 已有大量 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_ibkr_client.py -x -q --tb=line`（或更窄 `-k`）
- **Per wave merge / phase gate:** 全量 `pytest tests/ -x -q --tb=line`

### Wave 0 Gaps

- [ ] 新测试类：`TestPlaceMarketOrderForex`（名称可调整）覆盖 UC-M1–M3、UC-E1–E3
- [ ] 显式 `reqContractDetailsAsync` 返回带 `sizeIncrement` 的 object（UC-E2）
- [ ] 可选：`client.py` 中 Forex `qty<=0` 分支消息常量或单测快照

*(若仅扩展现有文件：不新增 `conftest` 亦可，沿用 `_always_rth` fixture。)*

## Sources

### Primary (HIGH confidence)

- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `place_market_order`, `_align_qty_to_contract`, `_get_tif_for_signal`
- `backend_api_python/tests/test_ibkr_client.py` — `_make_mock_ib_insync`, `_make_client_with_mock_ib`, `TestTifForexPolicy`, `TestCreateContractForex`
- [IBKR Campus — Order Types](https://ibkrcampus.com/ibkr-api-page/order-types/) — Forex / `cashQty` 与产品类型 **CASH**；文档亦强调 API 层对 **Forex** 与 **quantity** 的特殊支持（与项目 `totalQuantity` 路径并存）
- `.planning/phases/06-tif-policy-for-forex/06-VERIFICATION.md` — EURUSD paper 验证

### Secondary (MEDIUM confidence)

- [IBKR — Forex Cash Quantity Orders](https://www.interactivebrokers.com/en/index.php?f=23876#963-02)（对比用：报价货币名义 vs 本项目 base 语义）
- Web search / community：IOC 部分成交行为 — 与 **Execution / orderStatus** 事件模型一致，非 `placeOrder` 同步返回

### Tertiary (LOW confidence)

- 历史页面 “IDEALPRO Minimum/Maximum Order Size (2011)” — 仅作背景；**以 IB Gateway 实时 ContractDetails 与拒单为准**

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — 来自 `requirements.txt` 与代码 import
- Architecture: **HIGH** — 直接引用仓库实现
- IBKR Forex 边缘行为（最小量、部分成交时机）: **MEDIUM** — 以 paper/生产为准；测试用注入 increment

**Research date:** 2026-04-10  
**Valid until:** ~30 days（IBKR 政策极少变；测试模式稳定）
