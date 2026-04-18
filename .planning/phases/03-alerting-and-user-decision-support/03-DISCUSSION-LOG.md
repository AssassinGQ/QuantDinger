# Phase 3: Alerting and user decision support - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-18
**Phase:** 3-alerting and user decision support
**Areas discussed:** 触发与日志分工, 冷却与去重, 有仓 vs 空仓文案, 渠道与 payload

---

## 触发与日志分工

| Option | Description | Selected |
|--------|-------------|----------|
| 仅在实际拦截 open/add 入队时触发 | 与 `ibkr_open_blocked_insufficient_data` 紧耦合，避免每 tick 评估不足刷屏 | ✓ |
| 每次评估 insufficient 都考虑发告警 | 靠冷却扛噪音 | |
| 混合：窗口内仅首次 blocked 发用户告警 | 窗口内后续仅日志 | |

**User's choice:** 仅在实际拦截 open/add 入队时触发（`block_only`）

**Notes:** 与 Phase 2 双结构化日志分工一致：Phase 2 管机器审计，Phase 3 管用户通道。

---

## 冷却与去重

### 复合键

| Option | Description | Selected |
|--------|-------------|----------|
| strategy + symbol + reason + exchange | 与 R4 字段一致，不同原因/标的独立 | ✓ |
| strategy + symbol + exchange | 不按 reason 分桶 | |
| 仅 strategy | 过粗 | |

**User's choice:** strategy_id + symbol + reason_code + exchange_id

### 默认冷却

| Option | Description | Selected |
|--------|-------------|----------|
| 5 分钟 | 同一键下抑制重复用户告警 | ✓ |
| 15 分钟 | | |
| 60 分钟 | | |
| Claude's Discretion | Planner 选默认 | |

**User's choice:** 5 分钟（用户曾询问「是什么的冷却」，已澄清为同一复合键下用户告警抑制窗口）

---

## 有仓 vs 空仓文案

### 无持仓

| Option | Description | Selected |
|--------|-------------|----------|
| info + 无 close/hold | | |
| warning + 若后续建仓提示 | | |
| warning + 不写 close/hold | 仅说明风险与数据状态 | ✓ |

**User's choice:** `warn_no_close_hold`

### 有持仓

| Option | Description | Selected |
|--------|-------------|----------|
| 标题或首行明确「有持仓」 | | ✓ |
| 仅在正文/payload 体现持仓 | | |

**User's choice:** `emphasize`（标题或首行突出有仓 + R5 close/hold 要求仍适用于正文）

---

## 渠道与 payload

### 发送路径

| Option | Description | Selected |
|--------|-------------|----------|
| load_notification_config + SignalNotifier.notify_signal | 与现有信号通知一致 | ✓ |
| 仅 persist_notification | | |
| 分路径 | | |

**User's choice:** `signal_notifier`

### 字段映射

| Option | Description | Selected |
|--------|-------------|----------|
| 镜像 Phase 2 稳定键 + 人类可读摘要 | | ✓ |
| 仅人类可读摘要 | | |
| 顶层友好 + nested blocked_open_context | | |

**User's choice:** `mirror_keys`

---

## Claude's Discretion

- N3 事件在「至少一渠道成功」vs「仅尝试」上的精确语义（见 `03-CONTEXT.md` D-11）。
- 冷却/去重覆盖配置挂载点（全局 vs `notification_config` 扩展字段）。

## Deferred Ideas

- ROADMAP 中 `stale_prev_close`、大 `missing_window` 操作员文案细化（部分可进 Phase 3 copy，阈值调优或延续 Phase 4）。
