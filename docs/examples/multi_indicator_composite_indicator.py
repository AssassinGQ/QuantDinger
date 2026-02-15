my_indicator_name = "Multi-Indicator Composite"
my_indicator_description = "SMA crossover + RSI + MACD + Volume composite buy/sell indicator"

df = df.copy()

# === SMA ===
sma_short = df["close"].rolling(10).mean()
sma_long = df["close"].rolling(30).mean()

# === RSI ===
delta = df["close"].diff()
gain = delta.where(delta > 0, 0).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
rsi = (100 - (100 / (1 + rs))).fillna(50)

# === MACD ===
exp1 = df["close"].ewm(span=12, adjust=False).mean()
exp2 = df["close"].ewm(span=26, adjust=False).mean()
macd = exp1 - exp2
macd_signal = macd.ewm(span=9, adjust=False).mean()

# === Volume MA ===
volume_ma = df["volume"].rolling(20).mean()

# === Signal conditions ===
ma_golden = (sma_short > sma_long) & (sma_short.shift(1) <= sma_long.shift(1))
ma_death = (sma_short < sma_long) & (sma_short.shift(1) >= sma_long.shift(1))
rsi_buy = rsi < 30
rsi_sell = rsi > 70
macd_golden = (macd > macd_signal) & (macd.shift(1) <= macd_signal.shift(1))
macd_death = (macd < macd_signal) & (macd.shift(1) >= macd_signal.shift(1))
volume_up = df["volume"] > volume_ma * 1.5

# === Composite buy/sell ===
buy = (ma_golden | rsi_buy) & (macd > macd_signal)
sell = (ma_death | rsi_sell) | macd_death

df["buy"] = buy.fillna(False).astype(bool)
df["sell"] = sell.fillna(False).astype(bool)

buy_marks = [df["low"].iloc[i] * 0.995 if df["buy"].iloc[i] else None for i in range(len(df))]
sell_marks = [df["high"].iloc[i] * 1.005 if df["sell"].iloc[i] else None for i in range(len(df))]

output = {
  "name": my_indicator_name,
  "plots": [
    {"name": "SMA10", "data": sma_short.fillna(0).tolist(), "color": "#FF9800", "overlay": True},
    {"name": "SMA30", "data": sma_long.fillna(0).tolist(), "color": "#3F51B5", "overlay": True}
]
  "signals": [
    {"type": "buy", "text": "B", "data": buy_marks, "color": "#00E676"},
    {"type": "sell", "text": "S", "data": sell_marks, "color": "#FF5252"}
  ]
}
