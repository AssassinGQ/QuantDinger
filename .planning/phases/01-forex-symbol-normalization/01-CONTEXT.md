# Phase 1: Forex symbol normalization - Context

**Gathered:** 2026-04-09
**Status:** Ready for planning

<domain>
## Phase Boundary

让 `normalize_symbol` 正确解析 Forex 符号为 IB 合约所需的参数格式，确保 Forex 符号不会被错误当成美股 ticker 处理。同时扩展 `parse_symbol` 和 `format_display_symbol` 支持 Forex。

</domain>

<decisions>
## Implementation Decisions

### 输入格式
- QuantDinger 数据库中 Forex symbol 统一为 **6 字母大写连写**：`EURUSD`、`XAUUSD`、`GBPJPY` 等
- 数据库验证：`qd_strategies_trading` 表中所有 `market_category='Forex'` 的记录 symbol 均为此格式
- 现有品种包括：AUDUSD, EURUSD, GBPUSD, USDJPY, XAGUSD, XAUUSD（策略），以及 CADJPY, CHFJPY, EURCHF, EURJPY, GBPAUD, GBPJPY, USDCAD, USDCHF（K线数据）
- 也应兼容 `EUR.USD`、`EUR/USD`、`eurusd` 等分隔/小写格式（strip 分隔符 + 转大写）

### 返回值设计
- **原则：对 IBKR 友好优先**
- `ib_insync.Forex(pair='EURUSD')` 要求 6 字母 pair 字符串
- `normalize_symbol` 对 Forex 返回 `(pair_6char, "IDEALPRO", quote_currency)` 格式
- quote_currency 从 pair 后 3 位提取（如 EURUSD → USD，USDJPY → JPY）
- `_create_contract` 拿到返回值后用 `Forex(pair=ib_symbol)` 构造合约

### 异常处理
- `market_type="Forex"` 但 symbol 格式异常（不是 6 字母、包含非法字符等）时 **抛出 ValueError**
- 明确报错信息，让当次请求失败
- 不静默降级为美股——这是最大风险点（当前 else 分支默认走美股）
- 不导致整个服务崩溃

### Claude's Discretion
- `parse_symbol` 自动检测 Forex 的具体逻辑（可参考 MT5 的 `FOREX_PAIRS` 集合或 6 字母全字母规则）
- `format_display_symbol` 对 Forex 的显示格式（建议 `EUR.USD` 点分隔，与 IBKR `localSymbol` 一致）
- 是否需要额外的辅助函数（如 `split_forex_pair` 提取 base/quote）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### IBKR 交易代码
- `backend_api_python/app/services/live_trading/ibkr_trading/symbols.py` — 当前 normalize_symbol/parse_symbol/format_display_symbol 实现（只有 USStock + HShare）
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — _create_contract 调用 normalize_symbol 的方式（第 780-783 行）

### MT5 参考实现
- `backend_api_python/app/services/live_trading/mt5_trading/symbols.py` — MT5 Forex symbol 处理参考（FOREX_PAIRS 集合、分隔符 strip 逻辑、parse_symbol 自动检测）

### 测试
- `backend_api_python/tests/test_ibkr_client.py` — 现有 IBKR 客户端测试
- `backend_api_python/tests/test_exchange_engine.py` — 交易引擎测试

### 研究
- `.planning/research/STACK.md` — ib_insync Forex 合约构造方式
- `.planning/research/PITFALLS.md` — symbol 格式相关陷阱（PITFALL 1-2: Stock/SMART 误路由、pair 编码不一致）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `mt5_trading/symbols.py` 的 `FOREX_PAIRS` 集合：包含主要/交叉/异域货币对、贵金属、指数，可直接参考或部分复用
- `mt5_trading/symbols.py` 的分隔符清洗逻辑：`replace("/", "").replace("-", "").replace("_", "").replace(" ", "")`

### Established Patterns
- `normalize_symbol(symbol, market_type)` 返回 `Tuple[str, str, str]`（ib_symbol, exchange, currency）——必须保持这个签名
- `parse_symbol(symbol)` 返回 `Tuple[str, Optional[str]]`（clean_symbol, market_type）——检测逻辑
- `format_display_symbol(ib_symbol, exchange)` 返回显示字符串

### Integration Points
- `IBKRClient._create_contract` 是唯一消费者——拿到 normalize_symbol 返回值后构造合约
- `IBKRClient.is_market_open`、`place_market_order`、`place_limit_order`、`get_quote` 都间接依赖

</code_context>

<specifics>
## Specific Ideas

- 数据库中 `market_type = 'spot'` 对应 Forex，但传入 normalize_symbol 的参数名是 `market_type`，实际传的值来自策略的 `market_category`（值为 `"Forex"`），由 StatefulClientRunner 解析。这个映射关系在 Phase 4/5 处理，Phase 1 只需确保 `market_type="Forex"` 时正确解析即可。

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-forex-symbol-normalization*
*Context gathered: 2026-04-09*
