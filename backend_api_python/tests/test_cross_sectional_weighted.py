"""
Test suite for cross sectional weighted strategy.
"""
import time
from unittest.mock import patch

import pandas as pd

from app.strategies.cross_sectional_weighted_indicator import (
    run_cross_sectional_weighted_indicator
)
from app.strategies.cross_sectional_weighted_signals import (
    generate_cross_sectional_weighted_signals
)
from app.strategies.cross_sectional_weighted import CrossSectionalWeightedStrategy

class TestCrossSectionalWeightedStrategy:
    """Test suite for CrossSectionalWeightedStrategy class and related functions."""

    def test_indicator_run(self):
        """Test basic execution of run_cross_sectional_weighted_indicator."""
        codes = {
            "BTC": "signal='long'",
            "ETH": "signal='short'",
            "XRP": "signal='flat'"
        }
        data = {
            "BTC": pd.DataFrame({"close": [1]}),
            "ETH": pd.DataFrame({"close": [2]}),
            "XRP": pd.DataFrame({"close": [3]}),
        }
        config = {}

        result = run_cross_sectional_weighted_indicator(codes, data, config)

        assert "weights" in result
        assert "signals" in result

        assert result["weights"]["BTC"] == 1
        assert result["weights"]["ETH"] == 1
        assert result["weights"]["XRP"] == 0

        assert result["signals"]["BTC"] == 1
        assert result["signals"]["ETH"] == -1
        assert result["signals"]["XRP"] == 0

    def test_generate_signals(self):
        """Test generation of signals from weights and current positions."""
        weights = {"BTC": 0.5, "ETH": 0.3}
        signals = {"BTC": 1, "ETH": -1, "SOL": 0}

        current_positions = [
            {"symbol": "BTC", "side": "long", "size": 1.0},
            {"symbol": "ETH", "side": "long", "size": 1.0},
            {"symbol": "SOL", "side": "short", "size": 1.0},
        ]

        result = generate_cross_sectional_weighted_signals(weights, signals, current_positions)

        assert len(result) == 4
        assert any(s["type"] == "close_long" and s["symbol"] == "ETH" for s in result)
        assert any(s["type"] == "close_short" and s["symbol"] == "SOL" for s in result)
        open_btc = next(s for s in result if s["type"] == "open_long" and s["symbol"] == "BTC")
        open_eth = next(s for s in result if s["type"] == "open_short" and s["symbol"] == "ETH")

        assert open_btc["position_size"] == 0.5
        assert open_btc["target_weight"] == 0.5

        assert open_eth["position_size"] == 0.3
        assert open_eth["target_weight"] == 0.3

    def test_indicator_run_nested_multiple(self):
        """Test nested format: multiple indicators per style, regime_weight evenly split."""
        codes = {
            "A": {
                "aggressive": ["signal=1", "signal=1"],
                "conservative": ["signal=-1"]
            }
        }
        data = {"A": pd.DataFrame({"vix": [10], "vhsi": [10], "fear_greed": [80], "c": [1]})}
        # low_vol regime (vix=10 < 15): aggressive=0.6, conservative=0.1
        # aggressive has 2 codes => regime_weight = 0.6/2 = 0.3 each
        # Code1: signal=1 * 0.3 = +0.3
        # Code2: signal=1 * 0.3 = +0.3
        # conservative has 1 code => regime_weight = 0.1
        # Code3: signal=-1 * 0.1 = -0.1
        # combined = +0.3 + 0.3 - 0.1 = +0.5
        res = run_cross_sectional_weighted_indicator(codes, data, {})
        assert res["signals"]["A"] == 1
        assert abs(res["weights"]["A"] - 0.5) < 1e-6

    def test_indicator_run_with_macro_config(self):
        """Test that custom macro_indicators and primary_macro_indicator are respected."""
        codes = {
            "A": {
                "aggressive": "signal=1",
                "conservative": "signal=-1"
            }
        }
        # primary_macro_indicator=fear_greed, fg=15 < fg_extreme_fear(20) => panic
        data = {"A": pd.DataFrame({"vix": [12], "fear_greed": [15], "c": [1]})}
        tc = {
            "macro_indicators": ["vix", "fear_greed"],
            "primary_macro_indicator": "fear_greed"
        }
        res = run_cross_sectional_weighted_indicator(codes, data, tc)
        meta = res.get("metadata") or {}
        assert meta.get("primary_indicator") == "fear_greed"
        assert meta.get("current_regime") == "panic"
        # Panic regime: conservative=0.8, aggressive=0.0
        # Only conservative contributes: signal=-1 * 0.8 = -0.8
        assert res["signals"]["A"] == -1
        assert abs(res["weights"]["A"] - 0.8) < 1e-6

    def test_indicator_run_edge_cases(self):
        """Test indicator run edge cases: missing data, invalid codes, unknown signal."""
        codes = {"A": "signal=1", "B": "bad code"}
        data = {
            "A": pd.DataFrame(),
            "B": pd.DataFrame({"c": [1]}),
            "C": pd.DataFrame({"c": [1]})
        }
        res = run_cross_sectional_weighted_indicator(codes, data, {})
        # A: empty df => skipped; B: exception => signal=0, weight=0; C: no code => skipped
        assert res["weights"] == {"B": 0}
        assert res["signals"] == {"B": 0}

        # Unknown signal string defaults to 0
        codes2 = {"A": "signal='unknown'"}
        data2 = {"A": pd.DataFrame({"c": [1]})}
        res2 = run_cross_sectional_weighted_indicator(codes2, data2, {})
        assert res2["signals"]["A"] == 0

    def test_generate_signals_edge_cases(self):
        """Test edge cases when generating signals like wrong side and zeros."""
        weights = {"A": 0.5, "B": 0.0, "C": -1}
        signals = {"A": 1, "B": 1, "C": 1}
        current = [{"symbol": "A", "side": "short", "size": 1.0}]
        res = generate_cross_sectional_weighted_signals(weights, signals, current)

        assert len(res) == 2
        assert res[0]["type"] == "close_short" and res[0]["symbol"] == "A"
        assert res[1]["type"] == "open_long" and res[1]["symbol"] == "A"

        weights2 = {"A": 0.5}
        signals2 = {"A": -1}
        current2 = [{"symbol": "A", "side": "long", "size": 1.0}]
        res2 = generate_cross_sectional_weighted_signals(weights2, signals2, current2)
        assert len(res2) == 2
        assert res2[0]["type"] == "close_long" and res2[0]["symbol"] == "A"

    def test_strategy_class_edge_cases(self):
        """Test edge cases in CrossSectionalWeightedStrategy."""
        strat = CrossSectionalWeightedStrategy()

        res1 = strat.get_signals({"data": {}})
        assert res1 == ([], True, False, None)

        mock_indicator = (
            "app.strategies.cross_sectional_weighted.run_cross_sectional_weighted_indicator"
        )
        mock_gen_signals = (
            "app.strategies.cross_sectional_weighted.generate_cross_sectional_weighted_signals"
        )

        with patch(mock_indicator) as mock_run:
            mock_run.return_value = {}
            res2 = strat.get_signals({"data": {"A": "df"}})
            assert res2 == ([], True, False, None)

        with patch(mock_indicator) as mock_run:
            mock_run.return_value = {"weights": {}, "signals": {}}
            with patch(mock_gen_signals) as mock_gen:
                mock_gen.return_value = []
                res3 = strat.get_signals({"data": {"A": "df"}})
                assert res3 == ([], True, True, None)

        strat = CrossSectionalWeightedStrategy()
        assert strat.need_macro_info() is True

        req = strat.get_data_request(
            1,
            {"trading_config": {"symbol_indicators": {"A": 1, "B": 2}}},
            time.time()
        )
        assert set(req["symbol_list"]) == {"A", "B"}
        assert req["need_macro"] is True

        ctx = {
            "strategy_id": 1,
            "trading_config": {"symbol_indicators": {"A": 1}},
            "data": {"A": pd.DataFrame({"close": [1]})}
        }

        with patch(mock_indicator) as mock_run:
            mock_run.return_value = {"weights": {"A": 0.5}, "signals": {"A": 1}}

            with patch(mock_gen_signals) as mock_gen:
                mock_gen.return_value = [{"symbol": "A", "type": "open_long"}]

                signals, keep_running, update_rebalance, _ = strat.get_signals(ctx)

                assert len(signals) == 1
                assert signals[0]["symbol"] == "A"
                assert keep_running is True
                assert update_rebalance is True
