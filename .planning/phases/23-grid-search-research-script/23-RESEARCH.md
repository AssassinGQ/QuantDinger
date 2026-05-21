# Phase 23: Grid-search research script - Research

**Researched:** 2026-05-19
**Domain:** Python batch script, HTTP API integration, walk-forward validation, checkpoint resume, YAML config, HTML reporting
**Confidence:** HIGH

## Summary

Phase 23 implements a standalone batch research script for grid-searching factor combinations with walk-forward validation. The script calls Phase 22's HTTP API (`POST /api/indicator/cross-sectional-portfolio-backtest`) to run backtests, uses YAML configuration for search space and window parameters, outputs results in JSONL/CSV/HTML formats, and supports checkpoint resume for long-running jobs.

**Primary recommendation:** Use the existing prototype (`scripts/cross_sectional/nq100_cross_sectional.py`) as a structural reference, but replace its local backtest engine with HTTP calls to Phase 22 API. Implement walk-forward validation using sliding fixed-size training/test windows. Use PyYAML for config parsing, simple f-string HTML generation (no Jinja2), and preserve the prototype's JSONL checkpoint pattern.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Implementation Decisions

**因子网格规格（SCRIPT-01）**
- **D-01:** 搜索空间由**配置文件（YAML）指定**，不硬编码。
- **D-02:** 配置文件包含：
  - `factors`: 显式因子列表（如 `['MOM_1M', 'VOL_20D', 'SHARPE_60D']`）
  - `combo_min`: 最小组合大小（如 `1`）
  - `combo_max`: 最大组合大小（如 `4`）
  - `n_long_options`: 持仓数列表（如 `[10, 20, 30, 40, 50, 60]`）
- **D-03:** 脚本启动时读取配置文件，动态生成搜索空间。配置文件路径通过CLI参数传入（默认 `grid_config.yaml`）。

**Walk-forward 验证（SCRIPT-04）**
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

**Phase 22 集成方式**
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

**行业中性化处理**
- **D-11:** Phase 22返回两套完整结果（`neutral_off` / `neutral_on`）。脚本**两套分别做网格搜索**。
- **D-12:** 输出两套TOP结果：
  - `neutral_off_top100.json`：不做行业中性化的最优组合
  - `neutral_on_top100.json`：做行业中性化的最优组合
- **D-13:** HTML报告包含对比分析：两套策略的Sharpe、年化、MaxDD对比，帮助研究者决策是否启用行业中性化。

**输出与报告（SCRIPT-02/03）**
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

**执行模式**
- **D-18:** **串行执行**（单线程），不做并行HTTP调用。避免API限流，保证稳定性。
- **D-19:** 进度实时输出：每N次回测打印进度（完成数/总数、速度、ETA）。

### Claude's Discretion

- YAML配置文件的具体字段命名与结构设计。
- HTML报告的样式与布局（简洁为主，不引入复杂前端框架）。
- Score评分公式（沿用原型或优化权重）。
- API调用超时与重试策略。

### Deferred Ideas (OUT OF SCOPE)

- **并行执行优化** — 若未来回测量大且API支持限流配置，可考虑异步并发。
- **动态因子权重（regime）** — Phase 20已标注归属研究脚本实验能力，可作为后续扩展配置项（如 `regime_config` 字段）。
- **交互式可视化前端** — 研究结果展示的前端UI属于v3范围。
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCRIPT-01 | 暴力搜索因子子集组合 × 持仓数网格（支持 >=793 种组合 × 7 种持仓数） | YAML config drives search space; `itertools.combinations` generates factor combos; combo sizes configurable |
| SCRIPT-02 | 标准指标输出（Sharpe / Calmar / MaxDD / 年化收益 / 胜率 / 总交易月数） | Phase 22 API returns complete summary metrics in `neutral_off.summary` and `neutral_on.summary`; prototype score formula available |
| SCRIPT-03 | 断点续传（checkpoint）+ JSONL 逐条结果输出 | Prototype checkpoint.json format verified (key: `"factor_combo|n_long|window_id"`); JSONL append pattern verified in `all_results.jsonl` |
| SCRIPT-04 | Walk-forward 滚动验证（训练窗口 + 测试窗口滑动） | Fixed-size rolling window algorithm documented; training months, test months, step months configurable via YAML |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| requests | 2.32.5 | HTTP API calls | Standard HTTP client for Python, handles timeouts/retries |
| PyYAML | 6.0.3 | Configuration parsing | YAML config file support for search space and window parameters |
| pandas | 3.0.0 | Data manipulation | CSV export, result aggregation, date calculations |
| numpy | 1.26.4 | Numerical operations | Score calculations, statistical aggregations |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| itertools | (stdlib) | Factor combination generation | `combinations()` for grid search space |
| argparse | (stdlib) | CLI argument parsing | Script invocation with config path, base URL, credentials |
| json | (stdlib) | JSONL checkpoint/output | Append results, checkpoint state |
| datetime | (stdlib) | Date calculations | Walk-forward window slicing |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| requests | httpx | httpx async support, but serial execution per D-18 makes async unnecessary |
| f-string HTML | Jinja2 | Jinja2 more powerful, but simple report needs only basic tables; avoids extra dependency |
| stdlib argparse | dataclasses-config | More structure, but simple CLI with 5-6 args doesn't justify extra library |

