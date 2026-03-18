# 单标 Regime 加权策略设计方案

## 一、需求概述

在现有单标策略基础上，新增一种支持根据市场状态（Regime）动态调整可用资金量的策略类型。

### 1.1 核心特性

1. **继承自单标策略**：基于现有 `SingleSymbolStrategy` + `SingleSymbolRunner` 扩展
2. **策略类型**：激进型(aggressive) / 保守型(conservative) / 平衡型(balanced)
3. **权重调整指标**：支持 VIX / VHSI / DXY / FearGreed（可多选）
4. **调整可用最大资金量**：根据 regime 调整实际可用于交易的最大资金
5. **调仓触发平仓**：当可用资金比例下降时，需要平掉部分持仓
6. **模块复用**：抽取 RegimeMixin，与 CrossSectionalWeightedStrategy 共用
7. **完全继承**：不修改现有 signal_executor/runner，通过继承实现

---

## 二、分阶段实施计划

### 阶段 0：抽取 RegimeMixin（复用基础）

**目标**：抽取 regime 计算共用逻辑，供两种策略复用

**任务**：
1. 创建 `app/strategies/regime_mixin.py`（包含从 regime_utils 合并的逻辑）
2. 实现 regime 计算和资金比例获取方法
3. 修改 `cross_sectional_weighted_indicator.py` 导入
4. 编写单元测试
5. 全量测试 + Code Review + Commit

### 阶段 1：实现 SingleRegimeWeightedStrategy

**目标**：创建新策略类

**任务**：
1. 创建 `app/strategies/single_regime_weighted.py`
2. 继承 `SingleSymbolStrategy` + `RegimeMixin`
3. 实现 `need_macro_info()` → True
4. 实现 `get_signals()` 扩展：
   - 计算当前 regime
   - 获取可用资金比例
   - 如需平仓（当前持仓 > 新可用资金），生成平仓信号
   - 调整新开仓位的 position_size
5. Factory 添加 `single_regime_weighted` 分支
6. 编写单元测试
7. 全量测试 + Code Review + Commit

### 阶段 2：实现 SingleRegimeWeightedRunner

**目标**：创建新 Runner，完全继承不修改现有代码

**任务**：
1. 创建 `app/strategies/runners/single_regime_weighted_runner.py`
2. 继承 `SingleSymbolRunner`
3. 适配策略的 `should_rebalance` 逻辑
4. Runner Factory 添加分支
5. 集成测试
6. 全量测试 + Code Review + Commit

### 阶段 3：CrossSectionalWeightedStrategy 适配 RegimeMixin（可选）

**目标**：让 CrossSectionalWeightedStrategy 也使用 RegimeMixin

**任务**：
1. 修改 `cross_sectional_weighted.py` 继承 `RegimeMixin`
2. 使用 `compute_regime_from_context` 和 `get_capital_ratio`
3. 集成测试
4. 全量测试 + Code Review + Commit

---

## 三、配置设计

### 3.1 trading_config 字段

```python
{
    "strategy_type": "single_regime_weighted",
    "symbol": "BTC",
    "timeframe": "1H",
    "indicator_code": "dual_ma",
    # --- Regime 相关配置 ---
    "macro_indicators": ["vix", "dxy"],           # 使用的宏观指标
    "primary_macro_indicator": "vix",             # 主指标
    "regime_strategy_type": "balanced",           # aggressive | conservative | balanced
    "rebalance_frequency": "daily",              # 调仓周期
}
```

### 3.2 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `macro_indicators` | list[string] | 是 | - | 宏观指标: vix, vhsi, dxy, fear_greed |
| `primary_macro_indicator` | string | 否 | vix | 主指标 |
| `regime_strategy_type` | string | 是 | - | 策略类型 |
| `rebalance_frequency` | string | 否 | daily | 调仓周期 |

### 3.3 Env 全局定义

```bash
# Regime 判断阈值
REGIME_VIX_PANIC=30
REGIME_VIX_HIGH_VOL=25
REGIME_VIX_LOW_VOL=15
REGIME_VHSI_PANIC=30
REGIME_VHSI_HIGH_VOL=25
REGIME_VHSI_LOW_VOL=15
REGIME_DXY_PANIC=110
REGIME_DXY_HIGH_VOL=105
REGIME_DXY_LOW_VOL=95
REGIME_FG_EXTREME_FEAR=20
REGIME_FG_HIGH_FEAR=35
REGIME_FG_LOW_GREED=65

# Regime × 策略类型 → 可用资金比例
REGIME_TO_WEIGHTS_JSON='{"panic":{"conservative":0.8,"balanced":0.2,"aggressive":0.0},"high_vol":{"conservative":0.5,"balanced":0.4,"aggressive":0.1},"normal":{"conservative":0.2,"balanced":0.6,"aggressive":0.2},"low_vol":{"conservative":0.1,"balanced":0.3,"aggressive":0.6}}'
```

