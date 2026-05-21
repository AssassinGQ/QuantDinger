---
phase: 22
slug: cross-sectional-portfolio-backtest-engine
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-15
---

# Phase 22 — Validation Strategy

> 本阶段验证契约：与 Phase 21 计划中的 `verification_contract` 对齐 — **每个任务 verify 必须包含全量 `pytest tests/`**。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `backend_api_python/pytest.ini` 或项目默认 discovery |
| **Quick run command** | `cd backend_api_python && pytest tests/test_cross_sectional_portfolio_bt01.py -q` |
| **Full suite command** | `cd backend_api_python && pytest tests/ -q` |
| **Estimated runtime** | 依仓库现状约 1–10 分钟（以 CI 实测为准） |

---

## Sampling Rate

- **After every task commit:** 运行该任务 `<verify>` 中 **第一行定向 pytest**（若存在）+ **末尾全量 `pytest tests/ -q`**
- **After every plan wave:** `cd backend_api_python && pytest tests/ -q`
- **Before `/gsd-verify-work`:** 全量 green
- **Max feedback latency:** 以 CI 上限为准；本地可并行 `-n auto`（若已配置 pytest-xdist）

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 22-01-01 | 01 | 1 | BT-01 | T-22-exec | 指标沙箱 builtins 白名单不变更缩小 | unit | `pytest tests/test_cross_sectional_portfolio_bt01.py -k contract` | ⬜ W0 | ⬜ pending |
| 22-01-02 | 01 | 1 | BT-01 | T-22-data | 股票池互斥校验拒绝非法请求体 | unit | `pytest tests/test_cross_sectional_portfolio_bt01.py -k pool` | ⬜ W0 | ⬜ pending |
| 22-01-03 | 01 | 1 | BT-01 | — | N/A | unit+integration | `pytest tests/test_cross_sectional_portfolio_bt01.py -k engine` | ⬜ W0 | ⬜ pending |
| 22-02-01 | 02 | 1 | BT-01 | T-22-http | 无敏感错误栈泄漏到 `msg` | api | `pytest tests/test_cross_sectional_portfolio_bt01.py -k api` | ⬜ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend_api_python/tests/test_cross_sectional_portfolio_bt01.py` — BT-01 主用例文件（可由 22-01 首任务创建）
- [ ] 共享 fixture：最小多标的 OHLCV 面板 + 可选 universe mock（不依赖外网）
- [ ] 现有 `tests/conftest.py` 复用优先

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 与真实 NQ100 生产数据一致性 | BT-01 | 生产 DB/凭证不在 CI | 在预发环境用只读连接跑同一请求体，比对 digest 与样本净值点 |

*其余行为尽量自动化。*

---

## Validation Sign-Off

- [ ] 所有任务 `<verify>` 含全量 `pytest tests/ -q`
- [ ] 每个任务含 `<test_case_specs>`（测试内容 / 输入 / 预期）
- [ ] Wave 0 测试文件存在且被 PLAN 引用
- [ ] `nyquist_compliant: true` 于执行通过后由维护者更新

**Approval:** pending
