# Phase 14: TIF unification (USStock/HShare) - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Align USStock open-signal TIF policy with Forex (IOC). Handle HShare exceptions based on research findings. Create exhaustive TIF matrix test covering all signal × market combinations to prevent future drift. No new order types, no TIF fallback mechanism — those belong in later phases or v2.

</domain>

<decisions>
## Implementation Decisions

### USStock open 信号 TIF 策略
- USStock open 信号从 DAY 改为 **IOC** — 与 Forex 完全对齐
- USStock close 信号保持 **IOC** — 现有行为不变
- 静默切换，无需用户操作、无功能开关、无 warning 日志
- 所有已有策略自动使用新 TIF 策略

### HShare 例外处理
- **由 researcher 调查决定** — 当前代码注释声称"港股不支持 IOC"，但来源不确定，需要 research 阶段验证 SEHK 对 IOC 的实际支持情况
- 如果 research 确认 HShare 支持 IOC → open/close 都改为 IOC
- 如果 research 确认 HShare 不支持 IOC → 保持 DAY，代码注释说明原因（引用具体来源）
- 如果不确定 → 保守策略保持 DAY
- 无论哪种结果，都需要在代码和测试中明确记录 HShare 的 TIF 策略及其依据

### TIF 矩阵测试
- 覆盖全部 **8 个信号类型** × **3 个市场**（Forex / USStock / HShare）= 24 种组合
- 组织方式：单个 `TestTifMatrix` 类，使用 `pytest.mark.parametrize` 穷举所有组合
- 每个组合明确断言预期的 TIF 值
- 漂移防护：穷举矩阵测试，任何 TIF 变化都会被自动测试捕获
- 现有的分散 TIF 测试（`TestTifForexPolicy`、`TestTifDay` 等）可以保留或由 Claude 决定是否合并

### Claude's Discretion
- HShare TIF 最终策略（基于 research 结果）
- 现有分散 TIF 测试是否合并到 `TestTifMatrix` 或保留
- `_get_tif_for_signal` 方法的具体重构方式（如需要）
- 是否为未知 market_type 添加 defensive raise

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### TIF 策略逻辑
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `_get_tif_for_signal` 静态方法（第 165 行），当前 TIF 决策点；`place_market_order` 和 `place_limit_order` 中 `tif` 参数的使用
- `backend_api_python/tests/test_ibkr_client.py` — `TestTifForexPolicy`（Forex IOC 全信号 + USStock/HShare 回归）、`TestTifDay`（USStock DAY 测试）、`TestPlaceMarketOrderForex`（含 tif 断言）

### HShare 支持
- IBKR 官方 SEHK 订单类型文档（researcher 需查阅）— 确认港交所对 IOC 的支持情况

### 项目约束
- `.planning/REQUIREMENTS.md` — INFRA-02（USStock open → IOC，HShare 例外记录，TIF 矩阵测试）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_get_tif_for_signal(signal_type, market_type)` — 唯一 TIF 决策点，所有下单路径通过此方法获取 TIF
- `TestTifForexPolicy` — 已有 Forex 8 信号 parametrize 测试，可作为矩阵扩展的基础
- `TestTifDay` — 已有 USStock DAY 测试（market + limit order），改后应该断言 IOC

### Established Patterns
- IBKRClient 使用 `@staticmethod` 实现 `_get_tif_for_signal` — 纯策略方法，易于单元测试
- 测试使用 `@pytest.mark.parametrize` 覆盖多信号类型
- `place_market_order` / `place_limit_order` 都在调用 `_get_tif_for_signal` 后直接传入 `tif=tif`

### Integration Points
- `_get_tif_for_signal` 是唯一需要修改的生产代码（改 USStock open 的返回值）
- 测试文件 `test_ibkr_client.py` 中多个测试类需要更新断言（DAY → IOC）
- Phase 17（限价单）会依赖本 phase 的 TIF 策略，需确保矩阵测试覆盖 limit order 路径

</code_context>

<specifics>
## Specific Ideas

- 当前代码注释 `"HShare" uses "DAY" (Hong Kong stocks do not support IOC orders)` 的来源不确定 — researcher 必须查证 SEHK 对 IOC 的实际支持情况
- Phase 6 验证了 Forex IOC（Paper 验证 DUQ123679），但 USStock/HShare 没有做 paper 验证
- 矩阵测试应覆盖 `_get_tif_for_signal` 的直接返回值，不需要通过 `place_market_order` 间接测试（间接测试已有）

</specifics>

<deferred>
## Deferred Ideas

- **TIF fallback (IOC→DAY)** — ADV-01，v2 需求。如果 IOC 被 IBKR 拒绝，自动用 DAY 重试。本 phase 不实现。
- **HShare paper 验证** — 如果 research 无法确认 SEHK IOC 支持，后续可通过 paper 账号实际验证

</deferred>

---

*Phase: 14-tif-unification-usstock-hshare*
*Context gathered: 2026-04-11*
