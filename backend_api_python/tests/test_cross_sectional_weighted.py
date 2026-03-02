"""
Test suite for cross sectional weighted strategy.
"""
import time
from unittest.mock import patch

import pandas as pd

from app.strategies.cross_sectional_weighted_indicator import run_cross_sectional_weighted_indicator
from app.strategies.cross_sectional_weighted_signals import generate_cross_sectional_weighted_signals
from app.strategies.cross_sectional_weighted import CrossSectionalWeightedStrategy

class TestCrossSectionalWeightedStrategy:
    def test_indicator_run(self):
        codes = {
            "BTC": "weight=0.5\nsignal='long'",
            "ETH": "weight=0.3\nsignal='short'",
            "XRP": "weight=0.0\nsignal='flat'"
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

        assert result["weights"]["BTC"] == 0.5
        assert result["weights"]["ETH"] == 0.3
        assert result["weights"]["XRP"] == 0.0

        assert result["signals"]["BTC"] == 1
        assert result["signals"]["ETH"] == -1
        assert result["signals"]["XRP"] == 0

    def test_generate_signals(self):
        weights = {"BTC": 0.5, "ETH": 0.3}
        signals = {"BTC": 1, "ETH": -1, "SOL": 0}

        current_positions = [
            {"symbol": "BTC", "side": "long", "size": 1.0}, # Keep/Adjust
            {"symbol": "ETH", "side": "long", "size": 1.0}, # Wrong side, should close
            {"symbol": "SOL", "side": "short", "size": 1.0}, # Signal 0, should close
        ]

        result = generate_cross_sectional_weighted_signals(weights, signals, current_positions)

        # We expect:
        # 1. close ETH long
        # 2. close SOL short
        # 3. open BTC long with position_size=0.5
        # 4. open ETH short with position_size=0.3

        assert len(result) == 4
        assert any(s["type"] == "close_long" and s["symbol"] == "ETH" for s in result)
        assert any(s["type"] == "close_short" and s["symbol"] == "SOL" for s in result)
        open_btc = next(s for s in result if s["type"] == "open_long" and s["symbol"] == "BTC")
        open_eth = next(s for s in result if s["type"] == "open_short" and s["symbol"] == "ETH")

        assert open_btc["position_size"] == 0.5
        assert open_btc["target_weight"] == 0.5

        assert open_eth["position_size"] == 0.3
        assert open_eth["target_weight"] == 0.3

    def test_indicator_run_edge_cases(self):
        codes = {"A": "weight=1\nsignal=1", "B": "bad code"}
        data = {
            "A": pd.DataFrame(), # Empty df -> lines 42
            "B": pd.DataFrame({"c":[1]}), # Exception -> lines 69-71
            "C": pd.DataFrame({"c":[1]})  # No code -> lines 46-47
        }
        res = run_cross_sectional_weighted_indicator(codes, data, {})
        assert not res["weights"]
        assert not res["signals"]

        # Test unexpected signal string
        codes2 = {"A": "weight=1\nsignal='unknown'"}
        data2 = {"A": pd.DataFrame({"c":[1]})}
        res2 = run_cross_sectional_weighted_indicator(codes2, data2, {})
        assert res2["signals"]["A"] == 0

    def test_generate_signals_edge_cases(self):
        weights = {"A": 0.5, "B": 0.0, "C": -1} # <= 0 weight -> lines 59
        signals = {"A": 1, "B": 1, "C": 1}
        # expected_signal=1, side='short' -> line 49
        current = [{"symbol": "A", "side": "short", "size": 1.0}]
        res = generate_cross_sectional_weighted_signals(weights, signals, current)

        assert len(res) == 2
        assert res[0]["type"] == "close_short" and res[0]["symbol"] == "A"
        assert res[1]["type"] == "open_long" and res[1]["symbol"] == "A"

        # expected_signal=-1, side='long'
        weights2 = {"A": 0.5}
        signals2 = {"A": -1}
        current2 = [{"symbol": "A", "side": "long", "size": 1.0}]
        res2 = generate_cross_sectional_weighted_signals(weights2, signals2, current2)
        assert len(res2) == 2
        assert res2[0]["type"] == "close_long" and res[0]["symbol"] == "A"

    def test_strategy_class_edge_cases(self):
        strat = CrossSectionalWeightedStrategy()

        # Missing data
        res1 = strat.get_signals({"data": {}})
        assert res1 == ([], True, False, None)

        # Indicator returned empty
        with patch("app.strategies.cross_sectional_weighted.run_cross_sectional_weighted_indicator") as mock_run:
            mock_run.return_value = {}
            res2 = strat.get_signals({"data": {"A": "df"}})
            assert res2 == ([], True, False, None)

        # Signals empty
        with patch("app.strategies.cross_sectional_weighted.run_cross_sectional_weighted_indicator") as mock_run:
            mock_run.return_value = {"weights": {}, "signals": {}}
            with patch("app.strategies.cross_sectional_weighted.generate_cross_sectional_weighted_signals") as mock_gen:
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

        with patch("app.strategies.cross_sectional_weighted.run_cross_sectional_weighted_indicator") as mock_run:
            mock_run.return_value = {"weights": {"A": 0.5}, "signals": {"A": 1}}

            with patch("app.strategies.cross_sectional_weighted.generate_cross_sectional_weighted_signals") as mock_gen:
                mock_gen.return_value = [{"symbol": "A", "type": "open_long"}]

                signals, keep_running, update_rebalance, _ = strat.get_signals(ctx)

                assert len(signals) == 1
                assert signals[0]["symbol"] == "A"
                assert keep_running is True
                assert update_rebalance is True
