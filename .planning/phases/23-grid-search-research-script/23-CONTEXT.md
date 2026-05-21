# Phase 23: Grid-search research script - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

独立批量研究脚本：暴力搜索因子组合网格，调用Phase 22回测引擎API，输出最优策略候选。不是生产功能、不是策略类型、不是实盘自动化。产出用于研究决策，不直接进入交易执行路径。

本phase只实现研究脚本能力，不扩展：
- 截面前端UI（out of scope）
- 截面实盘自动化（out of scope）
- 新因子定义（Phase 20已锁定）
- 回测引擎能力（Phase 22已锁定）

</domain>

<decisions>
## Implementation Decisions

### 因子网格规格（SCRIPT-01）
- **D-01:** 搜索空间由**配置文件（YAML）指定**，不硬编码。
- **D-02:** 配置文件包含：
  - `factors`: 显式因子列表（如 `['MOM_1M', 'VOL_20D', 'SHARPE_60D']`）
  - `combo_min`: 最小组合大小（如 `1`）
  - `combo_max`: 最大组合大小（如 `4`）
  - `n_long_options`: 持仓数列表（如 `[10, 20, 30, 40, 50, 60]`）
- **D-03:** 脚本启动时读取配置文件，动态生成搜索空间。配置文件路径通过CLI参数传入（默认 `grid_config.yaml`）。

### Walk-forward 验证（SCRIPT-04）
- **D-04:** 采用**滚动窗口walk-forward验证**（固定训练长度 + 固定测试长度 + 固定步长滑动）。
- **D-05:** 窗口参数由配置文件指定（不硬编码）：
  - `train_months`: 训练窗口月数（如 `36`）
  - `test_months`: 测试窗口月数（如 `12`）
  - `step_months`: 滑动步长月数（如 `12`）
- **D-06:** 每个窗口：
  1. 训练窗口内做网格搜索，找出最优因子组合 + 最优持仓数
  2. 测试窗口用该最优组合跑回测，记录out-of-sample表现
  3. 滑动到下一个窗口，重复
- **D-07:** 输出包含：
  - 各窗口最优组合（训练期）
  - 各窗口测试期表现（out-of-sample）
  - 综合统计：平均OOS Sharpe、平均OOS年化、稳定性指标

### Phase 22 集成方式
- **D-08:** 脚本通过**HTTP API调用Phase 22引擎**（`POST /api/indicator/cross-sectional-portfolio-backtest`）。
- **D-09:** 不直接复用后端服务层。HTTP方式保证：
  - 可移植（可在不同机器运行脚本）
  - 可复现（API契约固定）
  - 与后端版本解耦（后端升级不影响脚本逻辑）
- **D-10:** 调用参数映射：
  - 因子组合 → Phase 22的截面指标代码
  - 持仓数 → `long_ratio` 或等价参数（待plan实现定）
  - Universe → NQ100 PIT API（Phase 19）
  - 日期范围 → 窗口参数自动计算

### 行业中性化处理
- **D-11:** Phase 22返回两套完整结果（`neutral_off` / `neutral_on`）。脚本**两套分别做网格搜索**。
- **D-12:** 输出两套TOP结果：
  - `neutral_off_top100.json`：不做行业中性化的最优组合
  - `neutral_on_top100.json`：做行业中性化的最优组合
- **D-13:** HTML报告包含对比分析：两套策略的Sharpe、年化、MaxDD对比，帮助研究者决策是否启用行业中性化。

### 输出与报告（SCRIPT-02/03）
- **D-14:** 输出三种格式：
  - `all_results.jsonl`：JSONL逐条追加（支持断点续传）
  - `all_results.csv`：CSV导出（适合Excel/Python分析）
  - `report.html`：HTML可视化报告
- **D-15:** JSONL/CSV字段对齐：因子组合、持仓数、年化收益、Sharpe、Calmar、MaxDD、胜率、总交易月数、Score、窗口标识（walk-forward时）。
- **D-16:** HTML报告包含：
  - 配置摘要（搜索空间、窗口参数）
  - TOP 20表格（neutral_off vs neutral_on对比）
  - 各持仓数最优
  - 因子频率统计（TOP 100中出现次数）
  - Walk-forward各窗口OOS表现曲线（若有）
