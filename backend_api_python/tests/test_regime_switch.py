"""
Tests for app/tasks/regime_switch.py — regime computation, target strategy
calculation, and the run() orchestration logic.
"""

import pytest
from unittest.mock import patch, MagicMock, call


# ── sample config ────────────────────────────────────────────────────────

SAMPLE_CONFIG = {
    "regime_rules": {
        "vix_panic": 30,
        "vix_high_vol": 25,
        "vix_low_vol": 15,
    },
    "regime_to_style": {
        "panic": ["conservative"],
        "high_vol": ["conservative", "balanced"],
        "normal": ["balanced"],
        "low_vol": ["balanced", "aggressive"],
    },
    "symbol_strategies": {
        "XAUUSD": {
            "conservative": [101],
            "balanced": [102],
            "aggressive": [103],
        },
        "NVDA": {
            "conservative": [201],
            "balanced": [202],
            "aggressive": [203],
        },
    },
    "user_id": 1,
    "interval_minutes": 15,
}


# ── compute_regime ───────────────────────────────────────────────────────

class TestComputeRegime:
    def test_panic(self):
        from app.tasks.regime_switch import compute_regime
        assert compute_regime(35.0, config=SAMPLE_CONFIG) == "panic"

    def test_high_vol(self):
        from app.tasks.regime_switch import compute_regime
        assert compute_regime(27.0, config=SAMPLE_CONFIG) == "high_vol"

    def test_normal(self):
        from app.tasks.regime_switch import compute_regime
        assert compute_regime(20.0, config=SAMPLE_CONFIG) == "normal"

    def test_low_vol(self):
        from app.tasks.regime_switch import compute_regime
        assert compute_regime(12.0, config=SAMPLE_CONFIG) == "low_vol"

    def test_boundary_panic(self):
        from app.tasks.regime_switch import compute_regime
        assert compute_regime(30.1, config=SAMPLE_CONFIG) == "panic"
        assert compute_regime(30.0, config=SAMPLE_CONFIG) == "high_vol"

    def test_boundary_low_vol(self):
        from app.tasks.regime_switch import compute_regime
        assert compute_regime(14.9, config=SAMPLE_CONFIG) == "low_vol"
        assert compute_regime(15.0, config=SAMPLE_CONFIG) == "normal"


# ── compute_target_strategy_ids ──────────────────────────────────────────

class TestComputeTargetStrategyIds:
    def test_panic_only_conservative(self):
        from app.tasks.regime_switch import compute_target_strategy_ids
        ids = compute_target_strategy_ids("panic", config=SAMPLE_CONFIG)
        assert ids == {101, 201}

    def test_normal_only_balanced(self):
        from app.tasks.regime_switch import compute_target_strategy_ids
        ids = compute_target_strategy_ids("normal", config=SAMPLE_CONFIG)
        assert ids == {102, 202}

    def test_low_vol_balanced_and_aggressive(self):
        from app.tasks.regime_switch import compute_target_strategy_ids
        ids = compute_target_strategy_ids("low_vol", config=SAMPLE_CONFIG)
        assert ids == {102, 103, 202, 203}

    def test_high_vol_conservative_and_balanced(self):
        from app.tasks.regime_switch import compute_target_strategy_ids
        ids = compute_target_strategy_ids("high_vol", config=SAMPLE_CONFIG)
        assert ids == {101, 102, 201, 202}

    def test_empty_config(self):
        from app.tasks.regime_switch import compute_target_strategy_ids
        ids = compute_target_strategy_ids("normal", config={})
        assert ids == set()


# ── _get_all_managed_ids ─────────────────────────────────────────────────

class TestGetAllManagedIds:
    def test_returns_all_ids(self):
        from app.tasks.regime_switch import _get_all_managed_ids
        ids = _get_all_managed_ids(config=SAMPLE_CONFIG)
        assert ids == {101, 102, 103, 201, 202, 203}


# ── run() orchestration ─────────────────────────────────────────────────

