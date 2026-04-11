# Phase 8: Quantity normalization & IB alignment - Research

**Researched:** 2026-04-11  
**Domain:** Forex order quantity — `ForexNormalizer` + IBKR `ContractDetails`-driven `_align_qty_to_contract`  
**Confidence:** HIGH (code verified against `git show HEAD:.../ibkr_trading/client.py`; working tree currently lacks `client.py` — restore from VCS before implementation)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-------------------|
| EXEC-04 | 数量处理复用 ForexNormalizer（整数取整）+ `_align_qty_to_contract`（IBKR sizeIncrement 对齐） | CONTEXT 将「整数取整」重新定义为：Normalizer **透传**；**取整/对齐**仅在 `_align_qty_to_contract` 用 `floor(qty/increment)*increment`。测试锁定两条链路。 |
</phase_requirements>

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **normalize() 改为透传**：`return raw_qty`（不再 `math.floor`），避免未来有人调用时截断贵金属等小数量（如 XAUUSD 0.5 oz）。数量取整完全由 `_align_qty_to_contract` 的 sizeIncrement 对齐负责。
- **check() 保持只检查 > 0**：与项目 Out of Scope（不加最小下单量检查）一致。IBKR 服务端拒单兜底。
- **normalize() 不加调用**：当前 `place_market_order` / `place_limit_order` 只调用 `check()`，这个行为不变。normalize() 作为基类抽象方法的实现存在，但不纳入主线调用链。
- **ForexNormalizer 全面边界测试**：负数、极小小数(0.001)、极大值(1e9)、浮点精度(20000.99)、多货币对(EURUSD/GBPJPY)的 normalize 输入输出。
- **_align_qty_to_contract 完整矩阵**：恰好整除；不整除但 >0；increment=1；increment 获取失败回退原量；缓存命中。
- **回归**：全量 `pytest tests/`（REGR-01）。

### Claude's Discretion

- 测试类命名和组织方式（扩展现有 `TestForexNormalizer` 还是新建类）。
- `_align_qty_to_contract` 测试中 mock 的具体参数值。
- 缓存测试的验证方式（call_count 断言 vs side_effect 追踪）。

### Deferred Ideas (OUT OF SCOPE)

- **贵金属合约归类（XAUUSD/XAGUSD/XAUEUR）** — 独立未来 Phase。
- **normalize() 在主线的调用时机** — 不在本 Phase 处理。
</user_constraints>

## Summary

Phase 8 交付物主要是 **测试规格落地 + `ForexNormalizer.normalize` 行为修正**。生产路径上，`place_market_order` / `place_limit_order` 仅调用 `get_normalizer(...).check()`；**对齐**发生在异步 `_align_qty_to_contract` 内，通过 `reqContractDetailsAsync` 读取 `sizeIncrement`（必要时回退 `minSize`），再按 \( \lfloor q / \text{increment} \rfloor \times \text{increment} \) 对齐。`ForexNormalizer` 若继续 `math.floor`，会与「由 IB 决定粒度」的设计冲突，故改为 **透传**，与 `CryptoNormalizer` 一致哲学，把粒度交给 IB 层。

