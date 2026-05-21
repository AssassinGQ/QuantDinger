from __future__ import annotations

import numpy as np
import pandas as pd

_ANNUAL_FACTOR = np.sqrt(252.0)


def mom(close: pd.Series, window: int) -> pd.Series:
    return close.pct_change(window)


def mom_skip(close: pd.Series, window: int, skip: int) -> pd.Series:
    return close.pct_change(window) - close.pct_change(skip)


def reversal(close: pd.Series, window: int) -> pd.Series:
    return -close.pct_change(window)


def volatility(close: pd.Series, window: int, annualize: bool = True) -> pd.Series:
    returns = close.pct_change()
    vol = returns.rolling(window).std(ddof=1)
    if annualize:
        vol = vol * _ANNUAL_FACTOR
    return vol


def sharpe(close: pd.Series, window: int, annualize: bool = True, ddof: int = 1) -> pd.Series:
    returns = close.pct_change()
    mean = returns.rolling(window).mean()
    std = returns.rolling(window).std(ddof=ddof).replace(0.0, np.nan)
    ratio = mean / std
    if annualize:
        ratio = ratio * _ANNUAL_FACTOR
    return ratio


def sortino(close: pd.Series, window: int, annualize: bool = True, ddof: int = 1) -> pd.Series:
    del ddof  # Keep signature aligned with sharpe for future extension.
    returns = close.pct_change()
    mean = returns.rolling(window).mean()
    downside_sq = (returns.clip(upper=0.0) ** 2).rolling(window).mean()
    downside_std = np.sqrt(downside_sq).replace(0.0, np.nan)
    ratio = mean / downside_std
    if annualize:
        ratio = ratio * _ANNUAL_FACTOR
    return ratio
