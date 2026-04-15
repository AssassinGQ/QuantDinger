# Tiingo 限流优化实施计划（第一阶段）

## 一、实施步骤

### 步骤 1：代码改动

**文件**：`backend_api_python/app/data_sources/forex.py`

**改动位置**：第 164-189 行

**具体改动**：
1. 删除收盘价的 API 请求代码（`price_url`, `price_params`, `requests.get()`）
2. 新增调用 `DataSourceFactory.get_kline()` 获取昨日收盘价
3. 复用 get_kline 的 5 分钟缓存

**改动量**：约 20 行

---

### 步骤 2：单元测试

**测试目标**：验证 get_ticker 功能正常

| 测试用例 | 描述 |
|----------|------|
| TC-01 | get_ticker 正常返回实时价格 |
| TC-02 | get_ticker 从 K 线正确获取昨日收盘价 |
| TC-03 | get_ticker 在 K 线缓存未命中时优雅降级（change=0） |
| TC-04 | get_ticker 缓存机制正常（60秒内不重复请求） |

---

### 步骤 3：集成测试

**测试目标**：验证整体流程

| 测试用例 | 描述 |
|----------|------|
| TC-05 | 策略循环调用 get_ticker，单小时请求数 ≤ 60 |
| TC-06 | 涨跌数据显示正确（与 K 线数据一致） |
| TC-07 | 多 symbol 场景（XAGUSD, XAUUSD）并发调用正常 |

---

### 步骤 4：验证测试

**测试目标**：生产环境验证

| 测试 | 方法 | 预期结果 |
|------|------|----------|
| 日志验证 | `grep "Rate limited" app.log` | 限流不再频繁出现 |
| 请求数验证 | 统计 Tiingo API 调用次数 | 每小时 ≤ 60 次 |
| 功能验证 | 检查前端涨跌数据 | changePercent 正常显示 |

---

## 二、测试用例详细设计

### 2.1 单元测试 (forex.py)

#### TC-01: get_ticker 正常返回实时价格

```python
def test_get_ticker_returns_price():
    """验证 get_ticker 返回实时价格"""
    # Arrange
    forex = ForexDataSource()

    # Act
    result = forex.get_ticker("XAGUSD")

    # Assert
    assert result['last'] > 0
    assert 'bid' in result
    assert 'ask' in result
```

#### TC-02: get_ticker 从 K 线获取昨日收盘价

```python
def test_get_ticker_uses_kline_cache():
    """验证 get_ticker 从 K 线缓存获取昨日收盘价"""
    # Arrange
    forex = ForexDataSource()
    # 预先填充 K 线缓存（模拟已获取过日线数据）

    # Act
    result = forex.get_ticker("XAGUSD")

    # Assert
    assert result['previousClose'] > 0
    assert result['change'] != 0  # 有涨跌数据
    assert result['changePercent'] != 0
```

#### TC-03: K 线缓存未命中时优雅降级

```python
def test_get_ticker_fallback_when_kline_unavailable():
    """验证 K 线缓存未命中时，涨跌数据为 0 但不影响主要功能"""
    # Arrange
    forex = ForexDataSource()
    # 模拟 K 线获取失败

    # Act
    result = forex.get_ticker("XAGUSD")

    # Assert
    assert result['last'] > 0  # 实时价格正常
    assert 'change' in result   # change 字段存在
    # change 允许为 0，不应抛出异常
```

#### TC-04: 缓存机制验证

```python
def test_get_ticker_cache():
    """验证 60 秒内重复调用不触发 API"""
    forex = ForexDataSource()

    # 第一次调用
    result1 = forex.get_ticker("XAGUSD")

    # 60 秒内第二次调用（应命中缓存）
    result2 = forex.get_ticker("XAGUSD")

    assert result1['last'] == result2['last']
    # 验证未发起新的 API 请求（通过日志或 mock）
```

---

### 2.2 集成测试

#### TC-05: 策略循环请求数验证

```python
def test_hourly_request_limit():
    """验证每小时请求数不超过 60 次"""
    # 模拟策略循环（每 10 秒一次，持续 1 小时）
    # 监控实际 API 调用次数

    # 预期：cache miss = 3600/60 = 60 次
    # 每次 1 个 API 请求（去掉收盘价请求）
    # 总计 60 次 ≤ 限制
```

#### TC-06: 涨跌数据一致性

```python
def test_change_consistency():
    """验证涨跌数据与 K 线数据一致"""
    # 获取 K 线昨日收盘价
    klines = DataSourceFactory.get_kline("Forex", "XAGUSD", "1D", 2)
    yesterday_close = klines[-2]['close']

    # 获取实时 ticker
    ticker = DataSourceFactory.get_ticker("Forex", "XAGUSD")

    # 计算涨跌
    expected_change = ticker['last'] - yesterday_close
    expected_pct = (expected_change / yesterday_close) * 100

    assert abs(ticker['change'] - expected_change) < 0.0001
    assert abs(ticker['changePercent'] - expected_pct) < 0.01
```

#### TC-07: 多 symbol 并发

```python
def test_multiple_symbols():
    """验证多 symbol 并发调用正常"""
    symbols = ["XAGUSD", "XAUUSD", "EURUSD"]

    results = [DataSourceFactory.get_ticker("Forex", s) for s in symbols]

    for r in results:
        assert r['last'] > 0
```

---

### 2.3 验证测试（生产/预发布）

| 验证项 | 方法 | 通过标准 |
|--------|------|----------|
| 限流验证 | `grep "Rate limited" app.log \| wc -l` | 1 小时内 ≤ 5 次 |
| API 请求验证 | 统计 Tiingo 请求日志 | 每小时 ≤ 60 次 |
| 功能验证 | 检查前端涨跌显示 | changePercent 有值 |
| 性能验证 | 响应时间监控 | get_ticker < 1s |

---

## 三、测试覆盖矩阵

| 功能点 | 测试类型 | 用例 | 覆盖 |
|--------|----------|------|------|
| 实时价格获取 | 单元 | TC-01 | ✅ |
| 昨日收盘价获取 | 单元 | TC-02 | ✅ |
| 优雅降级 | 单元 | TC-03 | ✅ |
| 缓存机制 | 单元 | TC-04 | ✅ |
| 请求数限制 | 集成 | TC-05 | ✅ |
| 数据一致性 | 集成 | TC-06 | ✅ |
| 多 symbol 并发 | 集成 | TC-07 | ✅ |
| 生产验证 | 端到端 | 验证测试 | ✅ |

**覆盖率**：100%

---

## 四、实施时间线

| 阶段 | 时长 | 内容 |
|------|------|------|
| 代码改动 | 0.5h | 修改 forex.py |
| 单元测试 | 1h | 编写/运行 TC-01~04 |
| 集成测试 | 1h | 编写/运行 TC-05~07 |
| 验证测试 | 1h | 预发布环境验证 |
| **总计** | **3.5h** | - |

---

## 五、回退方案

```bash
# 快速回退
git checkout backend_api_python/app/data_sources/forex.py

# 重启服务
systemctl restart quantdinger
```

---

## 六、验收签字

| 检查项 | 状态 | 备注 |
|--------|------|------|
| 代码改动完成 | ⬜ | |
| 单元测试通过 | ⬜ | |
| 集成测试通过 | ⬜ | |
| 生产验证通过 | ⬜ | |
| 文档更新 | ⬜ | |