**Primary recommendation:** 实现 `normalize` 透传；用单元测试锁定 UC-N*；用 **AsyncMock** 的 `reqContractDetailsAsync` + **测试前后清空 `IBKRClient._lot_size_cache`** 锁定 UC-A*；全仓 pytest 作为 REGR-01。

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.10+ | Runtime | 项目后端版本 |
| pytest | (project default) | Unit/integration tests | 现有 `backend_api_python/tests/` 已采用 |
| ib_insync | 0.9.86（`requirements.txt`） | IB API 封装 | 与 `reqContractDetailsAsync`、`ContractDetails` 字段一致 |
| `unittest.mock` | stdlib | `MagicMock` / `AsyncMock` | 与现有 `test_ibkr_order_callback.py` 一致 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `asyncio` | stdlib | 在**同步** pytest 中运行 `_align_qty_to_contract` | 若未引入 `pytest-asyncio`，用 `asyncio.run()` 包装单次协程调用 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asyncio.run()` in sync tests | `pytest-asyncio` | 需新增 dev 依赖与配置；当前仓库未强制使用 asyncio 插件 |

**Installation:** 无新增包（沿用 `ib_insync>=0.9.86`）。

**Version verification:** `pip index versions ib_insync` → latest **0.9.86** (matches `requirements.txt`).

## Architecture Patterns

### Recommended Project Structure

```
backend_api_python/tests/
├── test_order_normalizer.py    # UC-N1–N6 (+ 可选 GBPJPY 重复断言)
└── test_ibkr_align_qty.py      # UC-A1–A5（新建）或并入现有 IBKR 测试模块 — Claude's discretion
```

### Pattern 1: Normalizer 纯函数测试

**What:** 直接 `ForexNormalizer()`，无 mock。  
**When to use:** UC-N1–N6。

### Pattern 2: 异步对齐函数隔离测试

**What:** `IBKRClient.__new__(IBKRClient)` 构造壳实例，注入 `client._ib`，实现/桩 `reqContractDetailsAsync`；**必须**在前后 `IBKRClient._lot_size_cache.clear()`。  
**When to use:** UC-A1–A5。

### Pattern 3: 同步测试内调用 async

**What:**  

```python
import asyncio

def test_align():
    async def _run():
        return await client._align_qty_to_contract(contract, qty, "EURUSD")
    out = asyncio.run(_run())
    assert out == expected
```

**Anti-Patterns to Avoid**

- **裸 `MagicMock` 充当 ContractDetails：** Phase 7 / CONTEXT 已说明 — 使用 `types.SimpleNamespace(sizeIncrement=..., minSize=...)`（或等价显式属性）。
- **跨测试泄漏 `_lot_size_cache`：** 会导致 UC-A5 假阳性/假阴性。
- **在 normalizer 测试中 mock IB：** 违背「不要过度 mock」的 phase 约束。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IB 合约最小增量 | 手写常量表 | `_align_qty_to_contract` + `reqContractDetailsAsync` | 增量随合约/交易所变化，缓存已在客户端实现 |
| 异步 IB 调用线程安全 | 在测试里直连真 TWS | Mock `reqContractDetailsAsync` | UC 要求可重复、无外部依赖 |

**Key insight:** EXEC-04 的「标准栈」是 **现有** normalizer 工厂 + **现有** 对齐函数；本 Phase 是 **行为修正 + 测试锁定**，不是新协议层。

## Common Pitfalls

### Pitfall 1: `normalize` 返回类型与基类不一致

**What goes wrong:** `OrderNormalizer.normalize` 注解为 `float`，当前 `ForexNormalizer` 标注 `-> int` 且 `floor`，与透传改造冲突。  
**How to avoid:** 改造后将注解改为 `float`，返回值与输入同型（透传）；必要时对浮点断言使用 `==` 或可预期小数用 `pytest.approx`。

### Pitfall 2: 日志/浮点格式化掩盖对齐结果

**What goes wrong:** 对齐日志用 `%.0f` 打印，调试时误以为总是整数；实际 `increment` 可为非整数（少见但可能）。  
**How to avoid:** 断言以函数返回值为准，不依赖日志。

### Pitfall 3: `conId == 0` 时不写入缓存

**What goes wrong:** HEAD 实现中 `if increment > 0 and con_id:` 才缓存；测试合约若无 `conId`，缓存分支测不到。  
**How to avoid:** UC-A5 使用 **非零 `conId`**（如 `424242`）。

## Code Examples

### `_align_qty_to_contract`（canonical，HEAD）

```python
# Source: git HEAD backend_api_python/app/services/live_trading/ibkr_trading/client.py
async def _align_qty_to_contract(self, contract, quantity: float, symbol: str) -> float:
    con_id = getattr(contract, "conId", 0) or 0
    increment = self._lot_size_cache.get(con_id)
    if increment is None:
        try:
            details_list = await self._ib.reqContractDetailsAsync(contract)
            if details_list:
                d = details_list[0]
                increment = float(getattr(d, "sizeIncrement", 0) or 0)
                if increment <= 0:
                    increment = float(getattr(d, "minSize", 0) or 0)
                if increment > 0 and con_id:
                    self._lot_size_cache[con_id] = increment
        except Exception as e:
            logger.warning("[IBKR] reqContractDetails failed for %s: %s", symbol, e)
            increment = None

    if not increment or increment <= 0:
        return quantity

    aligned = math.floor(quantity / increment) * increment
    ...
    return aligned
