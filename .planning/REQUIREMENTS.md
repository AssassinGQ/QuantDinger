# Requirements: QuantDinger v1.1 Tech Debt Cleanup + Limit Orders

**Defined:** 2026-04-11
**Core Value:** 清理 v1.0 遗留技术债务，增加 Forex 限价单和贵金属交易能力，补全 E2E 测试覆盖。

## v1.1 Requirements

### 交易能力增强 (TRADE)

- [ ] **TRADE-01**: IBKRClient 支持 Forex LimitOrder，价格精度使用 ContractDetails.minTick 对齐，TIF 支持 IOC/DAY/GTC
- [ ] **TRADE-02**: 限价单部分成交处理——orderStatus PartiallyFilled 正确更新 remaining，不重复计入 fills/positions
- [ ] **TRADE-03**: 限价单策略自动化——StatefulClientRunner 支持 limit order 信号，PendingOrderWorker 传递 limit price
- [ ] **TRADE-04**: 贵金属合约创建——XAUUSD/XAGUSD 使用正确 secType（CMDTY/SMART 或经 paper qualify 验证的类型），与 Forex CASH/IDEALPRO 分开路由
- [ ] **TRADE-05**: 贵金属交易 E2E 验证——从 API 信号到 IBKR 下单的完整链路测试（mock IBKR），覆盖 qualify + order + callback
- [ ] **TRADE-06**: 限价单交易 E2E 验证——从策略信号到限价单提交的完整链路测试，覆盖正常成交 + 部分成交 + 取消场景

### 基础设施优化 (INFRA)

- [x] **INFRA-01**: `qualifyContractsAsync` 结果按 `(symbol, market_type)` 缓存；Forex / USStock / HShare 各自 TTL 可配（`IBKR_QUALIFY_TTL_*_SEC`，默认 600 秒）；在 qualify 失败、qualify 异常、或该 symbol 的 post-qualify 校验失败时使对应缓存项失效；**IBKR reconnect does not clear the cache**（与按重连清空缓存的早期表述不一致时以 Phase 13 CONTEXT 为准）
- [x] **INFRA-02**: USStock / HShare / Forex 统一为 IOC（八种信号类型）；未知 `market_type` 使用 DAY；TIF 矩阵与 IBKR IOC/SEHK 文档引用（Phase 14）
- [x] **INFRA-03**: order pipeline 中 normalize 在 check 之后、qualify 之前调用，align 在 qualify 之后调用，两者不重复执行

### 测试质量 (TEST)

- [x] **TEST-01**: test_forex_ibkr_e2e.py 中 blueprint prefix 与生产 API 路由一致（消除 /api/strategy/ vs /api/ 差异）
- [ ] **TEST-02**: 前端 HTTP E2E 测试——Vue wizard 创建 Forex+IBKR 策略的 HTTP round-trip 验证（可选 Playwright）

## v2 Requirements (Deferred)

### 高级订单

- **ADV-01**: TIF fallback（IOC 被拒后自动用 DAY 重试）
- **ADV-02**: cashQty 下单方式（指定报价货币金额，IBKR 自动计算数量）

## Out of Scope

| Feature | Reason |
|---------|--------|
| 止损/止盈/括号订单 | 超出当前范围，v2+ |
| MT5 相关改动 | MT5 独立实现，不受影响 |
| FXCONV 货币转换订单 | 非策略交易路径 |
| Forex 专用策略类型 | 复用现有策略框架 |
| ForexNormalizer 最小下单量检查 | IBKR 拒单兜底 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TRADE-01 | Phase 17 | Pending |
| TRADE-02 | Phase 17 | Pending |
| TRADE-03 | Phase 17 | Pending |
| TRADE-04 | Phase 16 | Pending |
| TRADE-05 | Phase 18 | Pending |
| TRADE-06 | Phase 18 | Pending |
| INFRA-01 | Phase 13 | Complete |
| INFRA-02 | Phase 14 | Complete |
| INFRA-03 | Phase 15 | Complete |
| TEST-01 | Phase 13 | Complete |
| TEST-02 | Phase 18 | Pending |

**Coverage:**
- v1.1 requirements: 11 total
- Mapped to phases: 11
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-11*
*Last updated: 2026-04-11 — INFRA-02 complete (Phase 14-01)*
