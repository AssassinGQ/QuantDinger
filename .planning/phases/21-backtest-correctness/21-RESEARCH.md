# Phase 21: Backtest correctness - Research

**Researched:** 2026-04-15  
**Domain:** Cross-sectional backtest correctness (survivorship, T+1 execution, tradeability)  
**Confidence:** HIGH（项目内约束）/ MEDIUM-HIGH（外部生态映射）

## Standard Stack

### Core
| Library / Component | Version Baseline | Purpose | Prescriptive Decision |
|---|---|---|---|
| Python | 3.10+ | 后端执行语义实现 | 保持纯 Python 规则引擎，不引入额外回测框架 |
| pandas | `requirements.txt` 现有版本 | 面板构建、T/T+1 位移、可交易掩码 | 统一使用 `DataFrame/Series`，避免 list/dict 手工对齐 |
| pytest | 项目既有 | correctness 回归门禁 | 每条 AUDIT 规则必须有 fixture 驱动测试 |

### Existing Project Components (must reuse)
| Component | Role in Phase 21 | Prescriptive Decision |
|---|---|---|
| `app/factors/panel.py` | 因子面板输入 | 保留“历史行不删”语义，作为 survivorship-aware 数据入口 |
| `app/strategies/cross_sectional_signals.py` | 目标持仓信号生成 | 不改“目标组合”职责；新增执行前过滤层而非把交易约束塞进信号层 |
| `app/strategies/runners/cross_sectional_runner.py` | tick dispatch | 在 `_dispatch_signals` 前插入 Phase 21 审计闸门 |
| `scripts/cross_sectional/nq100_cross_sectional.py` | 研究脚本基线 | 仅作为“现状参考”；禁止继续沿用其简化成交假设作为正确性标准 |

### External Ecosystem Evidence (for critical claims)
- Zipline/QuantRocket 文档与示例都采用“盘前基于前日数据计算，开盘执行”流程，强调信号-执行分离。  
  - https://www.quantrocket.com/codeload/zipline-intro/intro_zipline/Part2-End-of-Day-Trading-Rules.ipynb.html
- Backtrader 官方文档明确：默认 market order 在回测中于“下一根 bar 开盘价”执行；同 bar 执行需要 `cheat_on_open`（应避免作为默认）。  
  - https://www.backtrader.com/docu/order/  
  - https://www.backtrader.com/docu/cerebro/cheat-on-open/cheat-on-open/
- QuantConnect 文档与 LEAN issue 说明：避免 stale/fill-forward 成交，强调 next available/open 语义与可配置 fill model。  
  - https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/market-orders  
  - https://github.com/QuantConnect/Lean/issues/2762

**结论（Prescriptive）:**  
用“信号日 T close + 执行日 T+1 next_open + 严格不可交易过滤”作为默认主链路；避免同 bar 成交和乐观填单。

## Architecture Patterns

### Pattern 1: Two-Phase Rebalance Ledger（信号账本与执行账本分离）
**Use X:** 先生成 `target_positions@T_close`，再在 `execution_engine@T+1` 消费。  
**Avoid Y:** 在同一函数中“排名 + 立即成交 + 改仓位”。

建议对象：
- `RebalancePlan`（immutable）: `signal_date`, `effective_exec_date`, `target_weights`, `metadata`
- `ExecutionAttempt`（append-only）: `symbol`, `intent(open/close)`, `status(filled/skipped_untradable/forced_cash_exit/held)`, `reason`
- `PortfolioState`: `positions`, `cash`, `pending_rebalance_id`, `untradable_flags`

### Pattern 2: Execution Filter Chain（严格过滤链）
执行顺序固定（D-04~D-11 对应）：
1. 日历闸门（IC `effective_date` 偏移规则，T+1->T+2）
2. 公司行动闸门（M&A/Delisting/Symbol Change/Bankruptcy）
3. 流动性闸门（20D dollar volume 阈值）
4. `next_open` 有效性闸门（`>0` 且非 NaN）
5. 订单侧策略（买单失败 -> 留现金；卖单失败 -> 保持持仓）