```

### `place_market_order` 调用链（仅 check，不对 normalize 的调用）

```python
# Source: git HEAD — same file
ok, reason = get_normalizer(market_type).check(quantity, symbol)
...
qty = await self._align_qty_to_contract(contract, quantity, symbol)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Forex `normalize` = `floor` | 透传 + IB `sizeIncrement` 对齐 | Phase 8（计划） | 避免误杀小数数量；与 EXEC-04 一致 |
| 每单请求合约详情 | `_lot_size_cache[conId]` | 已在 HEAD | 减少 API 负载 |

## Test Use Cases & Specifications

> 下列规格可直接复制到 PLAN task 的 **前置条件 / 步骤 / 期望 / 断言**。

### ForexNormalizer — UC-N1 … UC-N6

| UC | 目的 | 输入 | 期望输出 | 断言条件 | Mock |
|----|------|------|----------|----------|------|
| **UC-N1** | 浮点透传（大数 + 小数） | `normalize(20000.99, "EURUSD")` | `20000.99` | `assert out == 20000.99` | 无 |
| **UC-N2** | 小数量不再被 floor 成 0 | `normalize(0.5, "EURUSD")` | `0.5` | `assert out == 0.5` | 无 |
| **UC-N3** | 极小正数透传 | `normalize(0.001, "EURUSD")` | `0.001` | `assert out == 0.001` | 无 |
| **UC-N4** | 极大值透传 | `normalize(1e9, "EURUSD")` | `1e9` | `assert out == 1e9` | 无 |
| **UC-N5** | check 拒绝负数 | `check(-5, "EURUSD")` | `(False, msg)` | `ok is False` 且 `"positive" in msg.lower()` 且 `"-5" in msg or "-5.0" in msg` | 无 |
| **UC-N6** | check 接受极小正数 | `check(0.001, "EURUSD")` | `(True, "")` | `ok is True` 且 reason `== ""` | 无 |

**补充（多货币对，CONTEXT）：** 在 **UC-N1**（或单独参数化用例）上对 `symbol="GBPJPY"` 重复 **同一数值**，期望与 EURUSD **完全相同**（当前 `ForexNormalizer` 实现不依赖 symbol；若未来依赖 symbol，测试会失败并提醒回归）。

**回归现有测试：** 改造后 **必须**更新 `TestForexNormalizer.test_normalize`：当前期望 `1000.7 → 1000`（floor）；改造后期望 `1000.7` 透传。

---

### `_align_qty_to_contract` — UC-A1 … UC-A5

**共享测试装置（每个测试函数内或 `setup_method`）：**

1. `from app.services.live_trading.ibkr_trading.client import IBKRClient`（需工作区存在 `client.py`）。
2. `client = IBKRClient.__new__(IBKRClient)`。
3. `client._ib = MagicMock()`。
4. `IBKRClient._lot_size_cache.clear()` **在 arrange 阶段开头**。
5. `contract = types.SimpleNamespace(conId=424242)`（UC-A5 依赖非零 conId；UC-A1–A4 可共用）。
6. `req = AsyncMock(...)` → `client._ib.reqContractDetailsAsync = req`。

**Async 执行（若未用 pytest-asyncio）：** `out = asyncio.run(client._align_qty_to_contract(contract, qty, "EURUSD"))`。

| UC | 目的 | Mock 返回值 | 输入 qty | 期望返回值 | 断言条件 |
|----|------|-------------|----------|------------|----------|
| **UC-A1** | 恰好整除 | `[SimpleNamespace(sizeIncrement=25000, minSize=1)]` | `50000` | `50000.0` | `out == 50000` |
| **UC-A2** | 不整除但 >0，向下对齐 | 同上 `sizeIncrement=25000` | `30000` | `25000.0` | `out == 25000`（因 `floor(30000/25000)=1`） |
| **UC-A3** | increment=1 等价无对齐 | `[SimpleNamespace(sizeIncrement=1, minSize=1)]` | `20000` | `20000.0` | `out == 20000` |
| **UC-A4** | API 异常回退原量 | `reqContractDetailsAsync` `side_effect=RuntimeError("boom")` | `20000` | `20000.0` | `out == 20000`；可选 `req.assert_called_once()` |
| **UC-A5** | 缓存命中，第二次不查 API | 第一次：`AsyncMock(return_value=[SimpleNamespace(sizeIncrement=25000, minSize=1)])` | 第一次 `qty=10000`，第二次 `qty=15000`（**同一 `contract` 对象**） | 第一次 `10000`；第二次对齐结果 `floor(15000/25000)*25000 = 0.0` | `req.call_count == 1` |

