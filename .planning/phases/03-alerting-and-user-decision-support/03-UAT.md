---
status: complete
phase: 03-alerting-and-user-decision-support
source:
  - 03-01-SUMMARY.md
  - 03-02-SUMMARY.md
started: "2026-04-18T14:00:00.000Z"
updated: "2026-04-18T15:24:51Z"
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

[testing complete]

<!-- 5/5 人工项为 skipped 且均有 reason；无 pending/blocked。Live 链路与渠道观测由后续 staging 补做；行为覆盖见列出的 pytest 模块。 -->

## Tests

### 1. User notification on IBKR insufficient live block
expected: Live IBKR open/add blocked by sufficiency produces one user-channel alert with flat-account copy rules (no 「有持仓」, no close/hold decision prompt).
result: skipped
reason: "没有这样的测试条件（无 live IBKR + 通知渠道的联调环境）"

### 2. Positioned-account alert copy
expected: If the strategy already has a non-zero position on the same symbol when blocked, the user-visible title or first line contains 「有持仓」 and the body asks you to decide 平仓 or 继续持有 explicitly.
result: skipped
reason: "与 Test 1 相同：缺少可复现的 live 执行路径与人工观测条件"

### 3. Cooldown dedup (no spam within 5 minutes)
expected: Two blocked attempts within five minutes for the same strategy, symbol, reason code, and exchange only produce **one** user notification (no duplicate spam in channels; optional confirm via logs).
result: skipped
reason: "与 Test 1 相同：缺少 live 场景下重复触发阻断的条件"

### 4. Empty notification channels
expected: Strategy with no usable notification channels still **blocks** the open safely; no crash; no outbound notify to channels (may see a single bounded warning in server logs only).
result: skipped
reason: "无运行中服务与策略配置用于人工点验；空渠道与阻断语义由 backend_api_python/tests 覆盖"

### 5. N3 audit log after successful dispatch
expected: After an alert is actually sent through channels, structured logs include an `ibkr_insufficient_data_alert_sent` event (same timeline as the user alert, not on skipped/empty-channel paths).
result: skipped
reason: "无联调环境产生真实日志流；N3 载荷与发射路径由 test_data_sufficiency_logging / test_ibkr_insufficient_user_alert 覆盖"

## Summary

total: 5
passed: 0
issues: 0
pending: 0
skipped: 5
blocked: 0

## Gaps

[none yet]

## Notes

无 issue 类测试结果；全部 skipped 均带 `reason`。若日后具备 live IBKR + 通知渠道的 staging，可重开人工观测项 1–3、5；当前依赖 `backend_api_python/tests`（见各条 `reason`）。
