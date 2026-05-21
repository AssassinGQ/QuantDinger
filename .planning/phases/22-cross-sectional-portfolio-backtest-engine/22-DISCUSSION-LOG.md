# Phase 22: Cross-sectional portfolio backtest engine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `22-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-15
**Phase:** 22-Cross-sectional portfolio backtest engine
**Areas discussed:** API contract, universe/panel, portfolio weighting, news timing, sector neutral reporting, long/short scope

---

## API contract

| Option | Description | Selected |
|--------|-------------|----------|
| Async job API | job_id + poll | |
| Sync POST aligned with existing `/api/backtest` | Same interaction style as current QD backtest | ✓ |
| Hybrid | Both | |

**User's choice:** Sync POST，与现有 QD 回测 API 一致；响应含 **完整可复现包**（universe / config hash / execution policy / neutralization flag 等语义）。

**Notes:** 具体 URL 与字段名实现阶段定稿。

---

## Universe / symbol_list

| Option | Description | Selected |
|--------|-------------|----------|
| symbol_list priority | Explicit list overrides universe | |
| universe priority | PIT universe overrides list | |
| Mutual exclusion | Both set → validation error | ✓ |

**User's choice:** **`symbol_list` 与 `universe` 互斥**；同时传 → **报错**。

---

## effective_date & calendar

| Option | Description | Selected |
|--------|-------------|----------|
| PIT cutoff at signal day T | `effective_date <= T` for membership at ranking | ✓ |
| PIT cutoff at execution T+1 | `effective_date <= T+1` | |

**User's choice:** 与 Phase 21 / roadmap 一致，在信号日 **T** 使用 **`effective_date <= T`** 的最新已生效成分；执行仍 T+1（及 Phase 21 顺延规则）。

**Notes:** `effective_date` 作用在 CONTEXT 中已写明（防未来、PIT、与调仓日历联动）。

---

## News / non-OHLCV timing

| Option | Description | Selected |
|--------|-------------|----------|
| Same-bar with price | Allow news to trade same session | |
| Next rebalance only | No realtime news; next period batch | ✓ |

**User's choice:** K 线与新闻等均 **T+1（或下一调仓周期）** 生效；当前不做实时新闻分析。

---

## scores vs weights

| Option | Description | Selected |
|--------|-------------|----------|
| Framework maps score → weight | Auto-normalize scores to weights | |
| Separate fields | scores = rank only, weights = allocation; both required | ✓ |
| Optional weights with equal fallback | Missing weights → equal | |

**User's choice:** **`scores` 与 `weights` 分离**；缺一 **报错**；若数值相同由策略 **自行填两份**；框架 **支持加权** 但不写死业务加权规则。

---

## Long / short (Phase 22 scope)

| Option | Description | Selected |
|--------|-------------|----------|
| Long default, short opt-in | | |
| Long/short like cross_sectional_signals default | | |
| Long-only hard in Phase 22 | | ✓ |

**User's choice:** Phase **22 硬限制仅做多**。

---

## Sector neutralization reporting

| Option | Description | Selected |
|--------|-------------|----------|
| Dual full blocks in one response | neutral_off + neutral_on each full metrics/curve | ✓ |
| Two separate API calls | | |
| Primary + summary only | | |

**User's choice:** 单次响应 **两套完整结果**（开/关对比）。

---

## Claude's Discretion

- `weights` 未归一化时引擎是 **报错** 还是 **归一化** — 实现阶段二选一并由测试固定。

## Deferred Ideas

- Mag7、regime 动态权重、前端 UI — 见 `22-CONTEXT.md` `<deferred>`。