### Pattern 3: Explicit Exception Routing（仅一类强制退出）
- 唯一强制退出：`cash_mna_forced_exit`
- 其他全部遵循 `UNTRADABLE hold` 规则，不做隐式替代成交

### Pattern 4: Deterministic Fixture-First
- 不连外网，不读“今天实时成分”
- fixture 固定：交易日历、IC 事件、K 线、corporate actions、预期执行日志
- 用 snapshot 断言执行轨迹（不仅断言最终净值）

## Don't Hand-Roll

| Problem | Don't Hand-Roll | Use Instead | Why |
|---|---|---|---|
| 交易日历偏移 | 手写 weekday + 1 天 | 统一交易日历 helper（项目内） | 避免节假日和跨月错位 |
| `next_open` fallback | 分散在多处 if/else | 单一 `resolve_execution_price()` | 保证策略一致且可测 |
| 公司行动判定 | 信号层临时判定 | execution filter 中央化 | 减少语义漂移 |
| 未成交处理 | “买不到就买备胎” | 严格现金替代（D-08） | 防止引入隐式优化偏差 |
| 退市样本处理 | 直接 drop 历史行 | 面板历史保留 + 当期可交易过滤 | 同时满足 AUDIT-01 和执行真实性 |
| 回测可复现 | 每次动态拉数据 | 固定 fixture + checksum | 回归可靠 |

## Common Pitfalls

1. **同 bar 污染（最高风险）**  
   - 错误：T 日 close 排名后同日成交  
   - 后果：未来函数，收益虚高  
   - 预防：强制 `exec_date > signal_date` 断言

2. **把“不可交易”简化成“价格缺失”**  
   - 错误：仅用 NaN 判断停牌/退市  
   - 后果：忽略 symbol change / bankruptcy / pending M&A  
   - 预防：事件驱动 `UNTRADABLE` 状态机

3. **买单失败自动补买**  
   - 错误：用候补池补仓追满仓  
   - 后果：策略与原始信号不一致，回测偏乐观  
   - 预防：严格现金替代（D-08）

4. **卖单失败直接清零仓位**  
   - 错误：忽略真实不可卖出场景  
   - 后果：低估回撤、夸大流动性  
   - 预防：失败卖单保留仓位，恢复可交易后按周期重评（D-11/D-12）

5. **IC 生效日调仓错位**  
   - 错误：固定 T+1 不看 `effective_date`  
   - 后果：用到不稳定成分名单  
   - 预防：跨生效日执行顺延 T+2（D-15）

6. **fallback 成为隐性 alpha**  
   - 错误：默认 `close`/`ffill` 却不记录比例  
   - 后果：策略依赖不可解释成交假设  
   - 预防：默认 `next_open`，fallback 必须显式开关并统计命中率

## Code Examples

```python
from dataclasses import dataclass
from typing import Literal
import pandas as pd

FallbackMode = Literal["strict", "ffill", "close", "bfill"]

@dataclass(frozen=True)
class ExecConfig:
    fallback_mode: FallbackMode = "strict"
    min_adv20_usd: float = 1_000_000.0
    long_halt_days: int = 5

def resolve_execution_price(row_t1: pd.Series, mode: FallbackMode) -> float | None:
    px = row_t1.get("next_open")
    if pd.notna(px) and float(px) > 0:
        return float(px)
    if mode == "strict":
        return None
    if mode == "close":
        c = row_t1.get("close")
        return float(c) if pd.notna(c) and float(c) > 0 else None
    if mode == "ffill":
        f = row_t1.get("open_ffill")
        return float(f) if pd.notna(f) and float(f) > 0 else None
    if mode == "bfill":
        b = row_t1.get("open_bfill")
        return float(b) if pd.notna(b) and float(b) > 0 else None
    return None
```

