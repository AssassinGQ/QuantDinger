# Phase 20: Built-in factors & normalization - Research

**Researched:** 2026-04-14 · **Updated:** 2026-04-15（task 用例规格；代码库核对；**方案细节**）
**Domain:** Python backend reusable factor + cross-sectional normalization library
**Confidence:** HIGH

## User Constraints (from CONTEXT.md)

### Locked Decisions
- 动量：`MOM_1M`, `MOM_3M`, `MOM_6M`, `MOM_12M_SKIP_1M`
- 反转：`REV_1W`, `REV_2W`, `REV_1M`
- 波动：`VOL_20D`, `VOL_60D`
- 风险调整：`SHARPE_60D`, `SORTINO_60D`
- 以上作为内置公共因子集合，统一注册入口，命名和默认窗口参数固定。
- 必选：`winsorize`（默认启用）
- 必选：`rank`（默认启用，作为主要跨截面输出）
- `z-score`：**实现但默认不启用**（按配置可启用）
- 默认流水线：`winsorize -> rank`
- `winsorize` 默认阈值：`1% ~ 99%`；同时支持通过配置覆盖阈值（可选 D）
- `rank` ties 默认：`average`；支持通过环境变量切换为 `average|first|dense`（A/B/C）
- NaN 处理默认：保留 NaN 并在截面排序时剔除；支持通过环境变量切换为 `drop|median_fill|zero_fill`（D）
- 采用 **A 口径**：先按单资产时序计算因子，再在每个调仓日做截面标准化/排序。
- 不采用“直接截面定义替代单资产时序计算”的默认路径。
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

### Deferred Ideas (OUT OF SCOPE)
- 行业中性化：Phase 22
- Mag7 约束：Phase 24
- VIX regime 动态权重：Phase 23

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FACTOR-01 | 后端内置 ≥6 种价量因子，可被截面指标和脚本直接调用 | 提供统一 factor registry + pure function API + 面板输入契约 |
| FACTOR-02 | 标准化工具 winsorize/z-score/rank 共享复用 | 提供标准化流水线 API（默认 winsorize->rank，z-score可选）与 env 配置契约 |

## Task Use Case Specifications（下游 PLAN 强制）

`/gsd-plan-phase` 生成的每个 `<task>` **必须**包含 `<use_case_spec>`（或与之下划线等价的同义块），且每个 task **至少一条**可追溯用例。规格表字段固定如下 — **不得**仅用散文描述“实现配置与函数”而不填表：

| 字段 | 必填 | 说明 |
|------|------|------|
| **编号** | 是 | 稳定 ID：`UC-20-{plan两位}-{T任务序号}`，例如 `UC-20-01-T1`、`UC-20-02-T2`。同一 phase 内唯一。 |
| **参与者** | 是 | 谁触发：开发者 import、引擎、研究脚本、注册表查找等。 |
| **前置条件** | 是 | 输入数据结构（Series/DataFrame 形）、最小历史长度、可选 env、是否依赖本 phase 其他 task 已合并。 |
| **触发** | 是 | 具体 API 调用链（函数名 + 关键参数），与 `<action>` 可一一对应。 |
| **主成功场景** | 是 | 可检验的期望：数值关系、键集合、index 对齐、无 `inf` 等（避免“行为正确”类主观句）。 |
| **扩展/异常** | 是 | 非法配置、零方差、未知因子名、NaN 主导截面等；期望异常类型或 NaN 传播规则。 |
| **验收映射** | 是 | 指向 `<test_spec>` 中具体 `test_*` 或 grep 条件；executor 应用测试证明用例已覆盖。 |

**与 `<test_spec>` 的关系：** 用例规格是**业务可读**的“谁、何时、期望什么”；`<test_spec>` 是**自动化**的测试函数表。二者必须 **1:1 可追踪**：每个 `test_*` 至少对应主成功或异常路径中的一行。

**与 `<acceptance_criteria>` 的关系：** acceptance 侧重实现与命令输出；use_case_spec 侧重调用场景。同一 task 内三者（use_case_spec / test_spec / acceptance_criteria）不得互相矛盾。

**已落地的 PLAN 参考：** `20-01-PLAN.md`、`20-02-PLAN.md` 中 `<use_case_spec>` 块可作为模板。

## Summary

