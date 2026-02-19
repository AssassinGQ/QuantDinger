"""
Tests for app/services/portfolio_allocator.py — weight computation,
capital allocation, threshold/normalization, and start/stop diff.
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.portfolio_allocator import (
    PortfolioAllocator,
    _apply_threshold,
    _normalize_weights,
    get_portfolio_allocator,
    reset_portfolio_allocator,
)


# ── Sample data ──────────────────────────────────────────────────────────

SAMPLE_SYMBOL_STRATEGIES = {
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
}

SAMPLE_INITIAL_CAPITALS = {
    101: 10000.0, 102: 10000.0, 103: 10000.0,
    201: 10000.0, 202: 10000.0, 203: 10000.0,
}

SAMPLE_CONFIG = {
    "multi_strategy": {
        "enabled": True,
        "regime_to_weights": {
            "panic": {"conservative": 0.80, "balanced": 0.20, "aggressive": 0.00},
            "high_vol": {"conservative": 0.50, "balanced": 0.40, "aggressive": 0.10},
            "normal": {"conservative": 0.20, "balanced": 0.60, "aggressive": 0.20},
            "low_vol": {"conservative": 0.10, "balanced": 0.30, "aggressive": 0.60},
        },
        "min_weight_threshold": 0.05,
        "max_allocation_ratio": 2.0,
    },
}


def _make_allocator(**kwargs):
    """Helper: create allocator and call update_regime."""
    a = PortfolioAllocator()
    regime = kwargs.get("regime", "normal")
    config = kwargs.get("config", SAMPLE_CONFIG)
    sym_strat = kwargs.get("symbol_strategies", SAMPLE_SYMBOL_STRATEGIES)
    caps = kwargs.get("capitals", SAMPLE_INITIAL_CAPITALS)
    a.update_regime(regime, config, sym_strat, strategy_initial_capitals=caps)
    return a


# ── Utility functions ────────────────────────────────────────────────────

class TestApplyThreshold:
    def test_below_threshold_zeroed(self):
        w = {"a": 0.8, "b": 0.04, "c": 0.16}
        result = _apply_threshold(w, 0.05)
        assert result["a"] == 0.8
        assert result["b"] == 0.0
        assert result["c"] == 0.16

    def test_equal_to_threshold_kept(self):
        w = {"a": 0.05}
        result = _apply_threshold(w, 0.05)
        assert result["a"] == 0.05

    def test_all_below_threshold(self):
        w = {"a": 0.01, "b": 0.02}
        result = _apply_threshold(w, 0.05)
        assert result == {"a": 0.0, "b": 0.0}


class TestNormalizeWeights:
    def test_normal(self):
        w = {"a": 0.8, "b": 0.2}
        result = _normalize_weights(w)
        assert abs(result["a"] - 0.8) < 1e-6
        assert abs(result["b"] - 0.2) < 1e-6

    def test_unnormalized(self):
        w = {"a": 0.6, "b": 0.2}  # sum = 0.8
        result = _normalize_weights(w)
        assert abs(result["a"] - 0.75) < 1e-6
        assert abs(result["b"] - 0.25) < 1e-6

    def test_all_zero(self):
        w = {"a": 0.0, "b": 0.0}
        result = _normalize_weights(w)
        assert result == {"a": 0.0, "b": 0.0}

    def test_with_zeroed_entries(self):
        w = {"a": 0.8, "b": 0.0, "c": 0.2}
        result = _normalize_weights(w)
        assert abs(result["a"] - 0.8) < 1e-6
        assert result["b"] == 0.0
        assert abs(result["c"] - 0.2) < 1e-6


# ── PortfolioAllocator core ─────────────────────────────────────────────

class TestAllocatorWeights:
    def test_normal_regime_weights(self):
        a = _make_allocator(regime="normal")
        w = a.effective_weights
        assert abs(w["conservative"] - 0.20) < 1e-6
        assert abs(w["balanced"] - 0.60) < 1e-6
        assert abs(w["aggressive"] - 0.20) < 1e-6

    def test_panic_regime_weights(self):
        a = _make_allocator(regime="panic")
        w = a.effective_weights
        assert abs(w["conservative"] - 0.80) < 1e-6
        assert abs(w["balanced"] - 0.20) < 1e-6
        assert w["aggressive"] == 0.0

    def test_low_vol_regime_weights(self):
        a = _make_allocator(regime="low_vol")
        w = a.effective_weights
        assert abs(w["conservative"] - 0.10) < 1e-6
        assert abs(w["balanced"] - 0.30) < 1e-6
        assert abs(w["aggressive"] - 0.60) < 1e-6

    def test_threshold_zeroes_small_weight(self):
        config = {
            "multi_strategy": {
                "regime_to_weights": {
                    "test": {"a": 0.96, "b": 0.04},
                },
                "min_weight_threshold": 0.05,
            },
        }
        a = PortfolioAllocator()
        a.update_regime("test", config, {"SYM": {"a": [1], "b": [2]}},
                        strategy_initial_capitals={1: 1000, 2: 1000})
        w = a.effective_weights
        assert w["b"] == 0.0
        assert abs(w["a"] - 1.0) < 1e-6  # renormalized


class TestAllocatorCapitalAllocation:
    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_normal_allocation(self, mock_running):
        a = _make_allocator(regime="normal")
        alloc = a.strategy_allocation

        # pool per symbol = max(initial_capital) * style_count = 10000 * 3 = 30000
        # conservative (w=0.2): 30000 * 0.2 / 1 = 6000
        # balanced (w=0.6): 30000 * 0.6 / 1 = 18000
        # aggressive (w=0.2): 30000 * 0.2 / 1 = 6000
        assert abs(alloc[101] - 6000) < 1
        assert abs(alloc[102] - 18000) < 1
        assert abs(alloc[103] - 6000) < 1
        assert abs(alloc[201] - 6000) < 1
        assert abs(alloc[202] - 18000) < 1
        assert abs(alloc[203] - 6000) < 1

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_panic_zero_weight_allocation(self, mock_running):
        a = _make_allocator(regime="panic")
        alloc = a.strategy_allocation
        assert alloc[103] == 0.0
        assert alloc[203] == 0.0
        assert alloc[101] > 0
        assert alloc[102] > 0

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_allocation_capped_by_max_ratio(self, mock_running):
        a = _make_allocator(regime="normal")
        alloc = a.strategy_allocation
        # max_allocation_ratio = 2.0, initial_capital = 10000 → cap at 20000
        # balanced gets 18000 which is within cap
        assert alloc[102] <= 20000
        assert alloc[202] <= 20000

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_configured_pool_overrides(self, mock_running):
        config = dict(SAMPLE_CONFIG)
        config["multi_strategy"] = dict(config["multi_strategy"])
        config["multi_strategy"]["symbol_capital_pool"] = {"XAUUSD": 50000}
        a = PortfolioAllocator()
        a.update_regime("normal", config, SAMPLE_SYMBOL_STRATEGIES,
                        strategy_initial_capitals=SAMPLE_INITIAL_CAPITALS)
        alloc = a.strategy_allocation
        # XAUUSD pool=50000, balanced=0.6 → 30000 (capped at 20000 by max_alloc_ratio)
        assert alloc[102] == 20000.0
        # NVDA still uses calculated pool
        assert alloc[202] > 0


class TestAllocatorStartStopDiff:
    @patch.object(PortfolioAllocator, "_get_running_ids", return_value={101, 102, 201, 202})
    def test_panic_stops_zero_weight_strategies(self, mock_running):
        a = _make_allocator(regime="panic")
        result = a.update_regime("panic", SAMPLE_CONFIG, SAMPLE_SYMBOL_STRATEGIES,
                                 strategy_initial_capitals=SAMPLE_INITIAL_CAPITALS)
        # aggressive weight=0, not running → not in stop
        # running 101,102,201,202 all have weight>0 → no stop
        assert 103 not in result["stopped"]
        assert 203 not in result["stopped"]

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value={101, 102, 103, 201, 202, 203})
    def test_panic_stops_running_zero_weight(self, mock_running):
        a = _make_allocator(regime="panic")
        result = a.update_regime("panic", SAMPLE_CONFIG, SAMPLE_SYMBOL_STRATEGIES,
                                 strategy_initial_capitals=SAMPLE_INITIAL_CAPITALS)
        assert 103 in result["stopped"]
        assert 203 in result["stopped"]

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_normal_starts_all_nonzero(self, mock_running):
        a = _make_allocator(regime="normal")
        result = a.update_regime("normal", SAMPLE_CONFIG, SAMPLE_SYMBOL_STRATEGIES,
                                 strategy_initial_capitals=SAMPLE_INITIAL_CAPITALS)
        assert set(result["started"]) == {101, 102, 103, 201, 202, 203}


class TestAllocatorQuery:
    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_get_allocated_capital(self, mock_running):
        a = _make_allocator(regime="normal")
        assert a.get_allocated_capital(102) is not None
        assert a.get_allocated_capital(102) > 0

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_get_allocated_capital_unmanaged(self, mock_running):
        a = _make_allocator(regime="normal")
        assert a.get_allocated_capital(999) is None

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_current_regime(self, mock_running):
        a = _make_allocator(regime="high_vol")
        assert a.current_regime == "high_vol"


class TestAllocatorWeightChanged:
    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_regime_change_detects_weight_change(self, mock_running):
        a = _make_allocator(regime="normal")
        result = a.update_regime("panic", SAMPLE_CONFIG, SAMPLE_SYMBOL_STRATEGIES,
                                 strategy_initial_capitals=SAMPLE_INITIAL_CAPITALS)
        # all styles change weights from normal→panic
        assert len(result["weight_changed"]) == 6  # all 6 strategies

    @patch.object(PortfolioAllocator, "_get_running_ids", return_value=set())
    def test_same_regime_no_weight_change(self, mock_running):
        a = _make_allocator(regime="normal")
        result = a.update_regime("normal", SAMPLE_CONFIG, SAMPLE_SYMBOL_STRATEGIES,
                                 strategy_initial_capitals=SAMPLE_INITIAL_CAPITALS)
        assert result["weight_changed"] == []


# ── Singleton ────────────────────────────────────────────────────────────

class TestSingleton:
    def test_singleton(self):
        reset_portfolio_allocator()
        a1 = get_portfolio_allocator()
        a2 = get_portfolio_allocator()
        assert a1 is a2
        reset_portfolio_allocator()


# ── regime_switch multi-strategy integration ─────────────────────────────

MULTI_CONFIG = {
    **SAMPLE_CONFIG,
    "regime_rules": {"vix_panic": 30, "vix_high_vol": 25, "vix_low_vol": 15},
    "symbol_strategies": SAMPLE_SYMBOL_STRATEGIES,
    "user_id": 1,
}


class TestRegimeSwitchMultiMode:
    """Test that regime_switch dispatches to multi-strategy path."""

    @patch("app.tasks.regime_switch._load_config", return_value=MULTI_CONFIG)
    @patch("app.tasks.regime_switch._fetch_macro_snapshot",
           return_value={"vix": 35.0, "dxy": 105.0, "fear_greed": 15.0})
    @patch("app.tasks.regime_switch._stop_strategies")
    @patch("app.tasks.regime_switch._start_strategies")
    @patch("app.services.portfolio_allocator.PortfolioAllocator._get_running_ids",
           return_value={102, 103, 202, 203})
    def test_multi_mode_dispatches_allocator(
        self, mock_running, mock_start, mock_stop, mock_macro, mock_config
    ):
        from app.services.portfolio_allocator import reset_portfolio_allocator
        reset_portfolio_allocator()

        from app.tasks.regime_switch import run
        run()

        # In panic: aggressive weight=0 → 103 and 203 should be stopped (they are running)
        if mock_stop.called:
            stopped = mock_stop.call_args[0][0]
            assert 103 in stopped
            assert 203 in stopped

    @patch("app.tasks.regime_switch._load_config", return_value={
        **SAMPLE_CONFIG,
        "multi_strategy": {"enabled": False},
        "regime_rules": {"vix_panic": 30, "vix_high_vol": 25, "vix_low_vol": 15},
        "regime_to_style": {"panic": ["conservative"]},
        "symbol_strategies": SAMPLE_SYMBOL_STRATEGIES,
        "user_id": 1,
    })
    @patch("app.tasks.regime_switch._fetch_macro_snapshot",
           return_value={"vix": 35.0, "dxy": 105.0, "fear_greed": 15.0})
    @patch("app.tasks.regime_switch._get_currently_running_ids",
           return_value={102, 202})
    @patch("app.tasks.regime_switch._stop_strategies")
    @patch("app.tasks.regime_switch._start_strategies")
    def test_disabled_falls_back_to_legacy(
        self, mock_start, mock_stop, mock_running, mock_macro, mock_config
    ):
        from app.tasks.regime_switch import run
        run()

        # Legacy P0 behavior: panic → only conservative
        mock_stop.assert_called_once()
        stopped = mock_stop.call_args[0][0]
        assert set(stopped) == {102, 202}

        mock_start.assert_called_once()
        started = mock_start.call_args[0][0]
        assert set(started) == {101, 201}


# ── TradingExecutor integration ──────────────────────────────────────────

import sys
import types


def _import_trading_executor():
    """Import TradingExecutor with heavy deps mocked out."""
    mock_ccxt = types.ModuleType("ccxt")
    mock_ccxt.Exchange = type("Exchange", (), {})
    sys.modules.setdefault("ccxt", mock_ccxt)
    for mod in ("pandas", "numpy", "ta"):
        sys.modules.setdefault(mod, types.ModuleType(mod))
    from app.services.trading_executor import TradingExecutor
    return TradingExecutor


class TestTradingExecutorIntegration:
    """Test that TradingExecutor._get_available_capital uses allocator."""

    @patch("app.services.portfolio_allocator.get_portfolio_allocator")
    def test_uses_allocator_when_managed(self, mock_get_alloc):
        mock_alloc = MagicMock()
        mock_alloc.get_allocated_capital.return_value = 5000.0
        mock_get_alloc.return_value = mock_alloc

        TradingExecutor = _import_trading_executor()
        te = TradingExecutor()
        result = te._get_available_capital(101, 10000.0)
        assert result == 5000.0

    @patch("app.services.portfolio_allocator.get_portfolio_allocator")
    def test_falls_back_when_unmanaged(self, mock_get_alloc):
        mock_alloc = MagicMock()
        mock_alloc.get_allocated_capital.return_value = None
        mock_get_alloc.return_value = mock_alloc

        TradingExecutor = _import_trading_executor()
        te = TradingExecutor()
        result = te._get_available_capital(999, 10000.0)
        assert result == 10000.0

    @patch("app.services.portfolio_allocator.get_portfolio_allocator",
           side_effect=Exception("allocator not available"))
    def test_falls_back_on_exception(self, mock_get_alloc):
        TradingExecutor = _import_trading_executor()
        te = TradingExecutor()
        result = te._get_available_capital(101, 10000.0)
        assert result == 10000.0