```python
def apply_order_with_tradeability(intent, portfolio, market_row, state):
    # intent: {"symbol": "AAPL", "side": "buy"|"sell", "qty": ...}
    if state.is_untradable(intent["symbol"]):
        if intent["side"] == "buy":
            return {"status": "skipped_untradable_buy_cash_kept"}
        return {"status": "skipped_untradable_sell_hold_position"}

    px = resolve_execution_price(market_row, state.exec_cfg.fallback_mode)
    if px is None:
        if intent["side"] == "buy":
            return {"status": "skipped_invalid_open_cash_kept"}
        return {"status": "skipped_invalid_open_hold_position"}

    if intent["side"] == "buy":
        portfolio.buy(intent["symbol"], intent["qty"], px)
        return {"status": "filled_buy", "price": px}
    portfolio.sell(intent["symbol"], intent["qty"], px)
    return {"status": "filled_sell", "price": px}
```

```python
def adjust_exec_date(signal_date, next_session, ic_effective_dates):
    # D-15: 若原执行日为指数成分生效日，则顺延一个交易日（T+2）
    t1 = next_session(signal_date)
    if t1 in ic_effective_dates:
        return next_session(t1)
    return t1
```

## Test Case Matrix (Critical Gray Areas)

> 每个 case 均需：场景设置、fixture 形状、状态迁移、组合/现金影响、断言示例。  
> 推荐落地为 `backend_api_python/tests/test_backtest_correctness_phase21.py` + `tests/fixtures/phase21/*.csv|json`.

### Case 1: T-day close ranking vs T+1 execution isolation（无未来函数）
- **Scenario setup:** `2024-01-31` 产生排名，`2024-02-01` 执行；人为构造 `2024-01-31` close 极端变化，保证若同 bar 成交会得到不同净值。
- **Fixture data shape:**  
  - `prices.csv`: columns=`date,symbol,close,next_open`（3 symbols x 6 dates）  
  - `rankings.json`: `signal_date -> ordered_symbols`
- **Expected state transition:** `PLANNED@T` -> `EXECUTED@T+1`；无 `EXECUTED@T`
- **Expected portfolio/cash impact:** 使用 `T+1 next_open` 成交；与 `T close` 成交净值必须显著不同（用于防伪）
- **Assertion examples:**  
  - `assert exec_trade_date == signal_date + 1_session`  
  - `assert fill_price == fixture.next_open`  
  - `assert not any(fill.trade_date == fill.signal_date for fill in fills)`

### Case 2: `next_open` validity + fallback policy behavior
- **Scenario setup:** 某 symbol 在执行日 `next_open` 为 NaN 或 <=0；分别测试 `strict/ffill/close/bfill`
- **Fixture data shape:**  
  - `prices_with_invalid_open.csv`: 包含 `next_open, open_ffill, open_bfill, close`
- **Expected state transition:**  
  - `strict` -> `SKIPPED_INVALID_OPEN`  
  - `close/ffill/bfill` -> `FILLED_FALLBACK_<mode>`
- **Expected portfolio/cash impact:**  
  - strict: 买单现金不变，卖单持仓不变  
  - fallback: 按 fallback 价成交并记录 `fallback_count += 1`
- **Assertion examples:**  
  - `assert skipped_buy.cash_kept is True`  
  - `assert fill.metadata["price_source"] == "close"`  
  - `assert metrics["fallback_rate"] == expected_rate`

### Case 3: Untradable filters（delisting/long halt/symbol change/bankruptcy）
- **Scenario setup:** 四类事件各给一个 symbol，在执行日前标记 `UNTRADABLE`
- **Fixture data shape:**  
  - `corp_actions.json`: `symbol,event_type,effective_date`  
  - `halts.csv`: `symbol,start_date,duration_days`
- **Expected state transition:** `TRADABLE -> UNTRADABLE(reason=...)`
- **Expected portfolio/cash impact:**  
  - buy intent: 不成交，保留现金  
  - sell intent: 不成交，继续持仓
- **Assertion examples:**  
  - `assert state[symbol].status == "UNTRADABLE"`  
  - `assert execution.status in {"skipped_untradable_buy_cash_kept","skipped_untradable_sell_hold_position"}`

