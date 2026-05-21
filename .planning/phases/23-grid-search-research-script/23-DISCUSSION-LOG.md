# Phase 23: Grid-search research script - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 23-grid-search-research-script
**Areas discussed:** 因子网格规格, Walk-forward验证, Phase 22集成方式, 输出与报告, 行业中性化处理, 执行模式, 断点续传

---

## 因子网格规格

| Option | Description | Selected |
|--------|-------------|----------|
| 硬编码（同原型） | 简单直接，适合研究实验。改代码就能换配置 | |
| 配置文件（YAML/JSON） | 适合可配置研究。YAML/JSON定义因子列表、组合范围、持仓数范围，CLI传入配置路径 | ✓ |
| 动态枚举 + CLI参数 | 适合自动化研究。启动时从Phase 20因子注册表自动枚举可用因子 | |

**User's choice:** 配置文件（YAML/JSON）
**Notes:** 用户选择配置文件指定搜索空间，包含显式因子列表 + 参数范围（组合大小min/max、持仓数列表）

---

## Walk-forward验证

| Option | Description | Selected |
|--------|-------------|----------|
| 滚动窗口（固定长度+固定步长） | 每个窗口固定长度（如36月训练+12月测试），滑动步长固定（如12月），适合标准化研究 | ✓ |
| 扩展窗口（训练递增+测试固定） | 训练窗口随时间扩展，适合观察策略稳定性随数据量增加的变化 | |
| 两阶段：全样本搜索 + Walk-forward验证 | 先在全样本做网格搜索，选定最优组合后再做walk-forward验证 | |
| 跳过walk-forward | 脚本先只做全样本网格搜索，walk-forward留给后续研究 | |

**User's choice:** 滚动窗口（固定长度+固定步长）
**Notes:** 用户理解了过度拟合问题后选择滚动窗口walk-forward。窗口参数（train_months/test_months/step_months）由配置文件指定，不硬编码。

---

## Phase 22集成方式

| Option | Description | Selected |
|--------|-------------|----------|
| HTTP API调用（推荐） | 脚本通过HTTP调用Phase 22 API。可移植、可复现、在不同机器运行 | ✓ |
| 直接复用后端服务层 | 脚本在后端进程内运行，直接调用服务层。更快、无网络开销 | |

**User's choice:** HTTP API调用
**Notes:** HTTP方式保证可移植、可复现，与后端版本解耦。

---

## 输出格式

| Option | Description | Selected |
|--------|-------------|----------|
| JSONL（已有，保留） | 原型已支持。每完成一次回测追加一行JSON，适合断点续传和增量分析 | ✓ |
| CSV导出 | 适合研究者用Excel/Python进一步分析。包含所有回测结果的扁平表格 | ✓ |
| HTML报告 | 适合自动化报告。包含配置摘要 + TOP20表格 + 各持仓最优 + 因子频率统计 | ✓ |

**User's choice:** 全选（JSONL + CSV + HTML）
**Notes:** 三种输出格式满足不同分析需求。

---

## 行业中性化处理

| Option | Description | Selected |
|--------|-------------|----------|
| 只用neutral_off | 网格搜索只用neutral_off结果做排名 | |
| 两套分别搜索 + 对比输出 | 两套分别做网格搜索，输出两套TOP结果。研究者可直接对比 | ✓ |
| 配置文件指定（默认neutral_off） | 配置文件指定用哪套。默认neutral_off | |

**User's choice:** 两套分别搜索 + 对比输出
**Notes:** 用户理解了框架层行业中性化能力（业界主流做法）后，选择两套分别搜索便于对比决策。

---

## 执行模式

| Option | Description | Selected |
|--------|-------------|----------|
| 串行执行（单线程） | 简单稳定，适合调试和短时任务。原型当前方式 | ✓ |
| 并行执行（多线程/异步） | 同时发起多个HTTP请求，适合大量回测 | |

**User's choice:** 串行执行
**Notes:** 稳定性优先，避免API限流。

---

## 断点续传

| Option | Description | Selected |
|--------|-------------|----------|
| 保留断点续传（推荐） | checkpoint.json + JSONL追加。中断后可恢复 | ✓ |
| 不需要断点续传 | 每次从头开始 | |

**User's choice:** 保留断点续传
**Notes:** 支持长耗时任务中断恢复。

---

## Claude's Discretion

- YAML配置文件字段命名与结构设计
- HTML报告样式与布局（简洁为主）
- Score评分公式（沿用原型或优化权重）
- API调用超时与重试策略

---

## Deferred Ideas

- 并行执行优化（未来回流量大时考虑）
- 动态因子权重（regime）配置（后续扩展）
- 交互式可视化前端（v3范围）

---

*Discussion log created: 2026-05-19*