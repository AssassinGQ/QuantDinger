# TradingExecutor 方法调用链分析

> 侧重：对外入口 → 内部调用 → 外部依赖；评估 ~1377 行代码是否应全部保留在 executor 中。

---

## 一、对外入口（仅 2 个）

| 入口 | 调用方 | 说明 |
|------|--------|------|
| **start_strategy(strategy_id)** | routes/strategy.py, regime_switch.py, app/__init__.py (scheduler) | 启动策略线程 |
| **stop_strategy(strategy_id)** | routes/strategy.py, regime_switch.py | 停止策略 |

**没有其他公开方法**。`portfolio_allocator` 会 `get_trading_executor()` 但仅用于判断 executor 是否存在，不直接调用方法。

---

## 二、从入口展开的调用链

### 入口 1：start_strategy

```
start_strategy(strategy_id)
├── [内部] self._log_resource_status()        # 线程/内存检查
├── [内部] threading.Thread(target=_run_strategy_loop, args=(strategy_id,))
└── [外部] data_handler.update_strategy_status()  # stop 时；start 不直接调

_run_strategy_loop(strategy_id)
├── [外部] load_and_create(strategy_id)      # strategies.factory
├── [内部] _run_single_symbol_loop() 或 _run_cross_sectional_loop()
└── [内部] 清理 running_strategies
```

### 入口 2：stop_strategy

```
stop_strategy(strategy_id)
├── [外部] data_handler.update_strategy_status(strategy_id, "stopped")
└── [内部] 从 running_strategies 移除（线程自检后退出）
```

---

## 三、单标循环调用链

```
_run_single_symbol_loop(strat, strategy_id, strategy, exchange)
├── [内部] _is_strategy_running() → data_handler.get_strategy_status()
├── [内部] sleep_until_next_tick()           # strategies.base
├── [内部] _fetch_current_price()           # 见下
├── [内部] strat.get_data_request()          # 策略接口
├── [外部] data_handler.get_input_context_single()
├── [内部] strat.get_signals(ctx)           # 策略接口
├── [外部] data_handler.update_position()    # meta.position_updates
└── [内部] _process_and_execute_signals()   # 核心信号处理
```

### _fetch_current_price

```
├── [内部] 内存价格缓存 _price_cache
└── [外部] DataSourceFactory.get_ticker(market_category, symbol)
```

### _process_and_execute_signals（~130 行）

```
├── [外部] check_take_profit_or_trailing_signal()  # server_side_risk
├── [外部] check_stop_loss_signal()                # server_side_risk
├── [外部] data_handler.get_current_positions()
├── [内部] _position_state(), _is_signal_allowed(), _signal_priority()
├── [内部] _should_skip_signal_once_per_candle()   # 信号去重
├── [内部] _execute_signal()
└── [外部] notify_strategy_signal_for_positions()  # portfolio_monitor
```

### _execute_signal（~260 行）

```
├── [内部] _position_state(), _is_signal_allowed()
├── [内部] _is_entry_ai_filter_enabled(), _entry_ai_filter_allows()
│   └── [外部] get_fast_analysis_service().analyze()  # AI 开仓过滤
├── [内部] _get_available_capital()
│   └── [外部] get_portfolio_allocator().get_allocated_capital()
├── [内部] to_ratio()  # server_side_risk
├── [内部] _execute_exchange_order()
│   └── [内部] _enqueue_pending_order()
│       ├── [外部] data_handler.find_recent_pending_order()
│       ├── [外部] data_handler.get_user_id()
│       └── [外部] data_handler.insert_pending_order()
└── [外部] data_handler.record_trade/update_position/close_position/persist_notification
```

---

## 四、截面循环调用链

```
_run_cross_sectional_loop(strat, strategy_id, strategy, exchange)
├── [内部] _is_strategy_running()
├── [内部] sleep_until_next_tick()
├── [内部] _should_rebalance()
│   └── [外部] data_handler.get_last_rebalance_at()
├── [外部] data_handler.get_input_context_cross()
├── [内部] strat.get_signals(ctx)
├── [内部] _execute_cross_sectional_signals()
│   └── [外部] data_handler.get_all_positions()
│   └── [内部] ThreadPoolExecutor 并发调用 _execute_signal()
└── [外部] data_handler.update_last_rebalance()
```

---

## 五、外部依赖汇总

| 模块 | 用途 |
|------|------|
| **DataHandler** | get_strategy_status, get_input_context_single/cross, get_current_positions, get_all_positions, update_position, close_position, record_trade, persist_notification, find_recent_pending_order, insert_pending_order, get_user_id, get_last_rebalance_at, update_last_rebalance, ensure_db_columns |
| **DataSourceFactory** | get_ticker (价格) |
| **server_side_risk** | check_stop_loss_signal, check_take_profit_or_trailing_signal, to_ratio |
| **load_and_create** | 策略加载 |
| **sleep_until_next_tick** | 节奏控制 |
| **FastAnalysisService** | AI 开仓过滤 |
| **PortfolioAllocator** | 动态资金分配 |
| **portfolio_monitor** | notify_strategy_signal_for_positions |
| **KlineService** | 经 data_handler 间接使用 |
| **console_print, logger** | 输出与日志 |