Phase 20 的关键不是“再写一份脚本逻辑”，而是把当前 `scripts/cross_sectional/nq100_cross_sectional.py` 的因子实现，提炼成**纯函数 + 注册表 + 标准化流水线**三层模块，让 `app/strategies/*`、未来 Phase 22 引擎、以及研究脚本共用同一实现，避免同名因子在不同调用方出现不同结果。

现有代码已经具备可复用基础：脚本中 `calc_factor()` 和 `FACTOR_DEFS` 已定义了因子类型与窗口语义；后端截面策略侧已经采用“传入 `data: Dict[str, DataFrame]` → 返回结果”的纯计算接口模式（`run_cross_sectional_indicator()`）。因此最佳路径是沿用该范式，新增一个 `app/factors/` 共享库，不在 strategy 或 script 中复制计算逻辑。

标准化契约建议固定为：默认 `winsorize -> rank`，`z-score` 实现并可通过配置插入流水线但默认关闭。配置只做“运行参数注入”，不改核心算法。NaN、ties、阈值等行为必须写成可测且有默认值的契约，避免 Phase 22/23 接入时产生行为分叉。

**Primary recommendation:** 落地 `app/factors/{registry,core,normalize,pipeline,config}.py`，以“面板输入 + 单日截面输出 + 可组合流水线”作为唯一标准接口。

## Codebase Verification（2026-04-15 再调研）

对当前仓库 **HEAD** 的核对结论（实现前必读，避免照搬脚本踩坑）：

### 实现落点
| 路径 | 状态 |
|------|------|
| `backend_api_python/app/factors/` | **不存在**（尚未落地；与 PLAN wave 一致，属预期） |
| `backend_api_python/app/strategies/cross_sectional_indicator.py` | 存在；`run_cross_sectional_indicator()` 仍为 `exec` 指标代码 + `scores`/`rankings` 纯函数边界，与本文 **Architecture Patterns** 一致 |
| `scripts/cross_sectional/nq100_cross_sectional.py` | 存在；为研究脚本，**仅作公式/窗口参考**，注册名与语义以 `20-CONTEXT.md` 为准 |

### 脚本与锁定目录的差异（必须显式处理）
| 主题 | 脚本现状 | 共享库应遵循 |
|------|----------|----------------|
| 12M skip 因子名 | `MOM_12M_1M` | **主键 `MOM_12M_SKIP_1M`**（可在 `factor_defs` 内对旧名做 deprecated alias） |
| `rev` 分支 | `calc_factor` 中 `rev` 与 `mom` **同为** `close.pct_change(w)`，仅 `FACTOR_DEFS["dir"]` 区分多空方向 | **CONTEXT** 要求反转语义；共享库中 `reversal()` 应实现为 **与短期动量相反的得分**（例如 `-pct_change(w)` 或与 docstring 等价的定义），并由单测固定。**不得**无差异复制脚本 `rev` 分支，否则与「反转」命名及 PHASE 决策不一致 |
| `mom_skip` | `pct_change(252) - pct_change(21)` | 与学术上常见「12-1」累积定义可能不同；须在 `FactorSpec` / docstring **写死代数含义**，单测对齐；若未来改定义应版本化 |
| Sortino / `REV_1M` | 脚本 `calc_factor` **未实现** Sortino；`FACTOR_DEFS` **无** `REV_1M`、`SORTINO_60D` | Phase 20 **新建**实现与注册项（与 `20-02-PLAN.md` 一致） |
| 额外探索因子 | 含 `DIST_MA50`、`DIST_MA200`、`VOL_RATIO` 等 | **不在** CONTEXT v1 内置目录；默认不进入 `get_builtin_factor_specs()`，避免污染「锁定 11 因子」集合 |

### REQUIREMENTS（FACTOR-01）六类 vs CONTEXT v1 目录
- `REQUIREMENTS.md` 文案含 **momentum / reversal / volatility / volume / mean-reversion / risk-adjusted** 六类。
- `20-CONTEXT.md` 锁定 **11 个具名因子**，覆盖动量、反转、波动、风险调整；**无单独「纯成交量」具名因子**（脚本的 `VOL_RATIO` 亦未纳入 v1）。
- **建议（验收口径）：** 在 Phase 20 交付说明或测试中显式对应：例如 **mean-reversion ↔ `REV_*`**；**volume 字样**若需严格满足 REQ，可在文档中说明「v1 以价量研究扩展为后续 phase」或 **增补** 一只量价类因子并回写 CONTEXT（需产品决策）。本 RESEARCH 不替代理清——仅标出 **REQ 字面与 v1 清单的张力**，避免 UAT 争议。

