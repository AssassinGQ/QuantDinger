"""
Regime 计算工具 — 向后兼容包装。

全部实现已迁移至 regime_mixin.py，此文件仅做 re-export。
"""
from app.strategies.regime_mixin import (  # noqa: F401
    REGIME_PANIC,
    REGIME_HIGH_VOL,
    REGIME_LOW_VOL,
    REGIME_NORMAL,
    check_rebalance_due,
    compute_regime,
    load_regime_rules,
    load_regime_to_weights,
    read_macro_values,
    RegimeMixin,
)

__all__ = [
    "REGIME_PANIC",
    "REGIME_HIGH_VOL",
    "REGIME_LOW_VOL",
    "REGIME_NORMAL",
    "check_rebalance_due",
    "compute_regime",
    "load_regime_rules",
    "load_regime_to_weights",
    "read_macro_values",
    "RegimeMixin",
]
