# Phase 19: NQ100 universe data plane - Context

**Gathered:** 2026-04-14 (updated — data source changed to Nasdaq Data Link)
**Status:** Ready for re-planning

<domain>
## Phase Boundary

获取 NQ100 成分股列表（日级）与 NDX 指数日度 `eod_index_value` 基准序列，后端 API 缓存 + 定时刷新、PostgreSQL 历史快照（PIT 查询）。数据源为用户已下载的 NEID 导出文件（`NDX_IC.csv` / `NDX_EIV.csv`）。不含策略逻辑、回测引擎或平仓策略。

</domain>

<decisions>
## Implementation Decisions

### 数据源（更新 2026-04-14）
- **主源：本地 NEID 导出文件**（稳定、已下载）
  - `NDX_IC.csv`：日级成分股快照（`index_symbol,date,component_symbol,...`），作为 universe PIT 主来源
  - `NDX_EIV.csv`：日级指数值（含 `eod_index_value`），作为**必需入库的基准收益**来源
- **权重补充源（可选）：QQQ 日度持仓**
  - 用于补充权重列（如可用），但不作为 Phase 19 必需交付
  - QQQ 拉取失败时：仅日志告警，不影响主流程（IC/EIV 入库与 PIT 查询）
- **失败策略：** NEID 主源不做外部降级（已本地落盘，视为稳定输入）。QQQ 仅做 best-effort 补充
- **已缓存数据不受影响：** 刷新失败时，回测和策略继续使用上一次成功拉取的成分列表
- **首次部署无数据时：** 回测脚本/策略应报错退出（"NQ100 成分列表为空，请先运行成分同步"），不可用空列表跑回测
- **权重数据：** 数据库保留 `weight` 列，但其值是可选字段；`eod_index_value` 才是 Phase 19 必需入库字段

### Ticker 标准化
- **做一层映射**，确保爬取到的 ticker 与 QD K-line API 兼容（如 BRK.B → BRK-B）
- 现有脚本中的硬编码列表可作为**初始种子数据**参考

### PIT 快照设计
- **两张表**：成员有效期表 + 变更事件表
  - 成员有效期表：(symbol, valid_from, valid_to, weight, source, scraped_at) — 查询某日成分用 `WHERE date BETWEEN valid_from AND valid_to`；weight 字段可选（QQQ 可用时补充）
  - 变更事件表：(symbol, event_type[add/remove], effective_date, source, scraped_at) — 追踪调仓历史
- PIT 快照记录**加入日期/移出日期**，供下游策略判断平仓时机
- 每次调仓的 **add/remove 变更事件**独立存储（哪几只进、哪几只出、生效日期）
- **注意：** 19-01 Plan 已完成 schema 创建（`0055_qd_nq100_universe.sql`），如需新增 weight 列需要追加 migration
- `eod_index_value` 独立入库（按交易日）并与 universe 查询日期对齐，用于基准收益曲线

### 数据回填与增量策略（统一逻辑）
- **不需要专门的首次回填脚本** — 一套逻辑统一处理
- 定时任务每次运行时检查数据库中已有的最新快照日期
- 如果表空（首次部署），从 `NDX_IC.csv` / `NDX_EIV.csv` 可用最早日期回填到当前最新日期
- 如果已有数据，只拉缺失的交易日（增量补全）
- 数据库中已有的快照不重复拉取
- `NDX_IC.csv` 为**日级精度**，PIT 查询直接按日匹配，无需月度换算逻辑

### 定时刷新策略
- **每周一次**（NQ100 一年只调仓 1-2 次，每周足够）
- 复用 `register_scheduled_job()` 现有 APScheduler 接口 + kline_sync 插件模板
- 失败处理：**记日志 + 跳过**，下次定时任务自动重试，不做单次执行内重试
- 提供**手动触发接口** `POST /api/universe/nq100/refresh`，方便调试和紧急更新

### API 端点设计
- **最小集**：当前成员列表 + PIT 查询 + 手动刷新
- `GET /api/universe/nq100?date=YYYY-MM-DD` — 不传 date 返回当前成员；传 date 返回 PIT 历史成员
- `POST /api/universe/nq100/refresh` — 手动触发刷新
- 路径前缀 `/api/universe/` 预留扩展（未来可加 SP500 等其他 universe）
- 遵循现有 `{code, msg, data}` 响应规范

### NQ100 成分列表与策略的关系
- NQ100 列表是**上游品种筛选器**，不是 DataFrame 的一列
- 回测引擎在每个调仓日通过 PIT 查询决定"当时有哪些股票参与排名"
- 实盘策略应引用 `universe: "NQ100"` 而非硬编码 symbol_list，调仓时动态查询当前成分
- 成分变更时，被移出的股票不再出现在排名中 → 自然出局（精确平仓时机由策略配置决定，见 Deferred Ideas）