**Installation:**
```bash
# All dependencies already available in project environment
pip install pyyaml requests pandas numpy  # if needed
```

**Version verification:**
```
PyYAML: 6.0.3 (verified via pip show)
requests: 2.32.5 (verified via pip show)
pandas: 3.0.0 (verified via pip show)
numpy: 1.26.4 (verified via pip show)
pytest: 9.0.2 (verified via pip show)
```

## Architecture Patterns

### Recommended Project Structure
```
scripts/cross_sectional/
├── grid_search.py              # Main script (new)
├── grid_config.yaml            # Search space config (new)
├── results/
│   ├── all_results.jsonl       # Incremental results (existing pattern)
│   ├── all_results.csv         # CSV export (new)
│   ├── neutral_off_top100.json # Best without neutralization (new)
│   ├── neutral_on_top100.json  # Best with neutralization (new)
│   ├── checkpoint.json         # Resume state (existing pattern)
│   └── report.html             # Visual report (new)
├── cache/                      # Optional: local OHLCV cache (existing)
└── __init__.py                 # Package init (optional)
```

### Pattern 1: YAML Configuration for Search Space

**What:** Config-driven grid search parameters, no hardcoded factor lists.
**When to use:** SCRIPT-01 requirement - factor combos, n_long options, window parameters.

**Example config structure:**
```yaml
# grid_config.yaml
search_space:
  factors:
    - MOM_1M
    - MOM_3M
    - MOM_6M
    - MOM_12M_SKIP_1M
    - REV_1W
    - REV_2W
    - REV_1M
    - VOL_20D
    - VOL_60D
    - SHARPE_60D
    - SORTINO_60D
  combo_min: 1
  combo_max: 4
  n_long_options: [10, 15, 20, 30, 40, 50, 60]

walk_forward:
  enabled: true
  train_months: 36
  test_months: 12
  step_months: 12
  # Optional: specific date range override
  start_date: "2020-01-01"
  end_date: "2026-04-01"

backtest_defaults:
  universe: "nq100"
  timeframe: "1D"
  initial_capital: 100000
  market: "USStock"

output:
  results_dir: "results"
  progress_interval: 50  # Print progress every N backtests
```

**Source:** [ASSUMED] - design based on CONTEXT.md D-01 through D-05

### Pattern 2: Phase 22 HTTP API Contract

**What:** Exact endpoint, request body, and response structure for backtest calls.
**When to use:** All SCRIPT-01 through SCRIPT-04 backtest invocations.

**Endpoint:**
```
POST /api/indicator/cross-sectional-portfolio-backtest
Authorization: Bearer {token}
Content-Type: application/json
```

**Request body (minimal):**
```json
{
  "universe": "nq100",
  "startDate": "2021-04-01",
  "endDate": "2024-04-01",
  "indicatorCode": "...",
  "timeframe": "1D",
  "market": "USStock"
}
```

**Request body (with trading_config):**
```json
{
  "universe": "nq100",
  "startDate": "2021-04-01",
  "endDate": "2024-04-01",
  "indicatorCode": "...",
  "timeframe": "1D",
  "market": "USStock",
  "tradingConfig": {
    "initialCapital": 100000,
    "rebalanceFrequency": "monthly"
  }
}
```