### Case 4: Cash substitution for failed buys
- **Scenario setup:** TopN 有 2 个买单失败（不可交易），其余成功；禁止候补替换
- **Fixture data shape:** `target_weights.json` + `execution_flags.csv`
- **Expected state transition:** 失败 buy -> `CASH_RESERVE`
- **Expected portfolio/cash impact:** 持仓数低于目标，`cash_weight` 上升，且无新增候补 symbol
- **Assertion examples:**  
  - `assert portfolio.holdings_count == target_count - failed_buys`  
  - `assert set(actual_new_symbols).issubset(set(target_symbols))`  
  - `assert "replacement_buy" not in execution_log_tags`

### Case 5: Hold behavior for failed sells + resume-on-tradable cycle
- **Scenario setup:** 某持仓在本次调仓应卖出，但执行日不可交易；两周期后恢复
- **Fixture data shape:** `tradability_timeline.csv`（按日标记 tradable/untradable）
- **Expected state transition:**  
  - Cycle A: `SELL_INTENT -> HELD_UNTRADABLE`  
  - Cycle B（恢复日）: 不做盘中强卖，仅回到排序池  
  - Cycle C: 若仍应卖，`T+1` 正常卖出
- **Expected portfolio/cash impact:**  
  - A: 仓位继续存在  
  - B: 无立即卖出现金流  
  - C: 正常入账卖出现金
- **Assertion examples:**  
  - `assert no_forced_intraday_exit_on_resume_day`  
  - `assert sell_fill_date == next_session(resume_signal_date)`  
  - `assert held_days >= expected_untradable_window`

### Case 6: Cash M&A forced exit exception
- **Scenario setup:** 持仓遇到现金并购生效日，尽管一般规则为 hold，但该场景必须强退
- **Fixture data shape:** `mna_cash_events.json`（包含 cash_consideration_price）
- **Expected state transition:** `UNTRADABLE -> FORCED_EXIT_CASH_MNA`
- **Expected portfolio/cash impact:** 按事件价或约定价入账现金，仓位清零
- **Assertion examples:**  
  - `assert execution.status == "forced_cash_exit"`  
  - `assert portfolio.position(symbol).qty == 0`  
  - `assert cash_delta == qty_before * forced_exit_price`

### Case 7: Rebalance calendar shift across IC effective_date（T+1 -> T+2）
- **Scenario setup:** `signal_date = E-1`，原定 `E` 执行，而 `E` 正好是 IC 生效日
- **Fixture data shape:**  
  - `ic_effective_dates.csv`  
  - `market_calendar.csv`（含节假日）
- **Expected state transition:** `PLANNED(exec=E) -> RESCHEDULED(exec=E+1_session)`
- **Expected portfolio/cash impact:** 全部订单在 `T+2` 价成交；`E` 无成交
- **Assertion examples:**  
  - `assert adjusted_exec_date == next_session(original_exec_date)`  
  - `assert trades_on_effective_date == 0`

## Verification Gate (Strict)

### Hard Pass/Fail Checklist
1. **No-lookahead gate（必须）**  
   - 任一成交若 `trade_date <= signal_date`，CI 失败。
2. **Survivorship gate（必须）**  
   - 历史退市 symbol 在其退市前行必须存在；若被 drop，CI 失败。
3. **Untradable semantics gate（必须）**  
   - 买失败必须现金留存；卖失败必须持仓保留。任一违反即失败。
4. **Calendar shift gate（必须）**  
   - 命中 IC 生效日场景必须发生 T+1->T+2 顺延，否则失败。
5. **Forced-exit exception gate（必须）**  
   - 现金并购场景若未强制平仓入账，失败。
6. **Determinism gate（必须）**  
   - 固定 fixture 连跑 2 次，交易日志哈希不一致则失败。
7. **Fallback observability gate（必须）**  
   - 若开启 fallback，必须输出 `fallback_count/rate`；缺指标则失败。