### pandas 细节（标准化）
- `Series.quantile` 默认 **线性插值**；小样本截面下 winsorize 截断点会与「手工分位」略有数值差，属预期——**单测用固定种子与足够长度面板**，并在文档注明依赖 pandas 行为。
- `Series.rank(pct=True)`：截面输出为 **0~1** 分位秩（与「pct rank」常见语义一致）；与「1..N 整数秩」不要混测。

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.10+（项目现状） | 运行后端与脚本共享代码 | 项目主栈，类型注解与 dataclass 可用 |
| pandas | >=1.5.0 (`requirements.txt`) | 面板/时序/截面运算 | 当前脚本和策略都使用 DataFrame/Series |
| numpy | 已使用（脚本现状） | 数值计算与 NaN 行为一致化 | 波动/Sharpe/Sortino 等公式需要 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 项目既有测试框架 | 单元与集成回归 | 每个因子、标准化函数、跨调用方一致性测试 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pandas quantile+clip | scipy.stats.mstats.winsorize | 增加依赖，不必要；当前需求可由 pandas 完成 |
| pandas rank | numpy argsort 手写 | ties/NaN 语义易错，维护成本高 |

**Installation:**
```bash
cd backend_api_python && pip install -r requirements.txt
```

## Architecture Patterns

### Recommended Project Structure
```text
backend_api_python/app/factors/
├── __init__.py               # exports stable public API
├── factor_defs.py            # built-in factor metadata + registry
├── core.py                   # pure factor calculations on Series
├── panel.py                  # panel-level builders (all symbols/all factors)
├── normalize.py              # winsorize / rank / zscore / nan policy
├── pipeline.py               # compose normalization chain
└── config.py                 # env parsing + validated runtime config
```

### Pattern 1: Registry + Pure Function Dual API
**What:** 既支持 `compute_factor_by_name("MOM_3M", close, volume)`，也支持直接调用 `mom(close, 63)`。
**When to use:** strategy/engine 动态配置用 registry；脚本实验/单测用纯函数。
**Example:**
```python
FACTOR_REGISTRY = {
    "MOM_1M": FactorSpec(func=mom, kwargs={"window": 21}, direction=1),
    "VOL_20D": FactorSpec(func=volatility, kwargs={"window": 20}, direction=-1),
}

def compute_factor_by_name(name: str, close: pd.Series, volume: pd.Series) -> pd.Series:
    spec = FACTOR_REGISTRY[name]
    return spec.func(close=close, volume=volume, **spec.kwargs)
```

### Pattern 2: 截面标准化流水线（单日）
**What:** 对单日 `Series(index=symbol, value=factor_value)` 执行有序变换。
**When to use:** 每个 rebalance 日、每个 factor 的截面处理。
**Example:**
```python
def normalize_cross_section(s: pd.Series, cfg: NormalizeConfig) -> pd.Series:
    out = apply_nan_policy(s, cfg.nan_policy)
    out = winsorize_series(out, cfg.winsor_lower, cfg.winsor_upper)
    if cfg.enable_zscore:
        out = zscore_series(out, ddof=cfg.zscore_ddof)
    out = rank_series(out, method=cfg.rank_ties, pct=True)
    return out
```

### Pattern 3: Panel Driver（先时序后截面）
**What:** 先对每个 symbol 计算时序因子，再按日期做截面标准化。
**When to use:** Phase 20 基础能力；Phase 22 引擎直接复用。
**Example:**
```python
def build_factor_panels(price_panel: pd.DataFrame, volume_panel: pd.DataFrame, factor_names: list[str]) -> dict[str, pd.DataFrame]:
    # returns: {factor_name: DataFrame(index=date, columns=symbol)}
    ...
```

### Anti-Patterns to Avoid
- **在脚本/策略内复制公式：** 同名因子漂移风险高；必须统一走 `app/factors`。
- **先 rank 再 winsorize：** 会削弱极值抑制意义，违背默认链路。
- **混用不同 NaN 语义：** 一个调用方 drop、另一个 fill 会导致回测不可复现。
- **把 T+1 执行写入 Phase 20：** 这是 Phase 21/22 职责，不在本 phase 处理。

## Implementation Design Details（方案细节）

本节为 **可直接照着写代码** 的约定（与 `20-02-PLAN.md` 窗口锁定、`20-01` 标准化契约一致）。若实现与下文冲突，**先改代码/单测对齐本文**，再更新 RESEARCH。