---

## 四、RegimeMixin 设计

### 4.1 regime_utils 合并

**结论**：合并到 regime_mixin 中

原因：
1. 保持内聚 - regime 相关逻辑集中在一个文件
2. 减少维护成本
3. cross_sectional_weighted_indicator.py 改为从 regime_mixin 导入

### 4.2 RegimeMixin 实现

```python
# app/strategies/regime_mixin.py
import os
import json
from typing import Any, Dict, Optional

REGIME_PANIC = "panic"
REGIME_HIGH_VOL = "high_vol"
REGIME_NORMAL = "normal"
REGIME_LOW_VOL = "low_vol"

_DEFAULT_REGIME_TO_WEIGHTS = {
    "panic": {"conservative": 0.8, "balanced": 0.2, "aggressive": 0.0},
    "high_vol": {"conservative": 0.5, "balanced": 0.4, "aggressive": 0.1},
    "normal": {"conservative": 0.2, "balanced": 0.6, "aggressive": 0.2},
    "low_vol": {"conservative": 0.1, "balanced": 0.3, "aggressive": 0.6},
}


def load_regime_rules() -> Dict[str, Any]:
    """从 .env 读取 regime 阈值配置"""
    def _env_float(key: str, default: float) -> float:
        try:
            return float(os.getenv(key, str(default)))
        except (ValueError, TypeError):
            return default

    return {
        "vix_panic": _env_float("REGIME_VIX_PANIC", 30),
        "vix_high_vol": _env_float("REGIME_VIX_HIGH_VOL", 25),
        "vix_low_vol": _env_float("REGIME_VIX_LOW_VOL", 15),
        "vhsi_panic": _env_float("REGIME_VHSI_PANIC", 30),
        "vhsi_high_vol": _env_float("REGIME_VHSI_HIGH_VOL", 25),
        "vhsi_low_vol": _env_float("REGIME_VHSI_LOW_VOL", 15),
        "dxy_panic": _env_float("REGIME_DXY_PANIC", 110),
        "dxy_high_vol": _env_float("REGIME_DXY_HIGH_VOL", 105),
        "dxy_low_vol": _env_float("REGIME_DXY_LOW_VOL", 95),
        "fg_extreme_fear": _env_float("REGIME_FG_EXTREME_FEAR", 20),
        "fg_high_fear": _env_float("REGIME_FG_HIGH_FEAR", 35),
        "fg_low_greed": _env_float("REGIME_FG_LOW_GREED", 65),
        "primary_indicator": os.getenv("REGIME_PRIMARY_INDICATOR", "vix"),
    }


def load_regime_to_weights() -> Dict[str, Dict[str, float]]:
    """从 .env 读取 regime→style 权重映射"""
    raw = os.getenv("REGIME_TO_WEIGHTS_JSON", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return dict(_DEFAULT_REGIME_TO_WEIGHTS)


def compute_regime(
    vix: float,
    fear_greed: Optional[float] = None,
    config: Optional[Dict] = None,
    vhsi: Optional[float] = None,
    dxy: Optional[float] = None,
    macro: Optional[Dict[str, float]] = None,
    primary_override: Optional[str] = None,
) -> str:
    """根据主指标计算当前 regime"""
    cfg = (config or {}).get("regime_rules") or (config if config else {})
    primary = (primary_override or cfg.get("primary_indicator") or "vix").strip().lower()

    if primary == "vhsi":
        vol_val = vhsi if vhsi is not None else (macro or {}).get("vhsi", vix)
        threshold_panic = cfg.get("vhsi_panic", cfg.get("vix_panic", 30))
        threshold_high = cfg.get("vhsi_high_vol", cfg.get("vix_high_vol", 25))
        threshold_low = cfg.get("vhsi_low_vol", cfg.get("vix_low_vol", 15))
        if vol_val > threshold_panic:
            return REGIME_PANIC
        if vol_val > threshold_high:
            return REGIME_HIGH_VOL
        if vol_val < threshold_low:
            return REGIME_LOW_VOL
        return REGIME_NORMAL

    if primary == "dxy":
        vol_val = dxy if dxy is not None else (macro or {}).get("dxy", 100.0)
        threshold_panic = cfg.get("dxy_panic", 110)
        threshold_high = cfg.get("dxy_high_vol", 105)
        threshold_low = cfg.get("dxy_low_vol", 95)
        if vol_val > threshold_panic:
            return REGIME_PANIC
        if vol_val > threshold_high:
            return REGIME_HIGH_VOL
        if vol_val < threshold_low:
            return REGIME_LOW_VOL
        return REGIME_NORMAL

    if primary == "fear_greed":
        fg = fear_greed if fear_greed is not None else 50.0
        fg_extreme_fear = cfg.get("fg_extreme_fear", 20)
        fg_high_fear = cfg.get("fg_high_fear", 35)
        fg_low_greed = cfg.get("fg_low_greed", 65)
        if fg < fg_extreme_fear:
            return REGIME_PANIC
        if fg < fg_high_fear:
            return REGIME_HIGH_VOL
        if fg > fg_low_greed:
            return REGIME_LOW_VOL
        return REGIME_NORMAL

    # 默认 VIX
    vix_panic = cfg.get("vix_panic", 30)
    vix_high_vol = cfg.get("vix_high_vol", 25)
    vix_low_vol = cfg.get("vix_low_vol", 15)
    if vix > vix_panic:
        return REGIME_PANIC
    if vix > vix_high_vol:
        return REGIME_HIGH_VOL
    if vix < vix_low_vol:
        return REGIME_LOW_VOL
    return REGIME_NORMAL


class RegimeMixin:
    """Regime 计算混入类，供 SingleRegimeWeightedStrategy 和 CrossSectionalWeightedStrategy 共用"""

    def compute_regime_from_context(
        self,
        macro: Dict[str, float],
        config: Dict[str, Any],
    ) -> str:
        """根据宏观数据计算当前 regime"""
        primary = config.get("primary_macro_indicator", "vix")
        regime_cfg = {"regime_rules": load_regime_rules()}

        return compute_regime(
            vix=macro.get("vix", 18.0),
            vhsi=macro.get("vhsi"),
            fear_greed=macro.get("fear_greed"),
            dxy=macro.get("dxy"),
            macro=macro,
            config=regime_cfg,
            primary_override=primary,
        )

    def get_capital_ratio(
        self,
        regime: str,
        strategy_type: str,
    ) -> float:
        """根据 regime 和策略类型获取可用资金比例"""
        weights = load_regime_to_weights()
        return weights.get(regime, {}).get(strategy_type, 1.0)
```

