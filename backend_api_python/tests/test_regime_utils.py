"""
Tests for app/strategies/regime_utils.py — regime computation and .env config loading.
Migrated from test_regime_switch.py::TestComputeRegime with new .env-based tests.
"""
import json
import os
from unittest.mock import patch

from app.strategies.regime_utils import (
    compute_regime,
    load_regime_rules,
    load_regime_to_weights,
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


class TestComputeRegime:
    """Migrated from test_regime_switch.py::TestComputeRegime."""

    def test_panic(self):
        assert compute_regime(35.0, config=SAMPLE_RULES) == "panic"

    def test_high_vol(self):
        assert compute_regime(27.0, config=SAMPLE_RULES) == "high_vol"

    def test_normal(self):
        assert compute_regime(20.0, config=SAMPLE_RULES) == "normal"

    def test_low_vol(self):
        assert compute_regime(12.0, config=SAMPLE_RULES) == "low_vol"

    def test_boundary_panic(self):
        assert compute_regime(30.1, config=SAMPLE_RULES) == "panic"
        assert compute_regime(30.0, config=SAMPLE_RULES) == "high_vol"

    def test_boundary_low_vol(self):
        assert compute_regime(14.9, config=SAMPLE_RULES) == "low_vol"
        assert compute_regime(15.0, config=SAMPLE_RULES) == "normal"

    def test_vhsi_primary_indicator(self):
        cfg = {
            "regime_rules": {
                **SAMPLE_RULES["regime_rules"],
                "primary_indicator": "vhsi",
            }
        }
        assert compute_regime(35.0, config=cfg, vhsi=35.0, primary_override="vhsi") == "panic"
        assert compute_regime(20.0, config=cfg, vhsi=12.0, primary_override="vhsi") == "low_vol"

    def test_fear_greed_primary(self):
        cfg = {"regime_rules": {"fg_extreme_fear": 20, "fg_high_fear": 35, "fg_low_greed": 65}}
        assert compute_regime(20.0, fear_greed=10.0, config=cfg, primary_override="fear_greed") == "panic"
        assert compute_regime(20.0, fear_greed=30.0, config=cfg, primary_override="fear_greed") == "high_vol"
        assert compute_regime(20.0, fear_greed=50.0, config=cfg, primary_override="fear_greed") == "normal"
        assert compute_regime(20.0, fear_greed=70.0, config=cfg, primary_override="fear_greed") == "low_vol"

    def test_civix_primary(self):
        cfg = {"regime_rules": {"civix_panic": 30, "civix_high_vol": 25, "civix_low_vol": 15}}
        macro = {"civix": 35.0}
        assert compute_regime(20.0, config=cfg, macro=macro, primary_override="civix") == "panic"
        macro = {"civix": 12.0}
        assert compute_regime(20.0, config=cfg, macro=macro, primary_override="civix") == "low_vol"


class TestLoadRegimeRules:
    def test_defaults(self):
        rules = load_regime_rules()
        assert rules["vix_panic"] == 30
        assert rules["vix_high_vol"] == 25
        assert rules["vix_low_vol"] == 15
        assert rules["fg_extreme_fear"] == 20
        assert rules["primary_indicator"] == "vix"

    def test_from_env(self):
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
        with patch.dict(os.environ, {"REGIME_VIX_PANIC": "not_a_number"}, clear=False):
            rules = load_regime_rules()
            assert rules["vix_panic"] == 30


class TestLoadRegimeToWeights:
    def test_defaults(self):
        weights = load_regime_to_weights()
        assert "panic" in weights
        assert weights["panic"]["conservative"] == 0.8
        assert weights["normal"]["balanced"] == 0.6

    def test_from_env(self):
        custom = {"panic": {"conservative": 1.0, "balanced": 0.0, "aggressive": 0.0}}
        with patch.dict(os.environ, {"REGIME_TO_WEIGHTS_JSON": json.dumps(custom)}, clear=False):
            weights = load_regime_to_weights()
            assert weights["panic"]["conservative"] == 1.0

    def test_invalid_json_uses_default(self):
        with patch.dict(os.environ, {"REGIME_TO_WEIGHTS_JSON": "{bad json"}, clear=False):
            weights = load_regime_to_weights()
            assert weights["panic"]["conservative"] == 0.8
