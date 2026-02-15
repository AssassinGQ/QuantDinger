# QuantDinger 自定义量化策略指南

## 架构概览

QuantDinger 采用 **信号提供者** 模式：Python 脚本处理 K 线数据，输出买卖信号，系统负责执行交易。

```
指标脚本 (qd_indicator_codes)  →  策略 (qd_strategies_trading)  →  执行引擎
       Python 代码                   指标 + 交易配置                  回测 / 实盘
```

## 指标脚本规范

### 输入

| 变量 | 类型 | 说明 |
|------|------|------|
| `df` | DataFrame | OHLCV 数据，列：`time`, `open`, `high`, `low`, `close`, `volume` |
| `pd` | module | pandas，无需 import |
| `np` | module | numpy，无需 import |
| `params` | dict | 策略模式下可用，读取前端配置的参数 |

### 必须输出

| 变量 | 说明 |
|------|------|
| `df["buy"]` | 布尔列，True = 买入信号 |
| `df["sell"]` | 布尔列，True = 卖出信号 |
| `output` | 字典，包含 `name`、`plots`、`signals` |

### 最小模板

```python
my_indicator_name = "My Indicator"
my_indicator_description = "Description here"

df = df.copy()
sma = df["close"].rolling(14).mean()
buy = (df["close"] > sma) & (df["close"].shift(1) <= sma.shift(1))
sell = (df["close"] < sma) & (df["close"].shift(1) >= sma.shift(1))
df["buy"] = buy.fillna(False).astype(bool)
df["sell"] = sell.fillna(False).astype(bool)

buy_marks = [df["low"].iloc[i] * 0.995 if df["buy"].iloc[i] else None for i in range(len(df))]
sell_marks = [df["high"].iloc[i] * 1.005 if df["sell"].iloc[i] else None for i in range(len(df))]

output = {
  "name": my_indicator_name,
  "plots": [],
  "signals": [
    {"type": "buy", "text": "B", "data": buy_marks, "color": "#00E676"},
    {"type": "sell", "text": "S", "data": sell_marks, "color": "#FF5252"}
  ]
}
```

## 注册流程

1. **保存指标**：`POST /api/indicator/saveIndicator` → 得到 `indicator_id`
2. **创建策略**：`POST /api/strategies/create` → 引用 `indicator_id`，配置交易参数
3. **启动策略**：`POST /api/strategies/start?id=<策略ID>`

## 回测方法

入口在**指标分析页面** (`/indicator-analysis`)：左侧指标列表 → 点击紫色烧杯图标 🧪 → 配置风控和回测参数 → 查看结果。

## 示例文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `dual_ma_with_params.py` | 策略（带参数） | 双均线交叉，支持 `@param` 前端配置 |
| `dual_ma_indicator.py` | 指标（敏捷版） | SMA3/8 + RSI6，快进快出，适合短线 |
| `multi_indicator_composite.py` | 策略（带参数） | 均线 + RSI + MACD + 成交量组合 |
| `multi_indicator_composite_indicator.py` | 指标 | 上述组合策略的指标格式版本 |
| `cross_sectional_momentum_rsi.py` | 截面策略 | 多标的动量 + RSI 评分排名 |

### 策略 vs 指标区别

- **策略文件**：有 `# @param` 声明和 `params.get()`，可在前端配置不同参数复用
- **指标文件**：参数硬编码，直接可用，符合 Demo Code 格式

## 信号设计要点

- **边缘触发**：用 `shift(1)` 检测穿越时刻，避免连续 K 线重复信号
- **NaN 处理**：`rolling()` 开头会产生 NaN，用 `.fillna()` 处理
- **敏捷策略**：缩短均线周期 + 多出场条件（RSI 超买、短期涨幅止盈）
- **K 线周期**：脚本内 `rolling(N)` 是 N 根 K 线，实际时间跨度取决于运行时选择的 timeframe