### Anti-Regression Requirements
- 新增或修改执行过滤器时，必须回放 7 个灰区 case 全量通过。
- 不允许只验证最终收益；必须校验执行日志状态序列（state transition trace）。
- 每次改动需跑：
  - `pytest tests/test_backtest_correctness_phase21.py -q`
  - `pytest tests/ -q`（全量，防止影响策略/runner 现有语义）

### Deterministic Fixture Requirements
- fixture 文件必须版本化并固定 checksum（建议在测试中校验）
- 禁止在测试时请求外部网络数据
- 交易日历 fixture 必含节假日与跨月边界
- 每个关键 case 至少 3 个 symbol（成功/失败/边界各 1）

### What Must Fail CI If Violated
- 同 bar 成交、未来函数痕迹
- 历史退市行缺失
- 买失败后出现候补替代买入
- 卖失败后仓位被直接清零
- 命中 cash M&A 却未强退
- IC 生效日未顺延
- 同 fixture 非确定性输出

## Deep Dive: Fallback Strategy

### Objective
- 默认语义必须保持“真实可成交优先”：`next_open` 无效即不成交（strict）。
- fallback 仅作为显式配置能力用于研究对比，禁止成为默认隐式成交假设。
- fallback 触发必须可观测（计数、比例、分 buy/sell 维度），并纳入 CI 门禁。

### Recommended Config Contract
```python
from dataclasses import dataclass
from typing import Literal

FallbackMode = Literal["strict", "ffill", "close", "bfill"]

@dataclass(frozen=True)
class FallbackConfig:
    mode: FallbackMode = "strict"
    enable_for_buy: bool = True
    enable_for_sell: bool = True
    max_fallback_rate: float = 0.05
```

### Prescriptive Implementation Rules
1. 使用单一入口 `resolve_execution_price()`，禁止在 runner 各处散落 fallback 分支。
2. 返回结构必须带 `price_source`（`next_open|ffill|close|bfill|none`）。
3. `strict` 模式下：
   - buy: `skipped_invalid_open_cash_kept`
   - sell: `skipped_invalid_open_hold_position`
4. fallback 命中后必须写 execution log + metrics：
   - `fallback_count_total`
   - `fallback_count_buy`
   - `fallback_count_sell`
   - `fallback_rate`

### CI/Verify Binding
- 若 `mode != strict` 且缺失 fallback 指标输出，CI fail。
- 若 `fallback_rate > max_fallback_rate`（可由环境覆盖）则 verify fail（防止策略依赖降级成交）。

## Deep Dive: UNTRADABLE State Machine

### Objective
- 将“不可交易”从价格缺失判断升级为事件驱动状态机。
- 明确状态迁移与执行行为，保证回测与实盘语义一致。

### State Definitions
- `TRADABLE`
- `UNTRADABLE(reason=<delisting|long_halt|symbol_change|bankruptcy|...>)`
- `FORCED_EXIT_CASH_MNA`（唯一强制退出例外）

### Transition Rules
1. `TRADABLE -> UNTRADABLE`：
   - 触发条件：退市/摘牌、长期停牌（>N，默认 5）、代码变更/换股、破产程序等。
2. `UNTRADABLE -> TRADABLE`：
   - 条件：事件解除且恢复可交易；恢复日不做盘中强卖。
3. `UNTRADABLE -> FORCED_EXIT_CASH_MNA`：
   - 条件：现金并购生效，按确定价格强退并入账现金。

### Execution Semantics (must hold)
- buy + `UNTRADABLE` => 跳过买入并留现金。
- sell + `UNTRADABLE` => 跳过卖出并保留仓位。
- 恢复交易后：回到完整调仓周期（T 日纳入排序，若触发卖出则 T+1 执行）。

### Suggested Interface
```python
class TradabilityStateStore:
    def mark_untradable(self, symbol: str, reason: str, asof): ...
    def mark_tradable(self, symbol: str, asof): ...
    def is_untradable(self, symbol: str, asof) -> bool: ...
    def reason(self, symbol: str, asof) -> str | None: ...
```

### Anti-Pattern to ban
- 用 `next_open is NaN` 直接等价 `UNTRADABLE`（会漏掉 symbol change / bankruptcy / pending M&A 等场景）。

