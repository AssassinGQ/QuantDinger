# Phase 3: Contract qualification - Context

**Gathered:** 2025-04-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Forex contracts qualify like equities: stable `conId`, `localSymbol`, and details for sizing and display. After `qualifyContracts` (or async equivalent), Forex contracts carry a valid `conId` and IB-expected `localSymbol` (e.g. `EUR.USD`). Qualification failure surfaces as a clear error; the system does not proceed with an unqualified Forex contract.

**Requirement:** CONT-03

</domain>

<decisions>
## Implementation Decisions

### Qualification 重试逻辑
- **保持现状，和 Stock 一致**
- `_qualify_contract_async` 本身不做重试（当前实现只做一次 `qualifyContractsAsync` 调用）
- `is_rth` 调用方已有 `_RTH_QUALIFY_RETRIES` 重试机制——Forex 自动继承
- 下单方法（`place_market_order`、`place_limit_order`）和 `get_quote` 不加重试——与现有 Stock 行为一致

### 错误消息增强
- qualify 失败的错误消息**包含市场类型**，让用户更容易定位问题
- 当前 4 个调用方返回 `"Invalid contract: {symbol}"`，改为带 `market_type` 的格式
- 示例：`"Invalid Forex contract: EURUSD"` 或 `"Invalid USStock contract: AAPL"`
- 所有市场类型统一加，不只是 Forex

### Post-qualify 防御性检查（`_validate_qualified_contract` 新方法）
- **新建 `_validate_qualified_contract(self, contract, market_type: str) -> tuple[bool, str]` 方法**
- 放在 `_qualify_contract_async` 之后、业务逻辑之前，由 4 个调用方调用
- 检查内容：
  1. `conId` 非零——下游的 `_align_qty_to_contract` 缓存和持仓管理依赖 `conId`
  2. `secType` 匹配预期——`Forex` → `"CASH"`，`USStock`/`HShare` → `"STK"`
- 失败时返回 `(False, reason)`，调用方返回友好错误，不崩溃服务
- `_qualify_contract_async` 保持纯粹（只关心 qualify 成功/失败），不引入业务类型感知

### 测试字段验证范围
- **运行时检查**（`_validate_qualified_contract` 内）：
  - `conId` 非零
  - `secType` 匹配预期（CASH / STK）
- **测试断言**（mock 测试中验证，不加运行时检查）：
  - `localSymbol` 格式正确（Forex 为 `"EUR.USD"` 等点分隔）
  - `exchange` 为 `"IDEALPRO"`

### Claude's Discretion
- `_validate_qualified_contract` 的具体实现细节（如 `expected_sec_types` 映射表结构）
- 错误消息的精确措辞
- 测试 mock 的具体实现方式（如何模拟 qualify 后字段填充）
- 是否需要为 `_validate_qualified_contract` 单独创建测试类或并入现有测试类

</decisions>

<specifics>
## Specific Ideas

### 实施约束（用户明确要求）
- **每个 task 必须有明确的用例及其规格（use cases with specifications）**
- **全量测试套件（~840 个测试）必须作为每个 task 的 verify 步骤的一部分**
- TDD 方法：RED（写失败测试）→ GREEN（实现代码使测试通过）

### 测试用例全景（9 个用例 + 1 个回归）

**UC-1: Forex 合约 qualify 成功 — 字段填充**
- 前置：`Forex(pair='EURUSD')` 创建合约
- 操作：mock `qualifyContractsAsync` 返回成功（填充 conId=12087792, secType='CASH', localSymbol='EUR.USD', exchange='IDEALPRO'）
- 断言：`_qualify_contract_async` 返回 `True`，合约字段被正确填充

**UC-2: Forex 合约 qualify 失败 — 返回 False**
- 前置：`Forex(pair='XXXYYY')` 创建不存在的合约
- 操作：mock `qualifyContractsAsync` 返回空列表
- 断言：`_qualify_contract_async` 返回 `False`

**UC-3: Forex 合约 qualify 异常 — 不崩溃**
- 前置：任意 Forex 合约
- 操作：mock `qualifyContractsAsync` 抛出异常
- 断言：`_qualify_contract_async` 返回 `False`，日志有 warning

**UC-4: `_validate_qualified_contract` — Forex secType 正确**
- 前置：qualified Forex 合约，secType='CASH', conId=12087792
- 断言：返回 `(True, "")`

