my_indicator_name = "Agile Dual MA"
my_indicator_description = "Fast SMA3/SMA8 crossover with RSI filter, quick in quick out"

df = df.copy()

# 短周期均线，信号更频繁
sma_fast = df["close"].rolling(3).mean()
sma_slow = df["close"].rolling(8).mean()

# RSI(6) 短周期，捕捉快速超卖超买
delta = df["close"].diff()
gain = delta.where(delta > 0, 0).rolling(6).mean()
loss = (-delta.where(delta < 0, 0)).rolling(6).mean()
rs = gain / loss
rsi = (100 - (100 / (1 + rs))).fillna(50)

# 买入：快线上穿慢线 或 RSI<25 超卖反弹
raw_buy = ((sma_fast > sma_slow) & (sma_fast.shift(1) <= sma_slow.shift(1))) | \
          ((rsi < 25) & (rsi.shift(1) >= 25))

# 卖出：快线下穿慢线 或 RSI>75 超买 或 涨幅达1.5%及时止盈
price_up_pct = (df["close"] - df["close"].shift(3)) / df["close"].shift(3) * 100
raw_sell = ((sma_fast < sma_slow) & (sma_fast.shift(1) >= sma_slow.shift(1))) | \
           ((rsi > 75) & (rsi.shift(1) <= 75)) | \
           (price_up_pct > 1.5)

# 边缘触发，避免连续重复信号
buy = raw_buy.fillna(False) & (~raw_buy.shift(1).fillna(False))
sell = raw_sell.fillna(False) & (~raw_sell.shift(1).fillna(False))

df["buy"] = buy.astype(bool)
df["sell"] = sell.astype(bool)

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
