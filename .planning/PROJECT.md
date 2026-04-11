# QuantDinger IBKR Forex 交易支持

## What This Is

为 QuantDinger 的 IBKR 交易客户端新增 Forex（外汇）交易能力。当前 IBKRClient 仅支持美股（USStock）和港股（HShare），本项目扩展其支持所有 IBKR IDEALPRO 上的外汇货币对，使策略系统可以自动执行外汇交易信号。

## Core Value

策略系统发出的 Forex 交易信号能正确通过 IBKRClient 在 IDEALPRO 上执行，从信号到成交的完整链路畅通。

## Requirements

### Validated

- ✓ IBKRClient 支持美股（USStock）下单 — existing
- ✓ IBKRClient 支持港股（HShare）下单 — existing
- ✓ ib_insync 连接管理（自动重连、paper/live 单例） — existing
- ✓ 事件驱动的成交/仓位/PnL 追踪 — existing
- ✓ PendingOrderWorker 完整的下单流程（信号→pending→执行→成交） — existing
- ✓ ForexNormalizer 数量透传（raw_qty passthrough） — Validated in Phase 8: normalize passthrough + UC-N1–UC-N6
- ✓ _align_qty_to_contract 从 IBKR ContractDetails 获取 sizeIncrement 对齐 — Validated in Phase 8: UC-A1–UC-A5 alignment tests
- ✓ RTH 检查基于 IBKR 合约交易时间 — existing
- ✓ StatefulClientRunner 统一调度 IBKR 下单 — existing

### Active

- ✓ IBKRClient 支持 Forex 市价单下单 — Validated in Phase 7: Forex market orders (integration tests UC-M1–M3, UC-E1–E3, UC-R1–R2; qty=0 IDEALPRO hint)
- ✓ Forex 合约创建（ib_insync.Forex，IDEALPRO 交易所） — Validated in Phase 2: Forex contract creation
- ✓ symbol 解析支持外汇对格式（如 EUR.USD, EURUSD） — Validated in Phase 1: Forex symbol normalization
- ✓ Forex 合约 qualify 验证（conId、localSymbol、secType 防御性检查） — Validated in Phase 3: Contract qualification
- ✓ IBKRClient.supported_market_categories 包含 "Forex" — Validated in Phase 4: Market category & worker gate
- ✓ map_signal_to_side 支持 Forex 双向交易信号（八信号映射，与 MT5 对齐） — Validated in Phase 5: Signal-to-side mapping (two-way FX)
- ✓ Forex TIF 策略：所有信号统一使用 IOC — Validated in Phase 6: TIF policy for Forex (paper trading verified on DUQ123679)
- ✓ Forex RTH 使用 IBKR 合约交易时间（liquidHours 24/5） — Validated in Phase 9: UC-FX-L01–L09 + UC-FX-I01–I05; Forex 关市消息含 24/5 提示
- ✓ Lot size 两层机制（ForexNormalizer passthrough + _align_qty_to_contract IB对齐） — Validated in Phase 8
- [ ] 策略系统可配置 market_category=Forex 执行自动交易
- [ ] 前端策略创建/编辑时 Forex 可选 ibkr-paper/ibkr-live 交易所

### Out of Scope

- 限价单 — 当前只需市价单，与需求一致
- 新建 Forex 专用策略类型 — 复用现有策略框架
- ForexNormalizer 最小下单量检查 — 依赖 IBKR 拒单和 _align_qty 兜底
- MT5 Forex 相关改动 — MT5 已有独立 Forex 实现，不受影响

## Context

- IBKRClient 当前 `_create_contract` 仅创建 `ib_insync.Stock`，需要根据 market_type 分支创建 `ib_insync.Forex`
- `normalize_symbol` 当前仅处理 USStock 和 HShare，需要新增 Forex 解析逻辑
- `supported_market_categories` 当前为 `{"USStock", "HShare"}`，需要加入 `"Forex"`
- IBKR IDEALPRO Forex 以基础货币单位下单（如 25000 EUR），不是标准手
- `ForexNormalizer.normalize` 透传原始数量（Phase 8 改为 passthrough），`_align_qty_to_contract` 负责 IB sizeIncrement 对齐
- ib_insync.Forex 合约构造：`Forex(pair='EURUSD')` 或 `Forex(symbol='EUR', currency='USD', exchange='IDEALPRO')`
- TIF 已确认：Forex 所有信号统一使用 IOC（Phase 6 决策，paper trading 验证通过）

## Constraints

- **Tech stack**: 必须使用 ib_insync 库，与现有 IBKR 集成一致
- **兼容性**: 不能影响现有 USStock 和 HShare 交易路径
- **架构**: 遵循现有 BaseStatefulClient / StatefulClientRunner 模式

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Forex TIF = IOC | IDEALPRO 市价单需要 IOC（避免 DAY 挂单残留），paper trading 验证通过 | ✓ Decided (Phase 6) |
| 市价单优先 | 外汇流动性好，市价单滑点可控，简化实现 | ✓ Decided (Phase 7) |
| Forex qty=0 after alignment 提示 IDEALPRO 最小量 | 用户可读性优化，区分 Forex 与股票的 qty=0 原因 | ✓ Decided (Phase 7) |
| ForexNormalizer passthrough + IB 对齐 | normalize 透传原始数量，_align_qty_to_contract 负责 sizeIncrement 对齐 | ✓ Decided (Phase 8) |
| RTH 复用 IBKR 合约时间 | 与股票路径一致，IBKR 返回的 liquidHours 能正确反映 Forex 24/5 特性 | ✓ Decided (Phase 9) |

---
*Last updated: 2026-04-11 — Phase 9 complete: Forex trading hours (liquidHours) — UC-FX-L01–L09 + UC-FX-I01–I05, Forex 24/5 关市提示*
