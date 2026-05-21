# Phase 22: Cross-sectional portfolio backtest engine - Research

**Researched:** 2026-05-15  
**Domain:** Python / Flask 后端；多标的截面组合回测；pytest 验证  
**Confidence:** HIGH（代码与依赖文件已在本会话用 Read/Grep/Shell 核对）；MEDIUM（行业中性化具体数值算法细节留待实现定稿）

<user_constraints>
## User Constraints（verbatim from `22-CONTEXT.md`）

### Phase Boundary（`<domain>`）

交付 **后端多标的截面组合回测引擎**（BT-01）：与现有单标的 `BacktestService.run()` **分离**；消费 Phase **19（UNIV）**、**20（FACTOR/标准化）**、**21（正确性与执行语义）** 的规则；对单次调用产出 **一个组合** 的净值/收益序列与标准摘要指标；结果在固定输入下 **可复现**、可回归测试。

不在本 phase：截面前端 UI、截面实盘自动化、NQ100 策略类型与 delisting 策略细节（Phase 24）、网格搜索脚本（Phase 23）、Mag7 集中度约束（Phase 24）。

### Locked Decisions（`<decisions>` / Implementation Decisions，不含 Discretion 小节）

#### API 形态与复现
- **D-01:** 新引擎的 HTTP 形态与现有 QD 回测一致：**同步 POST**、响应包络 **`{code,msg,data}`**；具体 URL 与字段名由 plan 实现时定，但不得引入与全站不一致的包络或异步契约（除非后续单独开 phase）。
- **D-02:** 成功响应的 `data` 内必须包含 **完整可复现包**（语义锁定，键名实现定稿）：至少覆盖 **universe 快照标识或等价 digest**、**因子/指标与标准化配置 hash 或等价物**、**执行策略（含 Phase 21 相关开关）**、**行业中性化开/关状态** 等，使下游可用同一输入复跑并得到一致结果。

#### 股票池请求：互斥
- **D-03:** 请求体中 **`symbol_list` 与 `universe`（如 NQ100）互斥**：若两者**同时非空**，返回 **校验错误**（HTTP 4xx + 明确 `msg`），**不做**优先级裁决。

#### `effective_date` 与信号 / 执行日
- **D-04:** 在**信号日 T** 做截面排序与组合决策时，成分池采用 **PIT 名单**，满足 **`effective_date <= T`** 的「最新已生效」记录；**禁止**使用尚未到 `effective_date` 的未来成分变更。  
- **D-05:** **执行**仍遵守 Phase **21** 已锁定语义：**T 日信号 → T+1（或经 `effective_date` 规则顺延后的下一可执行日）成交**；`next_open` 为主价格口径；指数调整 **生效日** 不顺延当日执行等规则 **不重复发明**，在引擎内 **复用/对齐** Phase 21 实现。

#### 新闻 / 事件 / 非 OHLCV 信息
- **D-06:** 当前产品路径 **不做实时新闻驱动**；新闻与类似事件信息 **仅在下一调仓周期** 与其他输入一并进入决策；与 K 线一致，**不得**用「尚未到下一执行周期」的信息在同一周期内完成交易，避免未来函数。

#### `scores` 与 `weights`（硬契约）
- **D-07:** 截面指标在每个**调仓决策点**（信号日 **T**）必须同时输出 **`scores`** 与 **`weights`**（结构为按 symbol 映射或可枚举为 symbol→float）。  
- **D-08:** **`scores` 仅用于排序**（选入组合、先后次序、TopN 等）；**`weights` 仅用于资金分配**（目标仓位比例）。框架 **不** 将 `scores` 自动当作 `weights`。若策略希望二者数值相同，由策略 **自行写入两份相同数据**。  
- **D-09:** **缺少 `scores` 或缺少 `weights` 任一**：**报错终止**，框架 **不提供** 等权、用 score 顶替、或其他兜底。  
- **D-10:** 框架 **支持任意由策略声明的合法加权方案**（等权、市值加权、自定义加权等均由 **`weights` 内容** 表达）；框架 **不写死**「必须等权」或「必须跟踪 NDX 权重」等业务规则。

