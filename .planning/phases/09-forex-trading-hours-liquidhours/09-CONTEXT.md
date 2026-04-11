# Phase 9: Forex trading hours (liquidHours) - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

确保 `is_market_open` 对 Forex 合约正确使用 IBKR liquidHours（24/5 特性），周末和节假日行为与 IBKR Forex 时间表匹配，不依赖美股 RTH 日历。测试覆盖 Forex 特有的时间窗口场景（跨日连续交易、维护间隔、周末边界）。

</domain>

<decisions>
## Implementation Decisions

### 代码改动范围
- **生产代码不需要修改**——现有 `is_market_open` → `_create_contract(symbol, market_type="Forex")` → `reqContractDetailsAsync` → `is_rth_check(details, ...)` 的链路已完整支持 Forex。
- 唯一的生产代码改动：Forex 关市错误消息加专属提示（类似 Phase 7 的 qty=0 提示），让用户区分 Forex 24/5 关市和美股 RTH 关市。
- Phase 9 的核心交付物是 **Forex 特有场景的测试覆盖**。

### Forex liquidHours 格式与测试场景
- IBKR Forex liquidHours 格式为跨日连续时段，如 `20260305:1715-20260306:1700`（周日 17:15 EST 开盘 → 次日 17:00 EST 收盘，中间 15 分钟维护间隔）。
- 现有 `parse_liquid_hours` 已能正确解析跨日格式（start/end 各自带日期），但从未被测试。
- 测试场景覆盖：
  - **工作日中间**（周二下午 EST，预期 open）
  - **周五 17:00 后**（当周最后一个交易时段结束，预期 closed）
  - **周六全天**（CLOSED 或无时段，预期 closed）
  - **周日 17:15 后**（新一周首个时段开始，预期 open）
  - **维护间隔**（17:00-17:15，预期 closed）
  - **节假日**（如圣诞节全天 CLOSED，预期 closed）

### 测试货币对覆盖
- **EURUSD**（EST 时区，主要测试对象）
- **GBPJPY** 或其他不同时区的货币对（验证时区解析兼容性）
- **XAGUSD**（贵金属类，验证可能不同的交易时间窗口）

### 测试数据来源
- 使用构造的合理 mock liquidHours 数据（不从 IBKR paper trading 获取真实数据）。
- mock 数据格式基于 IBKR Forex 实际格式构造。

### 周末/节假日边界行为
- **fuse 机制**：保持现有设计，不对 Forex 做特殊处理。周末 48 小时关市如果 liquidHours 包含下周时段，fuse 会是 ~24h（半剩余时间）；如果不包含则 30 分钟后重试。两种都可接受。
- **节假日**：增加测试覆盖（CLOSED 格式），处理方式与现有一致。
- **`suppress_dedup_clear=True` 行为**：对 Forex 周末合适——信号不丢弃，开市后新信号可触发下单。

### 测试层级
- **纯逻辑层**（`trading_hours.py`）：新增 Forex 场景到 `test_trading_hours.py`（跨日解析、24h 时段、周末/节假日/维护间隔、不同时区、XAGUSD）。
- **集成路径**（`IBKRClient.is_market_open`）：新增 Forex 版集成测试到 `test_ibkr_client.py`，mock 完整链路（`_qualify_contract_async`、`reqCurrentTimeAsync`、`reqContractDetailsAsync`）。
- **mock 模式**：复用现有 `_make_mock_ib_insync` + patch 模式（方案 A）。

### Forex 关市提示消息
- 当 `is_market_open` 判定 Forex 关市时，错误消息增加 Forex 专属上下文（如 "Forex 24/5 market — check weekend/maintenance window" 或类似描述），帮助用户区分 Forex 关市原因与美股 RTH 关市。
- 实现位置：`IBKRClient.is_market_open` 中 `is_rth_check` 返回 False 后，根据 `market_type` 追加提示。

### Claude's Discretion
- 具体测试用例 ID 和命名
- mock liquidHours 字符串的精确构造
- Forex 关市提示消息的具体措辞
- 是否用 parametrize 或独立 test 方法覆盖各场景

</decisions>

<specifics>
## Specific Ideas

- IBKR Forex 典型交易周期：周日 17:15 EST → 周五 17:00 EST，中间每日 17:00-17:15 EST 维护间隔。
- GOOGL 策略的 RTH 拦截分析（2026-04-10）确认现有 RTH 机制工作正常：非交易时段正确拦截，交易时段正确放行，fuse 配合 1H 策略频率合理。
- 策略 537（ibkr-live）出现过 `RTH check failed:` 空消息——是 IBKR gateway 连接瞬时问题，不是 RTH 逻辑 bug，但说明错误消息应包含更多上下文（Phase 9 的 Forex 提示改进也间接帮助这类诊断）。

</specifics>

<canonical_refs>
## Canonical References

No external specs — requirements are fully captured in decisions above and the following codebase files:

### RTH 纯逻辑
- `backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py` — `parse_liquid_hours`, `is_rth_check`, fuse 机制
- `backend_api_python/tests/test_trading_hours.py` — 现有 RTH 测试（美股/港股场景，需扩展 Forex）

### RTH 集成路径
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `is_market_open` 方法（line ~995），RTH details cache
- `backend_api_python/tests/test_ibkr_client.py` — `test_is_market_open_returns_false_outside_rth`, `test_is_market_open_returns_true_during_rth`

### 调用链
- `backend_api_python/app/services/live_trading/runners/stateful_runner.py` — `pre_check` → `is_market_open` → `suppress_dedup_clear`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `trading_hours.py`: 完整的纯逻辑模块（`parse_liquid_hours`, `is_rth_check`, `_activate_fuse`, `_resolve_tz`, `clear_cache`），已支持跨日时段和多时区。
- `test_trading_hours.py`: 19 个测试（`TestParseLiquidHours`, `TestResolveTz`, `TestIsRTHCheck`, `TestFuse`），`_make_details` helper 和 `autouse` fixture 可直接复用。
- `test_ibkr_client.py`: `_make_mock_ib_insync()` 和 `_make_client_with_mock_ib()` mock 工厂。

### Established Patterns
- RTH 纯逻辑测试使用 `now` 参数覆盖时间，不依赖真实时钟。
- 集成测试使用 `@patch` + `MagicMock`/`AsyncMock` mock IBKR 交互。
- `_TZ_MAP` 已包含 EST/EDT/JST/HKT/GMT/BST/CET 等常见时区缩写。

### Integration Points
- `IBKRClient.is_market_open` 在判定关市后返回 `(False, f"{sym} is outside RTH (market closed)")`——Phase 9 在此处根据 `market_type` 追加 Forex 专属提示。
- `_create_contract(symbol, market_type="Forex")` 已在 Phase 2 实现，`is_market_open` 调用时自动创建 Forex 合约。

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-forex-trading-hours-liquidhours*
*Context gathered: 2026-04-11*
