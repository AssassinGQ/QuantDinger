# Phase 1: IBKR Data Source Implementation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-08
**Phase:** 01-ibkr-data-source-implementation
**Mode:** discuss
**Areas discussed:** 数据源选择, 连接管理, 市场关系

---

## 数据源选择

| Option | Description | Selected |
|--------|-------------|----------|
| 扩展 get_source() 方法 | 在 DataSourceFactory 中添加 exchange_id 参数，根据 'ibkr-live' 字符串直接创建 IBKRDataSource | ✓ |
| 基于 market + exchange_id 元数据 | 保持 market 参数不变，添加 exchange_id 到数据源实例的元数据 | |
| 新增方法而非修改现有方法 | 新增 get_source_by_exchange() 方法，与原有 get_source() 并存 | |

**User's choice:** 扩展 get_source() 方法
**Notes:** 保持现有调用方式兼容

---

## 方法签名

| Option | Description | Selected |
|--------|-------------|----------|
| 添加可选 exchange_id 参数 | get_source(market: str, exchange_id: str = None) — 可选参数兼容现有调用 | ✓ |
| 自动检测类型 | get_source(market_or_exchange: str) — 自动判断类型 | |
| 两个必填参数 | get_source(market: str, exchange_id: str) — 必须传两个参数 | |

**User's choice:** 添加可选 exchange_id 参数

---

## 连接管理

| Option | Description | Selected |
|--------|-------------|----------|
| 复用 IBKRClient 实例 | 复用现有 IBKRClient 实例，减少连接开销，适合多策略使用同一数据源 | ✓ |
| 每次创建新连接 | 每次调用时创建新连接，简化代码但连接开销大 | |
| 可配置的连接模式 | 根据配置决定，可以切换连接模式 | |

**User's choice:** 复用 IBKRClient 实例

---

## 市场关系

| Option | Description | Selected |
|--------|-------------|----------|
| 独立数据源 | IBKRDataSource 是独立的数据源，不属于任何 market 类型 | ✓ |
| USStock 的子类型 | IBKRDataSource 作为 USStock 的一个实现变体 | |
| 自动推断市场类型 | 根据交易标的自动推断市场类型（股票/外汇） | |

**User's choice:** 独立数据源

---

## Claude's Discretion

- IBKR Gateway 连接参数的具体配置方式
- 数据重试和错误处理的具体实现细节
- K线数据格式的微调

---

## Deferred Ideas

- 港股数据支持 — Phase 2
- 外汇数据支持 — Phase 2
