# QuantDinger - IBKR 数据源

## What This Is

为 `exchange_id = ibkr-live` 的交易策略提供原生 IBKR 数据源，从 Interactive Brokers API 获取 K线和实时报价，替代当前使用的 yfinance/Finnhub。

**Core value**: 实盘交易策略使用与实际下单同一数据源，确保数据一致性。

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] 创建 IBKRDataSource 类，继承 BaseDataSource
- [ ] 实现 get_kline() 方法获取历史K线
- [ ] 实现 get_ticker() 方法获取实时报价
- [ ] 根据 exchange_id 选择 IBKR 数据源（非 market_category）
- [ ] 支持美股数据获取
- [ ] 架构支持扩展到港股、外汇

### Out of Scope

- 非 IBKR 实盘策略的数据源变更
- 回测数据源（保持 yfinance）
- 数据存储/缓存优化

## Context

- **现有代码库**: QuantDinger 交易平台
- **参考实现**: `/home/workspace/ws/ibkr-datafetcher/` 使用 ib_insync
- **当前 USStock 数据源**: yfinance + Finnhub
- **目标 exchange_id**: `ibkr-live`

## Constraints

- **技术**: 使用 ib_insync 库连接 IBKR Gateway
- **IBKR Gateway**: 需要本地运行 IBKR Gateway 或 IBKR 账户
- **兼容性**: 支持多种市场类型（架构设计）

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 基于 exchange_id 选择数据源 | 与 trading executor 的 exchange_id 一致，支持多数据源 | — Pending |
| 优先美股，后续港股外汇 | ibkr-live 当前只有美股策略 | — Pending |

---

*Last updated: 2026-04-08 after initialization*