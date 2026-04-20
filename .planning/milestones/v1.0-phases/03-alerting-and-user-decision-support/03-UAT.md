---
status: testing
phase: 03-alerting-and-user-decision-support
source:
  - 03-01-SUMMARY.md
  - 03-02-SUMMARY.md
started: "2026-04-18T14:00:00.000Z"
updated: "2026-04-20T15:05:00Z"
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 1
name: User notification on IBKR insufficient live block
expected: |
  Live IBKR open/add blocked by sufficiency should trigger one user-channel alert.
  In flat-account case, copy should NOT claim existing position and should NOT ask close/hold decision.
awaiting: user response

<!-- 5/5 人工项为 skipped 且均有 reason；无 pending/blocked。Live 链路与渠道观测由后续 staging 补做；行为覆盖见列出的 pytest 模块。 -->

## Tests

### 1. User notification on IBKR insufficient live block
expected: Live IBKR open/add blocked by sufficiency produces one user-channel alert with flat-account copy rules (no 「有持仓」, no close/hold decision prompt).
result: pending

### 2. Positioned-account alert copy
expected: If the strategy already has a non-zero position on the same symbol when blocked, the user-visible title or first line contains 「有持仓」 and the body asks you to decide 平仓 or 继续持有 explicitly.
result: pending

### 3. Cooldown dedup (no spam within 5 minutes)
expected: Two blocked attempts within five minutes for the same strategy, symbol, reason code, and exchange only produce **one** user notification (no duplicate spam in channels; optional confirm via logs).
result: pending

### 4. Empty notification channels
expected: Strategy with no usable notification channels still **blocks** the open safely; no crash; no outbound notify to channels (may see a single bounded warning in server logs only).
result: pending

### 5. N3 audit log after successful dispatch
expected: After an alert is actually sent through channels, structured logs include an `ibkr_insufficient_data_alert_sent` event (same timeline as the user alert, not on skipped/empty-channel paths).
result: pending

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps

[none yet]

