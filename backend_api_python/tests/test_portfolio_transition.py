"""
Tests for P1b: gradual weight transition, over-allocation handling,
and freeze_new_entry mechanism.
"""

import pytest
from unittest.mock import patch

from app.services.portfolio_allocator import (
    PortfolioAllocator,
    _apply_gradual_transition,
    _normalize_weights,
)


# ── Sample data ──────────────────────────────────────────────────────────

SAMPLE_SYMBOL_STRATEGIES = {
    "XAUUSD": {
        "conservative": [101],
        "balanced": [102],
        "aggressive": [103],
    },
}

SAMPLE_CAPITALS = {101: 10000.0, 102: 10000.0, 103: 10000.0}


def _make_config(mode="immediate", max_step=0.20, enabled=True):
    return {
        "multi_strategy": {
            "enabled": enabled,
            "regime_to_weights": {
                "panic": {"conservative": 0.80, "balanced": 0.20, "aggressive": 0.00},
                "normal": {"conservative": 0.20, "balanced": 0.60, "aggressive": 0.20},
                "low_vol": {"conservative": 0.10, "balanced": 0.30, "aggressive": 0.60},
            },
            "min_weight_threshold": 0.05,
            "max_allocation_ratio": 2.0,
            "transition": {
                "mode": mode,
                "max_step_per_tick": max_step,
            },
        },
    }


# ── _apply_gradual_transition ─────────────────────────────────────────────

class TestGradualTransition:
    def test_immediate_mode_jumps(self):
        current = {"a": 0.5, "b": 0.3, "c": 0.2}
        target = {"a": 0.8, "b": 0.1, "c": 0.1}
        result = _apply_gradual_transition(current, target, {"mode": "immediate"})
        assert abs(result["a"] - 0.8) < 1e-6
        assert abs(result["b"] - 0.1) < 1e-6

    def test_empty_current_jumps(self):
        target = {"a": 0.6, "b": 0.4}
        result = _apply_gradual_transition({}, target, {"mode": "gradual", "max_step_per_tick": 0.1})
        assert abs(result["a"] - 0.6) < 1e-6

    def test_gradual_caps_step(self):
        current = {"a": 0.20, "b": 0.60, "c": 0.20}
        target = {"a": 0.80, "b": 0.20, "c": 0.00}
        cfg = {"mode": "gradual", "max_step_per_tick": 0.20}
        result = _apply_gradual_transition(current, target, cfg)

        # a: 0.20 → 0.80, diff=0.60, capped to +0.20 → 0.40
        # b: 0.60 → 0.20, diff=-0.40, capped to -0.20 → 0.40
        # c: 0.20 → 0.00, diff=-0.20, exactly step → 0.00
        # Before normalization: a=0.40, b=0.40, c=0.00 → sum=0.80 → normalized
        assert result["c"] == 0.0
        assert result["a"] > 0.20
        assert result["a"] < 0.80
        assert result["b"] < 0.60
        assert result["b"] > 0.20

    def test_gradual_reaches_target_in_steps(self):
        current = {"a": 0.20, "b": 0.80}
        target = {"a": 0.80, "b": 0.20}
        cfg = {"mode": "gradual", "max_step_per_tick": 0.20}

        for _ in range(10):
            current = _apply_gradual_transition(current, target, cfg)

        assert abs(current["a"] - 0.80) < 1e-4
        assert abs(current["b"] - 0.20) < 1e-4

    def test_gradual_small_diff_jumps(self):
        current = {"a": 0.59, "b": 0.41}
        target = {"a": 0.60, "b": 0.40}
        cfg = {"mode": "gradual", "max_step_per_tick": 0.20}
        result = _apply_gradual_transition(current, target, cfg)
        assert abs(result["a"] - 0.60) < 1e-4
        assert abs(result["b"] - 0.40) < 1e-4


# ── Allocator gradual transition integration ──────────────────────────────