**Response structure:**
```json
{
  "code": 1,
  "msg": "OK",
  "data": {
    "repro": {
      "universe_digest": "...",
      "indicator_config_hash": "...",
      "execution_profile": {...}
    },
    "neutral_off": {
      "equity_curve": [{"time": "...", "value": ...}, ...],
      "summary": {
        "totalReturn": 125.5,
        "annualReturn": 18.2,
        "maxDrawdown": -28.3,
        "sharpeRatio": 1.15,
        "calmarRatio": 0.64,
        "winRate": 62.5,
        ...
      },
      "repro": {...}
    },
    "neutral_on": {
      "equity_curve": [...],
      "summary": {...},
      "repro": {...}
    }
  }
}
```

**Source:** [VERIFIED: backend_api_python/app/routes/cross_sectional_portfolio_backtest.py lines 103-247]

### Pattern 3: Indicator Code Generation for Factor Combinations

**What:** Dynamic indicator code string that computes composite scores and weights from factor combo.
**When to use:** SCRIPT-01 - generating backtest indicator for each factor combination.

**Example indicator code template:**
```python
def build_indicator_code(factors: list[str], directions: list[int]) -> str:
    """Generate indicator code for a factor combination."""
    # Factor definitions come from Phase 20 built-in factors
    factor_calls = []
    for f in factors:
        factor_calls.append(f"factor_{f} = compute_factor_by_name('{f}', close, volume)")

    # Score computation: weighted rank combination
    score_lines = []
    for i, (f, d) in enumerate(zip(factors, directions)):
        weight = 1.0 / len(factors)
        score_lines.append(
            f"    raw_{f} = factor_{f}\n"
            f"    ranked_{f} = raw_{f}.rank(pct=True)\n"
            f"    composite += {d} * ranked_{f} * {weight}"
        )

    # TopN selection based on n_long (passed via trading_config)
    code = f'''
from app.factors.factor_defs import compute_factor_by_name
close = data[symbol]["close"]
volume = data[symbol]["volume"] if "volume" in data[symbol] else None

# Compute factors
{chr(10).join(factor_calls)}

# Composite score
composite = pd.Series(0.0, index=data.keys())
for symbol in data.keys():
    try:
{chr(10).join(score_lines)}
    except Exception:
        pass

# Sort by composite, select top n_long
n_long = trading_config.get("n_long", 20)
sorted_symbols = composite.sort_values(ascending=False).head(n_long).index.tolist()

# Assign scores and weights
for s in symbols:
    scores[s] = composite.get(s, 0.0)
for s in sorted_symbols:
    weights[s] = 1.0 / n_long

rankings = sorted_symbols
'''
    return code
```

**Source:** [CITED: backend_api_python/app/factors/factor_defs.py] - factor names and compute_factor_by_name function

### Pattern 4: Walk-Forward Window Algorithm

**What:** Sliding fixed-size windows for training (grid search) and test (out-of-sample validation).
**When to use:** SCRIPT-04 - rolling walk-forward validation.

**Algorithm:**
```python
def generate_walk_forward_windows(
    start_date: date,
    end_date: date,
    train_months: int,
    test_months: int,
    step_months: int,
) -> list[dict]:
    """Generate walk-forward window definitions."""
    windows = []
    train_len = timedelta(days=train_months * 30)  # Approximate
    test_len = timedelta(days=test_months * 30)
    step_len = timedelta(days=step_months * 30)

    window_start = start_date
    while window_start + train_len + test_len <= end_date:
        train_end = window_start + train_len
        test_end = train_end + test_len

        windows.append({
            "window_id": len(windows) + 1,
            "train_start": window_start.isoformat(),
            "train_end": train_end.isoformat(),
            "test_start": train_end.isoformat(),
            "test_end": test_end.isoformat(),
        })

        window_start += step_len  # Slide forward

    return windows
```

**Example output (36m train, 12m test, 12m step):**
```python
# Start: 2020-01-01, End: 2026-04-01
# Window 1: Train 2020-01 to 2023-01, Test 2023-01 to 2024-01
# Window 2: Train 2021-01 to 2024-01, Test 2024-01 to 2025-01
# Window 3: Train 2022-01 to 2025-01, Test 2025-01 to 2026-01
```

