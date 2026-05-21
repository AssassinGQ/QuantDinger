from __future__ import annotations

import pandas as pd

from .config import NormalizeConfig
from .normalize import apply_nan_policy, rank_series, winsorize_series, zscore_series


def normalize_cross_section(s: pd.Series, cfg: NormalizeConfig) -> pd.Series:
    normalized = apply_nan_policy(s, cfg.nan_policy)
    normalized = winsorize_series(normalized, cfg.winsor_lower, cfg.winsor_upper)
    if cfg.enable_zscore:
        normalized = zscore_series(normalized, ddof=cfg.zscore_ddof)
    normalized = rank_series(normalized, method=cfg.rank_ties, pct=True)
    return normalized