### A. 符号与输入

| 符号 | 含义 |
|------|------|
| `P` | 收盘价 `close`，按时间升序的 `pd.Series`，`DatetimeIndex` |
| `r` | 日简单收益 `r_t = P_t / P_{t-1} - 1`，即 `close.pct_change()` |
| `w` | 滚动窗口长度（**交易日个数**，由下文映射表给出） |

**输入契约：** `close` 不得就地修改；缺失价格可为 NaN，由 pandas 自然下传；因子输出与 `close` **同一 index**。

### B. v1 因子名 → 窗口（交易日近似，与 PLAN 一致）

| 因子名 | `w`（或额外参数） | core 路由 |
|--------|-------------------|-----------|
| `MOM_1M` | 21 | `mom(close, 21)` |
| `MOM_3M` | 63 | `mom(close, 63)` |
| `MOM_6M` | 126 | `mom(close, 126)` |
| `MOM_12M_SKIP_1M` | long=252, skip=21 | `mom_skip(close, 252, 21)` |
| `REV_1W` | 5 | `reversal(close, 5)` |
| `REV_2W` | 10 | `reversal(close, 10)` |
| `REV_1M` | 21 | `reversal(close, 21)` |
| `VOL_20D` | 20 | `volatility(close, 20)` |
| `VOL_60D` | 60 | `volatility(close, 60)` |
| `SHARPE_60D` | 60 | `sharpe(close, 60)` |
| `SORTINO_60D` | 60 | `sortino(close, 60)` |

### C. 时序因子代数式（实现须与单测数值一致）

以下均基于 `r = close.pct_change()`。

1. **`mom(close, w)`**  
   - **定义：** `mom = close.pct_change(w)`（与 pandas 一致：\(P_t/P_{t-w}-1\)）。  
   - **前导 NaN：** 前 `w` 根可为 NaN，不特殊填充。

2. **`mom_skip(close, long, skip)`**（12M 跳过近 1M）  
   - **与当前脚本对齐的定义（锁定为可测）：**  
     `mom_skip = close.pct_change(long) - close.pct_change(skip)`  
     其中 `long=252`, `skip=21`。  
   - **说明：** 这是**两个重叠简单收益之差**，不是几何复合的学术「12-1」；若未来改为累积收益定义，须**新版本因子名**或显式 `FactorSpec` 版本字段，避免静默漂移。

3. **`reversal(close, w)`**  
   - **定义：** `reversal = -close.pct_change(w)`（即 **短期收益的相反数**）。  
   - **校验关系：** `reversal(close, w) == -mom(close, w)`（同 index，容差 0）。

4. **`volatility(close, w, annualize=True)`**  
   - **定义：** `σ = r.rolling(w).std()` × `sqrt(252)`（若 `annualize=True`）。  
   - **pandas：** `rolling(w).std()` 默认 `ddof=1`（样本标准差），与脚本一致则**不要改 ddof**，仅在 docstring 写明。  
   - **无效窗：** 有效样本不足时 pandas 产出 NaN；**禁止**出现 `inf`。

5. **`sharpe(close, w, annualize=True, ddof=1)`**（与脚本 Sharpe 分支一致）  
   - `μ = r.rolling(w).mean()`  
   - `σ = r.rolling(w).std(ddof=ddof)`  
   - `sharpe = μ / σ.replace(0, np.nan) * sqrt(252)`（若 `annualize=True`）。  
   - **`σ` 为 0 或 NaN：** 结果为 NaN。

6. **`sortino(close, w, annualize=True, ddof=1)`**  
   - **下行波动（锁定为可实现的常见定义）：** 仅使用**非正**收益构造下行二阶矩：  
     `downside_sq = (r.clip(upper=0.0) ** 2).rolling(w).mean()`  
     `downside_std = sqrt(downside_sq)`（对全 0 下行样本，`downside_std` 为 0）。  
   - `sortino = r.rolling(w).mean() / downside_std.replace(0, np.nan) * sqrt(252)`（若 `annualize=True`）。  
   - **与 Sharpe 区分：** 全正收益窗口内 `downside_std` 可能为 0 → 结果为 NaN，**不得**为 `inf`。  
   - **注意：** 业界对 Sortino 是否减 MAR、是否用 `n_down` 等有分歧；以上定义**以可测与 PLAN「仅下行」为准**，若日后调整须改版本与测试。

