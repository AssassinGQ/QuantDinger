# Phase 10: Fills, position & PnL events - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

成交/仓位/PnL 事件回调正确处理 Forex 合约数据——symbol key 使用 `localSymbol`（EUR.USD）、DB 存储真实合约元数据（secType/exchange/currency）、`ibkr_save_pnl` NameError bug 修复。测试覆盖 Forex 合约的 fill → position → PnL 全生命周期。

</domain>

<decisions>
## Implementation Decisions

### 改动范围总览

Phase 10 有 **3 类改动**：
1. **DB 表 `qd_ibkr_pnl_single` 加 3 列**（sec_type, exchange, currency）+ 事件回调存入真实值 + `get_positions()` 读出
2. **`ibkr_save_pnl` NameError 修复** — 删除 3 行引用未定义变量的死代码
3. **`_conid_to_symbol` 统一用 `localSymbol or symbol`** — 所有产品类型（含 Forex）symbol key 一致

### 决策 1: DB 表加列 + get_positions() 从 DB 读真实元数据

- `qd_ibkr_pnl_single` 新增 3 列：
  - `sec_type VARCHAR(20) DEFAULT ''` — 如 'STK', 'CASH'
  - `exchange VARCHAR(50) DEFAULT ''` — 如 'SMART', 'IDEALPRO'
  - `currency VARCHAR(10) DEFAULT ''` — 如 'USD', 'EUR'
- `_ensure_tables()` 中使用 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 追加列（兼容已有表）。
- `ibkr_save_position()` 新增 `sec_type`/`exchange`/`currency` 参数，INSERT 和 UPDATE 覆盖。
- `_on_position` 和 `_on_update_portfolio` 回调中从 `position.contract.secType` / `.exchange` / `.currency` 提取真实值传入。
- `_on_pnl_single` 不变（没有 contract 引用；元数据由 position/portfolio 事件先行填入）。
- `ibkr_get_positions` 的 SELECT 增加这 3 列。
- `get_positions()` 从 DB 行读取 `sec_type`/`exchange`/`currency`，取代硬编码 `STK`/`SMART`/`USD`。缺省 fallback 保留原值（兼容旧数据）。

### 决策 2: ibkr_save_pnl NameError 修复

- `records.py` 中 `ibkr_save_pnl()` 函数体内 3 行 clamp 代码引用了未定义变量 `position`/`avg_cost`/`value`，但 SQL 不使用这些字段——是死代码遗留。
- **修复方式**：删除这 3 行（`position = max(...)`, `avg_cost = max(...)`, `value = max(...)`），保留 `daily_pnl`/`unrealized_pnl`/`realized_pnl` 的 clamp。
- 新增测试确保 `ibkr_save_pnl()` 不再 NameError（mock DB，断言不抛异常）。

### 决策 3: _conid_to_symbol 统一用 localSymbol

- 所有使用 `contract.symbol` 作为 symbol label 的位置改为 `contract.localSymbol or contract.symbol or ""`。
- 影响位置：`_on_position`、`_on_update_portfolio`（存入 `_conid_to_symbol` 和传给 `ibkr_save_position`）。
- 对股票/港股无影响（`localSymbol` 与 `symbol` 一致，如 AAPL/700）。
- 对 Forex：从存 `EUR` 改为存 `EUR.USD`，与 Phase 1 的 display format 和策略 symbol 对齐。
- Fallback `or contract.symbol` 保证 qualify 前的极端场景不丢数据。

### 测试策略

- **纯 records 层**：mock DB，测试 `ibkr_save_pnl` 不 NameError、`ibkr_save_position` 接受新列参数。
- **事件回调层**：mock `_fire_submit` + `records.*`，构造 Forex 合约（secType=CASH, localSymbol=EUR.USD, exchange=IDEALPRO, currency=USD），验证传入 `ibkr_save_position` 的参数包含正确的 sec_type/exchange/currency 和 localSymbol。
- **get_positions() 层**：mock `ibkr_get_positions` 返回含新列的行，验证输出字典包含真实 secType/exchange/currency。
- **回归**：现有 `test_ibkr_client.py` 和 `test_ibkr_order_callback.py` 全量通过。

### Claude's Discretion

- `ALTER TABLE ADD COLUMN IF NOT EXISTS` 的精确 SQL 语法
- `ibkr_save_position` 新参数的默认值
- 测试用例的具体 ID 和命名
- 是否用 parametrize 覆盖 Forex + Stock 场景

</decisions>

<specifics>
## Specific Ideas

- IBKR Forex 合约：`contract.symbol` = base currency (EUR)，`contract.localSymbol` = EUR.USD，`contract.secType` = CASH，`contract.exchange` = IDEALPRO，`contract.currency` = quote currency (USD)。
- 股票：`contract.symbol` = AAPL = `contract.localSymbol`，`contract.secType` = STK，`contract.exchange` = SMART/NYSE，`contract.currency` = USD。
- `_handle_fill` 使用 `ctx.symbol`（来自下单上下文），不受 `_conid_to_symbol` 影响——fill 路径的 symbol 已经正确。
- `_on_commission_report` 同理使用 `ctx.symbol`，不受影响。
- DB 主键是 `(account, con_id)` — 稳定的合约标识，symbol 只是 label。

</specifics>

<canonical_refs>
## Canonical References

### 事件回调
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_on_position` (line ~615), `_on_update_portfolio` (line ~580), `_on_pnl_single` (line ~725), `_on_pnl` (line ~688), `_handle_fill` (line ~866), `get_positions()` (line ~1300)

### DB records
- `backend_api_python/app/services/live_trading/records.py` — `ibkr_save_pnl` (line ~544), `ibkr_save_position` (line ~582), `ibkr_get_positions` (line ~641), `_ensure_tables` (line ~26)

### 现有测试
- `backend_api_python/tests/test_ibkr_client.py` — `_on_position`, `_on_pnl`, `_on_pnl_single` 测试（records 被 mock）
- `backend_api_python/tests/test_ibkr_order_callback.py` — `_handle_fill` / `_handle_reject` 测试

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_make_mock_ib_insync()` 和 `_make_client_with_mock_ib()` — 可复用构造 mock IB 环境
- `_always_rth` autouse fixture — 在事件回调测试中保持 RTH 始终 open
- `IBKROrderContext(order_id, pending_order_id, strategy_id, symbol, signal_type)` — fill 上下文已包含策略 symbol

### Established Patterns
- 事件回调通过 `_fire_submit` 异步提交 DB 操作
- DB mock 模式：`@patch("app.services.live_trading.records.ibkr_save_position")` 等
- 所有 records 函数的测试使用 mock DB 连接

### Integration Points
- `_conid_to_symbol` dict 被 `_on_position`、`_on_update_portfolio` 填入，被 `_on_pnl_single` 消费。
- `get_positions()` 从 `ibkr_get_positions()` 读 DB 行，展示给前端/API。
- `get_positions_normalized()` 从 `get_positions()` 构造 `PositionRecord`，被 `sync_positions` 消费。

### Bug: ibkr_save_pnl NameError
- `records.py:553-558` — 函数签名只有 4 参数，但体内引用了 `position`/`avg_cost`/`value`（未定义）。
- SQL INSERT 只用 4 字段，这 3 行 clamp 是死代码遗留。
- 修复：删除 3 行死代码。

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 10-fills-position-pnl-events*
*Context gathered: 2026-04-11*
