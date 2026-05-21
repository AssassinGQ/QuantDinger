# Phase 21: Backtest correctness - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-15
**Phase:** 21-backtest-correctness
**Areas discussed:** 可交易性判定规则, T+1 执行细则, 退市样本保留与出场口径, 调仓日历约束

---

## 可交易性判定规则

| Option | Description | Selected |
|--------|-------------|----------|
| 严格口径 | 检查 `next_open`、停牌/涨跌停与状态过滤，买不到留现金、卖不掉继续持有 | ✓ |
| 简化口径 | 仅检查 `next_open` 是否存在 | |
| 可配置口径 | 默认严格，允许切换简化 | ✓（用户要求默认严格并支持 env 配置） |

**User's choice:** 默认严格口径，并设计执行层过滤器（公司行动/退市/代码变更、流动性阈值、现金替代原则），同时支持 env 配置。  
**Notes:** 用户补充了明确过滤器集合，并强调“现金替代，不自动补买其他标的”。

---

## T+1 执行细则

| Option | Description | Selected |
|--------|-------------|----------|
| A | 固定 `next_open` 执行，无效则不成交 | ✓（默认） |
| B | `next_open` 缺失时 fallback 成交 | |
| A + fallback 配置 | 默认 A，同时可配置 fallback | ✓ |

**User's choice:** A 为默认，并允许配置 fallback：`ffill` / `close` / `bfill`。  
**Notes:** 用户确认当前讨论为回测语义；同时关注回测与实盘一致性，要求关键执行闸门一致。

---

## 退市样本保留与出场口径

| Option | Description | Selected |
|--------|-------------|----------|
| A | 历史保留 + 不可交易持仓继续持有直至可交易退出 | ✓ |
| B | 历史保留 + 生效日强制退出 | |
| C | 默认 A + 可配置强制退出 | |

**User's choice:** 选择 A 作为唯一主实现（同时定义唯一例外）。  
**Notes:**  
- 定义 `UNTRADABLE` 状态，触发条件包含退市、长期停牌（默认 5 天可配置）、代码变更/换股、破产程序。  
- `UNTRADABLE` 持仓在调仓日跳过买卖，恢复交易后按完整调仓周期处理。  
- 唯一强制退出例外：Cash M&A，按确定收购价入账。

---

## 调仓日历约束

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | NDAQ/IC `effective_date` 唯一准绳 | ✓ |
| 2 | 交易所日历 + 人工覆盖 | |
| 3 | 双源校验 + fallback | |

**User's choice:** 以 NDAQ/IC 为唯一准绳。  
**Notes:** 若 T/T+1 跨越生效日，则原定 T+1 调仓顺延至 T+2 执行，避免生效日当天调仓。

---

## Claude's Discretion

- 过滤器模块的代码组织与调用顺序。
- 配置项键名、默认值常量位置与文档格式。
- fallback 策略在回测引擎中的开关落点。

## Deferred Ideas

- None
