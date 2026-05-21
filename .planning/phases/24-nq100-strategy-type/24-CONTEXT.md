# Phase 24: NQ100 Strategy Type - Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Phase Boundary

创建 `NQ100Strategy` 继承 `CrossSectionalStrategy`，实现动态 universe 绑定（从 Phase 19 PIT API）和三种可配置 delisting 策略（immediate / delayed_N_months / hold_until_signal_exit），确保回测引擎与实盘策略均遵守 delisting 策略配置。

不在本 phase：截面前端 UI、截面实盘自动化（v3）、自动化破产/造假检测（需外部数据源）、Mag7 约束实现逻辑（仅预留配置）。

</domain>

<decisions>
## Implementation Decisions

### STRAT-01：Universe 动态绑定
- **D-01:** 采用三层继承结构：`CrossSectionalStrategy` → `DynamicCrossSectionalStrategy` → `NQ100Strategy`（或其他 universe 子类如 `SP100Strategy`）。
- **D-02:** 中间层 `DynamicCrossSectionalStrategy` 提供接口 `get_universe_list(as_of_date: date) -> List[str]`，子类必须实现此接口返回动态成分股列表。
- **D-03:** `NQ100Strategy.get_universe_list(as_of_date)` 调用 Phase 19 的 `get_constituents_as_of(as_of_date)` 获取 PIT 成分股。
- **D-04:** 动态 universe 与静态 `symbol_list` 互斥：若 `trading_config` 中同时配置 `symbol_list` 和 `universe` 字段 → 校验报错（HTTP 4xx + 明确 msg）。
- **D-05:** `DynamicCrossSectionalStrategy.get_data_request()` 调用子类 `get_universe_list()` 替代静态 `symbol_list` 读取。

### STRAT-02：Delisting Policy 架构
- **D-06:** 采用分层架构：Strategy 层处理 universe 成员池调整，Runner 层处理执行时机和强制卖出。
- **D-07:** Strategy 层职责：
  - `immediate` / `delayed` 模式：被剔除股**不参与**排名（从 universe 移除）
  - `hold_until_signal_exit` 模式：被剔除股**仍参与**排名，标记为 `excluded_from_universe`
- **D-08:** Runner 层职责：
  - 新增 `DelistingPolicyFilter` 到 FilterChain
  - 检测 `qd_nq100_change_events` 中成分变更事件
  - 根据 `delisting_policy.mode` 和 `effective_date` 决定强制卖出时机
- **D-09:** `hold_until_signal_exit` 模式下，卖出信号发出后（排名落出 TopN），Runner 标记排除出 universe，后续调仓不再参与排名。

### Delisting Policy 配置结构
- **D-10:** 配置字段：`trading_config.delisting_policy = {"mode": "immediate" | "delayed" | "hold_until_signal_exit", "months": N}`
- **D-11:** `months` 字段仅在 `mode="delayed"` 时有效，默认值为 3，可配置范围 1-12。
- **D-12:** `mode="immediate"` 时，生效日强制卖出被剔除股持仓。
- **D-13:** `mode="delayed"` 时，延迟 `months` 月后强制卖出被剔除股持仓。

### 特殊案例处理
- **D-14:** 破产/财务造假/退市风险：实盘立即退出（最快速度卖出），不受 `delisting_policy` 配置影响。
- **D-15:** 回测模拟：特殊案例统一假设**全亏**（退出价格=0），保守方案，不区分是否有交易数据。
- **D-16:** Phase 24 仅支持**手动标记**特殊案例（通过 `trading_config.force_exit_symbols` 列表），自动化检测延后到后续 phase（需外部数据源接入）。

### Mag7 集中度约束
- **D-17:** Phase 24 仅**预留配置字段**，实现逻辑延后到后续 phase：
  - `trading_config.mag7_min_count`: 组合中至少保留 N 只 Mag7（如 N=3）
  - `trading_config.mag7_max_weight`: 单只 Mag7 权重上限（如 X=10%）
- **D-18:** 当前 phase 不实现 Mag7 约束逻辑，完全依赖截面排名自然配置。

### 回测一致性
- **D-19:** 回测引擎与实盘策略共用 `trading_config.delisting_policy` 配置，确保行为一致。
- **D-20:** 回测引擎复用 Runner 的 `DelistingPolicyFilter`，不单独实现一套逻辑。