### D. 截面标准化流水线（单日 `Series`，index=symbol）

**顺序（固定）：**  
`apply_nan_policy` → `winsorize_series` →（若 `cfg.enable_zscore`）`zscore_series` → `rank_series(..., pct=True)`。

1. **`winsorize_series(s, lower_q, upper_q)`**  
   - 在 **当日非 NaN** 子集上算 `lo = quantile(lower_q)`, `hi = quantile(upper_q)`（pandas 默认线性插值）。  
   - 输出 `s.clip(lower=lo, upper=hi)`，**原 NaN 位置保持 NaN**。

2. **`zscore_series(s, ddof)`**（截面）  
   - 在 **当日非 NaN** 上算 `μ`、`σ`（`σ` 用 `ddof`，全常数截面 → `σ=0` → 输出 NaN，无 `inf`）。

3. **`rank_series(s, method, pct=True)`**  
   - 直接 `s.rank(method=method, pct=pct)`；NaN 默认不参与排名，结果对应位置为 NaN。

4. **`apply_nan_policy`**（与 `20-CONTEXT` / PLAN 一致）  
   - **`drop`：** 参与 winsorize/rank 时只用非 NaN；最终输出 **与输入 index 对齐**，被剔除的 symbol 位置为 NaN（与 PLAN 中「对齐 index」描述一致）。  
   - **`median_fill` / `zero_fill`：** 在截面内填完后，再 winsorize/rank；输出 index 不变。

### E. 面板 `build_factor_panels`（A 口径）

1. 输入 `price_panel`: `index` = 交易日（升序），`columns` = symbol，`values` = 收盘价。  
2. 对每个 `factor_name`：对 **每一列** `price_panel[col]` 调 `compute_factor_by_name` 或 `FactorSpec`，得到与 index 等长的 `Series`，合并为 `DataFrame`。  
3. **不要求**所有 symbol 同日都有价：缺失为 NaN，与脚本 `union` 行为一致。  
4. 与 `normalize_cross_section` 的衔接：**取某一调仓日 `row = panel.loc[date]`** 得到单日截面，再标准化。

### F. `compute_factor_by_name` 与 `volume`

- v1 因子不强制使用 volume；签名保留 `volume: pd.Series | None`，未使用时传 `pd.Series(index=close.index, dtype=float)` 全 NaN 或与 `close` 同形的占位，**禁止**因缺 volume 抛错。

### G. 与 Pattern 示例的一致性修正

- `normalize_cross_section` **只**从 `cfg.enable_zscore` 读取是否插入 z-score，**不要**再暴露重复的 `enable_zscore` 形参（避免双重来源）。

## 函数签名建议

```python
# factor_defs.py
@dataclass(frozen=True)
class FactorSpec:
    name: str
    func: Callable[..., pd.Series]
    direction: int
    kwargs: dict[str, Any]
    category: str

def get_builtin_factor_specs() -> dict[str, FactorSpec]: ...

# core.py
def mom(close: pd.Series, window: int) -> pd.Series: ...
def mom_skip(close: pd.Series, window: int, skip: int) -> pd.Series: ...
def reversal(close: pd.Series, window: int) -> pd.Series: ...
def volatility(close: pd.Series, window: int, annualize: bool = True) -> pd.Series: ...
def sharpe(close: pd.Series, window: int, annualize: bool = True, ddof: int = 1) -> pd.Series: ...
def sortino(close: pd.Series, window: int, annualize: bool = True, ddof: int = 1) -> pd.Series: ...

# normalize.py
def winsorize_series(s: pd.Series, lower_q: float = 0.01, upper_q: float = 0.99) -> pd.Series: ...
def rank_series(s: pd.Series, method: str = "average", pct: bool = True) -> pd.Series: ...
def zscore_series(s: pd.Series, ddof: int = 0) -> pd.Series: ...
def apply_nan_policy(s: pd.Series, policy: str = "drop") -> pd.Series: ...

# pipeline.py
@dataclass(frozen=True)
class NormalizeConfig:
    winsor_lower: float = 0.01
    winsor_upper: float = 0.99
    rank_ties: str = "average"
    nan_policy: str = "drop"
    zscore_ddof: int = 0
    enable_zscore: bool = False

def load_normalize_config_from_env(env: Mapping[str, str] | None = None) -> NormalizeConfig: ...
def normalize_cross_section(s: pd.Series, cfg: NormalizeConfig) -> pd.Series: ...
```

