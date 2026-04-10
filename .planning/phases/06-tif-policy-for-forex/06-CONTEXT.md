# Phase 6: TIF policy for Forex - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

`_get_tif_for_signal` 增加 Forex 专属分支，所有 Forex 信号统一返回 IOC。美股/港股逻辑不变。

**Requirement:** EXEC-03

**Depends on:** Phase 5 (Forex signal mapping with `market_category`).

</domain>

<decisions>
## Implementation Decisions

### Forex TIF 策略（用户确认：全 IOC）

- **所有 Forex 信号统一使用 `"IOC"`**（Immediate-Or-Cancel）。
- 不区分 open/close/add/reduce — Forex 是 24/5 市场，无盘前/盘后概念，IOC 对所有信号语义一致。
- 理由：自动交易系统不应有意外挂单；IOC 确保能成交就成交，不能成交的部分立即取消。
- 实现方式：在 `_get_tif_for_signal` 中，当 `market_type == "Forex"` 时直接返回 `"IOC"`，无需判断 `signal_type`。

### 非 Forex 逻辑（不变）

- **美股（USStock）**：open → DAY, close → IOC — **不改**。
- **港股（HShare）**：open → DAY, close → DAY — **不改**。
- Phase 6 范围严格限于 Forex 分支的添加。

### 错误处理（不加 fallback）

- 如果 IBKR 拒绝 IOC 订单，走现有 `_handle_reject` 流程（标记失败、通知、不自动重试）。
- 不增加 TIF fallback 机制（如 IOC 失败后自动改 DAY 重试）。
- 理由：Forex 市价单 + IOC 在正常流动性下几乎不会被拒；自动重试增加复杂性和风险。

### `_get_tif_for_signal` 签名

- **保持现有签名不变**：`_get_tif_for_signal(signal_type: str, market_type: str = "USStock") -> str`。
- `market_type` 参数已有，调用方（`place_market_order`、`place_limit_order`）已传入 `market_type`。
- 只需在方法体内新增 Forex 判断分支。

### Claude's Discretion

- Forex 分支的具体代码位置（方法顶部 early return 还是 elif）。
- 测试类命名（扩展 `TestTifDay` 还是新建 `TestTifForex`）。
- 是否为 `_get_tif_for_signal` 的 Forex 分支写参数化测试或独立测试方法。

</decisions>

<specifics>
## Specific Ideas

### 建议用例规格（供 06-01-PLAN 引用）

- **UC-T1:** `_get_tif_for_signal("open_long", "Forex")` → `"IOC"`
- **UC-T2:** `_get_tif_for_signal("close_long", "Forex")` → `"IOC"`
- **UC-T3:** `_get_tif_for_signal("open_short", "Forex")` → `"IOC"`
- **UC-T4:** `_get_tif_for_signal("close_short", "Forex")` → `"IOC"`
- **UC-T5:** `_get_tif_for_signal("add_long", "Forex")` → `"IOC"`
- **UC-T6:** `_get_tif_for_signal("add_short", "Forex")` → `"IOC"`
- **UC-T7:** `_get_tif_for_signal("reduce_long", "Forex")` → `"IOC"`
- **UC-T8:** `_get_tif_for_signal("reduce_short", "Forex")` → `"IOC"`
- **UC-E1:** `_get_tif_for_signal("open_long", "USStock")` → `"DAY"`（回归，不变）
- **UC-E2:** `_get_tif_for_signal("close_long", "USStock")` → `"IOC"`（回归，不变）
- **UC-E3:** `_get_tif_for_signal("close_long", "HShare")` → `"DAY"`（回归，不变）
- **REGR-01:** `cd backend_api_python && python -m pytest tests/ -x -q --tb=line` 全绿

### 实施约束（延续项目惯例）

- 每个 task 需有**明确用例与规格**；**全量 `pytest tests/`** 作为每个 task 的 verify 组成部分（无 `| head` / `| tail` 管道，使用 `--tb=line`）。

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 核心实现
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_get_tif_for_signal`（约 134–147 行）、`place_market_order` 调用 TIF（约 1069 行）、`place_limit_order` 调用 TIF（约 1139 行）

### 测试
- `backend_api_python/tests/test_ibkr_client.py` — `TestTifDay`（约 646–665 行）：现有 TIF 测试

### 项目文档
- `.planning/REQUIREMENTS.md` — **EXEC-03**
- `.planning/ROADMAP.md` — Phase 6 成功标准

### 先前 Phase
- `.planning/phases/05-signal-to-side-mapping-two-way-fx/05-CONTEXT.md` — `map_signal_to_side` + `market_category` 已实现

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`_get_tif_for_signal`**：已有 `market_type` 参数，只需增加 Forex 分支。
- **`TestTifDay`**：已有 TIF 测试基础设施（mock IB client + 检查 placed_order.tif）。

### Established Patterns
- **静态方法**：`_get_tif_for_signal` 是 `@staticmethod`，不依赖实例状态。
- **调用方**：`place_market_order` 和 `place_limit_order` 都调用 `_get_tif_for_signal(signal_type, market_type)` 获取 TIF。
- **现有逻辑**：`is_close` 判断 → HShare 特殊处理 → 默认 IOC/DAY。

### Integration Points
- **`place_market_order`（~1069 行）**：`tif = self._get_tif_for_signal(signal_type, market_type)` — 无需改此行，只改 `_get_tif_for_signal` 方法体。
- **`place_limit_order`（~1139 行）**：同上。

</code_context>

<deferred>
## Deferred Ideas

- **美股/港股 open 信号也改为 IOC**：用户确认后续要做，对自动交易更安全。记为 pending 任务，加入后续 phase 或独立 task。
- **TIF fallback 机制**（IOC 被拒后自动改 DAY 重试）：当前不需要，若实际运行中发现 IOC 被拒频率高再考虑。

</deferred>

---

*Phase: 06-tif-policy-for-forex*
*Context gathered: 2026-04-10*
