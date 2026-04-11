# Requirements

## v1.1 IBKR策略数据源集成 + E2E测试

### Runner broker_id 透传

- [ ] **INT-06**: single_symbol_runner.run_tick() 从 strategy['trade_config'] 取 broker_id，传给 price_fetcher.fetch_current_price(exchange_id=broker_id)
- [ ] **INT-07**: regime_runner.run_tick() 同上
- [ ] **INT-08**: single_regime_weighted_runner.run_tick() 同上

### E2E 测试

- [ ] **INT-09**: E2E 测试 — 策略 tick 链路验证（Python 直接调用，不过 API）：strategy config → runner.run_tick() → price_fetcher.fetch_current_price(exchange_id='ibkr-paper') → DataSourceFactory.get_ticker() → IBKRDataSource → ib_insync [MOCKED]

---

## Out of Scope

- `/api/market/kline` 和 `/api/market/price` 的 exchange_id 参数
- DataSourceFactory.get_kline() 修改（get_ticker 已支持 exchange_id）
- `/api/indicator/kline` 修改

---

*Requirements defined: 2026-04-11 for v1.1*
