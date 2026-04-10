# Phase 5: Signal-to-side mapping (two-way FX) - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Strategy signal semantics for Forex map to correct IB BUY/SELL including short-style flows. `open_long` → BUY, `close_long` → SELL, `open_short` → SELL, `close_short` → BUY for Forex (per project conventions). Forex no longer fails purely because “short” is disallowed as on single-stock equity assumptions. Table-driven tests cover all four signal types for `market_category=Forex`.

**Requirement:** EXEC-02

**Depends on:** Phase 4 (Forex in `supported_market_categories`).

</domain>

<decisions>
## Implementation Decisions

### API 与调用链（用户选择讨论项后未填问卷 — 采用默认方案）

- **扩展 `BaseStatefulClient.map_signal_to_side` 签名**：增加仅关键字参数 **`*, market_category: str = ""`**，返回类型仍为 `str`。
- **语义**：`market_category` 表示策略/订单上下文的品类（如 `"Forex"`、`"USStock"`），与 `OrderContext.market_category` 对齐。
- **`StatefulClientRunner.execute`**：将  
  `client.map_signal_to_side(ctx.signal_type)`  
  改为  
  `client.map_signal_to_side(ctx.signal_type, market_category=ctx.market_category or "")`  
  （或等价地传入 `ctx.market_category` 经 strip 后的字符串）。
- **所有 `BaseStatefulClient` 子类**（`IBKRClient`、`MT5Client`、`EFClient`、`USmartClient` 等）在 Phase 5 **同步更新方法签名**；非 IBKR 实现 **忽略** `market_category`（保持与当前仅 `signal_type` 时完全一致的行为）。
- **向后兼容**：默认 `market_category=""` 时，**现有单参调用与单测行为不变**（IBKR 仍对含 `"short"` 的信号抛 `ValueError`，除非后续显式传入 `market_category="Forex"`）。

### 信号集合范围（讨论项默认）

- **本阶段仅实现 EXEC-02 列出的四条**：`open_long`、`close_long`、`open_short`、`close_short`。
- **`add_short` / `reduce_short`（及 IBKR 上其它 short 变体）**：**不在 Phase 5 强制范围**；若策略后续需要，记入 **Deferred**（可与 MT5 的 `_SIGNAL_MAP` 对齐时再开子任务或后续 phase）。

### Forex 映射表（锁定，与 REQUIREMENTS / MT5 一致）

| signal_type   | side (return) |
|---------------|----------------|
| open_long     | buy            |
| close_long    | sell           |
| open_short    | sell           |
| close_short   | buy            |

- 大小写：与现有一致，对 `signal_type` 做 `strip().lower()` 再查表。

### 非 Forex / 股票逻辑（错误信息与兼容性）

- **`market_category != "Forex"`（含空字符串）时**：保留现有逻辑 — 若 `signal_type` 中含子串 **`"short"`**，仍 **`raise ValueError`**（与当前 `IBKRClient` 行为一致），**不强制修改**错误文案（避免大范围改 `test_exchange_engine.TestIBKRSignalMapping` 的 `match=`）。
- **`market_category == "Forex"` 时**：**不得**因含 `"short"` 而提前抛错；仅在映射表缺失时 `raise ValueError(... Unsupported signal_type ...)`。

### Claude's Discretion

- `_SIGNAL_MAP` 拆成「仅 long」+ Forex 分支内联 dict，还是维护「Forex 专用小表」合并查找 — 由实现者选可读性最优写法。
- 表驱动测试放在 `test_exchange_engine.py` 扩展 `TestIBKRSignalMapping` 还是新建 `TestIBKRSignalMappingForex` 类。
- Phase 5 计划中 **用例编号（UC-x）与 REGR-01** 的具体命名由 planner 与用户对齐惯例（与 Phase 3/4 一致）。

</decisions>

<specifics>
## Specific Ideas

### 实施约束（延续项目惯例）