## Environment Variable 配置设计

| Env Var | Default | Allowed | Effect |
|---------|---------|---------|--------|
| `QD_FACTOR_WINSOR_LOWER` | `0.01` | `(0,1)` | winsorize 下分位 |
| `QD_FACTOR_WINSOR_UPPER` | `0.99` | `(0,1)` 且 `>lower` | winsorize 上分位 |
| `QD_FACTOR_RANK_TIES` | `average` | `average|first|dense` | rank ties 行为 |
| `QD_FACTOR_NAN_POLICY` | `drop` | `drop|median_fill|zero_fill` | 标准化前 NaN 策略 |
| `QD_FACTOR_ENABLE_ZSCORE` | `false` | `true|false` | 是否在 rank 前启用 z-score |
| `QD_FACTOR_ZSCORE_DDOF` | `0` | `0|1` | z-score 标准差自由度 |

**Contract:**
- 配置解析错误必须 fail-fast（抛 `ValueError`），禁止静默回退。
- `drop` 语义：仅在当日截面中剔除 NaN 参与排序，输出对原 index 对齐并保留 NaN。
- `median_fill/zero_fill`：先填充，再执行 winsorize/rank，保证输出全量 symbol。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 分位截断 | 手写 percentile 循环 | `pandas.Series.quantile` + `clip` | 语义清晰且可测 |
| ties 排名 | 手写排序编号 | `pandas.Series.rank` | 已覆盖 average/first/dense |
| 面板对齐 | 自己管理 index merge | `DataFrame.reindex` / union index | 降低错位风险 |

**Key insight:** Phase 20 的复杂度在“行为一致性”，不是公式本身。任何手写替代都会增加跨调用方偏差。

## Common Pitfalls

### Pitfall 1: 因子命名漂移（`MOM_12M_1M` vs `MOM_12M_SKIP_1M`）
**What goes wrong:** 脚本命名与锁定目录不一致，调用方找不到或混用。
**Why it happens:** 原型脚本命名未完全对齐 phase 决策。
**How to avoid:** registry 以锁定名为唯一主键，旧名仅做别名映射并标 deprecated。
**Warning signs:** 相同窗口参数出现两套名字，测试中断言 key 不稳定。

### Pitfall 1b: 照搬脚本 `rev` 导致「反转」名不副实（2026-04-15 确认）
**What goes wrong:** `nq100_cross_sectional.py` 中 `rev` 与 `mom` 返回同一类 `pct_change(w)`，仅靠元数据 `dir` 表达多空；与 **CONTEXT**「反转因子」及 `20-02-PLAN` 中「与短期动量符号相反」的测试意图不一致。
**Why it happens:** 脚本侧重搜索组合，`rev` 可能仅作标签使用。
**How to avoid:** 共享库 `reversal()` 按 CONTEXT/PLAN 实现负向或脚本外明确文档的反转定义；单测断言与 `mom` 的符号关系。
**Warning signs:** `reversal` 与 `mom` 同窗完全相等。

### Pitfall 2: NaN 策略隐式变化导致结果不一致
**What goes wrong:** script 使用 fill，engine 使用 drop，回测不可复现。
**Why it happens:** NaN 行为散落在调用方，不在共享库统一。
**How to avoid:** 所有标准化入口强制要求 `NormalizeConfig`。
**Warning signs:** 同一输入在不同模块输出 symbol 集合长度不同。

### Pitfall 3: Sortino 下行波动为 0 的除零
**What goes wrong:** 结果 `inf`/`NaN` 传播到 rank。
**Why it happens:** 单边收益样本太短或全正收益。
**How to avoid:** 分母为 0 时返回 NaN，并统一让后续 NaN policy 处理。
**Warning signs:** 输出序列出现大量 `inf`。

### Pitfall 4: 把执行时序逻辑混入因子层
**What goes wrong:** 因子函数开始依赖 T+1/成交规则，污染职责边界。
**Why it happens:** 实现时把“选股”与“交易模拟”耦合。
**How to avoid:** 因子层只产出分数；T+1 在 Phase 21/22 实现。
**Warning signs:** 因子模块开始接触仓位、订单、成交时间。

## Code Examples

Verified patterns from current codebase:

### 因子原型来源（脚本）
```python
def calc_factor(close, volume, fname):
    cfg = FACTOR_DEFS[fname]
    t, w = cfg["type"], cfg["w"]
    if t == "mom":
        return close.pct_change(w)
    if t == "vol":
        return close.pct_change().rolling(w).std() * np.sqrt(252)
```