class TestAllocatorGradualTransition:
    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_immediate_transition(self, mock_running):
        a = PortfolioAllocator()
        config = _make_config(mode="immediate")
        a.update_regime("normal", config, SAMPLE_SYMBOL_STRATEGIES,
                        strategy_initial_capitals=SAMPLE_CAPITALS)
        a.update_regime("panic", config, SAMPLE_SYMBOL_STRATEGIES)

        w = a.effective_weights
        assert abs(w["conservative"] - 0.80) < 1e-6
        assert abs(w["balanced"] - 0.20) < 1e-6

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_gradual_first_tick_partial(self, mock_running):
        a = PortfolioAllocator()
        config = _make_config(mode="gradual", max_step=0.20)

        a.update_regime("normal", config, SAMPLE_SYMBOL_STRATEGIES,
                        strategy_initial_capitals=SAMPLE_CAPITALS)
        w_before = a.effective_weights.copy()

        a.update_regime("panic", config, SAMPLE_SYMBOL_STRATEGIES)
        w_after = a.effective_weights

        # conservative should increase but not jump to 0.80
        assert w_after["conservative"] > w_before["conservative"]
        assert w_after["conservative"] < 0.80

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_gradual_converges(self, mock_running):
        a = PortfolioAllocator()
        config = _make_config(mode="gradual", max_step=0.20)

        a.update_regime("normal", config, SAMPLE_SYMBOL_STRATEGIES,
                        strategy_initial_capitals=SAMPLE_CAPITALS)

        target = config["multi_strategy"]["regime_to_weights"]["panic"]
        for _ in range(20):
            a.update_regime("panic", config, SAMPLE_SYMBOL_STRATEGIES)

        w = a.effective_weights
        # Should have converged (aggressive=0 after threshold, then normalized)
        assert w["aggressive"] == 0.0
        assert w["conservative"] > 0.5

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_target_weights_reflect_target(self, mock_running):
        a = PortfolioAllocator()
        config = _make_config(mode="gradual", max_step=0.10)
        a.update_regime("normal", config, SAMPLE_SYMBOL_STRATEGIES,
                        strategy_initial_capitals=SAMPLE_CAPITALS)
        a.update_regime("panic", config, SAMPLE_SYMBOL_STRATEGIES)

        # target_weights should be the final target, not the gradual effective
        tw = a.target_weights
        assert abs(tw["conservative"] - 0.80) < 1e-6
        assert abs(tw["balanced"] - 0.20) < 1e-6
        assert tw["aggressive"] == 0.0


# ── Freeze / over-allocation ──────────────────────────────────────────────

class TestFreezeAndOverAllocation:
    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_allocation_decrease_freezes(self, mock_running):
        a = PortfolioAllocator()
        config = _make_config(mode="immediate")
        a.update_regime("normal", config, SAMPLE_SYMBOL_STRATEGIES,
                        strategy_initial_capitals=SAMPLE_CAPITALS)

        old_balanced = a.strategy_allocation[102]

        a.update_regime("panic", config, SAMPLE_SYMBOL_STRATEGIES)
        new_balanced = a.strategy_allocation[102]

        assert new_balanced < old_balanced
        assert a.is_frozen(102) is True

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_allocation_increase_unfreezes(self, mock_running):
        a = PortfolioAllocator()
        config = _make_config(mode="immediate")

        # normal → panic (freezes balanced)
        a.update_regime("normal", config, SAMPLE_SYMBOL_STRATEGIES,
                        strategy_initial_capitals=SAMPLE_CAPITALS)
        a.update_regime("panic", config, SAMPLE_SYMBOL_STRATEGIES)
        assert a.is_frozen(102) is True

        # panic → normal (balanced allocation increases → unfreeze)
        a.update_regime("normal", config, SAMPLE_SYMBOL_STRATEGIES)
        assert a.is_frozen(102) is False

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_zero_allocation_clears_freeze(self, mock_running):
        a = PortfolioAllocator()
        config = _make_config(mode="immediate")
        a.update_regime("normal", config, SAMPLE_SYMBOL_STRATEGIES,
                        strategy_initial_capitals=SAMPLE_CAPITALS)
        a.update_regime("panic", config, SAMPLE_SYMBOL_STRATEGIES)
        # aggressive goes to 0, should not be frozen (cleared)
        assert a.is_frozen(103) is False

    def test_manual_freeze_unfreeze(self):
        a = PortfolioAllocator()
        assert a.is_frozen(999) is False
        a.freeze_strategy(999)
        assert a.is_frozen(999) is True
        a.unfreeze_strategy(999)
        assert a.is_frozen(999) is False

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_frozen_strategies_property(self, mock_running):
        a = PortfolioAllocator()
        config = _make_config(mode="immediate")
        a.update_regime("normal", config, SAMPLE_SYMBOL_STRATEGIES,
                        strategy_initial_capitals=SAMPLE_CAPITALS)
        a.update_regime("panic", config, SAMPLE_SYMBOL_STRATEGIES)

        frozen = a.frozen_strategies
        assert isinstance(frozen, dict)
        # At least balanced (102) should be frozen (allocation decreased)
        assert 102 in frozen
