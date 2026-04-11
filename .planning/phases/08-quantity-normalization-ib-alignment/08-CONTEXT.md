# Phase 8: Quantity normalization & IB alignment - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

确保 Forex 数量处理链路（ForexNormalizer + `_align_qty_to_contract`）被显式测试锁定，并对 ForexNormalizer.normalize() 做防御性改造（透传而非 floor）。生产代码改动极少，核心价值是**专项测试覆盖 + normalizer 透传修正**。

**Requirement:** EXEC-04

**Depends on:** Phase 7 (Forex 市价单全路径已验证，UC-M1–M3/UC-E2 已隐式覆盖 normalizer + alignment)

**关键事实:**
- `ForexNormalizer` 和 `_align_qty_to_contract` 已存在且在 Phase 7 的全路径测试中被隐式调用。
- `place_market_order` 中只调用 `check()`，不调用 `normalize()`。`normalize()` 是基类抽象方法的实现，当前为"死代码路径"。
- Phase 8 聚焦**纯 Forex 货币对**（EURUSD、GBPJPY 等），贵金属（XAUUSD 等）归类问题 deferred。

</domain>

<decisions>
## Implementation Decisions

### ForexNormalizer 改造（用户确认）

- **normalize() 改为透传**：`return raw_qty`（不再 `math.floor`），避免未来有人调用时截断贵金属等小数量（如 XAUUSD 0.5 oz）。数量取整完全由 `_align_qty_to_contract` 的 sizeIncrement 对齐负责。
- **check() 保持只检查 > 0**：与项目 Out of Scope（不加最小下单量检查）一致。IBKR 服务端拒单兜底。
- **normalize() 不加调用**：当前 `place_market_order` / `place_limit_order` 只调用 `check()`，这个行为不变。normalize() 作为基类抽象方法的实现存在，但不纳入主线调用链。

### 测试覆盖（用户确认：全面）

- **ForexNormalizer 全面边界测试**：负数、极小小数(0.001)、极大值(1e9)、浮点精度(20000.99)、多货币对(EURUSD/GBPJPY)的 normalize 输入输出。
- **_align_qty_to_contract 完整矩阵**：
  - 恰好整除（50000 / sizeIncrement=25000 → 50000）
  - 不整除但 >0（30000 / 25000 → 25000）
  - increment=1（无对齐效果，原量返回）
  - increment 获取失败（reqContractDetailsAsync 异常 → 回退原量）
  - qty=0 场景已由 Phase 7 UC-E2 覆盖，可引用但不重复
- **缓存测试**：验证 `_lot_size_cache` 第二次调用命中缓存、不再查询 `reqContractDetailsAsync`。

### 回归策略

- **全量 `pytest tests/` 即可**（REGR-01）：现有 TestUSStockNormalizer(8 tests) + TestHShareNormalizer(14 tests) + TestForexNormalizer(3 tests) + Phase 7 UC-R1/UC-R2 已充分覆盖。不需要额外交叉测试。

### Claude's Discretion

