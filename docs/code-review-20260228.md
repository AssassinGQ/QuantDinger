# 代码检视报告：TradingExecutor 近期改动

> 检视范围：server_side 风控抽取、_console_print 移除、executor-call-chain 文档

---

## 一、逐行注释

### 1. trading_executor.py

📍 第 14-19 行: [🟢 建议]
新增 `server_side_risk` 导入，与原有 `from app.utils.console import console_print` 之间无空行分隔。按 PEP8，同一来源的 import 可放一起，不同模块之间应有空行。
💡 建议: 保持现状即可；若严格遵循「stdlib → third-party → local」，可将 server_side_risk 与 data_handler 等 local 导入归类。

📍 第 472 行: [🟡 警告]
`strat._state.get("pending_signals", [])` 访问策略内部 `_state` 属性。
💡 建议: 若策略有公开接口可获取 pending_signals，优先使用；否则可加注释说明为何访问 protected 成员（如「SingleSymbolIndicator 内部状态，暂无公开 API」）。

📍 第 308 行（原 308）: [🟢 建议]
测试中 `patch("app.services.trading_executor.console_print")` 未赋给变量，仅用于静默输出。
💡 建议: 当前写法正确，patch 生效即可；若需断言 console_print 被调用，可 `as mock_cp` 并 `mock_cp.assert_called()`。

---

## 二、Pylint 自动化结果摘要

### trading_executor.py 主要问题（多为既有问题，非本次引入）

| 类型 | 数量 | 示例 |
|------|------|------|
| line-too-long | 35+ | 多处超 100 字符 |
| too-many-lines | 1 | 模块 1376 行 (上限 1000) |
| too-many-arguments | 多处 | _process_and_execute_signals 17 参数 |
| too-many-instance-attributes | 1 | 10 个实例属性 (上限 7) |
| broad-exception-caught | 20+ | `except Exception` |
| protected-access | 1 | strat._state |

### test_trading_executor_te.py

| 类型 | 示例 |
|------|------|
| invalid-name | TradingExecutorCls 不符合 snake_case |
| use-implicit-booleaness-not-comparison | `signals == []` 可改为 `not signals` |
| missing-function-docstring | 部分 test 方法缺 docstring |
| protected-access | 测试直接调用 `_run_strategy_loop`（合理，用于集成测试）|

---

## 三、代码检视总结

### 📊 概览

- 检视文件数: 4（trading_executor.py, test_trading_executor_te.py, server_side_risk.py, executor-call-chain.md）
- 严重问题: 0
- 警告: 2
- 建议: 3

### 🔴 严重问题

无。本次改动未引入正确性或安全性问题。

### 🟡 主要警告

1. **strat._state 访问**（trading_executor.py:472）
   - 直接访问策略 protected 成员，耦合内部实现
   - 建议：评估是否在策略侧提供 `get_pending_signals_count()` 等公开接口

2. **patch 目标一致性**
   - server_side 相关测试 patch `app.services.trading_executor.check_stop_loss_signal`，正确（patch 使用处）
   - console_print 同理 patch `app.services.trading_executor.console_print`，正确

### ✅ 优点

1. **职责拆分清晰**：server_side 风控逻辑抽出到独立模块，executor 瘦身约 250 行
2. **去除冗余封装**：删除 `_console_print` 和 `_to_ratio`，直接调用公共函数，符合「测试服务核心代码」原则
3. **测试适配正确**：patch 目标从 `TradingExecutor._console_print` 改为 `app.services.trading_executor.console_print`，40 个测试全部通过
4. **文档补充**：executor-call-chain.md 为后续重构提供清晰路线图
5. **复用 to_ratio**：统一使用 server_side_risk.to_ratio，避免重复实现

### 📝 改进建议（已实施 2026-02-28）

1. ✅ **优先**：对 `strat._state` 的访问加简短注释
2. ✅ **一般**：处理部分 pylint line-too-long（最严重 10+ 处已修复）、consider-using-max-builtin
3. ✅ **测试**：将 `signals == []` 改为 `not signals`（7 处）

---

## 四、结论

本次改动质量良好，无严重问题。server_side 风控抽取与 _console_print 移除均符合设计目标，测试覆盖完整。改进建议已实施，剩余 line-too-long 可在后续重构中继续处理。
