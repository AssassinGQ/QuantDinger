# Requirements: QuantDinger IBKR Forex

**Defined:** 2026-04-09
**Core Value:** 策略系统发出的 Forex 交易信号能正确通过 IBKRClient 在 IDEALPRO 上执行，从信号到成交的完整链路畅通

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### 合约与路由 (Contract & Routing)

- [ ] **CONT-01**: IBKRClient._create_contract 根据 market_type="Forex" 创建 ib_insync.Forex 合约（secType=CASH, exchange=IDEALPRO）
- [x] **CONT-02**: normalize_symbol 支持 Forex 符号格式（EURUSD, EUR.USD, EUR/USD）解析为 base+quote
- [ ] **CONT-03**: Forex 合约通过 qualifyContracts 验证，正确获取 conId 和 localSymbol
- [ ] **CONT-04**: IBKRClient.supported_market_categories 包含 "Forex"，PendingOrderWorker 的 validate_market_category 放行

### 交易执行 (Trading Execution)

- [ ] **EXEC-01**: IBKRClient.place_market_order 可对 Forex 合约下市价单（MarketOrder + totalQuantity 基础货币单位）
- [ ] **EXEC-02**: map_signal_to_side 支持 Forex 双向交易（open_long→BUY, close_long→SELL, open_short→SELL, close_short→BUY）
- [ ] **EXEC-03**: _get_tif_for_signal 有 Forex 专属分支，根据 paper 验证结果设定正确的 TIF（DAY/IOC/GTC）
- [ ] **EXEC-04**: 数量处理复用 ForexNormalizer（整数取整）+ _align_qty_to_contract（IBKR sizeIncrement 对齐）

### 运行时支持 (Runtime Support)

- [ ] **RUNT-01**: is_market_open 对 Forex 合约使用 IBKR liquidHours 判断交易时间（24/5 特性）
- [ ] **RUNT-02**: 成交/仓位/PnL 事件回调正确处理 Forex 合约的数据（symbol key、数量、币种）
- [ ] **RUNT-03**: 策略可通过配置 market_category=Forex + exchange_id=ibkr-paper/ibkr-live 触发 Forex 自动交易

### 前端适配 (Frontend)

- [ ] **FRNT-01**: 策略创建/编辑页面，当 market_category=Forex 时，交易所选择列表包含 ibkr-paper 和 ibkr-live（不仅限于 MT5）

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### 高级订单 (Advanced Orders)

- **ADV-01**: 支持 Forex 限价单（LimitOrder）
- **ADV-02**: 支持 cashQty 下单方式（按报价货币金额下单）
- **ADV-03**: 算法订单（TWAP 等）

### 风控与监控 (Risk & Monitoring)

- **RISK-01**: Forex 保证金使用率监控
- **RISK-02**: 多币种对冲功能

### 前端 (Frontend)

- **UI-01**: 前端 UI 适配 Forex 交易展示
- **UI-02**: 交易助手路由区分 Forex 走 IBKR 还是 MT5

## Out of Scope

| Feature | Reason |
|---------|--------|
| ForexNormalizer 最小下单量检查 | 依赖 IBKR 拒单和 _align_qty_to_contract 兜底，保持简洁 |
| MT5 Forex 相关改动 | MT5 已有独立 Forex 实现，不在本项目范围 |
| 前端 UI 改动 | 纯后端功能扩展，前端 v2 再做 |
| Forex 专用策略类型 | 复用现有策略框架，不新建策略类型 |
| FXCONV 货币转换订单 | 非策略交易路径，与 IDEALPRO 现货交易无关 |
| 止损/止盈/括号订单 | v1 仅市价单 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONT-01 | Phase 2 | Pending |
| CONT-02 | Phase 1 | Complete |
| CONT-03 | Phase 3 | Pending |
| CONT-04 | Phase 4 | Pending |
| EXEC-01 | Phase 7 | Pending |
| EXEC-02 | Phase 5 | Pending |
| EXEC-03 | Phase 6 | Pending |
| EXEC-04 | Phase 8 | Pending |
| RUNT-01 | Phase 9 | Pending |
| RUNT-02 | Phase 10 | Pending |
| RUNT-03 | Phase 11 | Pending |
| FRNT-01 | Phase 12 | Pending |

**Coverage:**
- v1 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-09*
*Last updated: 2026-04-09 after roadmap creation*