#### 多空范围（Phase 22）
- **D-11:** Phase 22 引擎 **硬限制仅做多**：不支持空头腿；与单标的回测习惯的扩展分阶段处理，若未来放开多空另起配置或后续 phase。

#### 行业中性化（与 roadmap 对齐）
- **D-12:** 行业中性化为引擎层 **可选**；默认关、可开、可复现。  
- **D-13:** 单次成功响应中必须包含 **两套完整结果**：**neutral_off** 与 **neutral_on**（各含组合净值或等价收益序列 + 标准摘要指标 + 各自复现子集字段），以满足「开/关对比」报告要求。

### Claude's Discretion（verbatim）

- 可复现包内各字段的 **精确命名**、hash 算法（SHA256 等）与 digest 粒度。  
- `weights` 的数值校验策略（例如是否允许未归一化由引擎 **归一化**，或要求严格和为 1 否则报错）——在实现阶段选一种并写测试固定。  
- 新路由 path（例如是否挂在 `/api/backtest/...` 下）与请求体与单标的回测的 **字段对齐表**。

### Deferred Ideas（OUT OF SCOPE）（verbatim from `<deferred>`）

- **Mag7 / 组合集中度约束** — Phase 24（roadmap 已标）。  
- **动态因子权重（regime）** — Phase 23 研究脚本层（roadmap）。  
- **截面策略前端管理 UI** — v3 / out of scope（PROJECT.md）。  
- **同请求内实时新闻流与同 bar 交易** — 与当前锁定语义冲突，不作为 v2.0 Phase 22 范围。

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BT-01 | 后端多品种截面回测引擎（截面指标 + symbol_list/日期 + 面板 + 截面指标执行 + T+1 模拟 + 净值与标准指标） | 新服务类编排面板、`run_cross_sectional_indicator` 演进、`CrossSectionalRunner`/filter_chain 与 `nq100_sources` 复用；HTTP 与 `BacktestService` 指标/结果格式对齐；pytest 全量门禁见 Validation Architecture |

</phase_requirements>

## Project Constraints（from CLAUDE.md）

仓库根 **无** 独立 `QuantDinger/CLAUDE.md`（本会话 Glob 未找到）。[VERIFIED: workspace Glob `**/CLAUDE.md` under QuantDinger]  
工作区上级 `CLAUDE.md` 约定：QuantDinger 为 Python 后端 + Vue；后端路径 `backend_api_python/`；多项目独立仓库。[CITED: workspace CLAUDE.md 摘要]

## Summary

Phase 22 在已锁定的 CONTEXT 下，研究结论是：**在 `BacktestService` 之外新增专用组合回测服务**，通过演进 `run_cross_sectional_indicator` 满足 **scores+weights 硬契约** [VERIFIED: `cross_sectional_indicator.py` 当前仅返回 `scores`/`rankings`，无 `weights`]，在执行与定价上 **调用或抽取与 Phase 21 相同的路径**（`cross_sectional_runner`、`cross_sectional_filter_chain`、`resolve_shifted_execution_date`），避免重复实现 T+1 与过滤器语义。HTTP 层保持 Flask Blueprint + `{code,msg,data}`，与现有 `backtest.py` 一致 [VERIFIED: `backtest.py` 使用 Blueprint 与 jsonify 模式]。

**Primary recommendation:** 先落地 **引擎内核 + 契约测试**（指标沙箱、组合权益单路径、互斥池校验、双结果 neutral），再挂 **同步 POST API**；每一提交以 **`cd backend_api_python && python3 -m pytest tests/ -q`** 作为全量回归（与 `.planning/config.json` 中 `verification_notes` 及 Nyquist 启用一致）。

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|----------------|
| Python | 3.11.x（本机 `python3 --version`） | 运行时 | 与 conda 环境一致 [VERIFIED: Shell `python3 --version`] |
| Flask | 2.3.3（pinned） | HTTP API | `requirements.txt` 锁定 [VERIFIED: `requirements.txt` L1] |
| pandas | >=1.5.0 | 面板 / OHLCV | 与现有指标与因子管线一致 [VERIFIED: `requirements.txt` L7] |
| SQLAlchemy | >=2.0.0 | ORM | 现有后端栈 [VERIFIED: `requirements.txt` L11] |
| pytest | 9.0.2（本机） | 自动化验证 | [VERIFIED: Shell `python3 -m pytest --version`] |

