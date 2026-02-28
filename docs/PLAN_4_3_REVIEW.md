# Plan 4.3 本地修改检视报告

## 一、Plan 4.3 目标回顾

| 步骤 | 目标 |
|------|------|
| 1 | 拆分 `_run_single_symbol_strategy_loop` 为子方法 |
| 2 | Executor 驱动循环：`strategy.need_macro_info()` → `_prepare_input_for_strategy` → `_execute_signals` |
| 3-4 | SingleSymbolStrategy 实现 `_run_indicator`、`_generate_signals` |
| 5-6 | CrossSectionalStrategy 实现 `_run_indicator`、`_generate_signals` |
| 7 | 抽取 CrossSectionalBase |
| 8 | Executor `_run_strategy_loop` 按 Executor 驱动编排 |
| 9 | SS-I01/02、CS-I01/02、SS-01、CS-01、TE-* 全部通过 |

---

## 二、当前实现与 Plan 对比

### 2.1 架构演化（合理）

| Plan 4.3 | 当前实现 | 评价 |
|----------|----------|------|
| `_prepare_input_*` 在 Executor | `DataHandler.get_input_context_single/cross` | ✓ 更合理：数据拉取集中到 DataHandler，职责清晰 |
| `_run_indicator`、`_generate_signals` 抽象 | `get_data_request`、`get_signals` | ✓ 接口语义等价：get_signals 内部完成 indicator + signals 解析 |
| Executor 调用 prepare→indicator→signals→execute | Executor 调用 strategy.get_data_request → DataHandler.get_input_context → strategy.get_signals → execute | ✓ 数据流一致，策略仍为纯计算 |
| CrossSectionalBase | 暂无 | 🟡 截面逻辑尚简单，可后续抽取 |

### 2.2 拆分结果（合理）

- **单标**：`run_single_indicator` + `extract_pending_signals_from_df` 抽到 `single_symbol_indicator.py`、`single_symbol_signals.py`
- **截面**：`run_cross_sectional_indicator` + `generate_cross_sectional_signals` 抽到独立模块
- **配置加载**：`strategy_config_loader.load_strategy` + `DataHandler.get_strategy_row` 替代原 Executor 内 `_load_strategy`
- **服务端风控**：`server_side_risk.py` 单独抽离

### 2.3 用例覆盖（✓ 通过）

- 40 个用例全部通过
- TE-LOAD 已改为测 `strategy_config_loader.load_strategy`
- TE-SP-01/02 已改为测 `DataHandler.get_input_context_*`
- TE-SP-03/04 已改为测 `run_single_indicator`、`run_cross_sectional_indicator`、`extract_pending_signals_from_df`
- SS-01、CS-01 级用例存在

---

## 三、发现的问题

### 🔴 1. need_macro 与 Plan 约定不一致

**Plan 3.4**：`need_macro_info()` 由策略类型决定，`include_macro` 不作为前端配置项。

**当前**：`SingleSymbolStrategy.get_data_request`、`CrossSectionalStrategy.get_data_request` 使用 `trading_config.get("include_macro", False)`，即仍从配置读取。

**影响**：前端若配置 `include_macro=true`，会拉 macro，但 plan 要求由策略类型决定。若后续新增 `CrossSectionalWeightedStrategy` 且 `need_macro_info()=True`，会出现两种来源冲突。

**已修正**：`get_data_request` 中 `need_macro` 已改为使用 `self.need_macro_info()`。

---

### ~~🟡 2. load_strategy 未复用 Executor 的 DataHandler~~

**说明**：DataHandler 重复实例化可接受，其内部多为静态/无状态逻辑。

---

### 🟡 3. Plan 中的 `_run_indicator`、`_generate_signals` 命名未保留

Plan 4.3 步骤 3–6 明确使用 `_run_indicator`、`_generate_signals`，当前实现用 `get_signals` 一揽子完成。

**评价**：语义等价，但若希望严格对齐 plan 文档，可在策略内部拆分：

- `get_signals(ctx)` 内部调用 `_run_indicator(ctx)` → `_generate_signals(raw_output, ctx)`  
或  
- 保持现状，在 plan 中注明“当前以 `get_signals` 统一实现 indicator + signals”。

---

### 🟡 4. CrossSectionalBase 未抽取

Plan 步骤 7：抽取 `CrossSectionalBase`，包含 `_execute_signals` 批量、`_should_tick` 调仓判断。

**当前**：`CrossSectionalStrategy` 独立实现，调仓判断在 Executor 的 `_run_cross_sectional_loop` 中（`_should_rebalance` 等）。

**评价**：截面逻辑尚简单，不抽取也可接受；若计划做 `CrossSectionalWeightedStrategy`，建议先抽 Base 再扩展。

---

### 🟢 5. 其他正向改动

- `server_side_risk.py` 抽离合理，便于单测
- `console_print` 抽到 utils 合理
- DataHandler 集中 K 线、持仓、InputContext 构建，职责清晰
- 策略类无 Executor 依赖，便于单测

---

## 四、总结

| 项目 | 结论 |
|------|------|
| Plan 4.3 核心目标 | ✓ 策略纯计算、Executor 驱动、职责分离 已达成 |
| 用例 | ✓ 40 个用例通过 |
| need_macro 约定 | 🔴 与 plan 不符，建议改为用 `need_macro_info()` |
| DataHandler 复用 | 🟡 可选优化 |
| 接口命名 | 🟡 与 plan 用词不同，可择一在 plan 或代码中统一 |
| CrossSectionalBase | 🟡 可按后续扩展节奏再抽 |

**优先建议**：修正 need_macro 逻辑，使 `get_data_request` 中的 `need_macro` 完全由 `self.need_macro_info()` 决定。
