---
phase: 03-alerting-and-user-decision-support
verified: 2026-04-20T14:48:19Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
---

# Phase 03 Verification

## Goal

在 IBKR live open/add 因数据不足被阻断时，经策略配置渠道发送去重告警，并提供 R5 决策支持文案，同时在用户告警路径产出 N3 结构化事件 `ibkr_insufficient_data_alert_sent`。

## Automated

- `python3 -m pytest backend_api_python/tests -q`  
  结果：`1191 passed, 11 skipped, 2 warnings in 382.34s`

## Must-haves

- [x] **Alerts delivered via configured channels**  
  证据：`signal_executor.py` 在阻断分支调用 `dispatch_insufficient_user_alert_after_block`，并在 `_notification_config` 缺失/空 channels 时回退 `load_notification_config`；`test_ibkr_insufficient_block_triggers_user_notify`、`test_ibkr_insufficient_block_loads_notification_config_when_missing` 覆盖。

- [x] **Repeated alerts deduplicated by cooldown**  
  证据：`ibkr_insufficient_user_alert.py` 定义 `(strategy_id, symbol, reason_code, exchange_id)` 键、`DEFAULT_COOLDOWN_SECONDS = 300.0`、`_dedup_lock`；`test_dedup_suppresses_second_send_within_cooldown`、`test_dedup_allows_after_cooldown_elapsed`、`test_dedup_key_isolates_exchange_id`、`test_dedup_key_isolates_reason_code` 覆盖。

- [x] **Payload includes actionable decision context**  
  证据：`build_insufficient_user_alert_extra` 包含 `_execution_mode`、`reason_code`、required/available/missing 诊断字段、`position_snapshot`、`user_alert_title/user_alert_plain`；`test_flat_alert_copy_has_no_position_prompt` 与 `test_positioned_alert_copy_requires_hold_close_prompt` 验证 flat/positioned 文案差异与 close/hold 提示。

- [x] **Block-only trigger (goal-backward link)**  
  证据：用户告警调度位于 `emit_ibkr_open_blocked_insufficient_data(...)` 之后、同一 `if not suff_result.sufficient` 分支内，且在 `return False` 前执行；不存在“每次 sufficiency 检查均告警”的独立路径。

- [x] **N3 structured event on user-alert path**  
  证据：`data_sufficiency_logging.py` 实现 `build_ibkr_insufficient_data_alert_sent_payload` 与 `emit_ibkr_insufficient_data_alert_sent`；`dispatch_insufficient_user_alert_after_block` 在 dedup 放行且 `notify_signal` 返回后组装并发射事件；`test_insufficient_data_alert_sent_payload_shape`、`test_emit_insufficient_data_alert_sent_smoke` 覆盖。

- [x] **Phase-level regression requirement (full backend suite)**  
  证据：Phase 03 要求“每个任务 verify 含全量 backend pytest”，本次重新执行全量并通过（1191 passed）。

## Requirement traceability

- **R4 (User Alerting):**  
  `signal_executor.py` + `ibkr_insufficient_user_alert.py` 实现渠道发送、去重、配置回退；`test_ibkr_insufficient_user_alert.py` 与 `test_signal_executor.py` 覆盖。

- **R5 (Existing Position Decision Support):**  
  positioned 分支含“有持仓 + 请自行决定平仓或继续持有”，flat 分支不含误导性 close/hold 指令；对应单测覆盖。

- **N3 (Observability):**  
  `ibkr_insufficient_data_alert_sent` payload builder + emitter 存在并被行为测试验证。

- **N4 (Testability):**  
  dedup、channel dispatch、executor wiring、logging payload/emitter 均具备单元/集成测试；全量套件通过。

## Gaps

- None（在 Phase 03 计划范围内未发现 blocker 或未闭环 must-have）。

## human_verification

- None（本次验证范围以内可由代码与自动化测试直接判定；无需新增人工 gate 才能判定 Phase 03 通过）。
