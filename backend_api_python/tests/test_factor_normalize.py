import numpy as np
import pandas as pd
import pytest

from app.factors.config import NormalizeConfig, load_normalize_config_from_env
from app.factors.normalize import (
    apply_nan_policy,
    rank_series,
    winsorize_series,
    zscore_series,
)
from app.factors.pipeline import normalize_cross_section


def test_normalize_config_defaults_match_context():
    cfg = NormalizeConfig()
    assert cfg.winsor_lower == 0.01
    assert cfg.winsor_upper == 0.99
    assert cfg.rank_ties == "average"
    assert cfg.nan_policy == "drop"
    assert cfg.enable_zscore is False
    assert cfg.zscore_ddof == 0


def test_load_normalize_config_invalid_winsor_range_raises():
    with pytest.raises(ValueError):
        load_normalize_config_from_env({"QD_FACTOR_WINSOR_LOWER": "0.9", "QD_FACTOR_WINSOR_UPPER": "0.1"})

    with pytest.raises(ValueError):
        load_normalize_config_from_env({"QD_FACTOR_WINSOR_LOWER": "1.1"})


def test_load_normalize_config_invalid_enum_raises():
    with pytest.raises(ValueError):
        load_normalize_config_from_env({"QD_FACTOR_RANK_TIES": "foo"})
    with pytest.raises(ValueError):
        load_normalize_config_from_env({"QD_FACTOR_NAN_POLICY": "bar"})


def test_load_normalize_config_accepts_truthy_zscore():
    cfg = load_normalize_config_from_env({"QD_FACTOR_ENABLE_ZSCORE": "true"})
    assert cfg.enable_zscore is True


def test_winsorize_series_clips_extremes():
    s = pd.Series([1.0, 2.0, 3.0, 100.0], index=["A", "B", "C", "D"])
    out = winsorize_series(s, lower_q=0.25, upper_q=0.75)
    assert out["A"] == pytest.approx(1.75)
    assert out["D"] == pytest.approx(27.25)
    assert out["B"] == 2.0
    assert out["C"] == 3.0


def test_rank_series_ties_average_first_dense():
    s = pd.Series([1.0, 1.0, 3.0], index=["A", "B", "C"])
    avg = rank_series(s, method="average", pct=False)
    fst = rank_series(s, method="first", pct=False)
    dns = rank_series(s, method="dense", pct=False)
    assert list(avg.values) == [1.5, 1.5, 3.0]
    assert list(fst.values) == [1.0, 2.0, 3.0]
    assert list(dns.values) == [1.0, 1.0, 2.0]


def test_zscore_series_zero_std_yields_nan():
    s = pd.Series([5.0, 5.0, 5.0], index=["A", "B", "C"])
    out = zscore_series(s)
    assert out.isna().all()
    assert np.isinf(out.fillna(0.0)).sum() == 0


def test_apply_nan_policy_drop_preserves_index_with_nan_slots():
    s = pd.Series([1.0, np.nan, 3.0], index=["A", "B", "C"])
    out = apply_nan_policy(s, "drop")
    assert list(out.index) == ["A", "B", "C"]
    assert pd.isna(out["B"])


def test_apply_nan_policy_median_and_zero_fill():
    s = pd.Series([1.0, np.nan, 3.0], index=["A", "B", "C"])
    median_filled = apply_nan_policy(s, "median_fill")
    zero_filled = apply_nan_policy(s, "zero_fill")
    assert median_filled["B"] == 2.0
    assert zero_filled["B"] == 0.0


def test_normalize_pipeline_default_winsorize_then_rank():
    s = pd.Series([1.0, 2.0, 3.0, 100.0], index=["A", "B", "C", "D"])
    cfg = NormalizeConfig(winsor_lower=0.25, winsor_upper=0.75)
    out = normalize_cross_section(s, cfg)
    expected = rank_series(winsorize_series(s, 0.25, 0.75), method="average", pct=True)
    pd.testing.assert_series_equal(out, expected)


def test_normalize_pipeline_optional_zscore_inserts_before_rank():
    s = pd.Series([1.0, 2.0, 3.0, 4.0], index=["A", "B", "C", "D"])
    cfg = NormalizeConfig(enable_zscore=True, zscore_ddof=0)
    z = zscore_series(winsorize_series(s, cfg.winsor_lower, cfg.winsor_upper), ddof=cfg.zscore_ddof)
    assert z.mean() == pytest.approx(0.0)
    assert z.std(ddof=0) == pytest.approx(1.0)
    out = normalize_cross_section(s, cfg)
    expected = rank_series(z, method=cfg.rank_ties, pct=True)
    pd.testing.assert_series_equal(out, expected)


def test_normalize_cross_section_end_to_end_deterministic():
    s = pd.Series([2.0, np.nan, 8.0, 4.0], index=["A", "B", "C", "D"])
    cfg = NormalizeConfig(nan_policy="median_fill")
    out = normalize_cross_section(s, cfg)
    assert list(out.index) == ["A", "B", "C", "D"]
    assert np.isinf(out.fillna(0.0)).sum() == 0
