# Research Summary

**Date:** 2026-04-08

## Key Findings

**Stack:**
- 使用 `ib_insync` 库连接 IBKR Gateway
- 异步事件循环在独立线程运行
- IBKRClient 单例管理连接

**Table Stakes:**
- get_kline(): 历史K线获取
- get_ticker(): 实时报价
- 与 BaseDataSource 接口兼容

**Architecture:**
- 新增 `app/data_sources/ibkr_stock.py`
- 修改 `factory.py` 支持基于 exchange_id 选择
- 保留 market_category 回退

**Watch Out For:**
- Gateway 未运行会导致连接失败
- 异步事件循环需独立线程
- 需要市场代码格式转换

## Files

- `.planning/research/STACK.md`
- `.planning/research/FEATURES.md`
- `.planning/research/ARCHITECTURE.md`
- `.planning/research/PITFALLS.md`