"""
Tests for SingleRegimeWeightedStrategy.
"""
import time
from unittest.mock import patch

import pandas as pd

from app.strategies.single_regime_weighted import SingleRegimeWeightedStrategy
from app.strategies.single_symbol import SingleSymbolStrategy
from app.strategies.factory import create_strategy
from app.strategies.regime_mixin import (
    REGIME_PANIC, REGIME_NORMAL, REGIME_LOW_VOL,
)


def _make_ctx(**overrides):
    """构造用于测试的最小 InputContext，支持通过 keyword 覆盖默认值。"""
    defaults = {
        "vix": 18.0, "dxy": 100.0,
        "should_regime_rebalance": False,
        "positions": None, "current_price": 100.0,
        "initial_capital": 10000.0,
        "macro_indicators": None,
        "primary_macro_indicator": "vix",
        "regime_strategy_type": "balanced",
        "indicator_code": "", "strategy_id": 1,
    }
    defaults.update(overrides)
    d = defaults
    macro_indicators = d["macro_indicators"] or ["vix"]
    current_price = d["current_price"]
    df = pd.DataFrame([{
        "open": 100.0, "high": 105.0, "low": 95.0, "close": current_price,
        "volume": 1000,
        "vix": d["vix"], "dxy": d["dxy"], "fear_greed": 50.0,
    }])
    return {
        "df": df,
        "positions": d["positions"] or [],
        "symbol": "BTC",
        "current_price": current_price,
        "current_time": time.time(),
        "strategy_id": d["strategy_id"],
        "indicator_code": d["indicator_code"],
        "should_regime_rebalance": d["should_regime_rebalance"],
        "trading_config": {
            "symbol": "BTC",
            "timeframe": "1H",
            "macro_indicators": macro_indicators,
            "primary_macro_indicator": d["primary_macro_indicator"],
            "regime_strategy_type": d["regime_strategy_type"],
            "initial_capital": d["initial_capital"],
        },
        "initial_highest_price": 0.0,
        "initial_position": 0,
        "initial_avg_entry_price": 0.0,
        "initial_position_count": 0,
        "initial_last_add_price": 0.0,
    }


class TestSingleRegimeWeightedStrategyBasic:
    """SingleRegimeWeightedStrategy 基础行为与工厂创建。"""

    def test_need_macro_info(self):
        """策略声明需要宏观信息。"""
        strat = SingleRegimeWeightedStrategy()
        assert strat.need_macro_info() is True

    def test_factory_creates_correct_type(self):
        """工厂按类型名创建 SingleRegimeWeightedStrategy 实例。"""
        strat = create_strategy("single_regime_weighted")
        assert isinstance(strat, SingleRegimeWeightedStrategy)

    def test_factory_still_creates_single(self):
        """single 类型仍创建 SingleSymbolStrategy 而非本策略。"""
        strat = create_strategy("single")
        assert isinstance(strat, SingleSymbolStrategy)
        assert not isinstance(strat, SingleRegimeWeightedStrategy)


class _TestableStrategy(SingleRegimeWeightedStrategy):
    """可测试子类，提供 public 接口初始化内部状态。"""

    def init_state_for_test(self, pending_signals=None):
        """预初始化策略状态，使 get_signals 跳过 _init_from_ctx。"""
        self._state = {
            "_initialized": True,
            "df": pd.DataFrame(),
            "pending_signals": pending_signals or [],
            "current_pos_list": [],
            "last_kline_update_time": 0,
            "timeframe_seconds": 3600,
        }


