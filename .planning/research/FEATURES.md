# FEATURES - IBKR Data Source

**Analysis Date:** 2026-04-08

## 功能特性

### Table Stakes (必须实现)

**获取历史K线:**
- 指定时间周期的K线数据
- 支持 timeframe: 1m, 5m, 15m, 30m, 1H, 4H, 1D
- 返回格式: `[{time, open, high, low, close, volume}]`
- 与现有 BaseDataSource 接口兼容

**获取实时报价:**
- 当前价格
- 涨跌额/涨跌幅
- 日内 High/Low
- 开盘价/昨收价

### Differentiators (竞争优势)

**数据源一致性:**
- 与实盘下单使用同一 IBKR 连接
- 确保回测/模拟/实盘数据一致

**多市场支持 (架构):**
- 美股 (Stock)
- 港股 (Stock with local symbol)
- 外汇 (Forex)
- 期货 (Future)

### Anti-Features (不实现)

- 非实时数据获取（回测仍用 yfinance）
- 多账户聚合
- 数据持久化存储

## 数据格式

**K线返回 (BaseDataSource 兼容):**
```python
[
  {"time": 1704067200, "open": 150.0, "high": 151.0, "low": 149.5, "close": 150.5, "volume": 1000000},
  ...
]
```

**报价返回:**
```python
{
  "last": 150.50,
  "change": 1.50,
  "changePercent": 1.0,
  "high": 151.00,
  "low": 149.00,
  "open": 149.00,
  "previousClose": 149.00
}
```

---
*Research: 2026-04-08*