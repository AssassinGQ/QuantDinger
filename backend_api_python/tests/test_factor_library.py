from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.factors.config import NormalizeConfig
from app.factors.factor_defs import compute_factor_by_name, get_builtin_factor_specs
from app.factors.panel import build_factor_panels
from app.factors.pipeline import normalize_cross_section


def _make_close(days: int = 320, daily_return: float = 0.01) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=days, freq="D")
    return pd.Series(100.0 * (1.0 + daily_return) ** np.arange(days), index=idx)


def test_factor_registry_contains_locked_v1_catalog():
    keys = set(get_builtin_factor_specs().keys())
    assert keys == {
        "MOM_1M",
        "MOM_3M",
        "MOM_6M",
        "MOM_12M_SKIP_1M",
        "REV_1W",
        "REV_2W",
        "REV_1M",
        "VOL_20D",
        "VOL_60D",
        "SHARPE_60D",
        "SORTINO_60D",
    }


def test_compute_factor_by_name_unknown_raises():
    close = _make_close()
    with pytest.raises(KeyError):
        compute_factor_by_name("UNKNOWN", close, None)


def test_mom_1m_matches_pct_change_21():
    close = _make_close()
    out = compute_factor_by_name("MOM_1M", close, None)
    assert out.iloc[21] == pytest.approx((1.01 ** 21) - 1.0)
    assert out.iloc[22] > 0


def test_mom_12m_skip_1m_excludes_recent_month():
    close = _make_close(days=400, daily_return=0.005)
    out = compute_factor_by_name("MOM_12M_SKIP_1M", close, None)
    expected = close.pct_change(252) - close.pct_change(21)
    pd.testing.assert_series_equal(out, expected)


def test_reversal_opposes_mom_short_window():
    close = _make_close()
    rev = compute_factor_by_name("REV_1W", close, None)
    mom = close.pct_change(5)
    pd.testing.assert_series_equal(rev, -mom)


def test_volatility_20d_annualization():
    idx = pd.date_range("2024-01-01", periods=200, freq="D")
    returns = pd.Series(np.where(np.arange(200) % 2 == 0, 0.01, -0.01), index=idx)
    close = 100 * (1 + returns).cumprod()
    out = compute_factor_by_name("VOL_20D", close, None)
    expected_daily_std = pd.Series(returns).rolling(20).std(ddof=1).iloc[-1]
    assert out.iloc[-1] == pytest.approx(expected_daily_std * np.sqrt(252))


def test_sharpe_60d_nan_when_zero_vol():
    idx = pd.date_range("2024-01-01", periods=200, freq="D")
    close = pd.Series(100.0, index=idx)
    out = compute_factor_by_name("SHARPE_60D", close, None)
    assert pd.isna(out.iloc[-1])


def test_sortino_uses_downside_only():
    idx = pd.date_range("2024-01-01", periods=200, freq="D")
    close = pd.Series(100.0 * (1.001 ** np.arange(200)), index=idx)
    out = compute_factor_by_name("SORTINO_60D", close, None)
    assert pd.isna(out.iloc[-1])


def test_build_factor_panels_shape_and_index():
    fixture = Path(__file__).parent / "fixtures" / "factor_panel_fixture.csv"
    frame = pd.read_csv(fixture, parse_dates=["date"])
    price = frame.pivot(index="date", columns="symbol", values="close").sort_index()
    vol = frame.pivot(index="date", columns="symbol", values="volume").sort_index()
    out = build_factor_panels(price, vol, ["MOM_1M", "REV_1W"])
    assert set(out.keys()) == {"MOM_1M", "REV_1W"}
    for panel in out.values():
        assert panel.index.equals(price.index)
        assert panel.columns.equals(price.columns)


def test_build_factor_panels_deterministic_csv():
    fixture = Path(__file__).parent / "fixtures" / "factor_panel_fixture.csv"
    frame = pd.read_csv(fixture, parse_dates=["date"])
    price = frame.pivot(index="date", columns="symbol", values="close").sort_index()
    panels = build_factor_panels(price, None, ["MOM_1M"])
    row = panels["MOM_1M"].iloc[25]
    expected = price["AAA"].pct_change(21).iloc[25]
    assert row["AAA"] == pytest.approx(expected, abs=1e-9)


def test_panel_then_cross_section_uses_normalize_import():
    fixture = Path(__file__).parent / "fixtures" / "factor_panel_fixture.csv"
    frame = pd.read_csv(fixture, parse_dates=["date"])
    price = frame.pivot(index="date", columns="symbol", values="close").sort_index()
    panels = build_factor_panels(price, None, ["MOM_1M"])
    one_day = panels["MOM_1M"].iloc[-1]
    out = normalize_cross_section(one_day, cfg=NormalizeConfig())
    assert np.isinf(out.fillna(0.0)).sum() == 0