### Claude's Discretion
- 定时任务的默认执行时间（每周几、几点）
- API 响应格式细节（遵循现有 `{code, msg, data}` 规范）
- CSV 字段映射细节（`NDX_IC.csv` / `NDX_EIV.csv` 到数据库字段）
- QQQ 权重补充任务的启停配置（默认开启但不阻塞）
- 是否需要 weight 列的 migration（取决于当前 schema 是否已包含）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 现有代码
- `scripts/cross_sectional/nq100_cross_sectional.py` L38-64 — 现有硬编码 NQ100_UNIVERSE 列表（~101 symbols），作为初始种子参考
- `backend_api_python/app/tasks/__init__.py` — 插件定时任务注册模式（`register_all_tasks()` + `register_scheduled_job()`）
- `backend_api_python/app/tasks/kline_sync.py` — 插件定时任务模板（JOB_ID, ENABLED, INTERVAL_MINUTES, run()）
- `backend_api_python/app/services/scheduler_service.py` — APScheduler 使用模式、`register_scheduled_job` API
- `backend_api_python/migrations/init.sql` — 数据库表定义模式（原生 SQL，非 SQLAlchemy，`qd_` 前缀）
- `backend_api_python/app/utils/db.py` — `get_db_connection()` 数据库访问模式
- `backend_api_python/app/routes/` — Flask Blueprint + `{code, msg, data}` 响应规范

### 第三方数据源
- `scripts/NDX_IC.csv` — NDX 成分股日级历史（Phase 19 universe 主输入）
- `scripts/NDX_EIV.csv` — NDX 指数日度 `eod_index_value`（Phase 19 基准收益必需入库输入）
- `scripts/qqq_holdings.csv` — QQQ 持仓权重（可选补充输入，失败仅告警）

### 研究文档
- `.planning/research/STACK.md` — beautifulsoup4 + lxml + tenacity 依赖建议
- `.planning/research/ARCHITECTURE.md` — NQ100 数据平面集成架构
- `.planning/research/PITFALLS.md` — PIT 成分快照 + 幸存者偏差

### NQ100 调仓规则（来自专家）
- NQ100 常规调仓每年 12 月进行一次（成分替换 + 权重再平衡）
- 季度权重再平衡在 3/6/9/12 月第三个周五收盘后生效
- 调整结果提前约 2 周公布
- 2026 年 5 月起新规：大型 IPO 可通过"快速准入"在上市第 15 个交易日被纳入

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `register_scheduled_job(job_id, func, interval_minutes, run_immediately)` — 直接复用于 NQ100 刷新任务
- `get_db_connection()` — 数据库访问入口
- `app/tasks/__init__.py` 的 `register_all_tasks()` — 新任务注册点
- `qd_market_symbols` 表 — 参考其 schema 设计模式，但 NQ100 成分需要独立表
- `app/tasks/kline_sync.py` — 插件定时任务模板（JOB_ID, ENABLED, run()）

### Established Patterns
- Flask Blueprint + `{code, msg, data}` 响应格式
- 原生 SQL + `init.sql` 表定义（无 SQLAlchemy，`qd_` 前缀）
- 插件式定时任务：模块导出 JOB_ID / INTERVAL_MINUTES / ENABLED / run()
- migration SQL 文件编号递增：`002_*`, `003_*`, ...

### Integration Points
- `app/tasks/__init__.py` — 注册 NQ100 定时刷新任务（新增 `from app.tasks import nq100_sync`）
- `migrations/init.sql` 或新 migration file — 新增 PIT 快照相关两张表
- `app/routes/` — 新增 universe API blueprint（`/api/universe/nq100`）
- `scripts/cross_sectional/nq100_cross_sectional.py` — 迁移硬编码列表到 API/DB

</code_context>

<specifics>
## Specific Ideas

- 主数据源从 HTML 爬虫变更为 **本地 NEID CSV 输入**（`NDX_IC.csv` + `NDX_EIV.csv`）
- PIT 快照必须支持查询"某只股票的加入日/移出日"，供下游策略判断平仓时机
- 一套逻辑统一处理首次回填和增量更新——定时任务检测缺失数据自动补全，不需要专门的回填脚本
- `eod_index_value` 是 Phase 19 必需入库交付（基准收益主序列）；权重列保留但非必需
- QQQ 权重仅作为可选补充，拉取失败只记录日志，不阻塞主流程
- **重要：** 19-01 Plan 已完成（schema + PIT 读服务），19-02 Task 1 已完成（deps + 归一化）。数据源变更主要影响 19-02 Task 2（fetch chain）和 19-03（sync + routes），需要重新规划这些部分

</specifics>

<deferred>
## Deferred Ideas

### NQ100 策略类型（新 Phase 24 — 已确认需新建）
继承 `CrossSectionalStrategy`，新增 `delisting_policy` 配置，三种模式：
1. **立即平仓（immediate）** — 生效日当天卖出被剔除股，买入新增股。最小化跟踪误差。适合被动跟踪。
2. **延迟 N 月平仓（delayed_N_months）** — 继续持有被剔除股 3-12 个月，利用"剔除股反弹效应"（学术研究：年化 +23bps）。适合主动增强。
3. **保留至信号退出（hold_until_signal_exit）** — 被剔除股继续参与截面打分，当指标自然发出平仓信号时才卖出，同时排除出 universe。适合截面 Alpha 优先的策略。

**特殊情况硬止损：** 破产/财务造假/退市风险 → 无条件立即平仓。

**事件驱动 Alpha 叠加：** 调仓公告后可做多被剔除股 + 做空新增股（Schaeffer's Research：被剔除股 3 个月跑赢新增股 ~3.5%）。

### 策略创建 UI
前端在创建 NQ100 截面策略时，选择三种平仓方式之一。

</deferred>

---

*Phase: 19-nq100-universe-data-plane*
*Context gathered: 2026-04-13, updated 2026-04-14 (data source: local NEID CSV: NDX_IC + NDX_EIV)*
