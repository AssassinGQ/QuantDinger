# STACK - IBKR Data Source

**Analysis Date:** 2026-04-08

## Technology Stack

**Primary Library:**
- `ib_insync` (>= 0.9.84) — Python client for IBKR API
- AsyncIO for event loop management
- Threading for non-blocking operations

**Reference Implementation:**
- `/home/workspace/ws/ibkr-datafetcher/src/ibkr_datafetcher/` — 独立的数据获取服务
- 使用 ib_insync.IB 连接 IBKR Gateway
- 支持历史K线、实时报价、新闻获取

## Key Components

**IBKRClient (from ibkr_datafetcher):**
- `__init__(config: GatewayConfig)` — 初始化 IB 连接
- `connect()` — 连接到 IBKR Gateway
- `get_historical_bars()` — 获取历史K线
- `get_historical_news()` — 获取新闻
- `disconnect()` — 断开连接

**数据格式:**
- KlineBar: `{time, open, high, low, close, volume, barCount}`
- NewsItem: `{id, time, source, headline, summary, url}`

## IBKR Gateway 配置

**连接参数:**
- host: `127.0.0.1` (本地 Gateway)
- port: `4001` (live) / `4002` (paper)
- client_id: 自动生成

**所需环境变量:**
- `IBKR_GATEWAY_HOST`
- `IBKR_GATEWAY_PORT`
- `IBKR_GATEWAY_MODE` (live/paper)

## 集成到 QuantDinger

**添加到现有数据源:**
- 新文件: `app/data_sources/ibkr_stock.py`
- 修改: `app/data_sources/factory.py` 支持基于 exchange_id 选择

**依赖:**
```python
from ib_insync import IB, Stock, Forex, Future
```

## 版本要求

- Python 3.8+
- ib_insync >= 0.9.84

---
*Research: 2026-04-08*