### Supporting

| Library | Purpose | When to Use |
|---------|---------|-------------|
| numpy | 指标 exec 环境已注入 | 截面指标代码内计算 [VERIFIED: `cross_sectional_indicator.py` 注入 `np`] |
| psycopg2-binary | PostgreSQL | universe / K 线读路径需 DB 时 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 扩展 `BacktestService.run()` 承载组合截面 | 新建 `CrossSectionalPortfolioBacktestService`（名称为建议） | CONTEXT 明确要求分离；混用易导致单标的与组合语义耦合 [ASSUMED: 可维护性风险，已与 CONTEXT 锁定方向一致] |

**Installation（后端）：** 见仓库 `backend_api_python/requirements.txt`。[VERIFIED]

**Version verification:** 未调用 npm；Python 依赖以 `requirements.txt` 为权威，本机 pytest 版本如上。

## Architecture Patterns

### Recommended placement（与 CONTEXT `<code_context>` 一致）

```
backend_api_python/app/
├── services/
│   └── {new}_cross_sectional_portfolio_backtest.py   # 组合引擎编排（建议新建）
├── routes/
│   └── {new}_cross_sectional_portfolio_backtest.py   # 同步 POST + 包络
├── strategies/
│   └── cross_sectional_indicator.py                  # 演进：weights 契约
└── strategies/runners/
    ├── cross_sectional_runner.py                     # 复用 Phase 21 语义（勿复制矛盾逻辑）
    └── cross_sectional_filter_chain.py
```

### Pattern 1: 指标沙箱与硬契约

**What:** `exec_env` 提供 `scores`、`weights`（新增），执行后二者缺一即失败。  
**When to use:** 每个调仓决策点 T。  
**Example（当前代码缺口）：** [VERIFIED: codebase]

```62:68:backend_api_python/app/strategies/cross_sectional_indicator.py
        scores = exec_env.get("scores", {})
        rankings: List[str] = exec_env.get("rankings", [])

        if not rankings and scores:
            rankings = sorted(scores.keys(), key=lambda x: scores.get(x, 0), reverse=True)

        return {"scores": scores, "rankings": rankings}
```

规划器应安排任务：增加 `weights` 读取与校验，且 **禁止** 用 `scores` 自动填 `weights`（违反 D-08/D-09）。

### Pattern 2: 响应包络

**What:** 与现有回测路由一致使用 Flask `jsonify` / 统一 `code,msg,data`。  
**When to use:** 所有新端点。  
**Example：** [VERIFIED: `backtest.py` 导入 `Blueprint, request, jsonify`]

### Anti-Patterns to Avoid

- **第二套 T+1 / 过滤语义：** 在引擎内复制 Phase 21 逻辑易产生与实盘/截面 runner 漂移；应 **import 并复用** 既有函数/类。  
- **用 rankings 代替 weights：** 违反 D-07–D-09。  
- **单测只跑新增文件即宣称完成：** `.planning/config.json` 要求覆盖全量用例；Nyquist 启用时 Validation Architecture 必须含全量命令。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP 包络 | 自定义非标准 JSON 形状 | 与 `backtest` 路由相同的 `{code,msg,data}` | 全站一致 [VERIFIED: CONTEXT D-01 + 现有 routes 模式] |
| 执行日 / 过滤 | 新写一套「顺延」「不可交易」 | `nq100_sources.resolve_shifted_execution_date` + `cross_sectional_filter_chain` | Phase 21 已锁定语义 [VERIFIED: `cross_sectional_runner.py` imports] |
| 组合指标摘要 | 随意新公式集合 | `BacktestService._calculate_metrics` / `_format_result` 对齐字段 | 产品报告一致性 [CITED: 22-CONTEXT canonical_refs] |

**Key insight:** 本 phase 风险在 **语义重复**，不在「缺少库」；优先 **编排 + 契约 + 测试**。

