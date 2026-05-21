from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from .core import mom, mom_skip, reversal, sharpe, sortino, volatility


@dataclass(frozen=True)
class FactorSpec:
    name: str
    func: Callable[..., pd.Series]
    direction: int
    kwargs: dict[str, Any]
    category: str


def get_builtin_factor_specs() -> dict[str, FactorSpec]:
    specs = {
        "MOM_1M": FactorSpec("MOM_1M", mom, 1, {"window": 21}, "momentum"),
        "MOM_3M": FactorSpec("MOM_3M", mom, 1, {"window": 63}, "momentum"),
        "MOM_6M": FactorSpec("MOM_6M", mom, 1, {"window": 126}, "momentum"),
        "MOM_12M_SKIP_1M": FactorSpec(
            "MOM_12M_SKIP_1M", mom_skip, 1, {"window": 252, "skip": 21}, "momentum"
        ),
        "REV_1W": FactorSpec("REV_1W", reversal, -1, {"window": 5}, "reversal"),
        "REV_2W": FactorSpec("REV_2W", reversal, -1, {"window": 10}, "reversal"),
        "REV_1M": FactorSpec("REV_1M", reversal, -1, {"window": 21}, "reversal"),
        "VOL_20D": FactorSpec("VOL_20D", volatility, -1, {"window": 20}, "volatility"),
        "VOL_60D": FactorSpec("VOL_60D", volatility, -1, {"window": 60}, "volatility"),
        "SHARPE_60D": FactorSpec("SHARPE_60D", sharpe, 1, {"window": 60}, "risk_adjusted"),
        "SORTINO_60D": FactorSpec(
            "SORTINO_60D", sortino, 1, {"window": 60}, "risk_adjusted"
        ),
    }
    return specs


def compute_factor_by_name(
    name: str, close: pd.Series, volume: pd.Series | None = None
) -> pd.Series:
    specs = get_builtin_factor_specs()
    if name not in specs:
        raise KeyError(f"Unknown factor name: {name}")
    spec = specs[name]
    if volume is None:
        volume = pd.Series(index=close.index, dtype=float)
    return spec.func(close=close, **spec.kwargs)