## Deep Dive: Verify Gate Test Templates

### Recommended Test File Layout
- `tests/test_backtest_correctness_phase21.py`
  - `TestNoLookaheadGate`
  - `TestFallbackPolicy`
  - `TestUntradableStateMachine`
  - `TestCashSubstitution`
  - `TestSellHoldAndResumeCycle`
  - `TestCashMnaForcedExit`
  - `TestIcEffectiveDateShift`
  - `TestDeterminismGate`

### Recommended Fixture Layout
- `tests/fixtures/phase21/prices.csv`
- `tests/fixtures/phase21/prices_with_invalid_open.csv`
- `tests/fixtures/phase21/corp_actions.json`
- `tests/fixtures/phase21/halts.csv`
- `tests/fixtures/phase21/ic_effective_dates.csv`
- `tests/fixtures/phase21/market_calendar.csv`
- `tests/fixtures/phase21/target_weights.json`
- `tests/fixtures/phase21/tradability_timeline.csv`
- `tests/fixtures/phase21/mna_cash_events.json`

### Pytest Skeleton (prescriptive)
```python
def test_no_lookahead_gate(engine, fixture_case1):
    result = engine.run(fixture_case1)
    assert all(fill.trade_date > fill.signal_date for fill in result.fills)

def test_strict_fallback_skips_invalid_open(engine, fixture_case2):
    result = engine.run(fixture_case2, fallback_mode="strict")
    assert result.logs.has("skipped_invalid_open_cash_kept")
    assert result.metrics["fallback_count_total"] == 0

def test_untradable_sell_hold(engine, fixture_case5):
    result = engine.run(fixture_case5)
    assert result.logs.has("skipped_untradable_sell_hold_position")
    assert result.position_qty("XYZ", on="cycleA_end") > 0

def test_cash_mna_forced_exit(engine, fixture_case6):
    result = engine.run(fixture_case6)
    assert result.logs.has("forced_cash_exit")
    assert result.position_qty("ABC", on="event_day_end") == 0
```

### Gate-to-Test Mapping (must remain explicit)
- No-lookahead gate -> `TestNoLookaheadGate`
- Survivorship gate -> `TestUntradableStateMachine` + dedicated delisted-history assertions
- Buy/sell untradable semantics -> `TestCashSubstitution` + `TestSellHoldAndResumeCycle`
- Calendar shift gate -> `TestIcEffectiveDateShift`
- Cash M&A forced exit gate -> `TestCashMnaForcedExit`
- Determinism gate -> `TestDeterminismGate`（同 fixture 连跑两次对比 execution log hash）
- Fallback observability gate -> `TestFallbackPolicy`

## Sources

### Project-local (HIGH)
- `.planning/phases/21-backtest-correctness/21-CONTEXT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `backend_api_python/app/strategies/cross_sectional.py`
- `backend_api_python/app/strategies/cross_sectional_signals.py`
- `backend_api_python/app/strategies/runners/cross_sectional_runner.py`
- `backend_api_python/app/factors/panel.py`
- `scripts/cross_sectional/nq100_cross_sectional.py`

### Ecosystem references (MEDIUM-HIGH)
- Zipline/QuantRocket EOD rules:  
  https://www.quantrocket.com/codeload/zipline-intro/intro_zipline/Part2-End-of-Day-Trading-Rules.ipynb.html
- Backtrader order semantics & cheat-on-open:  
  https://www.backtrader.com/docu/order/  
  https://www.backtrader.com/docu/cerebro/cheat-on-open/cheat-on-open/
- QuantConnect market/MOO and stale fill discussion:  
  https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/market-orders  
  https://github.com/QuantConnect/Lean/issues/2762

## RESEARCH COMPLETE

Phase 21 研究结论：以“信号-执行隔离 + 严格可交易过滤 + 明确异常路由 + 可复现 fixture”作为唯一默认主路径；不再接受简化回测成交假设。灰区场景已转化为 7 条强制测试矩阵，并配套 CI hard gates，可直接支撑后续 plan/execution phase。