## Runtime State Inventory

本 phase 为 **greenfield 功能增强**（非 rename/refactor/migration）。按 `gsd-phase-researcher` 规范：**本节省略**。

## Common Pitfalls

### Pitfall 1: 仅扩展返回 dict 但未改调用方

**What goes wrong:** 指标函数返回 `weights` 但上游仍只读 `rankings`，静默忽略契约。  
**Why it happens:** 历史代码路径只认 rankings。  
**How to avoid:** 所有调用 `run_cross_sectional_indicator` 的组合引擎路径统一校验；pytest 覆盖「缺 weights 抛错」。  
**Warning signs:** 集成测试仍用旧 fixture 只断言 rankings。

### Pitfall 2: universe 与 symbol_list 校验在「服务层」遗漏

**What goes wrong:** 数据库已查仍不拒绝双非空。  
**How to avoid:** 在路由或服务入口最早校验，返回 4xx + 明确 `msg`（D-03）。

### Pitfall 3: neutral 只算一套指标

**What goes wrong:** 只实现默认路径，报告无法对比。  
**How to avoid:** 单次成功响应固定包含 `neutral_off` 与 `neutral_on` 两套对象（D-13）。

## Code Examples

### 现有指标沙箱 exec 环境（扩展点）

[VERIFIED: `cross_sectional_indicator.py`]

```python
exec_env = {
    "symbols": list(all_data.keys()),
    "data": all_data,
    "scores": {},
    "rankings": [],
    # 规划：新增 "weights": {},
    "np": np,
    "pd": pd,
    "trading_config": trading_config,
    "config": trading_config,
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 截面指标仅 scores + 派生 rankings | scores + weights 显式分离 | Phase 22 实施时 | 与 CONTEXT D-07–D-10 对齐 |
| 单标的 `BacktestService.run()` | 独立组合引擎服务 | Phase 22 | BT-01 边界清晰 |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `BacktestService._calculate_metrics` 可直接或薄封装复用于组合权益序列 | Summary | 若输入形状不兼容需适配层 |
| A2 | 行业中性化「按行业回归残差」在代码库尚无标准实现 | Open Questions | 需新增模块与行业映射数据源确认 |

**若上表与正文凡标注 `[ASSUMED]` 的命题：** 执行前应用测试或 CONTEXT 定稿确认。

## Open Questions

1. **`weights` 归一化策略（Claude's Discretion）**  
   - What we know: CONTEXT 允许二选一并测试锁死。  
   - What's unclear: 是否要求 sum(weights)==1 在信号日强制。  
   - Recommendation: 在首个引擎任务中选定并在 `test_cross_sectional_portfolio_bt01.py`（或等价）中断言。

2. **行业字段来源**  
   - What we know: D-12/D-13 要求可选中性化。  
   - What's unclear: 行业分类来自哪张表/外部映射。  
   - Recommendation: planner 在实现任务 `read_first` 中锁定 `database.md` 或现有 equity metadata 路径；若缺失则 Wave 0 fixture 用静态 sector map。

## Environment Availability

Step 2.6 已执行（本 phase 依赖 Python/pytest/Flask 生态）。

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python3 | 后端 / pytest | ✓ | 3.11.14 | — |
| pytest | Nyquist / CI | ✓ | 9.0.2 | — |
| PostgreSQL | UNIV / K 线读 | 未在本会话探测 `pg_isready` | — | CI 或 docker-compose；规划任务中注明测试可用 fixture/SQLite 若项目已有模式 [ASSUMED: 以现有 tests 为准] |

**Missing dependencies with no fallback:** 无（开发可在无 DB 下用 fixture 若测试已如此设计）。  
**Step 2.6:** 对外部 DB 未做端口探测 — 标记为 MEDIUM confidence；执行前以 `tests/conftest.py` 为准。

## Validation Architecture

> `.planning/config.json` 中 **`workflow.nyquist_validation` 未显式 false** → 视为启用 [VERIFIED: 读 config 为 `true`]。

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x [VERIFIED: Shell] |
| Config file | 未检出根级 `pytest.ini` [VERIFIED: Glob `backend_api_python/pytest.ini` 无]；以默认 discovery 与 `tests/` 为准 |
| Quick run command | `cd backend_api_python && python3 -m pytest tests/test_cross_sectional_portfolio_bt01.py -q`（Wave 0 创建该文件后） |
| Full suite command | `cd backend_api_python && python3 -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| BT-01 | symbol_list 与 universe 双非空 → 4xx + msg | unit/api | `pytest tests/test_cross_sectional_portfolio_bt01.py -k mutual_exclusive -q` | ❌ Wave 0 |
| BT-01 | 缺 scores 或 weights → 错误终止 | unit | `pytest tests/test_cross_sectional_portfolio_bt01.py -k contract -q` | ❌ Wave 0 |
| BT-01 | 单次响应含 neutral_off 与 neutral_on | unit/api | `pytest tests/test_cross_sectional_portfolio_bt01.py -k neutral -q` | ❌ Wave 0 |
| BT-01 | 全量回归不破坏 Phase 21 等既有用例 | regression | `pytest tests/ -q` | ✅ 已有 `tests/` 树 |