**Note（2026-04-15）：** 脚本中 `rev` 分支与 `mom` 相同（均为 `pct_change(w)`）；共享库 **不得** 照抄——见 **Codebase Verification** 与 **Pitfall 1b**。

### 后端纯计算接口风格（可复用）
```python
def run_cross_sectional_indicator(indicator_code: str, data: Dict[str, pd.DataFrame], trading_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    exec_env = {"symbols": list(data.keys()), "data": data, "scores": {}, "rankings": []}
    exec(indicator_code, exec_env)
    return {"scores": exec_env.get("scores", {}), "rankings": exec_env.get("rankings", [])}
```

## 测试矩阵（函数名建议）

### Unit Test Matrix
| Area | Function | Suggested Test Name |
|------|----------|---------------------|
| Factor registry | `get_builtin_factor_specs` | `test_factor_registry_contains_locked_v1_catalog` |
| MOM | `mom` | `test_mom_returns_pct_change_with_window_21` |
| MOM_SKIP | `mom_skip` | `test_mom_skip_subtracts_skip_leg` |
| REV | `reversal` | `test_reversal_uses_short_window_return` |
| VOL | `volatility` | `test_volatility_annualizes_rolling_std` |
| SHARPE | `sharpe` | `test_sharpe_returns_nan_on_zero_std` |
| SORTINO | `sortino` | `test_sortino_uses_downside_std_only` |
| winsorize | `winsorize_series` | `test_winsorize_clips_by_quantiles` |
| rank ties | `rank_series` | `test_rank_series_respects_ties_method_average_first_dense` |
| z-score | `zscore_series` | `test_zscore_series_respects_ddof_and_nan` |
| NaN policy | `apply_nan_policy` | `test_apply_nan_policy_drop_median_fill_zero_fill` |
| pipeline default | `normalize_cross_section` | `test_normalize_pipeline_default_winsorize_then_rank` |
| env config | `load_normalize_config_from_env` | `test_load_normalize_config_from_env_validates_ranges` |

### Integration Test Matrix
| Goal | Suggested Test Name | Assertion |
|------|---------------------|----------|
| script vs shared lib 一致 | `test_script_factor_output_matches_shared_library_fixture_panel` | 相同 fixture panel 下各因子序列一致 |
| strategy vs shared lib 一致 | `test_cross_sectional_strategy_uses_shared_normalize_pipeline` | strategy 输出排名与 library 完全一致 |
| engine adapter 一致（预留） | `test_engine_factor_adapter_matches_strategy_output_fixture` | Phase 22 接入后同输入同输出 |
| env 开关一致 | `test_enable_zscore_env_switch_changes_only_configured_steps` | 仅流水线步骤变化，其他行为不变 |

## 与 Phase 21/22/23/24 的边界说明

| Phase | In Scope Here? | Boundary |
|-------|-----------------|----------|
| 21 Backtest correctness | 否 | Phase 20 仅提供分数/排名输入，T+1、停牌、退市处理不在本层 |
| 22 Cross-sectional engine | 部分依赖 | Phase 20 产出可复用 factor+normalize API；组合模拟在 22 |
| 23 Grid-search script | 是（被复用） | 23 只编排实验，不重写因子/标准化公式 |
| 24 NQ100 strategy type | 是（被复用） | 24 处理策略约束与 delisting policy，不改因子定义 |

## State of the Art (Project-local)

| Old Approach | Current Recommended Approach | When Changed | Impact |
|--------------|------------------------------|--------------|--------|
| 单脚本 `calc_factor` | `app/factors` 共享库 | Phase 20 | engine/script/strategy 统一结果 |
| 调用方自由标准化 | 固定默认链 `winsorize->rank` | Phase 20 | 降低分叉与回归风险 |
| 仅脚本断点测试 | 后端单测+集成测矩阵 | Phase 20 | 可持续回归保障 |

## Open Questions

1. **`REV_1M` 是否定义为 21 交易日回报（与 `MOM_1M` 同窗）**
   - **Update 2026-04-15:** `20-02-PLAN.md` 已锁定交易日近似：`1M=21`；`REV_*` 为短期收益取负（或与原型一致的反转定义）。实现时以 PLAN + `factor_defs` docstring 为准，**本项视为已收敛**。

