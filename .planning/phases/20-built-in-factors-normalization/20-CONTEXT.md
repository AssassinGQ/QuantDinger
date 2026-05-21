# Phase 20: Built-in factors & normalization - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

构建可复用的后端“因子 + 标准化”共享库，供指标代码、截面回测引擎、研究脚本统一调用。  
本 phase 只定义与实现通用计算能力，不实现组合约束策略（如 Mag7 保留）和 regime 配置策略决策本身。

</domain>

<decisions>
## Implementation Decisions

### 因子目录（v1 锁定）
- 动量：`MOM_1M`, `MOM_3M`, `MOM_6M`, `MOM_12M_SKIP_1M`
- 反转：`REV_1W`, `REV_2W`, `REV_1M`
- 波动：`VOL_20D`, `VOL_60D`
- 风险调整：`SHARPE_60D`, `SORTINO_60D`
- 以上作为内置公共因子集合，统一注册入口，命名和默认窗口参数固定。

### 标准化契约（锁定）
- 必选：`winsorize`（默认启用）
- 必选：`rank`（默认启用，作为主要跨截面输出）
- `z-score`：**实现但默认不启用**（按配置可启用）
- 默认流水线：`winsorize -> rank`
- `winsorize` 默认阈值：`1% ~ 99%`；同时支持通过配置覆盖阈值（可选 D）
- `rank` ties 默认：`average`；支持通过环境变量切换为 `average|first|dense`（A/B/C）
- NaN 处理默认：保留 NaN 并在截面排序时剔除；支持通过环境变量切换为 `drop|median_fill|zero_fill`（D）

### 面板语义（锁定）
- 采用 **A 口径**：先按单资产时序计算因子，再在每个调仓日做截面标准化/排序。
- 不采用“直接截面定义替代单资产时序计算”的默认路径。

### 背景理由（来自用户）
- NDX 分布右偏且极值明显，先做 winsorize 以避免极端值污染。
- rank 不依赖正态分布假设，适合 NDX 结构。
- z-score 在当前分布下可能误伤头部巨头，仅保留为可选工具。

### 跨 phase 归属（锁定）
- 行业中性化（行业回归残差）归属 **Phase 22**（引擎参数能力）
- Mag7 保留/集中度约束归属 **Phase 24**（策略层配置能力）
- 动态权重（如 VIX regime）归属 **Phase 23**（研究脚本实验能力）
- **T+1 执行约束归属 Phase 21/22**：调仓信号使用 T 日收盘数据，但成交必须在 T+1 生效；禁止“用 T 收盘算信号并在 T 立即成交”的同 bar 执行。
- 行业中性化运行策略：回测报告必须输出“开启/关闭”两组对比；实盘默认关闭，但创建截面策略时支持选择开启。
- 动态权重（VIX regime）运行策略：回测报告必须输出“静态权重 vs 动态权重”对比；实盘默认关闭，但创建截面策略时支持选择开启。

### Claude's Discretion
- winsorize 默认分位阈值（建议 `1%~99%`）可在实现时定稿
- rank ties 处理（average/min/first）按库稳定性与可测性决定
- z-score 具体参数（ddof、NaN 传播）在测试中固定并文档化

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/ROADMAP.md`（Phase 20/22/23/24 目标与依赖）
- `.planning/REQUIREMENTS.md`（FACTOR-01/FACTOR-02）
- `scripts/cross_sectional/nq100_cross_sectional.py`（已有原型因子定义可复用为参考，不直接复用脚本架构）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/cross_sectional/nq100_cross_sectional.py` 已包含多类价量因子的原型定义（窗口、方向、计算逻辑）
- 后端目前缺少统一因子库模块，需要从脚本原型抽象为可 import 的服务层模块

### Established Patterns
- 后端 Python 代码统一通过 `app/services`、`app/utils` 组织
- pytest 全量回归作为强制门禁（`cd backend_api_python && pytest tests/ -q`）

### Integration Points
- Phase 22 引擎调用：共享因子/标准化库
- Phase 23 脚本调用：共享因子/标准化库
- Phase 24 策略调用：共享因子输出与标准化结果

</code_context>

<specifics>
## Specific Ideas

- 因子与标准化都提供“函数级 API + 注册表 API”双接口，便于动态组合与静态调用。
- 所有函数需给出固定输入输出契约（DataFrame/Series、index 对齐、NaN 行为）并由单元测试覆盖。
- 标准化默认链路固定为 `winsorize -> rank`，避免各处出现“同名因子不同结果”。

</specifics>

<deferred>
## Deferred Ideas

- 行业中性化：Phase 22
- Mag7 约束：Phase 24
- VIX regime 动态权重：Phase 23

</deferred>

---

*Phase: 20-built-in-factors-normalization*
*Context gathered: 2026-04-14*
