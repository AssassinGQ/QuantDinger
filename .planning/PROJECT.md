# QuantDinger - IBKR 数据源

## What This Is

为 `exchange_id = ibkr-live` 的交易策略提供原生 IBKR 数据源，从 Interactive Brokers API 获取 K线和实时报价，替代当前使用的 yfinance/Finnhub。

**Core value**: 实盘交易策略使用与实际下单同一数据源，确保数据一致性。

## Requirements

### Validated

- ✓ IBKRDataSource 类创建 — v1.0
- ✓ get_kline() 实现 — v1.0
- ✓ get_ticker() 实现 — v1.0
- ✓ 连接 IBKR Gateway — v1.0
- ✓ DataSourceFactory 支持 exchange_id — v1.0
- ✓ trading_executor 传递 exchange_id — v1.0
- ✓ exchange_id="ibkr-live" 使用 IBKRDataSource — v1.0

### Active

- [ ] 支持港股数据获取
- [ ] 支持外汇数据获取
- [ ] 优化连接复用和重连机制

### Out of Scope

- 非 IBKR 实盘策略的数据源变更
- 回测数据源（保持 yfinance）
- 数据存储/缓存优化

## Context

- **现有代码库**: QuantDinger 交易平台
- **参考实现**: `/home/workspace/ws/ibkr-datafetcher/` 使用 ib_insync
- **当前 USStock 数据源**: IBKR 原生数据源 (v1.0)
- **目标 exchange_id**: `ibkr-live`
- **技术栈**: ib_insync, Python, Flask
- **里程碑**: v1.0 shipped 2026-04-09

## Constraints

- **技术**: 使用 ib_insync 库连接 IBKR Gateway
- **IBKR Gateway**: 需要本地运行 IBKR Gateway 或 IBKR 账户
- **兼容性**: 支持多种市场类型（架构设计）

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 基于 exchange_id 选择数据源 | 与 trading executor 的 exchange_id 一致，支持多数据源 | ✓ Good - 已通过 DataSourceFactory 实现 |
| 优先美股，后续港股外汇 | ibkr-live 当前只有美股策略 | ✓ Good - v1.0 专注美股，v2.0 规划港股外汇 |

---

*Last updated: 2026-04-09 after v1.0 milestone*
