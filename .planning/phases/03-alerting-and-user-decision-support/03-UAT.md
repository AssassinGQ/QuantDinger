---
status: partial
phase: 03-alerting-and-user-decision-support
source:
  - 03-01-SUMMARY.md
  - 03-02-SUMMARY.md
started: "2026-04-18T14:00:00.000Z"
updated: "2026-04-18T14:30:00.000Z"
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

[testing complete]

<!-- Note: status=partial — 全部人工项 skipped（无 live 联调条件）；功能由 CI/pytest 覆盖。 -->

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

- truth: "团队可在 staging 或纸面对 IBKR live 阻断路径完成 Phase 3 人工 UAT"
  status: failed
  reason: "User reported: 没有这样的测试条件"
  severity: minor
  test: 1
  root_cause: "缺少可用的 live IBKR（ibkr-paper/ibkr-live）联调环境与完整通知渠道配置，无法在真实执行链路上做人工观测"
  artifacts: []
  missing:
    - "Staging：live 模式 + IBKR Gateway + 策略 notification_config + 可稳定触发数据不足阻断的信号场景"
  debug_session: ""
