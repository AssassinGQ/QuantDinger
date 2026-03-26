"""
Tests for app/strategies/regime_mixin.py — regime computation, DXY support, RegimeMixin class.
"""
import json
import os
from unittest.mock import patch

import pandas as pd

from app.strategies.regime_mixin import (
    RegimeMixin,
    compute_regime,
    load_regime_rules,
    load_regime_to_weights,
    read_macro_values,
    REGIME_PANIC,
    REGIME_HIGH_VOL,
    REGIME_NORMAL,
    REGIME_LOW_VOL,
)

SAMPLE_RULES = {
    "regime_rules": {
        "vix_panic": 30,
        "vix_high_vol": 25,
        "vix_low_vol": 15,
    },
}

DXY_RULES = {
    "regime_rules": {
        "dxy_panic": 110,
        "dxy_high_vol": 105,
        "dxy_low_vol": 95,
    },
}

FG_RULES = {
    "regime_rules": {
        "fg_extreme_fear": 20,
        "fg_high_fear": 35,
        "fg_low_greed": 65,
    },
}


class TestComputeRegime:
    """测试 compute_regime 在 VIX 规则下的 panic 等档位。"""

    def test_panic(self):
        """VIX 高于 panic 阈值时应为 panic。"""
        assert compute_regime(35.0, config=SAMPLE_RULES) == "panic"

    def test_high_vol(self):
        """VIX 处于 high_vol 区间时应为 high_vol。"""
        assert compute_regime(27.0, config=SAMPLE_RULES) == "high_vol"

    def test_normal(self):
        """VIX 处于 normal 区间时应为 normal。"""
        assert compute_regime(20.0, config=SAMPLE_RULES) == "normal"

    def test_low_vol(self):
        """VIX 低于 low_vol 阈值时应为 low_vol。"""
        assert compute_regime(12.0, config=SAMPLE_RULES) == "low_vol"

    def test_boundary_panic(self):
        """panic 与 high_vol 在边界值处的划分。"""
        assert compute_regime(30.1, config=SAMPLE_RULES) == "panic"
        assert compute_regime(30.0, config=SAMPLE_RULES) == "high_vol"

    def test_boundary_low_vol(self):
        """low_vol 与 normal 在边界值处的划分。"""
        assert compute_regime(14.9, config=SAMPLE_RULES) == "low_vol"
        assert compute_regime(15.0, config=SAMPLE_RULES) == "normal"

    def test_vhsi_primary_indicator(self):
        """主指标为 VHSI 时用 VHSI 数值计算 regime。"""
        cfg = {
            "regime_rules": {
                **SAMPLE_RULES["regime_rules"],
                "primary_indicator": "vhsi",
            }
        }
        assert compute_regime(
            35.0, config=cfg, vhsi=35.0, primary_override="vhsi",
        ) == "panic"
        assert compute_regime(
            20.0, config=cfg, vhsi=12.0, primary_override="vhsi",
        ) == "low_vol"

    def test_fear_greed_primary(self):
        """主指标为恐惧贪婪指数时各档划分。"""
        assert compute_regime(
            20.0, fear_greed=10.0, config=FG_RULES,
            primary_override="fear_greed",
        ) == "panic"
        assert compute_regime(
            20.0, fear_greed=30.0, config=FG_RULES,
            primary_override="fear_greed",
        ) == "high_vol"
        assert compute_regime(
            20.0, fear_greed=50.0, config=FG_RULES,
            primary_override="fear_greed",
        ) == "normal"
        assert compute_regime(
            20.0, fear_greed=70.0, config=FG_RULES,
            primary_override="fear_greed",
        ) == "low_vol"

    def test_civix_primary(self):
        """主指标为 CIVIX 时从 macro 读取并划分 regime。"""
        cfg = {"regime_rules": {
            "civix_panic": 30, "civix_high_vol": 25, "civix_low_vol": 15,
        }}
        assert compute_regime(
            20.0, config=cfg, macro={"civix": 35.0},
            primary_override="civix",
        ) == "panic"
        assert compute_regime(
            20.0, config=cfg, macro={"civix": 12.0},
            primary_override="civix",
        ) == "low_vol"