- 测试类命名和组织方式（扩展现有 TestForexNormalizer 还是新建类）。
- _align_qty_to_contract 测试中 mock 的具体参数值。
- 缓存测试的验证方式（call_count 断言 vs side_effect 追踪）。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 核心实现
- `backend_api_python/app/services/live_trading/order_normalizer/__init__.py` — `OrderNormalizer` 基类、`get_normalizer` 工厂、`CryptoNormalizer`
- `backend_api_python/app/services/live_trading/order_normalizer/forex.py` — `ForexNormalizer`（normalize + check，**Phase 8 要改 normalize 为透传**）
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_align_qty_to_contract`（~835–862 行）、`_lot_size_cache`（类变量）、`place_market_order`（~1063–1132 行，check + align 调用链）

### 现有测试
- `backend_api_python/tests/test_order_normalizer.py` — `TestForexNormalizer`（3 tests）、`TestUSStockNormalizer`（8 tests）、`TestHShareNormalizer`（14 tests）、`TestGetNormalizer`
- `backend_api_python/tests/test_ibkr_symbols.py` — `TestNormalizeSymbolForex`（symbol 解析，非数量处理）

### Phase 7 已有覆盖（避免重复）
- Phase 7 UC-E2：sizeIncrement=25000 + qty=10000 → 0 + Forex IDEALPRO 提示
- Phase 7 UC-M1–M3：EURUSD/GBPJPY/XAUUSD 全路径（隐式 normalizer + alignment）
- Phase 7 UC-E3：qty=0 → ForexNormalizer check() 拦截

### 项目文档
- `.planning/REQUIREMENTS.md` — **EXEC-04**
- `.planning/ROADMAP.md` — Phase 8 成功标准

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`TestForexNormalizer`**（`test_order_normalizer.py`）：已有 3 个测试（normalize/check_valid/check_zero），可以直接扩展。
- **`_make_client_with_mock_ib()`**（测试 helper）：用于 _align_qty_to_contract 测试，可 mock `reqContractDetailsAsync`。
- **`IBKRClient._lot_size_cache`**：类级别 dict，需要在测试间 `.clear()` 避免交叉污染（Phase 7 UC-E2 已建立此模式）。

### Established Patterns
- **normalizer 测试模式**：直接实例化 normalizer 类，调用 normalize()/check()，断言返回值。无需 mock。
- **_align_qty_to_contract 测试**需要 mock `client._ib.reqContractDetailsAsync`，返回 `types.SimpleNamespace(sizeIncrement=..., minSize=...)` 而非裸 MagicMock（Phase 7 research 明确指出）。

### Integration Points
- `place_market_order` 中 check() 在 async _do() 外面调用，_align 在 _do() 里面调用。两者不在同一层级。
- normalizer 变更（透传）不影响 `place_market_order` 因为它只调用 check()。

</code_context>

<specifics>
## Specific Ideas

### 实施约束（延续项目惯例）

- 每个 task 需有**明确用例与规格**（UC-xxx）；**全量 `pytest tests/`** 作为每个 task 的 verify 组成部分。
- **不要过度 mock**：normalizer 测试不需要 mock；_align 测试仅 mock `reqContractDetailsAsync`。

### 建议用例规格（供 08-01-PLAN 引用）

**ForexNormalizer 边界（单元测试）：**
- **UC-N1:** `normalize(20000.99, "EURUSD")` → `20000.99`（透传）
- **UC-N2:** `normalize(0.5, "EURUSD")` → `0.5`（透传，不再 floor 为 0）
- **UC-N3:** `normalize(0.001, "EURUSD")` → `0.001`（极小值透传）
- **UC-N4:** `normalize(1e9, "EURUSD")` → `1e9`（极大值透传）
- **UC-N5:** `check(-5, "EURUSD")` → `(False, "Quantity must be positive...")`
- **UC-N6:** `check(0.001, "EURUSD")` → `(True, "")`（极小正数通过）

**_align_qty_to_contract（mock IB）：**
- **UC-A1:** qty=50000, sizeIncrement=25000 → aligned=50000（恰好整除）
- **UC-A2:** qty=30000, sizeIncrement=25000 → aligned=25000（不整除但 >0）
- **UC-A3:** qty=20000, sizeIncrement=1 → aligned=20000（increment=1 无效果）
- **UC-A4:** `reqContractDetailsAsync` 抛异常 → 回退原量 20000（容错）
- **UC-A5:** 第二次调用相同 conId → `reqContractDetailsAsync.call_count == 1`（缓存命中）

**回归：**
- **REGR-01:** `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` 全绿

</specifics>

<deferred>
## Deferred Ideas

- **贵金属合约归类（XAUUSD/XAGUSD/XAUEUR）**：IBKR 合约信息显示 XAUUSD 是 "Commodity (OTC Derivative)"（conId=69067924），可能需要 `secType='CMDTY'` 而非 `CASH`。当前代码将其归入 `KNOWN_FOREX_PAIRS` 并用 `ib_insync.Forex(pair=...)` 创建合约。需要：1) 在 paper trading 上实际验证 XAUUSD qualify 结果；2) 如果确认需要 CMDTY，则从 `KNOWN_FOREX_PAIRS` 分离，新增 market_type="Metal" 或类似分支。**建议新增独立 Phase（如 Phase 12.1）处理。**
- **normalize() 在主线的调用时机** — 当前 `place_market_order` 不调用 `normalize()`，如果未来需要在提交前做预处理（如贵金属小数对齐），可考虑在 check() 之后增加 normalize() 调用。不在本 Phase 处理。

</deferred>

---

*Phase: 08-quantity-normalization-ib-alignment*
*Context gathered: 2026-04-10*