**Source:** [CITED: https://machinelearningmastery.com/walk-forward-validation-for-time-series-forecasting/]

### Pattern 5: JSONL Checkpoint Resume

**What:** Incremental results appended to JSONL; checkpoint.json tracks completed keys.
**When to use:** SCRIPT-03 - fault tolerance for long-running grid search.

**Checkpoint format (from prototype):**
```json
{
  "done": ["MOM_1M+VOL_20D|10|w1", "MOM_1M+VOL_20D|15|w1", ...],
  "results": [...optional cached results...]
}
```

**Key format:** `{factor_combo_str}|{n_long}|{window_id}` for walk-forward mode.

**Resume logic:**
```python
def load_checkpoint(ckpt_path: str) -> set[str]:
    if not os.path.exists(ckpt_path):
        return set()
    with open(ckpt_path) as f:
        data = json.load(f)
    return set(data.get("done", []))

def should_skip(key: str, done: set[str]) -> bool:
    return key in done

def append_result(jsonl_path: str, result: dict):
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
```

**Source:** [VERIFIED: scripts/cross_sectional/results/checkpoint.json and all_results.jsonl]

### Anti-Patterns to Avoid

- **Hardcoded factor list:** Violates D-01; factor list must come from YAML config
- **Parallel HTTP calls:** Violates D-18; serial execution required for stability
- **Skipping neutral_on results:** Violates D-11; both neutral_off and neutral_on must be processed
- **Using local backtest engine:** Violates D-08; must call Phase 22 HTTP API
- **Checkpoint key without window_id:** Walk-forward mode requires window_id in key for correct resume

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP retries/timeout | Custom retry loop | `requests` with timeout param, simple while-retry | Deceptively complex: exponential backoff, connection errors, read timeouts |
| Factor combinations | Manual permutation loops | `itertools.combinations()` | Handles all combo sizes correctly, no duplicate logic |
| CSV formatting | Manual string concatenation | `pandas.DataFrame.to_csv()` | Handles escaping, encoding, index correctly |
| Date arithmetic | Manual month calculations | `dateutil.relativedelta` or `pandas.DateOffset` | Month boundaries, leap years, edge cases |
| JSONL parsing | Custom line reader | `json.loads()` per line | Standard, handles edge cases (empty lines, malformed) |

**Key insight:** This is a research script, not production code. Simplicity and correctness > optimization. Use stdlib and standard libraries wherever possible.

## Common Pitfalls

### Pitfall 1: Phase 22 API Pool Validation Error

**What goes wrong:** Sending both `symbolList` and `universe` in request body causes HTTP 400 error.
**Why it happens:** Phase 22 D-03 enforces mutual exclusivity.
**How to avoid:** Always use `universe: "nq100"` for this script (per D-10), never send `symbolList`.
**Warning signs:** Response `{"code": 0, "msg": "BT01_POOL: symbolList and universe are mutually exclusive"}`

**Source:** [VERIFIED: backend_api_python/app/routes/cross_sectional_portfolio_backtest.py lines 31-51]

### Pitfall 2: Indicator Code Missing weights

**What goes wrong:** Indicator code omits `weights` dict, causing CROSS_SECTIONAL_CONTRACT error.
**Why it happens:** Phase 22 requires both `scores` and `weights` (D-07); framework does not auto-derive weights from scores.
**How to avoid:** Indicator code must explicitly assign `weights[s] = 1.0/n_long` for top N symbols.
**Warning signs:** HTTP 422 response, `CROSS_SECTIONAL_CONTRACT: missing weights` in service logs

**Source:** [VERIFIED: backend_api_python/app/strategies/cross_sectional_indicator.py lines 32-55]

### Pitfall 3: Walk-Forward Window Overlap

**What goes wrong:** Test windows overlap, causing same data used for multiple out-of-sample evaluations.
**Why it happens:** Step size smaller than test length.
**How to avoid:** Validate `step_months >= test_months` at config load time; warn if violated.
**Warning signs:** Same test_end date appearing in multiple windows

### Pitfall 4: JSONL Corruption on Crash

**What goes wrong:** Partial JSON line written during crash, causing resume parse errors.
**Why it happens:** Write interrupted mid-line, or OS flush not completed.
**How to avoid:** Write complete line with single `write()` call; rely on OS atomic append (POSIX guarantees).
**Warning signs:** `json.loads()` parse error when reading JSONL on resume

**Mitigation:** Skip malformed lines on resume, log warning, continue.

### Pitfall 5: Negative Weight Rejection

**What goes wrong:** Indicator code produces negative weights for some symbols, causing LONG_ONLY error.
**Why it happens:** Factor direction produces negative composite scores, but weight assignment logic is flawed.
**How to avoid:** Always assign positive weights only to top N selected symbols.
**Warning signs:** HTTP 422 response, `CROSS_SECTIONAL_LONG_ONLY: negative weight for 'XXX'`

**Source:** [VERIFIED: backend_api_python/app/services/cross_sectional_portfolio_backtest.py lines 135-139]

## Code Examples

### Phase 22 API Call with Error Handling

```python
# Source: [VERIFIED: backend_api_python/app/routes/cross_sectional_portfolio_backtest.py]
import requests
from typing import Any

def call_phase22_backtest(
    base_url: str,
    token: str,
    universe: str,
    start_date: str,
    end_date: str,
    indicator_code: str,
    n_long: int,
    timeout: float = 120.0,
) -> dict[str, Any] | None:
    """Call Phase 22 backtest API with retry on transient errors."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "universe": universe,
        "startDate": start_date,
        "endDate": end_date,
        "indicatorCode": indicator_code,
        "timeframe": "1D",
        "market": "USStock",
        "tradingConfig": {
            "initialCapital": 100000,
            "n_long": n_long,  # Passed to indicator code via trading_config
        },
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                f"{base_url}/api/indicator/cross-sectional-portfolio-backtest",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            data = resp.json()
            if data.get("code") == 1:
                return data.get("data")
            # Business error (e.g., pool validation, contract error)
            print(f"  API error: {data.get('msg')}")
            return None
        except requests.Timeout:
            if attempt < max_retries - 1:
                print(f"  Timeout, retry {attempt+2}/{max_retries}")
                continue
            print(f"  Timeout after {max_retries} retries")
            return None
        except requests.RequestException as e:
            print(f"  HTTP error: {e}")
            return None
    return None
```

### Walk-Forward Grid Search Loop

```python
# Source: [CITED: prototype pattern + walk-forward algorithm]
from datetime import date
from itertools import combinations

def grid_search_with_walk_forward(
    config: dict,
    base_url: str,
    token: str,
    done_keys: set[str],
    jsonl_path: str,
) -> list[dict]:
    """Run walk-forward grid search with checkpoint resume."""
    factors = config["search_space"]["factors"]
    combo_min = config["search_space"]["combo_min"]
    combo_max = config["search_space"]["combo_max"]
    n_long_options = config["search_space"]["n_long_options"]

    wf_config = config["walk_forward"]
    windows = generate_walk_forward_windows(
        date.fromisoformat(wf_config["start_date"]),
        date.fromisoformat(wf_config["end_date"]),
        wf_config["train_months"],
        wf_config["test_months"],
        wf_config["step_months"],
    )

    results = []
    for window in windows:
        # Training phase: grid search on train window
        train_best = None
        train_best_score = -9999

        for combo_size in range(combo_min, combo_max + 1):
            for factor_combo in combinations(factors, combo_size):
                directions = [FACTOR_DEFS[f]["direction"] for f in factor_combo]
                indicator_code = build_indicator_code(factor_combo, directions)

                for n_long in n_long_options:
                    key = f"{'+'.join(factor_combo)}|{n_long}|w{window['window_id']}"
                    if key in done_keys:
                        continue

                    data = call_phase22_backtest(
                        base_url, token, "nq100",
                        window["train_start"], window["train_end"],
                        indicator_code, n_long,
                    )

                    if data and data.get("neutral_off"):
                        summary = data["neutral_off"]["summary"]
                        score = compute_score(summary)
                        result = {
                            "factors": list(factor_combo),
                            "n_long": n_long,
                            "window_id": window["window_id"],
                            "phase": "train",
                            "score": score,
                            **summary,
                        }
                        results.append(result)
                        append_result(jsonl_path, result)
                        done_keys.add(key)

                        if score > train_best_score:
                            train_best = (factor_combo, directions, n_long)
                            train_best_score = score

        # Test phase: evaluate best combo on test window
        if train_best:
            factor_combo, directions, n_long = train_best
            indicator_code = build_indicator_code(factor_combo, directions)
            test_key = f"{'+'.join(factor_combo)}|{n_long}|test_w{window['window_id']}"

            if test_key not in done_keys:
                data = call_phase22_backtest(
                    base_url, token, "nq100",
                    window["test_start"], window["test_end"],
                    indicator_code, n_long,
                )
                if data and data.get("neutral_off"):
                    summary = data["neutral_off"]["summary"]
                    score = compute_score(summary)
                    result = {
                        "factors": list(factor_combo),
                        "n_long": n_long,
                        "window_id": window["window_id"],
                        "phase": "test",
                        "score": score,
                        **summary,
                    }
                    results.append(result)
                    append_result(jsonl_path, result)
                    done_keys.add(test_key)

    return results
```

### Simple HTML Report Generation

```python
# Source: [ASSUMED] - simple f-string HTML, no Jinja2
def generate_html_report(results: list[dict], config: dict, output_path: str):
    """Generate simple HTML report without framework."""
    # Sort by score descending
    sorted_results = sorted(results, key=lambda x: x.get("score", -9999), reverse=True)

    top20 = sorted_results[:20]
    factor_stats = {}
    for r in sorted_results[:100]:
        for f in r.get("factors", []):
            factor_stats[f] = factor_stats.get(f, 0) + 1

    html = f'''<!DOCTYPE html>
<html>
<head>
<title>Grid Search Report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
h1, h2 {{ color: #333; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #f4f4f4; }}
tr:nth-child(even) {{ background-color: #f9f9f9; }}
.positive {{ color: green; }}
.negative {{ color: red; }}
</style>
</head>
<body>
<h1>NQ100 Cross-Sectional Grid Search Report</h1>

<h2>Configuration</h2>
<ul>
<li>Factors: {len(config["search_space"]["factors"])} available</li>
<li>Combo sizes: {config["search_space"]["combo_min"]} to {config["search_space"]["combo_max"]}</li>
<li>Holdings: {config["search_space"]["n_long_options"]}</li>
<li>Walk-forward: {config["walk_forward"]["train_months"]}m train, {config["walk_forward"]["test_months"]}m test, {config["walk_forward"]["step_months"]}m step</li>
</ul>

<h2>Top 20 Results (Neutral OFF)</h2>
<table>
<tr><th>#</th><th>Factors</th><th>Holdings</th><th>Ann Return</th><th>Sharpe</th><th>MaxDD</th><th>Score</th></tr>
'''

    for i, r in enumerate(top20):
        ann = r.get("annualReturn", 0) or 0
        shr = r.get("sharpeRatio", 0) or 0
        dd = r.get("maxDrawdown", 0) or 0
        sc = r.get("score", 0) or 0
        factors_str = ", ".join(r.get("factors", []))
        html += f'''<tr>
<td>{i+1}</td>
<td>{factors_str}</td>
<td>{r.get("n_long", 0)}</td>
<td class="{ann >= 0 and 'positive' or 'negative'}">{ann:+.1f}%</td>
<td>{shr:.2f}</td>
<td class="negative">{dd:.1f}%</td>
<td>{sc:.1f}</td>
</tr>'''

    html += f'''</table>

<h2>Factor Frequency (Top 100)</h2>
<table>
<tr><th>Factor</th><th>Appearances</th><th>Percentage</th></tr>
'''

    for f, count in sorted(factor_stats.items(), key=lambda x: -x[1]):
        pct = count
        html += f'''<tr><td>{f}</td><td>{count}</td><td>{pct}%</td></tr>'''

    html += '''</table>

<h2>Walk-Forward Out-of-Sample Summary</h2>
<table>
<tr><th>Window</th><th>Train Best</th><th>Test Ann</th><th>Test Sharpe</th></tr>
'''

    test_results = [r for r in results if r.get("phase") == "test"]
    for r in test_results:
        html += f'''<tr>
<td>{r.get("window_id", "?")}</td>
<td>{", ".join(r.get("factors", []))}</td>
<td>{r.get("annualReturn", 0):+.1f}%</td>
<td>{r.get("sharpeRatio", 0):.2f}</td>
</tr>'''

    html += '''</table>

<p>Generated: ''' + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '''</p>
</body>
</html>'''

    with open(output_path, "w") as f:
        f.write(html)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded factor lists | YAML config-driven search space | Phase 23 D-01 | Researcher can experiment without code changes |
| Local backtest engine | HTTP API calls (Phase 22) | Phase 23 D-08 | Reusability, reproducibility, API contract stability |
| Single-pass grid search | Walk-forward validation (SCRIPT-04) | Phase 23 D-04 | Out-of-sample validation, reduces overfitting risk |
| Single output file | JSONL + CSV + HTML triple output | Phase 23 D-14 | Multiple analysis workflows (Excel, Python, visual) |
| Manual restart from crash | Checkpoint resume (SCRIPT-03) | Prototype pattern | Fault tolerance for multi-hour jobs |

**Deprecated/outdated:**
- Prototype's local factor computation (`calc_factor`): Phase 22 handles factors via built-in library
- Prototype's own backtest engine: Phase 22 API provides complete backtest
- Prototype's hardcoded NQ100_UNIVERSE list: Phase 19 PIT API provides universe

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research. The planner and discuss-phase use this section to identify decisions that need user confirmation before execution.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | YAML config structure design (field names like `search_space.factors`) | Architecture Patterns | Config parsing fails, researcher cannot specify search space |
| A2 | HTML report uses simple f-string generation, no Jinja2 | Architecture Patterns | Report generation more complex than expected, may need Jinja2 for conditional sections |
| A3 | Score formula from prototype is adequate: `ann*0.25 + sharpe*10*0.30 + min(calmar,5)*5*0.15 - |dd|*0.15 + min(winRate,70)*0.15` | Common Pitfalls | Score may not reflect researcher's preference, may need adjustment |
| A4 | n_long parameter passed via `tradingConfig.n_long` in API request | Architecture Patterns | API may expect different parameter name; check Phase 22 actual implementation |

**If this table is empty:** All claims in this research were verified or cited.

## Open Questions (RESOLVED)

All open questions resolved during planning.

1. **Indicator code format for n_long selection**
   - What we know: Phase 22 indicator code has access to `trading_config` dict (verified in cross_sectional_indicator.py)
   - What was unclear: Exact mechanism to pass n_long from script to indicator code
   - **RESOLVED:** Plan 02 Task 2 shows indicator code accesses `trading_config.get("n_long", 20)`; `tradingConfig.n_long` in HTTP request maps to `trading_config` in indicator execution context

2. **Industry data for neutral_on mode**
   - What we know: Phase 22 accepts `industryBySymbol` parameter in request body
   - What was unclear: Whether NQ100 stocks have industry classification data available
   - **RESOLVED:** Use `_DEFAULT` fallback per Phase 22 implementation; script processes both neutral_off and neutral_on results from API (neutral_on uses default industry grouping if no industryBySymbol provided)

3. **Walk-forward window dates using actual trading days vs calendar months**
   - What we know: Prototype uses monthly_ends() function to find last trading day of each month
   - What was unclear: Whether Phase 22 API handles date alignment internally
   - **RESOLVED:** Send calendar-month dates (e.g., "2023-01-01" to "2024-01-01"); Phase 22 service uses master_calendar from panel to find actual trading days

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | Script runtime | ✓ | 3.11.14 | — |
| PyYAML | Config parsing | ✓ | 6.0.3 | — |
| requests | HTTP API calls | ✓ | 2.32.5 | — |
| pandas | CSV export, data | ✓ | 3.0.0 | — |
| numpy | Score calculations | ✓ | 1.26.4 | — |
| pytest | Test framework | ✓ | 9.0.2 | — |
| Backend API | Phase 22 backtest | ✓ | reachable (health check OK) | — |
| NQ100 PIT API | Universe data | ✓ | Phase 19 implemented | — |

**Missing dependencies with no fallback:**
- None

**Missing dependencies with fallback:**
- None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `backend_api_python/pytest.ini` (project default) |
| Quick run command | `cd backend_api_python && pytest tests/test_grid_search_script.py -q` |
| Full suite command | `cd backend_api_python && pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCRIPT-01 | YAML config parsing generates correct search space | unit | `pytest tests/test_grid_search_script.py -k config -v` | ❌ Wave 0 |
| SCRIPT-01 | Factor combination generation covers all sizes | unit | `pytest tests/test_grid_search_script.py -k combos -v` | ❌ Wave 0 |
| SCRIPT-02 | Score calculation matches prototype formula | unit | `pytest tests/test_grid_search_script.py -k score -v` | ❌ Wave 0 |
| SCRIPT-03 | Checkpoint resume skips completed keys | unit | `pytest tests/test_grid_search_script.py -k checkpoint -v` | ❌ Wave 0 |
| SCRIPT-03 | JSONL append creates valid output | unit | `pytest tests/test_grid_search_script.py -k jsonl -v` | ❌ Wave 0 |
| SCRIPT-04 | Walk-forward window generation produces correct ranges | unit | `pytest tests/test_grid_search_script.py -k walk_forward -v` | ❌ Wave 0 |
| SCRIPT-04 | Walk-forward OOS results aggregate correctly | integration | `pytest tests/test_grid_search_script.py -k oos -v` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** Quick run command for affected test file
- **Per wave merge:** Full suite command
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend_api_python/tests/test_grid_search_script.py` — main test file for Phase 23 script
- [ ] `scripts/cross_sectional/test_grid_config.yaml` — minimal test config fixture
- [ ] Script execution test harness (mock Phase 22 API responses)

*(If no gaps: "None - existing test infrastructure covers all phase requirements")*

Note: Script is standalone batch job, not backend API. Tests should:
1. Mock Phase 22 HTTP responses (using `unittest.mock.patch` on `requests.post`)
2. Test pure functions (config parsing, combination generation, walk-forward windows, score formula)
3. Integration test with minimal mock API server for end-to-end flow

## Security Domain

> Phase 23 is a research script, not production API. Security considerations are minimal.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | minimal | Script uses API token for Phase 22 calls (already implemented in prototype) |
| V3 Session Management | no | Script is batch job, no sessions |
| V4 Access Control | minimal | API token scopes (inherited from backend) |
| V5 Input Validation | yes | YAML config validation (PyYAML handles parsing; validate ranges) |
| V6 Cryptography | no | No crypto operations in script |

### Known Threat Patterns for Python Batch Scripts

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious YAML (code execution via !python/object) | Tampering, Elevation | Use `yaml.safe_load()` only (never `yaml.load()` without Loader) |
| API token leakage in logs/files | Information Disclosure | Token from CLI/env, never in config file; exclude from JSONL output |
| Path traversal in output files | Tampering | Use fixed output directory, validate paths do not contain `..` |

### Script-Specific Security Notes

- **Token handling:** Token from CLI args or environment variable (e.g., `QD_API_TOKEN`), never stored in config file
- **YAML safety:** Always use `yaml.safe_load()` for config parsing
- **Output isolation:** Results written to configurable directory; script should validate directory exists and is writable before running

## Sources

### Primary (HIGH confidence)
- `backend_api_python/app/routes/cross_sectional_portfolio_backtest.py` — Phase 22 API endpoint implementation (lines 103-247) [VERIFIED]
- `backend_api_python/app/services/cross_sectional_portfolio_backtest.py` — Phase 22 service contract, neutral_off/neutral_on structure [VERIFIED]
- `backend_api_python/app/strategies/cross_sectional_indicator.py` — Indicator code contract, scores+weights requirement [VERIFIED]
- `backend_api_python/app/factors/factor_defs.py` — Built-in factor names and compute_factor_by_name [VERIFIED]
- `scripts/cross_sectional/nq100_cross_sectional.py` — Prototype reference (587 lines) [VERIFIED]
- `scripts/cross_sectional/results/all_results.jsonl` — JSONL output format [VERIFIED]
- `scripts/cross_sectional/results/checkpoint.json` — Checkpoint format [VERIFIED]

### Secondary (MEDIUM confidence)
- `.planning/phases/22-cross-sectional-portfolio-backtest-engine/22-CONTEXT.md` — Phase 22 locked decisions (D-01 through D-13) [CITED]
- `.planning/phases/22-cross-sectional-portfolio-backtest-engine/22-VALIDATION.md` — Phase 22 test infrastructure [CITED]
- `backend_api_python/tests/test_cross_sectional_portfolio_bt01.py` — Phase 22 test patterns [CITED]
- [Machine Learning Mastery - Walk-Forward Validation](https://machinelearningmastery.com/walk-forward-validation-for-time-series-forecasting/) — Walk-forward algorithm reference [CITED]
- [sklearn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) — Rolling window reference [CITED]

### Tertiary (LOW confidence)
- YAML config field naming — design based on CONTEXT.md, needs validation [ASSUMED]
- HTML report f-string approach — simple, but complex reports may need Jinja2 [ASSUMED]
- n_long passing mechanism — inferred from trading_config in indicator code, needs testing [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All dependencies verified via pip show, already available
- Architecture: HIGH - Phase 22 API contract verified from source code, walk-forward pattern from literature
- Pitfalls: HIGH - All pitfalls verified from Phase 22 source code (pool validation, contract errors, weight rejection)
- HTML report: MEDIUM - Simple approach should work, but complex sections may need refinement
- n_long mechanism: MEDIUM - Inferred from indicator code, needs end-to-end test

**Research date:** 2026-05-19
**Valid until:** 30 days (stable Python libraries, Phase 22 API contract locked)