class TestComputeRegimeDXY:
    """测试主指标为 DXY 时 compute_regime 的各档与边界。"""

    def test_dxy_panic(self):
        """DXY 高于 panic 阈值时应为 panic。"""
        assert compute_regime(
            20.0, config=DXY_RULES, dxy=115.0,
            primary_override="dxy",
        ) == REGIME_PANIC

    def test_dxy_high_vol(self):
        """DXY 处于 high_vol 区间时应为 high_vol。"""
        assert compute_regime(
            20.0, config=DXY_RULES, dxy=107.0,
            primary_override="dxy",
        ) == REGIME_HIGH_VOL

    def test_dxy_normal(self):
        """DXY 处于中间区间时应为 normal。"""
        assert compute_regime(
            20.0, config=DXY_RULES, dxy=100.0,
            primary_override="dxy",
        ) == REGIME_NORMAL

    def test_dxy_low_vol(self):
        """DXY 低于 low_vol 阈值时应为 low_vol。"""
        assert compute_regime(
            20.0, config=DXY_RULES, dxy=90.0,
            primary_override="dxy",
        ) == REGIME_LOW_VOL

    def test_dxy_boundary(self):
        """DXY 在 panic/high_vol 与 low_vol/normal 边界处的划分。"""
        assert compute_regime(
            20.0, config=DXY_RULES, dxy=110.1,
            primary_override="dxy",
        ) == REGIME_PANIC
        assert compute_regime(
            20.0, config=DXY_RULES, dxy=110.0,
            primary_override="dxy",
        ) == REGIME_HIGH_VOL
        assert compute_regime(
            20.0, config=DXY_RULES, dxy=94.9,
            primary_override="dxy",
        ) == REGIME_LOW_VOL
        assert compute_regime(
            20.0, config=DXY_RULES, dxy=95.0,
            primary_override="dxy",
        ) == REGIME_NORMAL

    def test_dxy_from_macro_dict(self):
        """从 macro 字典读取 DXY 并计算 regime。"""
        assert compute_regime(
            20.0, config=DXY_RULES, macro={"dxy": 115.0},
            primary_override="dxy",
        ) == REGIME_PANIC

    def test_dxy_defaults_when_no_value(self):
        """无 dxy 且 macro 中无时默认 100.0，对应 normal。"""
        assert compute_regime(
            20.0, config=DXY_RULES, primary_override="dxy",
        ) == REGIME_NORMAL

    def test_dxy_env_thresholds(self):
        """环境变量覆盖 DXY 相关阈值时 load_regime_rules 生效。"""
        env = {
            "REGIME_DXY_PANIC": "112",
            "REGIME_DXY_HIGH_VOL": "108",
            "REGIME_DXY_LOW_VOL": "92",
        }
        with patch.dict(os.environ, env, clear=False):
            rules = load_regime_rules()
            assert rules["dxy_panic"] == 112.0
            assert rules["dxy_high_vol"] == 108.0
            assert rules["dxy_low_vol"] == 92.0


class TestLoadRegimeRules:
    """测试 load_regime_rules 默认值与环境变量。"""

    def test_defaults_include_dxy(self):
        """默认规则包含 DXY、VIX 及主指标字段。"""
        rules = load_regime_rules()
        assert rules["dxy_panic"] == 110
        assert rules["dxy_high_vol"] == 105
        assert rules["dxy_low_vol"] == 95
        assert rules["vix_panic"] == 30
        assert rules["primary_indicator"] == "vix"

    def test_from_env(self):
        """环境变量可覆盖 VIX 阈值与主指标。"""
        env = {
            "REGIME_VIX_PANIC": "40",
            "REGIME_VIX_HIGH_VOL": "32",
            "REGIME_VIX_LOW_VOL": "12",
            "REGIME_PRIMARY_INDICATOR": "vhsi",
        }
        with patch.dict(os.environ, env, clear=False):
            rules = load_regime_rules()
            assert rules["vix_panic"] == 40.0
            assert rules["vix_high_vol"] == 32.0
            assert rules["vix_low_vol"] == 12.0
            assert rules["primary_indicator"] == "vhsi"

    def test_invalid_env_uses_default(self):
        """非法环境变量数值时回退到默认规则。"""
        with patch.dict(
            os.environ, {"REGIME_VIX_PANIC": "not_a_number"},
            clear=False,
        ):
            rules = load_regime_rules()
            assert rules["vix_panic"] == 30