### Sampling Rate

- **Per task commit:** 定向 `pytest … -k …`（若已拆分）+ **`python3 -m pytest tests/ -q`**（与项目 `verification_notes` 一致）
- **Per wave merge:** `python3 -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `backend_api_python/tests/test_cross_sectional_portfolio_bt01.py` — 覆盖 BT-01 契约与 API
- [ ] 若需：共享 fixture（多标的 OHLCV 最小面板、mock universe）
- [ ] Framework：pytest 已安装 — **无**额外 Wave 0 安装任务 [VERIFIED]

## Security Domain

> `workflow.security_enforcement` 在 config 中未显式 `false` → 按启用处理 [VERIFIED: key absent]。

### Applicable ASVS Categories（节选）

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V5 Input Validation | yes | 校验互斥池、日期范围、指标代码长度/危险 import；保持 `cross_sectional_indicator` builtins 白名单策略 [VERIFIED: 现有 `safe_builtins` 模式] |
| V4 Access Control | yes（若路由需登录） | 与现有 `backtest` 路由一致：`login_required` 与否由 planner 对照 `backtest.py` [VERIFIED: `backtest.py` 存在 `login_required` import — 新路由须显式决策] |
| V7 Error Handling | yes | 不向客户端泄漏堆栈；结构化 `msg` |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| 指标 `exec` 滥用 | Execution | 延续白名单 builtins；禁止 `__import__` 等 [VERIFIED: 代码已禁用] |
| 过大 symbol_list | DoS | 上限 + 输入校验 [ASSUMED: 具体上限由 planner 与产品约定] |

## Sources

### Primary（HIGH）

- [VERIFIED: codebase Read/Grep] `backend_api_python/app/strategies/cross_sectional_indicator.py`
- [VERIFIED: codebase Read] `backend_api_python/app/strategies/runners/cross_sectional_runner.py`（imports 与 Phase 21 依赖）
- [VERIFIED: codebase Read] `backend_api_python/app/routes/backtest.py`（Blueprint 形态）
- [VERIFIED: file] `backend_api_python/requirements.txt`
- [VERIFIED: file] `.planning/phases/22-cross-sectional-portfolio-backtest-engine/22-CONTEXT.md`
- [VERIFIED: file] `.planning/config.json`

### Secondary（MEDIUM）

- `.planning/ROADMAP.md` Phase 22 段 — 成功标准与 locked notes [CITED: 先前 grep 会话]

### Tertiary（LOW）

- 无外部 WebSearch 引用（本子会话未跑联网检索）。

## Metadata

**Confidence breakdown:**

- Standard Stack: **HIGH** — requirements + 本机 pytest 已核对  
- Architecture: **HIGH** — 与 CONTEXT canonical_refs 一致  
- Pitfalls: **MEDIUM** — 基于代码结构与 GSD 经验  
- Security: **MEDIUM** — 需 planner 在 PLAN `<threat_model>` 细化端点认证策略  

**Research date:** 2026-05-15  
**Valid until:** ~2026-06-15（栈为 pinned Flask 2.3.x，变化慢）