2. **Sortino 年化因子与 ddof 取值**
   - What we know: 需要实现风险调整因子，z-score ddof 可裁量。
   - What's unclear: Sortino 与 z-score 是否统一 ddof。
   - Recommendation: Sortino 与 Sharpe 均使用 `ddof=1`，z-score 保持配置项（默认 0）。

3. **REQUIREMENTS「volume」类是否在 v1 验收中必须对应单独因子名**
   - What we know: CONTEXT v1 无独立 volume-only 因子。
   - What's unclear: 产品/UAT 是否接受「六类」用 REV/VOL/文档说明覆盖。
   - Recommendation: 执行 phase 前与 ROADMAP owner 确认一句验收口径；否则需扩展因子或调整 REQ 映射表。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest（existing） |
| Config file | none — uses default pytest discovery |
| Quick run command | `cd backend_api_python && pytest tests/test_factor_library.py -q` |
| Full suite command | `cd backend_api_python && pytest tests/ -q` |

**Update 2026-04-15（与 `20-VALIDATION.md` / PLAN `<verification_contract>` 对齐）：** 每个 task 的 **verify** 以 **`tests/` 全量** 为阻断门禁；定向文件仅辅助排障。若未来存在依赖 PostgreSQL 的用例，需先起 `docker-compose` 依赖再跑同一全量命令。

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FACTOR-01 | built-in 因子可复用且输出稳定 | unit + integration | `cd backend_api_python && pytest tests/test_factor_library.py::test_factor_registry_contains_locked_v1_catalog -q` | ❌ Wave 0 |
| FACTOR-02 | winsorize/z-score/rank 共享模块可配置复用 | unit + integration | `cd backend_api_python && pytest tests/test_factor_normalize.py::test_normalize_pipeline_default_winsorize_then_rank -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend_api_python && pytest tests/test_factor_library.py tests/test_factor_normalize.py -q`
- **Per wave merge:** `cd backend_api_python && pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `backend_api_python/tests/test_factor_library.py` — covers FACTOR-01
- [ ] `backend_api_python/tests/test_factor_normalize.py` — covers FACTOR-02
- [ ] `backend_api_python/tests/fixtures/factor_panel_fixture.csv` — deterministic fixture panel

## Sources

### Primary (HIGH confidence)
- `.planning/phases/20-built-in-factors-normalization/20-CONTEXT.md` - 锁定决策、phase 边界、默认标准化契约
- `.planning/ROADMAP.md` - Phase 20~24 依赖顺序与目标
- `.planning/REQUIREMENTS.md` - FACTOR-01 / FACTOR-02 需求文本
- `scripts/cross_sectional/nq100_cross_sectional.py` - 当前因子原型与 panel 计算路径（**注意 `rev` 与锁定语义差异**，见 **Codebase Verification**）
- `backend_api_python/app/strategies/cross_sectional_indicator.py` - 后端可复用纯函数接口风格
- `backend_api_python/app/strategies/cross_sectional.py` - 截面策略 data->signal 管道边界
- `backend_api_python/tests/test_cross_sectional_weighted.py` - 现有 pytest 风格与命名习惯
- `backend_api_python/requirements.txt` - pandas/numpy 依赖基线
- `.planning/config.json` - nyquist_validation=true（需包含验证架构）

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - 完全来自仓库依赖与现有实现
- Architecture: HIGH - 由现有脚本与后端接口模式推导，且与锁定决策一致
- Pitfalls: MEDIUM - 基于当前代码风险点与典型截面因子实践
- **Implementation Design Details:** HIGH（代数式/窗口）用于编码；**Sortino 下行定义**若在业界文献中有多种变体，已锁定为 **Implementation Design Details §C.6** 的可测定义，后续若变更须显式版本化

**Research date:** 2026-04-14（**再核对：** 2026-04-15）
**Valid until:** 2026-05-14

## RESEARCH COMPLETE

Phase 20 调研结论已写入本文（含 Standard Stack、Architecture Patterns、**Implementation Design Details（方案细节）**、Don't Hand-Roll、Common Pitfalls、Validation Architecture）。**2026-04-15 增补：**（1）**Task Use Case Specifications**；（2）**Codebase Verification**；（3）**方案细节**——v1 窗口表、各 core 代数式、`mom_skip`/Sortino/截面流水线逐步语义、`build_factor_panels` 与 volume 占位约定；（4）全量 pytest 门禁。下一步：`/gsd-execute-phase 20`（PLAN 已存在时直接执行与验证）。