- 每个 task 需有**明确用例与规格**；**全量 `pytest tests/`** 作为每个 task 的 verify 组成部分（无 `| head` / `| tail` 管道，使用 `--tb=line`）。

### 建议用例规格（供 05-01-PLAN 引用）

- **UC-F1:** `map_signal_to_side("open_long", market_category="Forex")` → `"buy"`
- **UC-F2:** `map_signal_to_side("close_long", market_category="Forex")` → `"sell"`
- **UC-F3:** `map_signal_to_side("open_short", market_category="Forex")` → `"sell"`
- **UC-F4:** `map_signal_to_side("close_short", market_category="Forex")` → `"buy"`
- **UC-E1:** `map_signal_to_side("open_short")`（无 kwarg 或 `market_category=""`）仍 `ValueError`，且信息仍含 `short`（与现有 `test_short_rejected` 兼容）
- **UC-E2:** `map_signal_to_side("close_long")` 无 kwarg → `"sell"`（回归）
- **REGR-01:** `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` 全绿

（Runner 级集成：若计划要求，可增加 **UC-R1**：mock `StatefulClientRunner.execute` 对 `market_category=Forex` + `open_short` 得到 `action=="sell"` — 可选，视 plan 粒度。）

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 核心实现
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_SIGNAL_MAP`（约 113–118 行）、`map_signal_to_side`（约 161–168 行）、`"short"` 拒绝分支
- `backend_api_python/app/services/live_trading/runners/stateful_runner.py` — `execute` 内 `map_signal_to_side` 调用（约 59–62 行）
- `backend_api_python/app/services/live_trading/base.py` — `OrderContext`（`market_category` 字段）、`BaseStatefulClient.map_signal_to_side` 抽象定义（约 200–202 行）

### 参考实现（Forex 双向已存在）
- `backend_api_python/app/services/live_trading/mt5_trading/client.py` — `MT5Client.map_signal_to_side` 与完整 `_SIGNAL_MAP` 形态

### 测试
- `backend_api_python/tests/test_exchange_engine.py` — `TestIBKRSignalMapping`、`TestMT5SignalMapping`

### 项目文档
- `.planning/REQUIREMENTS.md` — **EXEC-02**
- `.planning/ROADMAP.md` — Phase 5 成功标准

### 先前 Phase
- `.planning/phases/04-market-category-worker-gate/04-CONTEXT.md` — `supported_market_categories` 含 `Forex`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **MT5 `_SIGNAL_MAP`**：已包含 `open_short` / `close_short` / `add_short` / `reduce_short` 等，可作为 Forex 四条映射的**语义参考**（本 phase 仅摘四条进 IBKR Forex 分支）。
- **`OrderContext.market_category`**：runner 已具备传入 `map_signal_to_side` 所需上下文，无需新增 payload 字段。

### Established Patterns
- **IBKR 股票**：仅 long 侧信号合法；`"short" in sig` 为硬拦。
- **Runner 错误包装**：`ValueError` → `ExecutionResult(success=False, error=f"{eid}_unsupported_signal:...")`（`stateful_runner.py`）。

### Integration Points
- **`base.py`**：`@abstractmethod map_signal_to_side` 签名变更 → 所有子类必须更新。
- **`stateful_runner.py`**：单行调用改为传 `market_category`。
- **测试**：在传入 `market_category="Forex"` 的新用例中验证四条映射；保留不传 kwarg 的现有 `TestIBKRSignalMapping` 用例以锁回归。

</code_context>

<deferred>
## Deferred Ideas

- **IBKR + Forex 的 `add_short` / `reduce_short`（及 reduce 系列与 MT5 完全对齐）**：本 phase 不承诺；若产品需要与 MT5 策略信号 1:1，可在 Phase 5 完成后单独立项。
- **优化非 Forex 的 short 拒绝文案**（例如标明「仅股票品类」）：当前不修改，避免无谓测试 churn；可记入后续 polish。

</deferred>

---

*Phase: 05-signal-to-side-mapping-two-way-fx*
*Context gathered: 2026-04-10*