class TestRegimeRebalance:
    """Regime 再平衡触发与未触发的行为。"""

    def test_no_rebalance_passthrough(self):
        """should_regime_rebalance=False 时不执行 regime 逻辑且 meta 无 current_regime。"""
        strat = _TestableStrategy()
        strat.init_state_for_test()
        ctx = _make_ctx(should_regime_rebalance=False, vix=35.0)
        _signals, cont, _, meta = strat.get_signals(ctx)
        assert cont is True
        if meta:
            assert "current_regime" not in meta

    def test_regime_metadata_added(self):
        """再平衡触发时 meta 含 current_regime 与 capital_ratio。"""
        strat = _TestableStrategy()
        strat.init_state_for_test()
        ctx = _make_ctx(
            should_regime_rebalance=True, vix=18.0,
            regime_strategy_type="balanced",
        )
        _signals, cont, _, meta = strat.get_signals(ctx)
        assert cont is True
        assert meta is not None
        assert meta["current_regime"] == REGIME_NORMAL
        assert meta["capital_ratio"] == 0.6

    def test_regime_panic_with_dxy(self):
        """主指标为 DXY 且高位时 regime 为 panic、激进风格资金比例为 0。"""
        strat = _TestableStrategy()
        strat.init_state_for_test()
        ctx = _make_ctx(
            should_regime_rebalance=True,
            dxy=115.0,
            macro_indicators=["dxy"],
            primary_macro_indicator="dxy",
            regime_strategy_type="aggressive",
        )
        _signals, _, _, meta = strat.get_signals(ctx)
        assert meta["current_regime"] == REGIME_PANIC
        assert meta["capital_ratio"] == 0.0

    def test_regime_low_vol(self):
        """低 VIX 时 regime 为 low_vol 且激进风格资金比例正确。"""
        strat = _TestableStrategy()
        strat.init_state_for_test()
        ctx = _make_ctx(
            should_regime_rebalance=True, vix=12.0,
            regime_strategy_type="aggressive",
        )
        _signals, _, _, meta = strat.get_signals(ctx)
        assert meta["current_regime"] == REGIME_LOW_VOL
        assert meta["capital_ratio"] == 0.6


class TestSignalAdjustment:
    """超配时生成平仓信号、低配时不平仓、开仓信号缩放。"""

    def test_close_signal_when_over_allocated(self):
        """panic 且 balanced 时 capital_ratio=0.2 应产生 close_long。"""
        positions = [{
            "symbol": "BTC", "side": "long",
            "size": 1.0, "entry_price": 8000.0,
        }]
        strat = _TestableStrategy()
        strat.init_state_for_test()
        ctx = _make_ctx(
            should_regime_rebalance=True, vix=35.0,
            positions=positions,
            current_price=8000.0,
            initial_capital=10000.0,
            regime_strategy_type="balanced",
        )
        signals, _, _, meta = strat.get_signals(ctx)
        assert meta["current_regime"] == REGIME_PANIC
        assert meta["capital_ratio"] == 0.2

        close_sigs = [
            s for s in signals
            if s.get("type", "").startswith("close_")
        ]
        assert len(close_sigs) == 1
        sig = close_sigs[0]
        assert sig["type"] == "close_long"
        assert sig["symbol"] == "BTC"
        assert 0 < sig["position_size"] <= 1.0

    def test_no_close_signal_when_under_allocated(self):
        """仓位很小未超可用资金时不产生平仓信号。"""
        positions = [{
            "symbol": "BTC", "side": "long",
            "size": 0.01, "entry_price": 100.0,
        }]
        strat = _TestableStrategy()
        strat.init_state_for_test()
        ctx = _make_ctx(
            should_regime_rebalance=True, vix=18.0,
            positions=positions,
            current_price=100.0,
            initial_capital=10000.0,
            regime_strategy_type="balanced",
        )
        signals, _, _, meta = strat.get_signals(ctx)
        assert meta["current_regime"] == REGIME_NORMAL
        close_sigs = [
            s for s in signals
            if s.get("type", "").startswith("close_")
        ]
        assert len(close_sigs) == 0

    @patch("app.strategies.single_symbol.run_single_indicator")
    def test_open_signal_size_adjusted(self, mock_ind):
        """open_long 的 position_size 应按 capital_ratio 比例缩放。"""
        mock_ind.return_value = (None, {})

        strat = _TestableStrategy()
        strat.init_state_for_test(pending_signals=[{
            "type": "open_long",
            "trigger_price": 0,
            "position_size": 0.1,
            "timestamp": 0,
        }])
        ctx = _make_ctx(
            should_regime_rebalance=True, vix=12.0,
            current_price=100.0,
            regime_strategy_type="aggressive",
        )
        signals, _, _, meta = strat.get_signals(ctx)

        assert meta["current_regime"] == REGIME_LOW_VOL
        ratio = meta["capital_ratio"]
        assert ratio == 0.6

        open_sigs = [
            s for s in signals if s.get("type") == "open_long"
        ]
        assert len(open_sigs) == 1
        assert open_sigs[0]["position_size"] == 0.1 * ratio
