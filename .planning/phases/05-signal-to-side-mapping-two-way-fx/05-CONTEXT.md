# Phase 5: Signal-to-side mapping (two-way FX) - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Strategy signal semantics for Forex map to correct IB BUY/SELL including short-style flows, **与 MT5 的 `_SIGNAL_MAP` 对齐**：除四条主信号外，Forex 路径亦支持 `add_long` / `close_long` / `reduce_long`（已有 long 侧）及 **`add_short` / `reduce_short`**。`open_long` → BUY, `close_long` → SELL, `open_short` → SELL, `close_short` → BUY（及 add/reduce 与 MT5 相同）。Forex 不再仅因股票式 “short 禁止” 而失败。表驱动测试覆盖 **`market_category=Forex`** 下的上述信号（至少与 MT5 表一致的全集）。

**Requirement:** EXEC-02

**Depends on:** Phase 4 (Forex in `supported_market_categories`).

</domain>

<decisions>
## Implementation Decisions

### API 与调用链 — **如何传入 `market_category`（方案说明与锁定）**

Quiz 选项若未落库会被误当作「默认」；**本轮用户书面确认**如下。

**为何必须显式区分品类：**  
`open_short` / `add_short` 等信号在 **Forex** 下应映射为 `sell`；在 **USStock/HShare** 下应拒绝。仅靠 `signal_type` 无法区分，**必须从调用链传入品类**（或等价信息）。

| 方案 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| **A（锁定采用）** | 扩展 `BaseStatefulClient.map_signal_to_side(self, signal_type: str, *, market_category: str = "")`；`StatefulClientRunner.execute` 传 `market_category=ctx.market_category or ""`。各子类统一加参；**非 IBKR 忽略**。 | 与 `OrderContext` 字段一致；单一点 truth；默认 `""` 不破坏旧单参调用。 | 需改所有 `BaseStatefulClient` 子类签名（机械但集中）。 |
| **B** | 仅 `IBKRClient` 加可选参数；runner 里 `isinstance` 或 try 两套调用。 | 改动表面最小。 | 破坏抽象一致性；runner 耦合具体 client；后续 EF/其它若也要品类会再炸。 |
| **C** | 不扩签名，只把 `ctx.market_type` 或拼接信息塞进 `signal_type`。 | 无签名变更。 | 脏、难测、与现有 `signal_type` 语义冲突，**不推荐**。 |

**锁定：** 采用 **方案 A**。

- **`StatefulClientRunner.execute`**：`client.map_signal_to_side(ctx.signal_type, market_category=(ctx.market_category or "").strip())`。
- **子类**：`MT5Client` / `EFClient` / `USmartClient` 等接收 `market_category=""` 并保持与当前行为完全一致。
- **向后兼容**：`market_category` 缺省为 `""` 时，IBKR 对 **非 Forex** 的 short 仍拒绝（见下条「错误文案」）。

### 信号集合范围 — **与 MT5 表对齐（用户确认）**

- **IBKR + `market_category=="Forex"`** 时，**`map_signal_to_side` 的合法信号集合与 `MT5Client._SIGNAL_MAP` 完全一致**（八项）：

| signal_type | side |
|-------------|------|
| open_long | buy |
| add_long | buy |
| close_long | sell |
| reduce_long | sell |
| open_short | sell |
| add_short | sell |
| close_short | buy |
| reduce_short | buy |

- **EXEC-02** 中明示的四条包含在上述表中；**add_short / reduce_short** 纳入本 phase，不再 Deferred。

### 非 Forex（USStock / HShare）— **错误文案与测试（用户确认）**

- 当 **`market_category` 为空或非 `"Forex"`** 且 `signal_type`（规范化后）属于 **short 侧**（命中与 MT5 相同的 short 信号名：`open_short`, `add_short`, `close_short`, `reduce_short` 等 — 实现上与当前 **`"short" in sig`** 子串判断对齐或改为**白名单 short 名**以避免误判，由实现选更稳者，但**语义**必须为：仅 Forex 允许 short 信号）时：**抛出 `ValueError`**。
- **文案（锁定意图，正文可微调用词但需满足 grep/测例）**：须**明确写出**美股/港股品类不支持该类信号，例如：  
  `"IBKR USStock and HShare do not support short-side signals; use market_category=Forex for FX."`  
  （中文需求等价为：**指明仅股票品类不支持 short 信号、Forex 另走映射**。）
- **测试**：`test_exchange_engine.py`（及任何 assert `"short"` in msg 的用例）**同步更新** `pytest.raises(..., match=...)` 或等价断言，以匹配新文案；**Forex + short 信号** 的新表驱动测例断言**不**抛该类错误且 side 与 MT5 一致。

### Forex 路径逻辑顺序（锁定）

1. 规范化 `signal_type`（strip + lower）。  
2. 若 `market_category == "Forex"`：**不得**先做全局 `"short" in sig` 拒绝；按 **MT5 同款表** 查侧；未知键 → `Unsupported signal_type`。  
3. 否则（非 Forex）：若为 short 侧信号 → **上文 ValueError（新文案）**；否则走 **现有 IBKR 仅 long** `_SIGNAL_MAP`（open_long / add_long / close_long / reduce_long）。

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

- **UC-F1..F4（主四条）：** `open_long`→buy, `close_long`→sell, `open_short`→sell, `close_short`→buy，均 `market_category="Forex"`。
- **UC-F5..F8（与 MT5 对齐的补充）：** `add_long`→buy, `reduce_long`→sell, `add_short`→sell, `reduce_short`→buy，均 `market_category="Forex"`。
- **UC-E1（非 Forex short）：** `map_signal_to_side("open_short")`（不传或 `market_category=""`）→ `ValueError`，消息匹配**新文案**（须含 USStock/HShare 或等价明确股票品类语义，见上文 `Implementation Decisions`）。
- **UC-E2:** `map_signal_to_side("close_long")` 无 kwarg → `"sell"`（回归）。
- **REGR-01:** `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` 全绿。

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
- **`MT5Client._SIGNAL_MAP`（八键）**：作为 IBKR **`market_category="Forex"`** 路径的**逐项对齐参考**（复制语义，不复制 MT5 依赖）。
- **`OrderContext.market_category`**：由 `StatefulClientRunner` 传入 `map_signal_to_side`，无需新增 payload 字段。

### Established Patterns
- **IBKR 股票**：仅 long 侧信号合法；`"short" in sig` 为硬拦。
- **Runner 错误包装**：`ValueError` → `ExecutionResult(success=False, error=f"{eid}_unsupported_signal:...")`（`stateful_runner.py`）。

### Integration Points
- **`base.py`**：`@abstractmethod map_signal_to_side` 签名变更 → 所有子类必须更新。
- **`stateful_runner.py`**：单行调用改为传 `market_category`。
- **测试**：表驱动覆盖 Forex 八信号 + 非 Forex short 新文案 + 原有 long 回归；同步改 `match=` / 断言字符串。

</code_context>

<deferred>
## Deferred Ideas

- **EF / USmart 等 REST 引擎是否也要读 `market_category` 做细分**：当前 Phase 仅要求 IBKR + Runner；若未来统一「品类感知」再扩。

</deferred>

---

*Phase: 05-signal-to-side-mapping-two-way-fx*
*Context gathered: 2026-04-10*