---

## 五、核心逻辑

### 5.1 调仓触发平仓

当 regime 变化导致可用资金比例下降时，需要平掉部分持仓：

```python
class SingleRegimeWeightedStrategy(SingleSymbolStrategy, RegimeMixin):
    
    def get_signals(self, ctx: InputContext):
        # 1. 继承原有单标逻辑，生成基础信号
        signals, should_continue, update_rebalance, meta = super().get_signals(ctx)

        # 2. 获取宏观数据
        macro = ctx.get("macro", {})
        if not macro:
            return signals, should_continue, update_rebalance, meta

        # 3. 计算当前 regime
        trading_config = ctx.get("trading_config", {})
        regime = self.compute_regime_from_context(macro, trading_config)

        # 4. 获取可用资金比例
        strategy_type = trading_config.get("regime_strategy_type", "balanced")
        capital_ratio = self.get_capital_ratio(regime, strategy_type)

        # 5. 检查是否需要平仓（当可用资金比例下降时）
        positions = ctx.get("positions", [])
        if positions and capital_ratio < 1.0:
            close_signals = self._generate_close_signals_for_ratio(
                positions, capital_ratio, ctx
            )
            signals.extend(close_signals)

        # 6. 调整新开仓位的 position_size
        for signal in signals:
            if signal.get("type", "").startswith("open_") or signal.get("type", "").startswith("add_"):
                base_size = signal.get("position_size")
                if base_size is not None:
                    signal["position_size"] = base_size * capital_ratio
                else:
                    signal["position_size"] = 0.05 * capital_ratio

        # 7. 记录元数据
        if meta is None:
            meta = {}
        meta["current_regime"] = regime
        meta["capital_ratio"] = capital_ratio

        return signals, should_continue, update_rebalance, meta

    def _generate_close_signals_for_ratio(
        self,
        positions: List[Dict],
        capital_ratio: float,
        ctx: InputContext,
    ) -> List[Dict]:
        """生成平仓信号，使持仓不超过新的可用资金比例"""
        close_signals = []
        initial_capital = ctx.get("_initial_capital", 10000.0)
        current_price = ctx.get("current_price", 0)
        
        # 计算新的可用资金
        available_capital = initial_capital * capital_ratio
        
        # 计算当前持仓占用的资金
        used_capital = 0
        for pos in positions:
            pos_size = float(pos.get("size", 0))
            entry_price = float(pos.get("entry_price", 0))
            used_capital += pos_size * entry_price

        # 如果当前持仓超过可用资金，需要平仓
        if used_capital > available_capital and current_price > 0:
            excess_ratio = (used_capital - available_capital) / used_capital
            excess_ratio = min(excess_ratio, 1.0)  # 最多平 100%
            
            for pos in positions:
                close_signals.append({
                    "symbol": pos.get("symbol"),
                    "type": f"close_{pos.get('side', 'long')}",
                    "position_size": excess_ratio,  # 平掉多余的仓位比例
                    "trigger_price": current_price,
                    "timestamp": int(time.time()),
                })

        return close_signals
```

