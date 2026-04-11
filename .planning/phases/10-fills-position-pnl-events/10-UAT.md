---
status: testing
phase: 10-fills-position-pnl-events
source: 10-01-SUMMARY.md
started: 2026-04-11T05:00:00Z
updated: 2026-04-11T05:00:00Z
---

## Current Test

number: 1
name: 全量自动化测试通过
expected: |
  运行 `python -m pytest backend_api_python/tests/ -v --tb=short` 全量测试套件，
  所有测试（包括新增的 UC-FP1–FP7、UC-FP6、UC-SCHEMA）全部 PASSED，无 ERROR 或 FAIL。
awaiting: user response

## Tests

### 1. 全量自动化测试通过
expected: 运行 `python -m pytest backend_api_python/tests/ -v --tb=short` 全量测试套件，所有测试（包括新增的 UC-FP1–FP7、UC-FP6、UC-SCHEMA）全部 PASSED，无 ERROR 或 FAIL。
result: [pending]

### 2. Forex 仓位回调使用 EUR.USD 式标签
expected: 在 `_on_position` / `_on_update_portfolio` 回调中，Forex 合约使用 `localSymbol`（如 `EUR.USD`）作为 symbol key 而非基础货币（`EUR`），测试 UC-FP1 和 UC-FP2 验证此行为。
result: [pending]

### 3. DB schema 包含 sec_type / exchange / currency 列
expected: `qd_ibkr_pnl_single` 表通过 ALTER TABLE 新增了 `sec_type`、`exchange`、`currency` 三列（VARCHAR，DEFAULT ''），`ibkr_save_position` 能正确写入这些字段。测试 UC-SCHEMA 验证元组包含这些字段。
result: [pending]

### 4. get_positions() 返回真实合约元数据
expected: `get_positions()` API 从数据库读取 `sec_type`/`exchange`/`currency`，Forex 仓位返回 `secType: "CASH"`, `exchange: "IDEALPRO"`, `currency: "USD"` 等真实值。空值时回退到 `STK`/`SMART`/`USD` 默认值。测试 UC-FP4 和 UC-FP5 验证此行为。
result: [pending]

### 5. ibkr_save_pnl 不再有 NameError
expected: `ibkr_save_pnl` 函数移除了引用未定义变量 `position`/`avg_cost`/`value` 的死代码，调用该函数不再抛出 NameError。测试 UC-FP6 直接调用该函数验证无异常。
result: [pending]

### 6. Forex 完整生命周期回调链路
expected: UC-FP7 测试验证 Forex 合约从 `_on_position` → `_on_pnl_single` → `get_positions()` 的完整数据流：position 写入后 pnl_single 更新，最终 get_positions 返回的数据包含正确的 symbol（EUR.USD）和合约元数据（CASH/IDEALPRO/USD）。
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0

## Gaps

[none yet]