**UC-5: `_validate_qualified_contract` — Forex secType 不匹配**
- 前置：qualify 后 secType='STK'（非预期），market_type='Forex'
- 断言：返回 `(False, "Expected secType=CASH for Forex, got STK")`

**UC-6: `_validate_qualified_contract` — conId 为 0**
- 前置：qualify 后 conId=0
- 断言：返回 `(False, "conId is 0 after qualification...")`

**UC-7: 错误消息包含市场类型**
- 前置：Forex 合约 qualify 失败
- 操作：通过 `place_market_order` 调用路径
- 断言：返回消息包含 "Forex"

**UC-8: Stock 合约回归 — qualify 行为不变**
- 前置：`Stock(symbol='AAPL', exchange='SMART', currency='USD')`
- 操作：mock `qualifyContractsAsync` 成功
- 断言：`_validate_qualified_contract` 对 secType='STK' 返回 `(True, "")`

**UC-9: HShare 合约回归 — qualify 行为不变**
- 前置：`Stock(symbol='700', exchange='SEHK', currency='HKD')`
- 操作：mock `qualifyContractsAsync` 成功
- 断言：`_validate_qualified_contract` 对 secType='STK' 返回 `(True, "")`

**REGR-01: 全量测试套件回归**
- 操作：运行全部 ~840 个测试
- 断言：全部通过

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 核心实现文件
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_qualify_contract_async`（行 790-795）、`_align_qty_to_contract`（行 799-826）、4 个调用方（行 ~967/1038/1103/1308）
- `backend_api_python/app/services/live_trading/ibkr_trading/symbols.py` — Phase 1 修改的 `normalize_symbol`（Forex 分支返回 `pair_6char, "IDEALPRO", quote_currency`）

### 测试文件
- `backend_api_python/tests/test_ibkr_client.py` — 现有 mock 基础设施（`MockForex`、`_make_mock_ib_insync()`），Phase 2 添加的 `TestCreateContractForex`
- `backend_api_python/tests/test_ibkr_symbols.py` — Phase 1 创建的 symbol 测试

### 先前 Phase Context
- `.planning/phases/01-forex-symbol-normalization/01-CONTEXT.md` — symbol 格式、异常处理策略
- `.planning/phases/02-forex-contract-creation-idealpro/02-CONTEXT.md` — `Forex(pair=ib_symbol)` 构造方式、`_create_contract` 三分支结构、`ValueError` 防御

### 项目文档
- `.planning/REQUIREMENTS.md` — CONT-03: qualifyContracts 解析 Forex 合约的 conId 和 localSymbol
- `.planning/ROADMAP.md` — Phase 3 成功标准

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_qualify_contract_async`（client.py:790-795）：已有的通用 qualify 方法，不区分合约类型，直接调用 `ib.qualifyContractsAsync(contract)`。Forex 合约可以直接通过此方法
- `MockForex`（test_ibkr_client.py）：Phase 2 创建的 Forex mock 类，可复用于 qualify 测试
- `_make_mock_ib_insync()`（test_ibkr_client.py）：mock 工厂，已包含 `MockForex`，可扩展 `qualifyContractsAsync` 的 mock 行为

### Established Patterns
- 调用方错误处理模式：qualify 失败 → 返回 `LiveOrderResult(success=False)` 或 `dict(success=False)`
- 日志模式：`logger.warning("Contract qualification failed: %s", e)`
- 缓存模式：`_lot_size_cache` 按 `conId` 缓存——依赖 qualify 后 `conId` 非零

### Integration Points
- 4 个调用方需要在 qualify 成功后增加 `_validate_qualified_contract` 调用：
  - `is_rth` 内的 `_task()`（行 ~971）
  - `place_market_order` 内的 `_do()`（行 ~1038）
  - `place_limit_order` 内的 `_do()`（行 ~1103）
  - `get_quote` 内的 `_task()`（行 ~1308）
- 错误消息增强需要修改上述 4 个调用方的 qualify 失败分支

</code_context>

<deferred>
## Deferred Ideas

- **Qualify 结果缓存**：同一 Forex 合约短时间内多次 qualify 浪费 API 调用。好想法，但当前 Stock 也没缓存，不在 Phase 3 范围内。记录到后续优化 backlog。

</deferred>

---

*Phase: 03-contract-qualification*
*Context gathered: 2025-04-09*
