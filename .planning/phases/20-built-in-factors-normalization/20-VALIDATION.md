# Phase 20: Validation strategy

**Phase:** `20-built-in-factors-normalization`  
**Requirements:** FACTOR-01, FACTOR-02

## Mandatory regression

Every task `verify` block must include **full** backend test discovery under `tests/`:

```bash
cd backend_api_python && pytest tests/ -q
```

**「全量」含义（与 `20-01-PLAN.md` / `20-02-PLAN.md` 中 `<verification_contract>` 一致）：** 对 `tests/` 包执行完整收集与运行；不得以单文件、`-k` 或子目录作为 task 完成的**唯一**依据。若部分用例需要 PostgreSQL 等，须先按 `docker-compose` 启动依赖并配置环境变量后重跑同一命令。

## Test modules

| Module | Purpose |
|--------|---------|
| `tests/test_factor_normalize.py` | FACTOR-02: winsorize, rank, z-score, NaN policy, pipeline, env config |
| `tests/test_factor_library.py` | FACTOR-01: registry, per-factor core math, panel builder |

## Quick smoke (optional during dev)

```bash
cd backend_api_python && pytest tests/test_factor_normalize.py tests/test_factor_library.py -q
```
