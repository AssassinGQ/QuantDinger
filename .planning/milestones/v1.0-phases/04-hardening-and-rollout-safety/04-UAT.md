---
status: testing
phase: 04-hardening-and-rollout-safety
source: 04-01-SUMMARY.md, 04-02-SUMMARY.md
started: 2026-04-20T14:25:14Z
updated: 2026-04-20T14:25:14Z
---

## Current Test

number: 1
name: 默认 guard 开启时，数据不足会阻断开仓/加仓
expected: |
  在未设置 QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED 的情况下，
  对 live + IBKR 的 open/add 信号，若数据不足，应出现阻断行为（不下单），
  并可观测到对应不足事件链路（例如阻断日志/后续告警链路仍按 Phase 3 语义工作）。
awaiting: user response

## Tests

### 1. 默认 guard 开启时，数据不足会阻断开仓/加仓
expected: 未设置 env 时 live+IBKR open/add 在数据不足场景会阻断（不下单），并保留既有不足告警链路语义
result: pending

### 2. 关闭 guard 后，sufficiency 分支整体跳过
expected: 设置 QUANTDINGER_IBKR_SUFFICIENCY_GUARD_ENABLED=false 后，live+IBKR open/add 不再因 sufficiency 被阻断，且不会发送该分支触发的 Phase 3 不足用户告警
result: pending

### 3. sufficiency 检查日志带可关联维度
expected: ibkr_data_sufficiency_check 含 event_lane=sufficiency_evaluation；当上下文存在时包含 exchange_id/strategy_id；不存在时不应出现 exchange_id=""
result: pending

### 4. schedule snapshot 重试可观测且有界
expected: get_ibkr_schedule_snapshot 瞬时失败时会记录 ibkr_schedule_snapshot_retry 并在重试后恢复；持续失败会在有限次数后按既有失败语义返回（无无限重试）
result: pending

### 5. 运维边界文档可用于排障
expected: 04-OPERATOR-BOUNDARIES.md 明确四类日志族、kill-switch 行为、告警耦合与已知边界，便于值班快速判断是否为已知风险边界
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
