# ARCHITECTURE - IBKR Data Source

**Analysis Date:** 2026-04-08

## 系统架构

**新增组件:**
```
app/data_sources/
├── ibkr_stock.py        # 新增: IBKR 股票数据源
└── factory.py        # 修改: 支持 exchange_id 选择

app/services/
├── trading_executor.py # 修改: 基于 exchange_id 选择数据源
```

**数据流:**
```
策略请求 K线
    ↓
trading_executor 检查 exchange_id
    ↓
如果 exchange_id == "ibkr-live"
    → IBKRDataSource.get_kline()
    ↓
连接 IBKR Gateway
    ↓
返回 klines
```

## 与现有系统集成

**现有数据源选择 (by market_category):**
- USStock → USStockDataSource (yfinance)
- AShare → AShareDataSource (akshare)
- etc.

**新增选择 (by exchange_id):**
- exchange_id == "ibkr-live" → IBKRDataSource

**修改点:**
1. DataSourceFactory 添加 `get_source_by_exchange_id()` 方法
2. trading_executor 优先使用 exchange_id 选择数据源
3. 保留原有 market_category 回退

## IBKR 连接模式

**单例模式:**
- 全局一个 IBKRClient 实例
- 线程安全的连接管理
- 自动重连机制

**参考 ibkr_datafetcher 实现:**
- asyncio 事件循环线程
- threading.Event 同步
- IB 实例持有

---
*Research: 2026-04-08*