**UC-A5 说明：** 第二次若期望仍为「对齐后非零」，可改用 `qty=30000`（得 `25000`）而保持 `call_count == 1`；CONTEXT 示例强调 **call_count**，故以 **两次调用、一次网络** 为主断言。

---

### 回归 — REGR-01

| UC | 命令 | 期望 |
|----|------|------|
| **REGR-01** | `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` | 退出码 0；无失败、无 error |

**范围说明：** 覆盖 `TestUSStockNormalizer`、`TestHShareNormalizer`、更新后的 `TestForexNormalizer`、IBKR 相关测试及 Phase 7 已存在用例；与 CONTEXT「不需要额外交叉测试」一致。

## Open Questions

1. **`.planning/STATE.md` 缺失**  
   - *What we know:* INIT 指向该路径，仓库中当前无此文件。  
   - *Recommendation:* 规划阶段可忽略；或从模板恢复 STATE.md 以免后续 phase 丢上下文。

2. **工作区 `ibkr_trading/client.py` 被删除**  
   - *What we know:* `git status` 显示删除；测试仍 `import` 该模块。  
   - *Recommendation:* Phase 8 实施前从 `HEAD` 恢复文件，否则无法跑 UC-A* 与 REGR-01。

## Validation Architecture

> `workflow.nyquist_validation` 在 `.planning/config.json` 中为 true — 本节保留。

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest（项目惯例） |
| Config file | 无独立 `pytest.ini` 检出 — 依赖默认 discovery `tests/` |
| Quick run command | `cd backend_api_python && python -m pytest tests/test_order_normalizer.py -x -q --tb=line` |
| Full suite command | `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| EXEC-04 | Forex 数量：check + IB 对齐 | unit | `pytest tests/test_order_normalizer.py tests/test_ibkr_align_qty.py -x -q`（对齐测试文件名以 PLAN 为准） | 对齐文件待 Wave 0 新增 |

### Sampling Rate

- **Per task commit:** `pytest` 针对本 task 新增/修改文件。  
- **Phase gate:** REGR-01 全绿。

### Wave 0 Gaps

- [ ] 新增 `_align_qty_to_contract` 专用测试模块（若未并入现有文件）。  
- [ ] 确认工作区恢复 `ibkr_trading/client.py`。  
- [ ] 更新 `TestForexNormalizer.test_normalize` 期望以匹配透传语义。

## Sources

### Primary (HIGH confidence)

- `git show HEAD:backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_align_qty_to_contract`, `_lot_size_cache`, `place_market_order`  
- `backend_api_python/app/services/live_trading/order_normalizer/forex.py` — 当前 `ForexNormalizer` 实现  
- `backend_api_python/app/services/live_trading/order_normalizer/__init__.py` — `OrderNormalizer` ABC  
- `.planning/phases/08-quantity-normalization-ib-alignment/08-CONTEXT.md` — 锁定决策与 UC 草案  
- `.planning/REQUIREMENTS.md` — EXEC-04

### Secondary (MEDIUM confidence)

- `backend_api_python/tests/test_order_normalizer.py` — 现有 normalizer 测试模式  
- `ib_insync` 0.9.86（PyPI `pip index versions`）

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — 与仓库依赖及现有测试风格一致  
- Architecture: **HIGH** — 与 HEAD 源码一致；工作树删除文件为 **环境风险**  
- Pitfalls: **MEDIUM-HIGH** — 类型与缓存行为已对照源码  

**Research date:** 2026-04-11  
**Valid until:** ~30 days（测试代码结构）；IB 对齐算法随 `client.py` 变更需重验证  

---

*Phase 8 — quantity-normalization-ib-alignment*