class TestRunOrchestration:
    """Test the full run() flow with mocked dependencies."""

    @patch("app.tasks.regime_switch._load_config", return_value=SAMPLE_CONFIG)
    @patch("app.tasks.regime_switch._fetch_macro_snapshot",
           return_value={"vix": 35.0, "dxy": 105.0, "fear_greed": 15.0})
    @patch("app.tasks.regime_switch._get_currently_running_ids",
           return_value={102, 202})  # balanced currently running
    @patch("app.tasks.regime_switch._stop_strategies")
    @patch("app.tasks.regime_switch._start_strategies")
    def test_panic_switches_to_conservative(
        self, mock_start, mock_stop, mock_running, mock_macro, mock_config
    ):
        from app.tasks.regime_switch import run

        run()

        # panic → conservative → {101, 201}
        # currently running & managed: {102, 202}
        # should stop {102, 202}, start {101, 201}
        mock_stop.assert_called_once()
        stopped_ids = mock_stop.call_args[0][0]
        assert set(stopped_ids) == {102, 202}

        mock_start.assert_called_once()
        started_ids = mock_start.call_args[0][0]
        assert set(started_ids) == {101, 201}

    @patch("app.tasks.regime_switch._load_config", return_value=SAMPLE_CONFIG)
    @patch("app.tasks.regime_switch._fetch_macro_snapshot",
           return_value={"vix": 20.0, "dxy": 100.0, "fear_greed": 50.0})
    @patch("app.tasks.regime_switch._get_currently_running_ids",
           return_value={102, 202})  # already running balanced
    @patch("app.tasks.regime_switch._stop_strategies")
    @patch("app.tasks.regime_switch._start_strategies")
    def test_normal_no_change(
        self, mock_start, mock_stop, mock_running, mock_macro, mock_config
    ):
        from app.tasks.regime_switch import run

        run()

        # normal → balanced → {102, 202}, already running → no change
        mock_stop.assert_not_called()
        mock_start.assert_not_called()

    @patch("app.tasks.regime_switch._load_config", return_value=SAMPLE_CONFIG)
    @patch("app.tasks.regime_switch._fetch_macro_snapshot",
           return_value={"vix": 12.0, "dxy": 98.0, "fear_greed": 70.0})
    @patch("app.tasks.regime_switch._get_currently_running_ids",
           return_value={102, 202})  # balanced running
    @patch("app.tasks.regime_switch._stop_strategies")
    @patch("app.tasks.regime_switch._start_strategies")
    def test_low_vol_adds_aggressive(
        self, mock_start, mock_stop, mock_running, mock_macro, mock_config
    ):
        from app.tasks.regime_switch import run

        run()

        # low_vol → balanced + aggressive → {102, 103, 202, 203}
        # running & managed: {102, 202}
        # stop: empty, start: {103, 203}
        stopped_ids = mock_stop.call_args[0][0] if mock_stop.called else []
        assert set(stopped_ids) == set()

        mock_start.assert_called_once()
        started_ids = mock_start.call_args[0][0]
        assert set(started_ids) == {103, 203}

    @patch("app.tasks.regime_switch._load_config", return_value={})
    @patch("app.tasks.regime_switch._stop_strategies")
    @patch("app.tasks.regime_switch._start_strategies")
    def test_empty_config_noop(self, mock_start, mock_stop, mock_config):
        from app.tasks.regime_switch import run

        run()

        mock_stop.assert_not_called()
        mock_start.assert_not_called()

    @patch("app.tasks.regime_switch._load_config", return_value=SAMPLE_CONFIG)
    @patch("app.tasks.regime_switch._fetch_macro_snapshot",
           return_value={"vix": 35.0, "dxy": 105.0, "fear_greed": 15.0})
    @patch("app.tasks.regime_switch._get_currently_running_ids",
           return_value={102, 202, 999})  # 999 is not managed
    @patch("app.tasks.regime_switch._stop_strategies")
    @patch("app.tasks.regime_switch._start_strategies")
    def test_only_manages_configured_strategies(
        self, mock_start, mock_stop, mock_running, mock_macro, mock_config
    ):
        from app.tasks.regime_switch import run

        run()

        # 999 is running but not in managed set → should NOT be stopped
        stopped_ids = mock_stop.call_args[0][0]
        assert 999 not in stopped_ids
        assert set(stopped_ids) == {102, 202}
