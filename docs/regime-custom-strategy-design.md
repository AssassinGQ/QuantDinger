# 自定义 Regime 策略设计（探讨）

## 背景

当前 regime 机制：
- `custom_code` 可执行 Python，输入 `macro`（vix/dxy/fear_greed），输出 `regime` 或 `regime_score`
- regime 映射到 `regime_to_weights` 得到 conservative/balanced/aggressive 权重
- 权重应用到所有品种，无 per-symbol 差异化

## 用户需求

> 根据数据源输入，计算出 agg/balance/conv 的比值，针对多个品种或品类的策略（Python 代码）

即：支持自定义 Python 直接输出 **weights**（aggressive/balanced/conservative 比例），并可按 **品种/品类** 差异化。

## 是否有必要

### 支持的理由

1. **灵活性**：现 regime→weights 是固定映射，无法表达「VIX+DXY 组合」「跨品种相关」等复杂逻辑
2. **品类差异**：港股/美股/外汇对宏观因子敏感度不同，同一 regime 下理想权重不同
3. **数据源扩展**：用户可能想接入自有数据（新闻情绪、资金流等），现有 custom_code 仅能输出 regime，无法直接改权重

### 不支持的考量

1. **复杂度**：per-symbol 或 per-market 权重会显著增加 PortfolioAllocator 与前端配置复杂度
2. **已有扩展点**：`custom_code` 已可输出 regime，通过配置 `regime_to_weights` 覆盖多种 regime 即可满足多数场景
3. **安全与维护**：用户 Python 直接改权重，错误或恶意代码影响面更大

## 推荐方案：分阶段

### 阶段 1（已具备）

- 新增 VHSI，支持 `primary_indicator: vhsi`、`auto`（港股用 VHSI）
- `custom_code` 输入增加 `vhsi`，可基于 vix/vhsi/dxy/fear_greed 计算 regime

### 阶段 2：自定义直接输出权重（可选）

扩展 `custom_code` 执行环境：

```python
# 可选输出（与 regime 二选一）：
weights = {"conservative": 0.3, "balanced": 0.5, "aggressive": 0.2}
# 或 per-symbol（进阶）：
weights_per_symbol = {"00700": {...}, "XAUUSD": {...}, "_default": {...}}
```

- 若代码设置 `weights`，则 ** bypass regime_to_weights**，直接使用该权重
- 若设置 `weights_per_symbol`，PortfolioAllocator 需支持 per-symbol 目标权重
- 需在 `safe_exec` 白名单中允许设置 `weights` / `weights_per_symbol`

### 阶段 3：多数据源输入（可选）

- 允许配置外部数据源 URL/API，定时拉取后注入 `macro` 或 `custom_data`
- custom_code 可访问 `custom_data`，实现「自有数据 + 宏观因子」组合计算

## 建议

- **短期**：不急于实现阶段 2/3。先用 VHSI + `primary_indicator: auto` 满足港股场景；复杂逻辑用 `custom_code` 输出 regime + 多组 `regime_to_weights` 配置
- **中期**：若用户确有「直接输出权重」需求，再实现阶段 2 的 `weights` 输出
- **长期**：若需 per-symbol 权重或多数据源，再设计阶段 2 的 `weights_per_symbol` 与阶段 3
