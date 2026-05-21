---
phase: 19-nq100-universe-data-plane
plan: 03
subsystem: api
tags: [nq100, apscheduler, flask, pit, eiv, csv-ingest]
requires:
  - phase: 19-02
    provides: CSV ingest for IC/EIV bundle import
provides:
  - Weekly APScheduler plugin for NQ100 CSV sync
  - Manual refresh API and PIT/EIV query APIs
  - Non-blocking QQQ weight enrichment behavior
affects: [phase-20-factor, phase-21-audit, cross-sectional-backtest]
tech-stack:
  added: []
  patterns: [plugin task contract, success-envelope api, best-effort enrichment fallback]
key-files:
  created:
    - backend_api_python/tests/test_universe_sync_db.py
    - backend_api_python/app/tasks/nq100_universe_sync.py
    - backend_api_python/tests/test_nq100_universe_sync_plugin.py
    - backend_api_python/app/routes/universe.py
    - backend_api_python/tests/test_universe_routes.py
  modified:
    - backend_api_python/app/services/nq100_csv_ingest_service.py
    - backend_api_python/app/services/universe_nq100_service.py
    - backend_api_python/app/tasks/__init__.py
    - backend_api_python/tests/test_tasks_registry.py
    - backend_api_python/app/routes/__init__.py
key-decisions:
  - "QQQ 权重补充采用 best-effort 模式，失败仅记录 warning 并回传 failed_non_blocking。"
  - "NQ100 刷新任务沿用现有插件任务契约（JOB_ID/INTERVAL_MINUTES/ENABLED/run）。"
  - "Universe API 统一返回 {code,msg,data}，并为无成分数据提供明确提示。"
patterns-established:
  - "任务编排模式：run() -> service sync -> structured summary logging。"
  - "读接口模式：按 date 参数解析为 date 类型后交给 service 处理。"
requirements-completed: [UNIV-02, UNIV-03]
duration: 43min
completed: 2026-04-14
---

# Phase 19 Plan 03: NQ100 Universe Runtime Surface Summary

**交付了可执行的 NQ100 数据平面运行面：每周自动同步、手动刷新、PIT 成分查询与 EIV 按日查询，并保证 QQQ 权重补充失败不阻塞主流程。**

## Performance

- **Duration:** 43 min
- **Started:** 2026-04-14T10:37:00Z
- **Completed:** 2026-04-14T11:20:00Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments
- 新增 `sync_nq100_from_csv`，串联 IC/EIV 入库与 QQQ 权重补充，满足 non-blocking 语义。
- 新增 `nq100_universe_sync` 每周任务插件并接入 `register_all_tasks`。
- 新增 `universe` 路由，提供 `/nq100`、`/nq100/eiv`、`/nq100/refresh` 三类接口。
- 补齐服务、插件、路由层自动化测试并通过全量 `pytest tests/ -q` 回归门禁。

## Task Commits

Each task was committed atomically:

1. **Task 1: 编排 CSV 同步服务并实现 QQQ 失败非阻塞** - `937e20a` (feat)
2. **Task 2: 实现 APScheduler 插件注册与调度测试** - `60de908` (feat)
3. **Task 3: 完成 universe 路由及接口测试** - `35830d1` (feat)

## Files Created/Modified
- `backend_api_python/app/services/nq100_csv_ingest_service.py` - 新增 `try_enrich_weights_from_qqq`，异常捕获并返回非阻塞状态。
- `backend_api_python/app/services/universe_nq100_service.py` - 新增 `sync_nq100_from_csv` 与 `get_eiv_as_of`。
- `backend_api_python/app/tasks/nq100_universe_sync.py` - 新增每周任务插件与默认 CSV 路径执行逻辑。
- `backend_api_python/app/tasks/__init__.py` - 新增 NQ100 插件注册分支。
- `backend_api_python/app/routes/universe.py` - 新增 Universe PIT/EIV/refresh API 蓝图。
- `backend_api_python/app/routes/__init__.py` - 注册 `universe_bp` 到 `/api/universe`。
- `backend_api_python/tests/test_universe_sync_db.py` - 覆盖 orchestrator 调用、QQQ 非阻塞和幂等。
- `backend_api_python/tests/test_nq100_universe_sync_plugin.py` - 覆盖插件契约与 run 调用路径。
- `backend_api_python/tests/test_tasks_registry.py` - 覆盖 registry 包含 `task_nq100_universe_sync`。
- `backend_api_python/tests/test_universe_routes.py` - 覆盖 4 个接口用例及空库提示信息。

## Decisions Made
- QQQ 权重补充失败视为非阻塞失败，避免影响 IC/EIV 主流程可用性。
- 插件调度固定为周频（10080 分钟），并复用现有 APScheduler 注册入口。
- `/nq100` 无数据时返回成功包络并给出同步提示，便于前端直接提示用户执行 refresh。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] 修复注册测试中 patch 参数签名不匹配**
- **Found during:** Task 2
- **Issue:** 使用 `patch(..., True/False)` 后仍声明 mock 参数，导致 pytest fixture 解析失败。
- **Fix:** 移除多余测试函数参数，保持 patch 语义与签名一致。
- **Files modified:** `backend_api_python/tests/test_tasks_registry.py`
- **Verification:** 定向测试 `test_register_all_tasks_includes_nq100_universe_sync_when_enabled` 通过。
- **Committed in:** `60de908`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** 偏差仅为测试签名修复，无范围扩张，计划目标完全达成。

## Issues Encountered
- 全量测试耗时较长（约 3 分钟级），但三轮回归均通过且无新失败。

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- NQ100 数据平面运行面已可由任务与 API 驱动，满足后续 FACTOR/AUDIT 阶段的读取前提。
- 可在后续阶段直接消费 `/api/universe/nq100` 与 `/api/universe/nq100/eiv` 结果进行策略与审计逻辑联调。

## Self-Check: PASSED
- FOUND: `.planning/phases/19-nq100-universe-data-plane/19-03-SUMMARY.md`
- FOUND commits: `937e20a`, `60de908`, `35830d1`
