# Phase 1: IBKR schedule + sufficiency domain model - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-16
**Phase:** 01-ibkr-schedule-sufficiency-domain-model
**Areas discussed:** Sufficiency result contract, reason code granularity, fail-safe policy, lookback normalization, component boundary

---

## Sufficiency Result Contract

| Option | Description | Selected |
|--------|-------------|----------|
| 精简版 | `sufficient + reason_code + required/available + diagnostics` | |
| 强类型版 | 固定顶层字段，便于下游消费与测试断言 | ✓ |
| 可扩展版 | 主字段固定 + details 字典扩展 | |

**User's choice:** 强类型版  
**Notes:** User requested clarification on result usage; decision anchored on downstream guard/alert stability and testability.

---

## Reason Code Granularity

| Option | Description | Selected |
|--------|-------------|----------|
| 粗粒度 | 4-6 个稳定主码 | |
| 细粒度 | 更细原因分类 | ✓ |
| 混合 | 主码 + sub_reason | |

**User's choice:** 细粒度  
**Notes:** User explicitly selected fine-grained reason codes.

---

## Schedule Failure Policy

| Option | Description | Selected |
|--------|-------------|----------|
| Fail-safe | schedule 不可信时阻断 open/add，保留 close/reduce | ✓ |
| 自然日降级 | 用自然日估算继续 | |
| 策略可配置 | 默认阻断，策略可改 | |

**User's choice:** Fail-safe  
**Notes:** User confirmed this decision multiple times as non-negotiable.

---

## Lookback Normalization

| Option | Description | Selected |
|--------|-------------|----------|
| bars-only | 策略仅声明 timeframe+bars，框架负责时段语义 | ✓ |
| time-window-only | 全部转时间窗 | |
| dual | bars+time 双轨更严格 | |

**User's choice:** bars-only  
**Notes:** User emphasized clear responsibility split: strategy declares bar requirements; framework interprets IBKR session context.

---

## Insufficient Threshold

| Option | Description | Selected |
|--------|-------------|----------|
| 硬阈值 | `available < required` 即不足 | ✓ |
| 容差阈值 | 允许部分缺口通过 | |
| 按市场差异 | 市场类型区分阈值 | |

**User's choice:** 硬阈值  
**Notes:** User stated this as obvious choice.

---

## Component Boundary (trading_hours vs validator)

| Option | Description | Selected |
|--------|-------------|----------|
| 合并组件 | 单一模块做会话+充分性 | |
| 并列组件 | `trading_hours` 与 `df_validator` 并列，各司其职 | ✓ |
| 渐进替换 | 先封装后替换 | |

**User's choice:** 并列组件  
**Notes:** User explicitly rejected merging responsibilities and proposed extracting only shared utility parts.

---

## Claude's Discretion

- Final naming (`df_filter` vs `df_validator` vs `data_sufficiency_validator`)
- Shared utility module split details
- Exact field naming for strong-typed sufficiency result

## Deferred Ideas

- Immediate full replacement of existing `trading_hours` logic
- Tolerance-based threshold in this milestone
