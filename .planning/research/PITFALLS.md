# PITFALLS - IBKR Data Source

**Analysis Date:** 2026-04-08

## 常见错误和陷阱

### 1. IBKR Gateway 未运行

**问题:** 连接 IBKR Gateway 失败
**警告 signs:** `ConnectionRefusedError`, `TimeoutError`
**Prevention:** 
- 检查 Gateway 进程运行
- 配置正确的 host/port
- 添加连接超时和重试

### 2. 异步事件循环阻塞

**问题:** ib_insync 的 asyncio 阻塞主线程
**Warning signs:** `RuntimeError: Event loop is running`
**Prevention:**
- 使用独立线程运行 asyncio (参考 ibkr_datafetcher)
- 不要在 Flask 路由中直接调用 async 代码

### 3. 市场代码格式

**问题:** IBKR 的股票代码与普通代码不同
**Examples:**
- AAPL (普通) → IBKR: `STK`, `AAPL`, `USD` (需要 secType, symbol, currency)
- 港股: `HK/00700` 格式
**Prevention:** 创建 symbol 转换函数

### 4. 数据获取限制

**问题:** IBKR API 请求频率限制
**Warning signs:** `Historical data request returned no data`
**Prevention:**
- 添加请求间隔
- 缓存短时间数据

### 5. 连接超时

**问题:** Gateway 响应慢
**Prevention:**
- 设置 RequestTimeout
- 添加连接超时

### 6. 线程安全

**问题:** IB 实例非线程安全
**Prevention:**
- 使用锁保护
- 或每线程独立实例

---

## Phase 映射

| Phase | 任务 |
|-------|------|
| Phase 1 | 基本 IBKRDataSource 实现 |
| Phase 1 | 集成到 DataSourceFactory |
| Phase 2 | 添加港股/外汇支持 |

---
*Research: 2026-04-08*