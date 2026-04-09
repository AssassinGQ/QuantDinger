# Phase 2: Forex contract creation (IDEALPRO) - Context

**Gathered:** 2026-04-09
**Status:** Ready for planning

<domain>
## Phase Boundary

修改 `IBKRClient._create_contract`，当 `market_type="Forex"` 时创建 `ib_insync.Forex` 合约（secType=CASH, exchange=IDEALPRO），而非 `ib_insync.Stock`。确保 USStock 和 HShare 合约创建路径不受影响。

</domain>

<decisions>
## Implementation Decisions

### 合约构造方式
- 使用 `ib_insync.Forex(pair=ib_symbol)` 构造 Forex 合约
- `ib_symbol` 来自 Phase 1 的 `normalize_symbol` 返回值（6 字母 pair，如 `"EURUSD"`）
- `Forex(pair='EURUSD')` 内部自动拆分为 `symbol='EUR'`, `currency='USD'`, `exchange='IDEALPRO'`
- 不使用显式拆分写法 `Forex(symbol='EUR', currency='USD', exchange='IDEALPRO')`——冗余且 Phase 1 已对齐

### 未知 market_type 防御
- `_create_contract` 收到未知/不支持的 `market_type` 时 **抛出 ValueError**
- 明确报错信息，包含收到的 market_type 值
- 不静默降级为 Stock——与 Phase 1 的 `normalize_symbol` 错误处理策略一致
- **必须确认**：`_create_contract` 的所有调用方（`place_market_order`、`get_quote` 等）有 try/except 保护，ValueError 只导致当次请求失败，不会崩溃整个服务进程
- 研究阶段需验证调用链的异常捕获

### 分支结构
- `_create_contract` 内部根据 `market_type` 分支：
  - `"Forex"` → `ib_insync.Forex(pair=ib_symbol)`
  - `"USStock"` → `ib_insync.Stock(symbol=ib_symbol, exchange=exchange, currency=currency)`（现有逻辑）
  - `"HShare"` → `ib_insync.Stock(symbol=ib_symbol, exchange=exchange, currency=currency)`（现有逻辑）
  - `else` → `raise ValueError(f"Unsupported market_type: {market_type}")`

### Claude's Discretion
- 是否需要将 `exchange` 和 `currency` 参数也传给 `Forex()` 构造函数（`pair=` 已包含全部信息，但是否显式传 exchange 作为双重保险）
- 测试中是否需要 mock `ib_insync.Forex` 类来验证参数传递
- 现有 USStock/HShare 的 `Stock(...)` 调用是否需要显式判断 market_type 而非依赖 else

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### IBKR 交易代码
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_create_contract` 方法（第 780-783 行），以及所有调用方（第 962, 1032, 1097, 1302 行）的异常捕获
- `backend_api_python/app/services/live_trading/ibkr_trading/symbols.py` — Phase 1 已修改，`normalize_symbol` Forex 返回 `(pair_6char, "IDEALPRO", quote_currency)`

### Phase 1 产出
- `.planning/phases/01-forex-symbol-normalization/01-CONTEXT.md` — 返回值设计决策（对 IBKR 友好优先）
- `backend_api_python/tests/test_ibkr_symbols.py` — Phase 1 测试，Phase 2 不应破坏

### 研究
- `.planning/research/STACK.md` — ib_insync Forex 合约构造方式
- `.planning/research/ARCHITECTURE.md` — IBKRClient 架构和调用链

### 测试
- `backend_api_python/tests/test_ibkr_client.py` — 现有 IBKR 客户端测试（93 个），Phase 2 不应引入回归

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `normalize_symbol` 已完成 Forex 分支（Phase 1）——`_create_contract` 无需再做 symbol 解析
- `_qualify_contract_async` 方法已存在，Phase 3 会用于 Forex 合约验证

### Established Patterns
- `_create_contract(symbol, market_type)` 签名不变
- 返回 ib_insync 合约对象（Stock 或 Forex），调用方不区分类型
- `_ensure_ib_insync()` 在创建合约前确保库已加载

### Integration Points
- `_create_contract` 被 4 个方法调用：`place_market_order`（962）、`place_limit_order`（1032）、`get_quote`（1097）、`is_market_open`（1302）
- 所有调用方需要能处理 Forex 合约对象（验证异常捕获链）

</code_context>

<specifics>
## Specific Ideas

- `_create_contract` 的改动很小（3 行变 5-6 行），核心是加一个 `if market_type == "Forex"` 分支
- `ib_insync.Forex` 和 `ib_insync.Stock` 都继承自 `Contract`，下游代码（qualify、place_order）不需要区分类型

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-forex-contract-creation-idealpro*
*Context gathered: 2026-04-09*