---

## 六、Runner 设计

### 6.1 继承结构

```
BaseStrategyRunner
    ├── SingleSymbolRunner
    │       └── SingleRegimeWeightedRunner  # 新增
    ├── CrossSectionalRunner
    │       └── RegimeRunner
```

### 6.2 SingleRegimeWeightedRunner

```python
# app/strategies/runners/single_regime_weighted_runner.py
from datetime import datetime
from typing import Any, Dict, Optional

from app.strategies.runners.single_symbol_runner import SingleSymbolRunner
from app.strategies.base import IStrategyLoop
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SingleRegimeWeightedRunner(SingleSymbolRunner):
    """单标 Regime 加权策略的运行流水线"""
    
    def _run_single_tick(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        strat_instance: IStrategyLoop,
        exchange: Any,
        current_time: float,
    ) -> bool:
        """每 tick 运行逻辑，支持调仓周期"""
        # 检查是否需要调仓
        last_rebalance = self.data_handler.get_last_rebalance_at(strategy_id)
        trading_config = strategy.get("trading_config") or {}
        rebalance_frequency = trading_config.get("rebalance_frequency", "daily")
        
        should_rebalance = self._should_rebalance(last_rebalance, rebalance_frequency)
        
        # 构建 context，注入 should_rebalance 供策略使用
        # ... 原有逻辑 ...
        
        return super()._run_single_tick(...)
    
    def _should_rebalance(
        self,
        last_rebalance_time: Optional[datetime],
        rebalance_frequency: str,
    ) -> bool:
        """判断是否到了调仓周期"""
        if last_rebalance_time is None:
            return True
        delta = datetime.now() - last_rebalance_time
        if rebalance_frequency == "daily":
            return delta.days >= 1
        if rebalance_frequency == "weekly":
            return delta.days >= 7
        if rebalance_frequency == "monthly":
            return delta.days >= 30
        return True
```

### 6.3 Runner Factory

```python
# app/strategies/runners/factory.py
from app.strategies.runners.single_regime_weighted_runner import SingleRegimeWeightedRunner

def create_runner(cs_type: str, data_handler, signal_executor) -> BaseStrategyRunner:
    if cs_type == "cross_sectional_weighted":
        return RegimeRunner(data_handler, signal_executor)
    if cs_type == "cross_sectional":
        return CrossSectionalRunner(data_handler, signal_executor)
    if cs_type == "single_regime_weighted":
        return SingleRegimeWeightedRunner(data_handler, signal_executor)
    return SingleSymbolRunner(data_handler, signal_executor)
```

---

## 七、目录结构

```
app/strategies/
  __init__.py
  base.py                          # IStrategyLoop, InputContext 等
  single_symbol.py                 # SingleSymbolStrategy
  single_regime_weighted.py       # 新增
  cross_sectional.py
  cross_sectional_weighted.py
  cross_sectional_base.py
  factory.py                       # 策略工厂
  regime_mixin.py                 # 新增：合并 regime_utils
  single_symbol_indicator.py
  single_symbol_signals.py
  cross_sectional_indicator.py
  cross_sectional_signals.py
  cross_sectional_weighted_indicator.py
  cross_sectional_weighted_signals.py

app/strategies/runners/
  __init__.py
  base_runner.py
  single_symbol_runner.py
  single_regime_weighted_runner.py  # 新增
  cross_sectional_runner.py
  regime_runner.py
  factory.py

tests/
  test_regime_mixin.py             # 新增
  test_single_regime_weighted.py   # 新增
```

---

## 八、阶段产出

| 阶段 | 代码变更 | 测试文件 |
|------|---------|---------|
| 0 | regime_mixin.py（合并） + 修改 cross_sectional_weighted_indicator.py 导入 | test_regime_mixin.py |
| 1 | single_regime_weighted.py + factory.py | test_single_regime_weighted.py |
| 2 | single_regime_weighted_runner.py + runners/factory.py | - |
| 3 | cross_sectional_weighted.py 适配 RegimeMixin（可选） | - |

---

## 九、回答你的问题

### 1. 调仓触发平仓
是的，方案已包含：在 `get_signals` 中检查当前持仓是否超过新的可用资金比例，如超过则生成平仓信号（`close_long` / `close_short`）。

### 2. 不修改 signal_executor/runner
已改为：
- 创建 `SingleRegimeWeightedRunner` 继承 `SingleSignalRunner`
- 不修改任何现有 runner 代码

### 3. regime_utils 合并
已合并到 `regime_mixin.py`，并修改 `cross_sectional_weighted_indicator.py` 的导入。
