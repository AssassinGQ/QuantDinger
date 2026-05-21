from __future__ import annotations

import numpy as np
import pandas as pd


def winsorize_series(s: pd.Series, lower_q: float = 0.01, upper_q: float = 0.99) -> pd.Series:
    if s.empty:
        return s.copy()
    valid = s.dropna()
    if valid.empty:
        return s.copy()
    lower = valid.quantile(lower_q)
    upper = valid.quantile(upper_q)
    clipped = s.clip(lower=lower, upper=upper)
    return clipped


def rank_series(s: pd.Series, method: str = "average", pct: bool = True) -> pd.Series:
    return s.rank(method=method, pct=pct)


def zscore_series(s: pd.Series, ddof: int = 0) -> pd.Series:
    if s.empty:
        return s.copy()
    valid = s.dropna()
    if valid.empty:
        return s.copy()
    std = valid.std(ddof=ddof)
    if pd.isna(std) or std == 0:
        out = pd.Series(np.nan, index=s.index, dtype=float)
        return out
    mean = valid.mean()
    out = (s - mean) / std
    out[s.isna()] = np.nan
    return out


def apply_nan_policy(s: pd.Series, policy: str = "drop") -> pd.Series:
    if policy == "drop":
        return s.copy()
    if policy == "median_fill":
        valid = s.dropna()
        if valid.empty:
            return s.fillna(0.0)
        return s.fillna(valid.median())
    if policy == "zero_fill":
        return s.fillna(0.0)
    raise ValueError(f"Unsupported nan policy: {policy}")
