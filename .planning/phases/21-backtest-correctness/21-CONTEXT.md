# Phase 21: Backtest correctness - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning

<domain>
## Phase Boundary

在截面回测路径中落实三类正确性约束：  
1) 幸存者偏差修复（退市样本历史保留），  
2) T 日信号 -> T+1 执行（禁止同 bar 未来函数），  
3) 不可交易标的处理（买不到留现金、卖不掉继续持有）。  

本 phase 只约束“回测数据与执行语义正确性”，不扩展到前端、实盘自动化策略 UI 或交易成本高级建模。

</domain>

<decisions>
## Implementation Decisions

### 数据日期与信号-执行隔离
- **D-01:** 因子计算与截面打分严格使用 **T 日收盘价**；信号生成阶段禁止混入任何 T+1 数据。
- **D-02:** 执行阶段与信号阶段完全分离：信号在 T 日收盘后确定，成交在 T+1 执行。
- **D-03:** 回测执行价默认固定为 `next_open`；同时支持可配置 fallback 策略（`ffill` / `close` / `bfill`）用于研究对比。

### 执行层可交易过滤器（严格口径）
- **D-04:** 默认采用严格执行过滤：在 T+1 执行前对候选单运行“执行层过滤器”，至少包含公司行动/退市事件、流动性阈值、交易状态过滤。
- **D-05:** 增加公司行动过滤器：若存在未决并购（M&A）、Delisting、Symbol Change 等事件，目标标的不执行买卖。
- **D-06:** 增加流动性过滤器：默认要求 `20D` 日均成交额超过阈值（默认 100 万美元，可通过环境变量配置）。
- **D-07:** `next_open` 有效性定义：`>0` 且非 NaN；无效即视为该时点不可成交。
- **D-08:** 买入不可成交时，执行严格现金替代：保留对应现金份额，不自动替换买入其他备选标的。

### 退市/停牌与不可交易持仓处理
- **D-09:** 退市标的历史 K 线保留在回测面板中，不因当前成分变化而从历史移除（AUDIT-01）。
- **D-10:** 定义统一不可交易状态 `UNTRADABLE`，触发条件包括：退市/摘牌、长期停牌（超过 N 个交易日，默认 5，可配置）、代码变更/换股、破产程序等。
- **D-11:** 调仓执行时若持仓标的为 `UNTRADABLE`，跳过其所有交易动作并继续持有，直到恢复可交易后再进入正常调仓决策流程。
- **D-12:** 恢复交易当日不做“盘中立刻强卖”；按完整调仓周期处理（T 日纳入排序，若触发卖出则 T+1 开盘执行）。
- **D-13:** 唯一强制退出例外：现金收购（Cash M&A）场景，按生效日确定价格强制退出并入账现金。

### 调仓日历约束
- **D-14:** 成分调整生效日以 NDAQ/IC `effective_date` 作为唯一准绳。
- **D-15:** 生效日当天不调仓；当调仓窗口跨越生效日时，原定于 T+1 的执行顺延至 T+2，确保使用稳定成分名单。

### Claude's Discretion
- 执行层过滤器的内部实现结构（函数拆分、模块组织、缓存策略）。
- 各过滤器环境变量命名与默认值常量位置。
- fallback 策略开关的配置键与文档呈现方式。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase/Requirement 契约
- `.planning/ROADMAP.md` — Phase 21 的 AUDIT-01/02/03 目标、已锁定讨论要点与跨 phase 依赖。
- `.planning/REQUIREMENTS.md` — AUDIT-01/02/03 需求定义与验收边界。
- `.planning/PROJECT.md` — v2.0 范围边界（仅后端 + 脚本；无前端截面 UI / 无实盘截面自动化）。

### 上游已锁定上下文
- `.planning/phases/19-nq100-universe-data-plane/19-CONTEXT.md` — NQ100 PIT 数据平面、`effective_date` 与变更事件来源约束。
- `.planning/phases/20-built-in-factors-normalization/20-CONTEXT.md` — 因子/标准化口径及 “T+1 执行约束归属 21/22” 的上游锁定。

### 现有代码实现基线
- `backend_api_python/app/strategies/cross_sectional.py` — 当前截面策略信号生成入口（尚未内建 Phase 21 执行审计约束）。
- `backend_api_python/app/strategies/cross_sectional_signals.py` — 当前仓位变更信号生成规则（可作为执行层过滤改造接入点）。
- `backend_api_python/app/strategies/runners/cross_sectional_runner.py` — 截面策略 tick 执行管道（调仓时机与 dispatch 路径）。
- `backend_api_python/app/factors/panel.py` — 面板/因子计算基础实现（用于保持 T 日数据口径清晰隔离）。
- `scripts/cross_sectional/nq100_cross_sectional.py` — 现有脚本回测基线（当前为简化执行假设，需对齐新 correctness 口径）。

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/strategies/cross_sectional_signals.py`: 已有“目标仓位 vs 当前仓位”差分信号生成，可在执行前插入可交易过滤器。
- `app/strategies/runners/cross_sectional_runner.py`: 已有统一 tick 调度与信号分发路径，适合承接 T+1 执行闸门。
- `app/factors/panel.py`: 因子按日期-标的面板计算，便于严格维持 T 日输入口径。

### Established Patterns
- 策略层与 runner 层分离：策略负责信号，runner 负责调度与执行分发。
- Python 后端以 `app/services`、`app/strategies`、`app/utils` 组织业务与基础设施。
- pytest 为主要回归门禁，新增 correctness 规则应以可复现 fixture 驱动测试。

### Integration Points
- 执行层过滤器应接入 `cross_sectional_runner` 的信号 dispatch 前。
- 状态标记（`UNTRADABLE` / `TRADABLE`）应进入组合状态管理与调仓决策读取路径。
- `effective_date` 读取应与 Phase 19 Universe 数据面 API/存储对齐，避免另建时间口径。

</code_context>

<specifics>
## Specific Ideas

- 默认“严格口径 + 执行层过滤器”，并通过 env 暴露可配置项（阈值、停牌天数、fallback 模式）。
- 回测语义优先：宁可保守（更多未成交），也不允许引入隐式未来函数或不真实成交假设。
- `UNTRADABLE` 恢复后按完整调仓周期卖出，避免恢复日主观择时。

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 21-backtest-correctness*
*Context gathered: 2026-04-15*
