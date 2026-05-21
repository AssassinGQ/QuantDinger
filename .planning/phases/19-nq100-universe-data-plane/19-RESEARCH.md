# Phase 19: NQ100 universe data plane - Research

**Researched:** 2026-04-14  
**Domain:** Index constituent ingestion, PostgreSQL PIT membership, APScheduler jobs, Flask APIs  
**Confidence:** HIGH for in-repo patterns (scheduler, routes, tests); HIGH for fallback package API (upstream source); MEDIUM for live scrape stability (HTML/ToS); MEDIUM for PyPI install verification in this environment (direct JSON API returned 404 — verify in target image)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **数据源（三级优先级）：** 主源 **Nasdaq.com**（权威源），备选 **Wikipedia**（结构化表格），兜底 **`nasdaq-100-ticker-history` pip 包**（前两个都失败时使用）。
- **`nasdaq-100-ticker-history` v2026.2.0** 覆盖 2015-01-01 至今；给定日期返回当时 NQ100 成分列表。
- **失败策略：** 主→备→兜底；全部失败则记日志，不影响系统运行，下次定时任务重试；已缓存数据继续服务。
- **首次部署无数据：** 回测/策略应报错退出（不可用空列表跑回测）。
- **Ticker 标准化：** 映射层，与 QD K-line API 兼容（如 BRK.B → BRK-B）。
- **PIT：** 两张表 — 成员有效期表 `(symbol, valid_from, valid_to, source, scraped_at)` + 变更事件表 `(symbol, event_type[add/remove], effective_date, source, scraped_at)`。
- **回填与增量：** 统一逻辑；定时任务检查已有最新快照；空表则从 2015 拉到今日；有数据则只补缺失；不重复拉已有快照。
- **定时：** 每周一次；复用 `register_scheduled_job()` + kline_sync 插件模式；失败记日志+跳过，单次执行内不重试。
- **API：** `GET /api/universe/nq100?date=YYYY-MM-DD`（无 date = 当前）；`POST /api/universe/nq100/refresh`；前缀 `/api/universe/`。
- **响应：** 遵循现有 `{code, msg, data}` 规范。

### Claude's Discretion

- HTML 解析实现（BeautifulSoup vs lxml vs 正则）。
- 定时任务默认执行时间（每周几、几点）。
- API 响应 `data` 字段细节（在规范内）。
- 两表具体字段名与索引设计。
- 数据源切换实现（串行尝试 vs 配置优先级）。

### Deferred Ideas (OUT OF SCOPE)

- NQ100 策略 `delisting_policy` 三种模式、策略创建 UI、事件驱动 Alpha 等 — **Phase 24 / 其他**，本阶段不做。
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **UNIV-01** | 从公开来源抓取并解析当前 NQ100 成分为标准 symbol | 三级数据源栈；BS4+lxml 栈（见 `.planning/research/STACK.md`）；ticker 归一化映射层 |
| **UNIV-02** | 后端缓存 + APScheduler 可配置周期刷新，日常更新无需发版 | `register_scheduled_job` + `app/tasks/__init__.py` 插件注册；新模块 `JOB_ID` / `INTERVAL_MINUTES` / `ENABLED` / `run()` |
| **UNIV-03** | PostgreSQL 历史成分 + PIT 查询 | 有效期行 + 事件行双表；查询 `date BETWEEN valid_from AND valid_to`；provenance 字段 |
</phase_requirements>

## Summary

Phase 19 在 brownfield Flask + PostgreSQL + APScheduler 上增加 **权威 NQ100 成员数据平面**：上游抓取/兜底包 → 归一化 symbol → 写入 **带有效期与变更事件** 的表 → **GET** 按日 PIT 查询、**POST** 手动刷新、**定时任务** 周更并自动 **2015→今日** 增量补洞。