### Claude's Discretion
- `DynamicCrossSectionalStrategy` 接口命名细节（`get_universe_list` vs `get_constituents_list`）
- `DelistingPolicyFilter` 内部实现结构（函数拆分、模块组织）
- `force_exit_symbols` 字段验证逻辑（格式、去重、时效）
- 回测全亏假设的具体实现位置（引擎层 vs Runner 层）

### Folded Todos

（本 phase `todo match-phase` 无匹配项，无折叠 todo。）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase / 需求
- `.planning/ROADMAP.md` — Phase 24 目标、STRAT-01/02 成功标准、已锁定讨论要点（Mag7 集中度约束、delisting 策略）。
- `.planning/REQUIREMENTS.md` — **STRAT-01/02** 条目。

### 上游 CONTEXT（已锁定依赖）
- `.planning/phases/19-nq100-universe-data-plane/19-CONTEXT.md` — PIT API、`get_constituents_as_of()`、`qd_nq100_change_events` 表结构、`effective_date` 语义。
- `.planning/phases/21-backtest-correctness/21-CONTEXT.md` — T+1 执行语义、`TradabilityFilter` + `ExecutionPriceFilter` 过滤链、`UNTRADABLE` 状态定义。
- `.planning/phases/22-cross-sectional-portfolio-backtest-engine/22-CONTEXT.md` — 回测引擎 API 形态、`scores`+`weights` 契约、可复现包要求。

### 现有实现基线（集成点）
- `backend_api_python/app/strategies/cross_sectional.py` — `CrossSectionalStrategy` 基类，`get_data_request()` / `get_signals()` 接口。
- `backend_api_python/app/strategies/runners/cross_sectional_runner.py` — `CrossSectionalRunner`，`_filter_phase21_signals()` 和 FilterChain。
- `backend_api_python/app/strategies/runners/cross_sectional_filter_chain.py` — Phase 21 过滤器链，`FilterChain` / `FilterContext` 模式。
- `backend_api_python/app/services/universe_nq100_service.py` — `get_constituents_as_of()` PIT 查询入口。

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `CrossSectionalStrategy`：基类接口，NQ100Strategy 继承并覆盖 `get_data_request()`（或引入中间层 `DynamicCrossSectionalStrategy`）。
- `CrossSectionalRunner._filter_phase21_signals()`：现有执行过滤链，可新增 `DelistingPolicyFilter`。
- `FilterChain` / `FilterContext` 模式：Phase 21 已建立，新增过滤器遵循相同结构。
- `get_constituents_as_of()`：PIT universe 查询，NQ100Strategy 调用此接口。

### Established Patterns
- 策略继承结构：子类覆盖 `get_data_request()` 实现特定 universe 逻辑。
- Flask Blueprint + `{code, msg, data}` 响应规范。
- pytest fixture 验证回测正确性（Phase 21 已示范）。

### Integration Points
- `app/strategies/dynamic_cross_sectional.py` — 新建中间层，提供 `get_universe_list()` 接口。
- `app/strategies/nq100_strategy.py` — 新建 NQ100Strategy，继承 DynamicCrossSectionalStrategy。
- `app/strategies/runners/cross_sectional_filter_chain.py` — 新增 `DelistingPolicyFilter`。
- `app/routes/strategy.py` — 策略创建 API 需支持 `delisting_policy` 和 `force_exit_symbols` 配置验证。

</code_context>

<specifics>
## Specific Ideas

- 三层继承结构：`CrossSectionalStrategy` → `DynamicCrossSectionalStrategy` → `NQ100Strategy`，中间层提供 `get_universe_list(date)` 接口。
- Delisting Policy 分层：Strategy 调整 universe 成员池（`hold_until_signal_exit` 被剔除股仍参与排名），Runner 新增 `DelistingPolicyFilter` 处理执行时机。
- 配置结构：`{"mode": "immediate" | "delayed" | "hold_until_signal_exit", "months": N}`。
- 特殊案例：实盘立即退出，回测统一全亏假设（保守方案）。
- Mag7 约束：预留配置字段，延后实现。

</specifics>

<deferred>
## Deferred Ideas

- **自动化破产/造假检测** — 需外部数据源（SEC filings / 新闻 API），延后到后续 phase。
- **Mag7 约束实现逻辑** — 预留配置字段，实现延后。
- **其他 universe 子类**（如 `SP100Strategy`）— 模式相同，后续按需创建。

### Reviewed Todos (not folded)

无。

</deferred>

---

*Phase: 24-nq100-strategy-type*
*Context gathered: 2026-05-20*