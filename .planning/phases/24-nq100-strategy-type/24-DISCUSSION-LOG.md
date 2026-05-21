# Phase 24: NQ100 Strategy Type - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 24-nq100-strategy-type
**Areas discussed:** Delisting Policy 架构, Universe 动态绑定, 特殊案例检测 + Mag7, 回测一致性 + 配置

---

## Delisting Policy 架构

| Option | Description | Selected |
|--------|-------------|----------|
| 分层：Strategy 做 universe 限制，Runner 做执行时机 | Strategy 调整 universe 成员池（hold_until_signal_exit 被剔除股仍参与排名），Runner 处理生效日强制卖出逻辑 | ✓ |
| 全部在 Strategy 层 | 所有逻辑集中在 Strategy 层，Runner 透传信号 | |
| 全部在 Runner 层 | 所有逻辑集中在 Runner 层，新增 DelistingPolicyFilter | |

**User's choice:** 分层方案
**Notes:** 三种模式的核心逻辑差异：immediate/delayed 是时间驱动（Runner 层），hold_until_signal_exit 是信号驱动（Strategy 层）。

### Strategy 层 universe exclusion 处理

| Option | Description | Selected |
|--------|-------------|----------|
| 标记 excluded_from_universe | hold_until_signal_exit 模式下，被剔除股仍参与排名但标记为 "excluded_from_universe"；卖出信号发出后，Runner 标记排除 | ✓ |
| 无标记，Runner 落后排除 | hold_until_signal_exit 模式下，被剔除股正常参与排名（无特殊标记）；卖出信号发出后，Runner 检查是否为被剔除股，若是则排除 | |
| 简化：不参与排名，等待自然退出 | hold_until_signal_exit 模式下，被剔除股不参与排名，但仍保留在组合中直到自然退出 | |

**User's choice:** 标记 excluded_from_universe

### Runner 层强制卖出实现

| Option | Description | Selected |
|--------|-------------|----------|
| 新增 Filter | 新增 DelistingPolicyFilter 到 FilterChain，检测 change_events 并根据 delisting_policy 配置决定是否强制卖出 | ✓ |
| 直接修改 _filter | 修改 _filter_phase21_signals() 内部逻辑，不新增 Filter | |
| 独立 Processor | 新增独立的 DelistingPolicyProcessor 在信号 dispatch 前执行 | |

**User's choice:** 新增 Filter

---

## Universe 动态绑定

| Option | Description | Selected |
|--------|-------------|----------|
| 三层继承 + get_universe_list 接口 | 中间层 DynamicCrossSectionalStrategy 提供 get_universe_list(date) 接口，子类 NQ100Strategy/SP100Strategy 实现此接口 | ✓ |
| 多个 get_xxx_list 接口 | 中间层提供 get_nq100_list / get_sp100_list 等多个接口，子类选择性实现 | |
| 二层继承，直接覆盖 | 不引入中间层，每个 universe 直接继承 CrossSectionalStrategy 并覆盖 get_data_request() | |

**User's choice:** 三层继承结构
**Notes:** 用户提出三层方案：CrossSectionalStrategy → DynamicCrossSectionalStrategy → NQ100Strategy，中间层提供 get_universe_list 接口。

---

## 特殊案例处理

| Option | Description | Selected |
|--------|-------------|----------|
| 手动标记 + Runner 强制退出 | Phase 24 仅支持手动标记（trading_config.force_exit_symbols），Runner 在每次调仓时检查并强制退出。自动化检测延后 | ✓ |
| 不实现特殊案例区分 | 不区分特殊案例，完全依赖 delisting_policy 配置处理所有被剔除股 | |
| 自动化检测 | 实现自动化检测（破产/造假），通过新闻/SEC API 触发强制退出 | |

**User's choice:** 手动标记 + Runner 强制退出
**Notes:** 实盘选择立即卖出（最快速度）；回测要模拟真实损失，统一假设全亏（保守方案）。

### 回测交易数据检测

| Option | Description | Selected |
|--------|-------------|----------|
| 统一全亏假设 | 不区分有无交易数据，统一假设全亏（保守方案） | ✓ |
| K 线 + 变更事件对比 | 使用 qd_kline_1d 最后交易日与 qd_nq100_change_events 公告日对比，判断是否有交易数据；有则用最后收盘价，无则假设全亏 | |
| 复用 TradabilityFilter | 使用 Phase 21 的 TradabilityFilter 检测 UNTRADABLE 状态，若 UNTRADABLE 则假设全亏 | |

**User's choice:** 统一全亏假设

---

## Mag7 集中度约束

| Option | Description | Selected |
|--------|-------------|----------|
| 预留配置，延后实现 | Phase 24 预留配置字段（mag7_min_count / mag7_max_weight），实现逻辑延后到后续 phase | ✓ |
| 实现 Mag7 约束 | Phase 24 实现 Mag7 约束：Strategy 在信号生成时检查并强制调整 | |
| 不实现 | 不实现 Mag7 约束，完全依赖截面排名自然配置 | |

**User's choice:** 预留配置，延后实现

---

## 回测一致性 + 配置结构

### 回测一致性

| Option | Description | Selected |
|--------|-------------|----------|
| 共用配置 + 复用 Filter | 回测引擎与实盘策略使用同一 trading_config.delisting_policy 配置；回测 API 直接传递 trading_config 给引擎，引擎复用 Runner 的 DelistingPolicyFilter | ✓ |
| 独立配置字段 | 回测引擎使用独立的 delisting_policy_backtest 配置字段，与实盘配置分离 | |
| 回测默认 immediate | 回测引擎默认使用 immediate 模式（最严格），实盘可配置其他模式 | |

**User's choice:** 共用配置 + 复用 Filter

### 配置结构

| Option | Description | Selected |
|--------|-------------|----------|
| 结构化对象 {mode, months} | trading_config.delisting_policy = {"mode": "delayed", "months": 3}；months 字段仅在 delayed 模式下有效 | ✓ |
| 字符串编码 | trading_config.delisting_policy = "immediate" / "delayed_3_months" / "hold_until_signal_exit" | |
| 分离字段 | trading_config.delisting_policy_mode + trading_config.delisting_delay_months 分离字段 | |

**User's choice:** 结构化对象 {mode, months}

---

## Claude's Discretion

- 接口命名细节（`get_universe_list` vs `get_constituents_list`）
- `DelistingPolicyFilter` 内部实现结构
- `force_exit_symbols` 字段验证逻辑
- 回测全亏假设的具体实现位置

## Deferred Ideas

- 自动化破产/造假检测（需外部数据源）
- Mag7 约束实现逻辑
- 其他 universe 子类（如 SP100Strategy）

---

*Discussion log created: 2026-05-20*