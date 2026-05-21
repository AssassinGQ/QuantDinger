# Phase 22: Cross-sectional portfolio backtest engine - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

交付 **后端多标的截面组合回测引擎**（BT-01）：与现有单标的 `BacktestService.run()` **分离**；消费 Phase **19（UNIV）**、**20（FACTOR/标准化）**、**21（正确性与执行语义）** 的规则；对单次调用产出 **一个组合** 的净值/收益序列与标准摘要指标；结果在固定输入下 **可复现**、可回归测试。

不在本 phase：截面前端 UI、截面实盘自动化、NQ100 策略类型与 delisting 策略细节（Phase 24）、网格搜索脚本（Phase 23）、Mag7 集中度约束（Phase 24）。

</domain>

<decisions>
## Implementation Decisions

### API 形态与复现
- **D-01:** 新引擎的 HTTP 形态与现有 QD 回测一致：**同步 POST**、响应包络 **`{code,msg,data}`**；具体 URL 与字段名由 plan 实现时定，但不得引入与全站不一致的包络或异步契约（除非后续单独开 phase）。
- **D-02:** 成功响应的 `data` 内必须包含 **完整可复现包**（语义锁定，键名实现定稿）：至少覆盖 **universe 快照标识或等价 digest**、**因子/指标与标准化配置 hash 或等价物**、**执行策略（含 Phase 21 相关开关）**、**行业中性化开/关状态** 等，使下游可用同一输入复跑并得到一致结果。

### 股票池请求：互斥
- **D-03:** 请求体中 **`symbol_list` 与 `universe`（如 NQ100）互斥**：若两者**同时非空**，返回 **校验错误**（HTTP 4xx + 明确 `msg`），**不做**优先级裁决。

### `effective_date` 与信号 / 执行日
- **D-04:** 在**信号日 T** 做截面排序与组合决策时，成分池采用 **PIT 名单**，满足 **`effective_date <= T`** 的「最新已生效」记录；**禁止**使用尚未到 `effective_date` 的未来成分变更。  
- **D-05:** **执行**仍遵守 Phase **21** 已锁定语义：**T 日信号 → T+1（或经 `effective_date` 规则顺延后的下一可执行日）成交**；`next_open` 为主价格口径；指数调整 **生效日** 不顺延当日执行等规则 **不重复发明**，在引擎内 **复用/对齐** Phase 21 实现。

### 新闻 / 事件 / 非 OHLCV 信息
- **D-06:** 当前产品路径 **不做实时新闻驱动**；新闻与类似事件信息 **仅在下一调仓周期** 与其他输入一并进入决策；与 K 线一致，**不得**用「尚未到下一执行周期」的信息在同一周期内完成交易，避免未来函数。

### `scores` 与 `weights`（硬契约）
- **D-07:** 截面指标在每个**调仓决策点**（信号日 **T**）必须同时输出 **`scores`** 与 **`weights`**（结构为按 symbol 映射或可枚举为 symbol→float）。  
- **D-08:** **`scores` 仅用于排序**（选入组合、先后次序、TopN 等）；**`weights` 仅用于资金分配**（目标仓位比例）。框架 **不** 将 `scores` 自动当作 `weights`。若策略希望二者数值相同，由策略 **自行写入两份相同数据**。  
- **D-09:** **缺少 `scores` 或缺少 `weights` 任一**：**报错终止**，框架 **不提供** 等权、用 score 顶替、或其他兜底。  
- **D-10:** 框架 **支持任意由策略声明的合法加权方案**（等权、市值加权、自定义加权等均由 **`weights` 内容** 表达）；框架 **不写死**「必须等权」或「必须跟踪 NDX 权重」等业务规则。

### 多空范围（Phase 22）
- **D-11:** Phase 22 引擎 **硬限制仅做多**：不支持空头腿；与单标的回测习惯的扩展分阶段处理，若未来放开多空另起配置或后续 phase。

### 行业中性化（与 roadmap 对齐）
- **D-12:** 行业中性化为引擎层 **可选**；默认关、可开、可复现。  
- **D-13:** 单次成功响应中必须包含 **两套完整结果**：**neutral_off** 与 **neutral_on**（各含组合净值或等价收益序列 + 标准摘要指标 + 各自复现子集字段），以满足「开/关对比」报告要求。

