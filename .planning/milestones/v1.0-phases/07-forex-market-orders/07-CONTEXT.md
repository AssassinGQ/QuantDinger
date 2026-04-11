# Phase 7: Forex market orders - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

`place_market_order` 能够为 Forex 合约正确提交市价单，`totalQuantity` 以基础货币单位计。所有底层构建块（contract 创建、qualify、信号映射、TIF）已在前序 Phase 就位，Phase 7 的重点是**补充集成测试**确保端到端路径正确，并处理 Forex 特有的 qty=0 错误提示优化。

**Requirement:** EXEC-01

**Depends on:** Phase 6 (Forex TIF = IOC, paper trading 已验证)

**关键事实:** Phase 6 的 paper trading 验证（EURUSD 20000 buy/sell on DUQ123679）已经证明 `place_market_order` 的 Forex 路径可以工作。Phase 7 是补充测试和锁定行为。

</domain>

<decisions>
## Implementation Decisions

### 数量语义（用户确认：保持现状）

- **totalQuantity 以基础货币单位计**（如 20000 EUR），与 IBKR IDEALPRO 约定一致。
- **ForexNormalizer 只检查 > 0**，不加最小下单量拦截（与项目 Out of Scope 一致）。
- **_align_qty_to_contract 从 ContractDetails.sizeIncrement 对齐**，复用现有两层机制。
- **最小下单量由 IBKR 服务端拒单兜底**（主流货币对约 20000 基础货币）。

### 测试覆盖（用户确认：完整 mock 集成 + 三货币对）

- **完整 mock 集成测试**：覆盖 contract 创建 → qualify → _align_qty_to_contract → MarketOrder 构造 → placeOrder 全路径。
- **三个货币对**：EURUSD（主流）+ 交叉盘（如 GBPJPY）+ 贵金属（如 XAUUSD），确保不同类型 Forex pair 都正确处理。
- **注意不要过度 mock**：测试应验证真实行为，不要 mock 过多导致只测了 mock 本身。参考现有 `TestTifDay` 和 `TestTifForexPolicy` 的 mock 粒度。
- **USStock/HShare 回归测试**：确认现有下单路径不被 Forex 改动影响。

### 异常处理

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

</decisions>

<specifics>
## Specific Ideas

### 实施约束（延续项目惯例）

- 每个 task 需有**明确用例与规格**；**全量 `pytest tests/`** 作为每个 task 的 verify 组成部分（无 `| head` / `| tail` 管道，使用 `--tb=line`）。
- **不要过度 mock**：测试验证真实行为，mock 粒度参考 `TestTifForexPolicy`。

### 建议用例规格（供 07-01-PLAN 引用）

**下单全路径（mock IB）：**
- **UC-M1:** `place_market_order("EURUSD", "buy", 20000.0, "Forex")` → 成功，MarketOrder.tif == "IOC"，contract.secType == "CASH"
- **UC-M2:** `place_market_order("GBPJPY", "sell", 50000.0, "Forex")` → 成功，验证交叉盘路径
- **UC-M3:** `place_market_order("XAUUSD", "buy", 10.0, "Forex")` → 成功，验证贵金属路径

**错误路径：**
- **UC-E1:** `place_market_order("INVALID", "buy", 20000.0, "Forex")` → qualify 失败，错误消息包含 "Forex"
- **UC-E2:** `_align_qty_to_contract` 返回 0 → 失败，错误消息包含 Forex 相关提示

**回归：**
- **UC-R1:** `place_market_order("AAPL", "buy", 100.0, "USStock")` → 行为不变
- **REGR-01:** `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` 全绿

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 核心实现
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `place_market_order`（~1063–1131 行）、`_create_contract`（~801–808 行）、`_qualify_contract_async`、`_validate_qualified_contract`、`_align_qty_to_contract`、`_get_tif_for_signal`（~134–151 行）
- `backend_api_python/app/services/live_trading/ibkr_trading/symbols.py` — `normalize_symbol` Forex 分支（~51–58 行）
- `backend_api_python/app/services/live_trading/order_normalizer/forex.py` — `ForexNormalizer`（normalize + check）

### Runner 集成
- `backend_api_python/app/services/live_trading/runners/stateful_runner.py` — `execute` 调用 `place_market_order`（~77–89 行）

### 测试
- `backend_api_python/tests/test_ibkr_client.py` — `TestTifForexPolicy`（~668–713 行，Phase 6 Forex TIF + 集成测试参考）、`TestTifDay`（~646–665 行）

### 项目文档
- `.planning/REQUIREMENTS.md` — **EXEC-01**
- `.planning/ROADMAP.md` — Phase 7 成功标准

### 先前 Phase
- `.planning/phases/06-tif-policy-for-forex/06-CONTEXT.md` — Forex TIF = IOC 决策
- `.planning/phases/06-tif-policy-for-forex/06-VERIFICATION.md` — Paper trading 验证结果（EURUSD buy/sell on DUQ123679）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`place_market_order` Forex 路径已完整**：contract 创建（Phase 2）→ qualify（Phase 3）→ TIF（Phase 6）→ MarketOrder 构造 → placeOrder。无需新增生产代码分支，只需测试锁定。
- **`TestTifForexPolicy` mock 模式**：已有 `@patch` + `_make_client_with_mock_ib` + 检查 `placed_order.tif` 的测试基础设施，可复用于 Phase 7 的全路径测试。
- **`ForexNormalizer`**：已有 `math.floor` + `> 0` 检查，无需改动。

### Established Patterns
- **fire-and-forget 下单模式**：`place_market_order` 提交订单后立即返回 `LiveOrderResult(status="Submitted")`，不等待成交。
- **异步 _do + _submit 模式**：所有 IB 操作通过 `_submit(_do(), timeout=15.0)` 提交到 worker thread。
- **错误已包含 market_type**：`f"Invalid {market_type} contract: {symbol}"` 等。

### Integration Points
- **`_align_qty_to_contract`**：Forex qty=0 场景需要优化错误消息。
- **Phase 10 依赖**：本 Phase 不处理 fills/position 回调，仅确保订单提交正确。仓位记录以 IBKR 回调为准。

</code_context>

<deferred>
## Deferred Ideas

- **cashQty 下单方式**（按报价货币金额下单，如 "用 23000 USD 买入 EUR"）→ v2 ADV-02
- **ForexNormalizer 最小量检查** → 项目 Out of Scope，保持 IBKR 拒单兜底
- **Forex 限价单** → v2 ADV-01

</deferred>

---

*Phase: 07-forex-market-orders*
*Context gathered: 2026-04-10*