---

## 六、代码分布与职责

| 方法/块 | 约行数 | 职责 | 是否适合迁出 |
|---------|--------|------|--------------|
| __init__ | ~25 | 初始化缓存、DataHandler、线程限 | 否 |
| _normalize_trade_symbol | ~55 | CCXT 合约符号规范化 | **可迁**：与 exchange 强相关，executor 在 signal 模式下不用 |
| _log_resource_status | ~40 | 资源/内存/线程监控 | **可迁**：通用监控工具 |
| _position_state, _is_signal_allowed, _signal_priority | ~40 | 状态机与信号优先级 | **可迁**：纯逻辑，独立 SignalStateMachine |
| _dedup_key, _should_skip_signal_once_per_candle | ~55 | 信号去重 | **可迁**：SignalDedup 服务 |
| start_strategy, stop_strategy | ~85 | 启停线程与 DB 状态 | 否，核心入口 |
| _run_strategy_loop | ~45 | 分发单标/截面 | 否 |
| _run_single_symbol_loop | ~110 | 单标 tick 循环 | 否 |
| _run_cross_sectional_loop | ~60 | 截面调仓循环 | 否 |
| _execute_cross_sectional_signals | ~85 | 截面批量执行 | 可并入 SignalExecutor |
| _get_timeframe_seconds | ~10 | timeframe 解析 | 可迁工具 |
| _is_strategy_running | ~5 | 状态查询 | 否 |
| _fetch_current_price | ~60 | 价格缓存 + 数据源 | **可迁**：PriceService/PriceFetcher |
| _process_and_execute_signals | ~130 | 风控+过滤+排序+执行 | **可迁**：SignalProcessor/Orchestrator |
| _execute_signal | ~260 | 校验+AI 过滤+下单+持仓更新 | **可迁**：核心应拆成 SignalExecutor |
| _is_entry_ai_filter_enabled | ~35 | AI 过滤配置解析 | 可迁入 AI 模块 |
| _entry_ai_filter_allows | ~95 | AI 分析调用 | 可迁入 AI 模块 |
| _extract_ai_trade_decision | ~25 | AI 结果解析 | 可迁入 AI 模块 |
| _execute_exchange_order | ~60 | 封装 _enqueue_pending_order | 可并入 SignalExecutor |
| _enqueue_pending_order | ~95 | pending 订单入队 | **可迁**：PendingOrderQueue |
| _get_available_capital | ~15 | 资金分配 | 否 |
| _should_rebalance | ~20 | 调仓频率 | **可迁**：RebalanceScheduler |

---

## 七、结论：1377 行是否应全在 Executor

### 1. 建议保留在 Executor 的部分

- **启停与调度**：`start_strategy`, `stop_strategy`, `_run_strategy_loop`, `_run_single_symbol_loop`, `_run_cross_sectional_loop`
- **线程与资源管理**：`running_strategies`、线程上限、入口入口
- **对外 API 形态**：仅暴露 start/stop，其他逻辑内聚

约 **300–400 行** 属于「调度与循环」核心，适合留在 `TradingExecutor`。

### 2. 建议迁出的部分

| 候选模块 | 迁出内容 | 约行数 |
|----------|----------|--------|
| **SignalProcessor** | `_process_and_execute_signals` + 风控调用 + 过滤/排序/选择 | ~150 |
| **SignalExecutor** | `_execute_signal` 中除 AI 以外的执行逻辑（校验、下单、持仓更新） | ~200 |
| **PendingOrderEnqueuer** | `_enqueue_pending_order`, `_execute_exchange_order` | ~160 |
| **EntryAIFilter** | `_is_entry_ai_filter_enabled`, `_entry_ai_filter_allows`, `_extract_ai_trade_decision` | ~155 |
| **PriceFetcher** | `_fetch_current_price` + 价格缓存 | ~65 |
| **SignalDedup** | `_dedup_key`, `_should_skip_signal_once_per_candle` | ~55 |
| **SignalStateMachine** | `_position_state`, `_is_signal_allowed`, `_signal_priority` | ~40 |
| **SymbolNormalizer** | `_normalize_trade_symbol` | ~55 |
| **RebalanceChecker** | `_should_rebalance` | ~20 |

迁出后，Executor 体量可收敛到 **~400 行**，职责清晰为「启停 + 循环调度 + 调用各服务」。

### 3. 推荐拆分顺序

1. **SignalProcessor**：信号处理与风控独立，易单独测试。
2. **SignalExecutor / PendingOrderEnqueuer**：执行与下单解耦，便于支持不同执行模式。
3. **EntryAIFilter**：AI 逻辑集中，便于替换或扩展。
4. **PriceFetcher**：价格获取与缓存与策略循环解耦，可复用。

### 4. 风险与注意点

- 单文件 1377 行包含多种职责，不利于阅读与单测。
- 多出 `_` 私有方法，但多数可视为可复用服务，不应为「可 mock」而长期留在 executor。
- 分步抽取、保持现有行为不变，再补测试，可控制回归风险。