**Primary recommendation:** 实现上严格复用 `kline_sync` 插件形态与 `register_scheduled_job`；持久层用 **原生 SQL migration**（`qd_` 前缀、与 `init.sql` 风格一致），服务层封装「抓取链 + 增量合并 + DB 写入」；**CI 用冻结 HTML fixture** 测解析器，不在 CI 依赖外网。

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **APScheduler** | `>=3.10.0` (existing `requirements.txt`) | 后台 interval 任务 | 已与 `scheduler_service.register_scheduled_job` 集成 |
| **Flask** | 2.3.x (existing) | HTTP API | 现有 `{code, msg, data}` 路由模式 |
| **psycopg2-binary** | existing | PostgreSQL | `get_db_connection()` 上下文管理 |
| **requests** | existing | Nasdaq/Wikipedia HTTP | 项目已用 |
| **beautifulsoup4** | `>=4.14,<5` | HTML 表解析 | `.planning/research/STACK.md` |
| **lxml** | `>=6.0,<7` | BS4 解析后端 | 同上 |
| **nasdaq-100-ticker-history** | pin **2026.2.0** (per CONTEXT) | 兜底历史/当日集合 | 上游提供 `tickers_as_of(year, month, day) -> frozenset` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **tenacity** | `>=8.2,<10` | 429/5xx 重试 | 仅对**主/备**外网源（CONTEXT：失败策略是切换源+下次重试；单次任务内可选有限重试，与决策不冲突时需产品确认） |
| **strictyaml** | 由 `nasdaq-100-ticker-history` 引入 | 包内 YAML |  transitive 依赖 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Interval 周任务 | `CronTrigger` 指定「每周一 02:00」 | 更可控；需改 `register_scheduled_job` 或另注册 cron（当前 API 为 `interval`） — ** discretion** |
| 仅事件表 | 仅有效期表 | 事件表便于审计 add/remove；有效期表便于单日 PIT SQL — **用户已要求两表** |
| pandas `read_html` | BeautifulSoup | 生产解析控制更细；`read_html` 适合探索 |

**Installation (backend):**

```bash
pip install "beautifulsoup4>=4.14,<5" "lxml>=6.0,<7" "nasdaq-100-ticker-history==2026.2.0"
```

**Version verification:** 在实现前于 **部署用 Python** 上执行 `pip install nasdaq-100-ticker-history==2026.2.0` 确认可解析；本仓库 `backend_api_python/Dockerfile` 为 **Python 3.12-slim**，满足下方 Python 下限。

### Critical: Python version vs fallback package