### Claude's Discretion
- 可复现包内各字段的 **精确命名**、hash 算法（SHA256 等）与 digest 粒度。  
- `weights` 的数值校验策略（例如是否允许未归一化由引擎 **归一化**，或要求严格和为 1 否则报错）——在实现阶段选一种并写测试固定。  
- 新路由 path（例如是否挂在 `/api/backtest/...` 下）与请求体与单标的回测的 **字段对齐表**。

### Folded Todos

（本 phase `todo match-phase` 无匹配项，无折叠 todo。）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase / 需求
- `.planning/ROADMAP.md` — Phase 22 目标、BT-01 成功标准、已锁定讨论要点（行业中性化对比、成分 `effective_date` 口径、`next_open` / MOO 对应等）。
- `.planning/REQUIREMENTS.md` — **BT-01** 条目。
- `.planning/PROJECT.md` — v2.0 范围（无截面前端、无截面实盘自动化）。

### 上游 CONTEXT（已锁定依赖）
- `.planning/phases/19-nq100-universe-data-plane/19-CONTEXT.md` — PIT、API、`effective_date` 数据源语义。
- `.planning/phases/20-built-in-factors-normalization/20-CONTEXT.md` — 因子集合、标准化默认链路、行业中性化归属 Phase 22 的说明。
- `.planning/phases/21-backtest-correctness/21-CONTEXT.md` — T/T+1、`next_open`、不可交易、`effective_date` 与调仓顺延、执行过滤器链等。

### 现有实现基线（集成点）
- `backend_api_python/app/routes/backtest.py` — 现有单标的回测 API 形态、`qd_backtest_runs` 持久化模式参考。
- `backend_api_python/app/services/backtest.py` — `BacktestService`、指标执行、`_calculate_metrics` / `_format_result` 等组合级指标可对标的参考。
- `backend_api_python/app/strategies/cross_sectional_indicator.py` — `run_cross_sectional_indicator`；**须演进**以支持强制 `scores`+`weights` 契约（当前仅 scores/rankings 不足）。
- `backend_api_python/app/strategies/runners/cross_sectional_runner.py` — Phase 21 执行过滤与 `resolve_shifted_execution_date` 集成参考。
- `backend_api_python/app/strategies/runners/cross_sectional_filter_chain.py` — Phase 21 过滤器链。
- `backend_api_python/app/factors/panel.py` — 多标的面板构建参考。

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BacktestService` 的指标执行、权益曲线与指标计算管线：组合回测可 **对齐字段命名与指标集合**，但 **不得** 把单标的 `run()` 误当作截面引擎本体。
- `run_cross_sectional_indicator`：可扩展为截面回测的「指标沙箱」入口，需增加 **`weights` 输出契约** 与严格校验。
- `CrossSectionalRunner._filter_phase21_signals` / `cross_sectional_filter_chain`：组合回测执行侧应 **复用** Phase 21 语义而非复制一套矛盾规则。

### Established Patterns
- Flask Blueprint + `{code,msg,data}`。
- pytest 回归与 fixture 驱动正确性验证（Phase 21 已示范）。

### Integration Points
- 新增路由模块 + `app/routes/__init__.py` 注册（与 codebase map 一致）。
- 新 `app/services/` 下截面组合回测服务类，避免与 `BacktestService` 职责混淆。

</code_context>

<specifics>
## Specific Ideas

- 用户明确：**排序与加权字段分离**；**二者缺一不可**；**互斥股票池参数**；**行业中性化单次双完整结果**；**Phase 22 仅做多**；**API 与现有回测一致、带全量复现包**。
- 产品路径上 **无实时新闻分析**；新闻等 **下一周期** 统一进入决策。

</specifics>

<deferred>
## Deferred Ideas

- **Mag7 / 组合集中度约束** — Phase 24（roadmap 已标）。  
- **动态因子权重（regime）** — Phase 23 研究脚本层（roadmap）。  
- **截面策略前端管理 UI** — v3 / out of scope（PROJECT.md）。  
- **同请求内实时新闻流与同 bar 交易** — 与当前锁定语义冲突，不作为 v2.0 Phase 22 范围。

### Reviewed Todos (not folded)

无。

</deferred>

---

*Phase: 22-cross-sectional-portfolio-backtest-engine*
*Context gathered: 2026-05-15*