class TestLoadRegimeToWeights:
    """测试 load_regime_to_weights 默认值与环境 JSON。"""

    def test_defaults(self):
        """默认 panic/normal 等档对应权重结构正确。"""
        weights = load_regime_to_weights()
        assert "panic" in weights
        assert weights["panic"]["conservative"] == 0.8
        assert weights["normal"]["balanced"] == 0.6

    def test_from_env(self):
        """REGIME_TO_WEIGHTS_JSON 可覆盖部分档位权重。"""
        custom = {
            "panic": {
                "conservative": 1.0, "balanced": 0.0, "aggressive": 0.0,
            },
        }
        with patch.dict(
            os.environ,
            {"REGIME_TO_WEIGHTS_JSON": json.dumps(custom)},
            clear=False,
        ):
            weights = load_regime_to_weights()
            assert weights["panic"]["conservative"] == 1.0

    def test_invalid_json_uses_default(self):
        """非法 JSON 时回退到默认权重。"""
        with patch.dict(
            os.environ,
            {"REGIME_TO_WEIGHTS_JSON": "{bad json"},
            clear=False,
        ):
            weights = load_regime_to_weights()
            assert weights["panic"]["conservative"] == 0.8


class TestReadMacroValues:
    """测试 read_macro_values 从 K 线 DataFrame 取宏指标。"""

    def _make_df(self, **kwargs):
        """构造单行 DataFrame 供宏指标读取测试。"""
        return pd.DataFrame([kwargs])

    def test_reads_from_last_row(self):
        """从最后一行读取指定列的 VIX、DXY 等。"""
        df = self._make_df(vix=35.0, dxy=108.0, close=100.0)
        result = read_macro_values(df, ["vix", "dxy"])
        assert result == {"vix": 35.0, "dxy": 108.0}

    def test_nan_fallback_to_default(self):
        """列为 NaN 时使用 VIX 等默认值。"""
        df = self._make_df(vix=float("nan"), close=100.0)
        result = read_macro_values(df, ["vix"])
        assert result == {"vix": 18.0}

    def test_missing_column_fallback(self):
        """缺失列时对 VIX、DXY 使用默认回退。"""
        df = self._make_df(close=100.0)
        result = read_macro_values(df, ["vix", "dxy"])
        assert result == {"vix": 18.0, "dxy": 100.0}

    def test_multiple_rows_uses_last(self):
        """多行时仅使用最后一行的指标值。"""
        df = pd.DataFrame([
            {"vix": 10.0, "dxy": 90.0},
            {"vix": 35.0, "dxy": 112.0},
        ])
        result = read_macro_values(df, ["vix", "dxy"])
        assert result == {"vix": 35.0, "dxy": 112.0}


class TestRegimeMixin:
    """测试 RegimeMixin 从 context 计算 regime 与资金比例。"""

    def setup_method(self):
        """每个用例前实例化 RegimeMixin。"""
        self.mixin = RegimeMixin()

    def test_compute_regime_from_context_vix(self):
        """主指标为 VIX 时从 macro 得到 panic 等结果。"""
        macro = {"vix": 35.0}
        config = {"primary_macro_indicator": "vix"}
        assert self.mixin.compute_regime_from_context(
            macro, config,
        ) == REGIME_PANIC

    def test_compute_regime_from_context_dxy(self):
        """主指标为 DXY 时高 DXY 对应 panic。"""
        macro = {"dxy": 115.0}
        config = {"primary_macro_indicator": "dxy"}
        assert self.mixin.compute_regime_from_context(
            macro, config,
        ) == REGIME_PANIC

    def test_compute_regime_from_context_dxy_low(self):
        """主指标为 DXY 时低 DXY 对应 low_vol。"""
        macro = {"dxy": 90.0}
        config = {"primary_macro_indicator": "dxy"}
        assert self.mixin.compute_regime_from_context(
            macro, config,
        ) == REGIME_LOW_VOL

    def test_get_capital_ratio_defaults(self):
        """默认档位与风格下的资金比例映射。"""
        r = self.mixin.get_capital_ratio
        assert r(REGIME_PANIC, "conservative") == 0.8
        assert r(REGIME_PANIC, "aggressive") == 0.0
        assert r(REGIME_NORMAL, "balanced") == 0.6
        assert r(REGIME_LOW_VOL, "aggressive") == 0.6

    def test_get_capital_ratio_unknown_regime(self):
        """未知 regime 时资金比例为 1.0。"""
        assert self.mixin.get_capital_ratio(
            "unknown", "balanced",
        ) == 1.0

    def test_get_capital_ratio_unknown_style(self):
        """未知风格时资金比例为 1.0。"""
        assert self.mixin.get_capital_ratio(
            REGIME_PANIC, "unknown_style",
        ) == 1.0