上游 [jmccarrell/n100tickers](https://github.com/jmccarrell/n100tickers) 的 `pyproject.toml` 声明 **`requires-python = ">=3.11, <4"`**。  
QuantDinger 后端容器为 **Python 3.12**（`backend_api_python/Dockerfile`），**兼容**。若本地开发使用 Python 3.10，**无法安装该兜底包** — 需在文档/CI 中明确 **3.11+** 或使用 Docker 开发。

## Architecture Patterns

### Recommended layout (align with repo + CONTEXT)

```
backend_api_python/app/
├── tasks/
│   └── nq100_universe_sync.py   # JOB_ID, INTERVAL_MINUTES (~10080), ENABLED, run()
├── services/
│   └── universe_nq100_service.py  # fetch chain, normalize, merge, persist, PIT read
├── routes/
│   └── universe.py                # GET/POST /api/universe/nq100...
└── utils/ (optional)
    └── symbol_normalize.py        # BRK.B → BRK-B 等，与 K-line 约定一致
```

新 migration：`0055_*.sql`（或下一编号）— **勿仅改 `init.sql` 若生产已有迁移链**；与 `migrations/init.sql` 同步新增表定义供新环境。

### Pattern 1: Plugin scheduled task (reuse kline_sync)

**What:** 模块导出 `JOB_ID`, `INTERVAL_MINUTES`, `ENABLED`, `run()`；`register_all_tasks()` 里 `register_scheduled_job(..., run_immediately=False)`。

**Source:** `backend_api_python/app/tasks/kline_sync.py`, `app/tasks/__init__.py`

**Weekly interval:** `7 * 24 * 60 = 10080` 分钟（与现有「分钟间隔」API 一致）。

### Pattern 2: PIT membership

**What:**  
- **有效期表：** 每个 symbol 连续成员区间 `[valid_from, valid_to]`，`valid_to` 可为 NULL 表示延续至今。  
- **变更表：** 每次 add/remove 一行，`effective_date` 与官方生效日对齐（与包内 YAML 的 change 日期一致时可审计）。

**PIT 查询：** `WHERE %(as_of)s::date BETWEEN valid_from AND COALESCE(valid_to, 'infinity'::date)`（或用 `daterange` / 半开区间，团队任选一种并全项目统一）。

**Anti-patterns:**  
- **仅用「当前成员」表：** 违反 UNIV-03。  
- **忽略 provenance：** 违反 roadmap 成功标准第 4 条与审计需求。

### Pattern 3: Unified backfill + incremental

**What:** 单次 `run()` 内：读 DB「已覆盖的最大日期 / 快照版本」→ 从 `max(2015-01-01, last+1)` 循环到 `today`（或按调仓稀疏拉取，由实现选择）→ 仅写入缺失区间。  
**Source:** CONTEXT「统一逻辑」；兜底包 `tickers_as_of(y,m,d)` 支持按日查询。

### Anti-Patterns to Avoid

- **在策略里硬编码 `NQ100_UNIVERSE`：** `scripts/cross_sectional/nq100_cross_sectional.py` 应最终改为 API/DB（可 Phase 19 末或后续 task）。  
- **爬虫 E2E 依赖实时 Nasdaq.com：** STATE.md — CI 用 **frozen HTML fixtures**。  
- **绕过 `get_db_connection()`：** 破坏连接池与事务约定。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 2015–至今 NQ100 历史成员集合 | 自维护 YAML/CSV | `nasdaq-100-ticker-history.tickers_as_of` | 上游维护年度变更文件；与包版本对齐 |
| HTML 解析 | 脆弱正则作为主方案 | BeautifulSoup + lxml | STACK.md |
| 分布式任务队列 | Celery | APScheduler 已有 | ARCHITECTURE / STACK 已否决 v2 引入 Celery |

**Key insight:** 主/备源负责「**当前**列表 freshness」；兜底包负责「**历史 PIT** 与全失败时的备份」— 合并写入时需 **统一 symbol 归一化**，避免同一公司两种写法占两行。

## Common Pitfalls

### Pitfall 1: Survivorship / “today’s list” for history

**What goes wrong:** 用今日成分跑历史回测。  
**Why:** 见 `.planning/research/PITFALLS.md` Pitfall 1。  
**How to avoid:** 所有下游只读 **PIT API/DB**；`GET` 无 date 时也应基于 **有效期表当前段**，而非单独未版本化缓存。  
**Warning signs:** 固定 100 只成分、多年无变化。

### Pitfall 2: Fallback package ticker set size

**What goes wrong:** 上游 `tickers_as_of` 文档示例中出现 **>100** 个 ticker（包内 doctest：`len(...) == 103`），与「纳指 100」直觉不符。  
**Why:** 指数编制含双类别/特殊成分等，**以数据源集合为准**。  
**How to avoid:** 归一化后与 QD `USStock` 符号对齐；文档说明「与官方发布计数可能略有差异」。  
**Confidence:** MEDIUM — 行为以包与 Nasdaq 定义为准。

### Pitfall 3: Scrape fragility

**What goes wrong:** Nasdaq/Wikipedia DOM 变更 → 解析空/错。  
**How to avoid:** 三级切换 + 日志；**单元测试**用 fixture HTML；监控 `scraped_at` 与连续失败次数。

### Pitfall 4: Open-ended `valid_to`

**What goes wrong:** 未关闭旧区间就插入新区间 → PIT 查询重复或遗漏。  
**How to avoid:** 事务内先 **close** 受影响 symbol 的当前行，再插入新行；或用事件表重建区间（实现选型属 discretion）。

## Code Examples

### Fallback package (verified from upstream source)

```python
# Source: https://github.com/jmccarrell/n100tickers/blob/main/src/nasdaq_100_ticker_history/__init__.py
from nasdaq_100_ticker_history import tickers_as_of

syms = tickers_as_of(2020, 6, 1)  # frozenset of str
assert "AMZN" in syms
```

### register_scheduled_job (existing API)

```python
# Source: backend_api_python/app/services/scheduler_service.py (register_scheduled_job)
sched.add_job(target_func, "interval", minutes=interval_minutes, id=job_id, ...)
```

### Flask response shape

```python
# Pattern from backend_api_python/app/routes/market.py
return jsonify({"code": 1, "msg": "success", "data": data})
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 脚本内硬编码 `NQ100_UNIVERSE` | DB + API PIT | Phase 19 | 可审计、可回测 |
| 单次爬取「当前」 | 有效期 + 事件 | Phase 19 | 满足 UNIV-03 |

**Deprecated/outdated:** 依赖「今天列表代表历史」— 明确禁止用于回测。

## Open Questions

1. **`tenacity` 与「单次不重试」：** CONTEXT 要求失败即切换源/记日志；是否在**单个源**内做 1–2 次指数退避？  
   - *Recommendation:* 默认 0 次重试以贴合字面；若加，仅限 429/5xx 且记录日志。

2. **PyPI 可用性：** 在部分网络下 `pypi.org/pypi/nasdaq-100-ticker-history/json` 可能不可用；需在实际 CI/registry 验证。  
   - *Recommendation:* Dockerfile 内 `pip install` 作为 gate。

3. **主源 URL 文档化：** 计划阶段需锁定 **具体 Nasdaq.com URL** 与 Wikipedia 表格版本，便于 fixture 与法务审查。

## Validation Architecture

> `workflow.nyquist_validation` is enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest（`backend_api_python/tests/`） |
| Config file | 无独立 `pytest.ini` — 使用默认 + `tests/conftest.py` |
| Quick run command | `cd backend_api_python && pytest tests/test_kline_sync_plugin.py tests/test_tasks_registry.py -x -q` |
| Full suite command | `cd backend_api_python && pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| UNIV-01 | 解析器对 fixture HTML 输出归一化 symbol | unit | `pytest tests/test_nq100_universe_ingest.py::test_parse_* -x` | ❌ Wave 0 |
| UNIV-02 | `nq100` 插件注册、`run()` 调用 service（mock 外网） | unit | `pytest tests/test_nq100_universe_sync_plugin.py -x` | ❌ Wave 0 |
| UNIV-02 | `POST /api/universe/nq100/refresh` 返回 code=1（mock） | integration | `pytest tests/test_universe_routes.py -x` | ❌ Wave 0 |
| UNIV-03 | PIT：给定日期返回预期集合（插入 fixture 行） | unit/integration | `pytest tests/test_universe_pit_query.py -x` | ❌ Wave 0 |
| UNIV-03 | `tickers_as_of` 与 DB 归一化一致（可选 smoke） | unit | `pytest tests/test_nq100_fallback_package.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** 相关 `pytest ... -x` 子集（<30s 目标）。
- **Per wave merge:** `pytest tests/ -q`。
- **Phase gate:** 全绿后再 `/gsd:verify-work`。

### Wave 0 Gaps

- [ ] `tests/test_nq100_universe_ingest.py` — HTML fixtures under `tests/fixtures/nq100/`（无实时网络）。
- [ ] `tests/test_nq100_universe_sync_plugin.py` — 对齐 `test_kline_sync_plugin.py` 模式。
- [ ] `tests/test_universe_routes.py` — Flask `test_client`（见 `conftest.py` `strategy_client` 模式）。
- [ ] `tests/test_universe_pit_query.py` — mock `get_db_connection`（见 `conftest.make_db_ctx`）或测试 DB 容器策略。

## Sources

### Primary (HIGH confidence)

- `backend_api_python/app/tasks/kline_sync.py`, `app/tasks/__init__.py`, `app/services/scheduler_service.py` — 定时任务模式
- `backend_api_python/tests/test_kline_sync_plugin.py`, `tests/test_tasks_registry.py` — 测试模式
- `https://raw.githubusercontent.com/jmccarrell/n100tickers/main/pyproject.toml` — 包名、版本 **2026.2.0**、`requires-python >=3.11`
- `https://raw.githubusercontent.com/jmccarrell/n100tickers/main/src/nasdaq_100_ticker_history/n100tickers.py` — `tickers_as_of` 语义
- `.planning/research/STACK.md`, `ARCHITECTURE.md`, `PITFALLS.md`
- `.planning/phases/19-nq100-universe-data-plane/19-CONTEXT.md` — 用户锁定决策

### Secondary (MEDIUM confidence)

- `backend_api_python/Dockerfile` — Python 3.12
- Web search / PyPI：包名与 GitHub 交叉验证；PyPI JSON 在此环境未成功拉取 — **安装时复核**

### Tertiary (LOW confidence)

- Nasdaq.com / Wikipedia 页面结构时效性 — 以 fixture + 人工抽检为准

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — 版本来自上游 pyproject + 现有 requirements
- Architecture: **HIGH** — 与现有模块一致
- Pitfalls: **HIGH** — PIT/survivorship 为量化通识 + 项目 PITFALLS.md

**Research date:** 2026-04-14  
**Valid until:** ~30 days（依赖外网 HTML 与 PyPI 发布节奏）