- **D-17:** 保留**断点续传**能力：
  - `checkpoint.json`：记录已完成回测（因子组合+持仓数+窗口标识）
  - 中断后重启自动跳过已完成项
  - JSONL追加写入保证不丢数据

### 执行模式
- **D-18:** **串行执行**（单线程），不做并行HTTP调用。避免API限流，保证稳定性。
- **D-19:** 进度实时输出：每N次回测打印进度（完成数/总数、速度、ETA）。

### Claude's Discretion
- YAML配置文件的具体字段命名与结构设计。
- HTML报告的样式与布局（简洁为主，不引入复杂前端框架）。
- Score评分公式（沿用原型或优化权重）。
- API调用超时与重试策略。

### Folded Todos

（本phase `todo match-phase` 无匹配项，无折叠todo。）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase/Requirement 契约
- `.planning/ROADMAP.md` — Phase 23目标、SCRIPT-01/02/03/04需求。
- `.planning/REQUIREMENTS.md` — SCRIPT-01/02/03/04定义。

### 上游已锁定上下文
- `.planning/phases/19-nq100-universe-data-plane/19-CONTEXT.md` — NQ100 PIT universe API、`effective_date`语义。
- `.planning/phases/20-built-in-factors-normalization/20-CONTEXT.md` — 因子集合、标准化流水线。
- `.planning/phases/21-backtest-correctness/21-CONTEXT.md` — T+1执行、UNTRADABLE处理。
- `.planning/phases/22-cross-sectional-portfolio-backtest-engine/22-CONTEXT.md` — Phase 22 API契约、`scores`+`weights`、`neutral_off`+`neutral_on`双套结果、复现包。

### 现有原型参考
- `scripts/cross_sectional/nq100_cross_sectional.py` — 已实现网格搜索原型（587行），可参考数据加载、因子计算、断点续传、输出格式。

### 后端API基线
- `backend_api_python/app/routes/` — Flask Blueprint + `{code, msg, data}`响应规范。
- Phase 22 API endpoint：`POST /api/indicator/cross-sectional-portfolio-backtest`（已实现）。

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/cross_sectional/nq100_cross_sectional.py`：
  - 数据加载 + 本地CSV缓存逻辑可参考
  - JSONL断点续传实现可复用
  - 终端进度输出模式可参考
  - **需改造**：调用Phase 22 API替代自有回测逻辑
  - **需新增**：walk-forward窗口划分逻辑
  - **需新增**：配置文件解析（YAML）
  - **需新增**：CSV导出 + HTML报告生成

### Established Patterns
- 脚本目录：`scripts/cross_sectional/`（已存在）
- 输出目录：`scripts/cross_sectional/results/`（已存在）
- 缓存目录：`scripts/cross_sectional/cache/`（已存在）
- Python脚本：标准CLI参数（argparse）+ 日志输出

### Integration Points
- Phase 22 HTTP API调用（需认证token）
- Phase 19 Universe API（`GET /api/universe/nq100?date=YYYY-MM-DD`）
- Phase 20因子注册表（可选，配置文件显式指定因子时不必自动枚举）

</code_context>

<specifics>
## Specific Ideas

- 配置文件驱动搜索空间（YAML），不硬编码。
- Walk-forward滚动验证（固定窗口 + 固定步长），参数可配置。
- HTTP API调用Phase 22引擎，保证可移植可复现。
- 两套neutral结果分别搜索，对比输出。
- 输出JSONL + CSV + HTML三种格式。
- 保留断点续传，支持长耗时任务中断恢复。
- 串行执行，不做并行（稳定性优先）。

</specifics>

<deferred>
## Deferred Ideas

- **并行执行优化** — 若未来回测量大且API支持限流配置，可考虑异步并发。
- **动态因子权重（regime）** — Phase 20已标注归属研究脚本实验能力，可作为后续扩展配置项（如 `regime_config` 字段）。
- **交互式可视化前端** — 研究结果展示的前端UI属于v3范围。

### Reviewed Todos (not folded)

无。

</deferred>

---

*Phase: 23-grid-search-research-script*
*Context gathered: 2026-05-19*