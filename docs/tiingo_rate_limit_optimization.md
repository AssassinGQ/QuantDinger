# Tiingo 限流优化方案（第一阶段）

## 一、问题分析

### 1.1 Tiingo API 限制

| 限制类型 | 数值 |
|---------|------|
| 每小时限制 | 50 次 |
| 每天限制 | 1000 次 |

### 1.2 当前系统请求量

| 指标 | 数值 |
|------|------|
| 策略循环间隔 | 10 秒 |
| 当前缓存 TTL | 60 秒 |
| 每次 get_ticker | 2 次 API 请求 (`/fx/top` + `/fx/{symbol}/prices`) |
| 每小时策略循环 | 360 次 |
| 每小时 cache miss | 60 次 |
| **每小时 Tiingo 请求** | **120 次** ❌ 严重超限 |

### 1.3 日志证据

```
2026-04-15 20:52:17 - Rate limited by Tiingo(cached), retry after 9.75s
2026-04-15 20:52:53 - Rate limited by Tiingo(cached), retry after 19.78s
...
```

频繁触发 429 限流，导致策略无法获取实时价格。

---

## 二、方案设计

### 2.1 目标

将 get_ticker 的 2 次 API 请求合并为 1 次，减少 50% 请求量。

### 2.2 原逻辑 vs 新逻辑

**原逻辑**：

```python
def get_ticker(symbol):
    # 请求 1: 获取实时价格
    response = requests.get(f"{base_url}/fx/top", params={...})

    # 请求 2: 获取昨日收盘价（用于计算涨跌）
    price_resp = requests.get(f"{base_url}/fx/{symbol}/prices", params={...})
```

**新逻辑**：

```python
def get_ticker(symbol):
    # 请求 1: 获取实时价格
    response = requests.get(f"{base_url}/fx/top", params={...})

    # 复用 get_kline 的缓存获取昨日收盘价（无额外请求）
    klines = DataSourceFactory.get_kline("Forex", symbol.upper(), "1D", 2)
    yesterday_close = klines[-2]['close']
```

### 2.3 效果

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 单次请求次数 | 2 次 | 1 次 |
| 每小时请求 | 120 次 | 60 次 |
| 状态 | ❌ 超限 | ⚠️ 接近但不超过限制 |

优化后每小时 60 次请求，接近 50 次限制。如仍有风险，可后续再延长缓存。

---

## 三、实现细节

### 3.1 文件位置

`backend_api_python/app/data_sources/forex.py`

### 3.2 代码改动

**位置**：第 164-189 行

**原代码**：

```python
# 获取前一天收盘价来计算涨跌（需要额外请求日线数据）
prev_close = 0
change = 0
change_pct = 0

try:
    yesterday = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    price_url = f"{self.base_url}/fx/{tiingo_symbol}/prices"
    price_params = {
        'startDate': yesterday,
        'endDate': today,
        'resampleFreq': '1day',
        'token': api_key
    }
    price_resp = requests.get(price_url, params=price_params, timeout=TiingoConfig.TIMEOUT)
    if price_resp.status_code == 200:
        price_data = price_resp.json()
        if price_data and len(price_data) > 0:
            prev_close = float(price_data[-1].get('close', 0) or 0)
            if prev_close and last_price:
                change = last_price - prev_close
                change_pct = (change / prev_close) * 100
except Exception:
    pass
```

**新代码**：

```python
# 获取前一天收盘价来计算涨跌（使用 get_kline 缓存获取）
prev_close = 0
change = 0
change_pct = 0

try:
    from app.data_sources import DataSourceFactory
    klines = DataSourceFactory.get_kline("Forex", tiingo_symbol.upper(), "1D", 2)
    if klines and len(klines) >= 2:
        yesterday_kline = klines[-2]
        prev_close = float(yesterday_kline.get('close', 0) or 0)
        if prev_close and last_price:
            change = last_price - prev_close
            change_pct = (change / prev_close) * 100
except Exception:
    pass
```

---

## 四、验收标准

### 4.1 功能验收

| 检查项 | 预期 |
|--------|------|
| 实时价格获取 | 正常返回 XAGUSD 等实时价格 |
| 涨跌数据 | 正确显示 change 和 changePercent（从 K 线获取昨日收盘） |
| 缓存机制 | 60 秒内重复调用不触发 API 请求 |

### 4.2 性能验收

| 指标 | 目标 |
|------|------|
| 每小时 Tiingo 请求 | ≤ 60 次 |
| 限流触发 | 日志中不再频繁出现 `Rate limited by Tiingo` |
| API 响应时间 | 实时价格请求 < 1 秒 |

### 4.3 测试方法

```bash
# 1. 观察日志，确认不再触发限流
tail -f /home/workspace/quantdinger/backend_logs/app.log | grep -E "Rate limited|ERROR"

# 2. 统计每小时 API 请求次数（通过日志计数）
grep "Using cached forex ticker" app.log | wc -l
```

---

## 五、风险与回退

### 5.1 风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| K 线缓存未命中 | 涨跌数据显示为 0 | get_kline 有 5 分钟缓存，正常情况不会发生 |
| 新版本兼容 | get_kline 返回格式变化 | 异常被捕获，不影响主要功能 |

### 5.2 回退方案

```bash
# 快速回退
git checkout backend_api_python/app/data_sources/forex.py
```

---

## 六、后续（如需进一步优化）

如第一阶段效果不足，可考虑：
- 延长 `_FOREX_CACHE_TTL` 从 60s 到 90s 或 120s
- 使用 IBKR 实时报价替代 Tiingo