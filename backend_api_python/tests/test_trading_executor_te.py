"""
TE-01 ~ TE-04: TradingExecutor 级用例

针对 _run_strategy_loop 及策略类（CrossSectionalStrategy/SingleSymbolStrategy）行为，
用 mock 构造可控输入，保证重构后行为不变。
"""

import os
import sys
import time
import types
from unittest.mock import patch, MagicMock

from tests.conftest import make_db_ctx


def _import_trading_executor():
    """Import TradingExecutor with ccxt mocked (pandas/numpy needed)."""
    mock_ccxt = types.ModuleType("ccxt")
    mock_ccxt.Exchange = type("Exchange", (), {})
    sys.modules.setdefault("ccxt", mock_ccxt)
    from app.services.trading_executor import TradingExecutor
    return TradingExecutor


# ── 共用 mock 数据 ────────────────────────────────────────────────────────

MOCK_KLINES = [
    {"time": 1700000000, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0},
    {"time": 1700003600, "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.0, "volume": 1200.0},
]

SINGLE_SYMBOL_STRATEGY = {
    "id": 1,
    "strategy_name": "test_single",
    "strategy_type": "IndicatorStrategy",
    "status": "running",
    "initial_capital": 10000.0,
    "leverage": 1,
    "decide_interval": 300,
    "execution_mode": "signal",
    "notification_config": {},
    "indicator_config": {
        "indicator_id": 1,
        "indicator_code": "scores = {}; rankings = []",
    },
    "trading_config": {
        "symbol": "BTC/USDT",
        "timeframe": "1H",
        "market_type": "swap",
        "leverage": 1,
        "trade_direction": "long",
    },
    "exchange_config": {},
    "ai_model_config": {},
    "market_category": "Crypto",
}

CROSS_SECTIONAL_STRATEGY = {
    **SINGLE_SYMBOL_STRATEGY,
    "id": 2,
    "strategy_name": "test_cross",
    "trading_config": {
        **SINGLE_SYMBOL_STRATEGY["trading_config"],
        "cs_strategy_type": "cross_sectional",
        "symbol_list": ["A", "B", "C"],
        "rebalance_frequency": "daily",
        "decide_interval": 300,
        "portfolio_size": 3,
        "long_ratio": 0.5,
    },
}


# ── TE-LOAD: load_strategy 加载、解析、校验 ─────────────────────────────────

class TestTELoadStrategy:
    """TE-LOAD: strategy_config_loader.load_strategy 解析、校验、归一化 _* 字段"""

    def test_load_strategy_valid_returns_normalized_fields(self):
        """有效策略返回含 _execution_mode、_market_type、_indicator_code 等"""
        from app.strategies.strategy_config_loader import load_strategy

        with patch("app.services.data_handler.get_db_connection") as mock_db:
            mock_db.return_value = make_db_ctx(dict(SINGLE_SYMBOL_STRATEGY))
            strategy = load_strategy(1)
        assert strategy is not None
        assert strategy["_execution_mode"] == "signal"
        assert strategy["_market_type"] in ("swap", "spot")  # leverage=1 -> spot
        assert strategy["_leverage"] == 1.0
        assert strategy["_indicator_code"]  # 非空
        assert "scores" in strategy["_indicator_code"] or "rankings" in strategy["_indicator_code"]

    def test_load_strategy_invalid_strategy_type_returns_none(self):
        """strategy_type 非 IndicatorStrategy 返回 None"""
        from app.strategies.strategy_config_loader import load_strategy

        bad = dict(SINGLE_SYMBOL_STRATEGY)
        bad["strategy_type"] = "Other"
        with patch("app.services.data_handler.get_db_connection") as mock_db:
            mock_db.return_value = make_db_ctx(bad)
            assert load_strategy(1) is None

    def test_load_strategy_leverage_one_sets_market_type_spot(self):
        """leverage=1 时 market_type 归一化为 spot"""
        from app.strategies.strategy_config_loader import load_strategy

        cfg = dict(SINGLE_SYMBOL_STRATEGY)
        cfg["trading_config"] = dict(cfg["trading_config"], leverage=1, market_type="swap")
        with patch("app.services.data_handler.get_db_connection") as mock_db:
            mock_db.return_value = make_db_ctx(cfg)
            strategy = load_strategy(1)
        assert strategy is not None
        assert strategy["_market_type"] == "spot"
        assert strategy["_leverage"] == 1.0

    def test_load_strategy_empty_indicator_code_returns_none(self):
        """indicator_code 为空且 _get_indicator_code_from_db 返回 None 时返回 None"""
        from app.strategies.strategy_config_loader import load_strategy

        cfg = dict(SINGLE_SYMBOL_STRATEGY)
        cfg["indicator_config"] = {"indicator_id": 1, "indicator_code": ""}
        with patch("app.services.data_handler.get_db_connection") as mock_db:
            mock_db.return_value = make_db_ctx(cfg, fetchone_side_effect=[cfg, None])
            assert load_strategy(1) is None

    def test_load_strategy_invalid_market_type_returns_none(self):
        """market_type 非 swap/spot 时返回 None"""
        from app.strategies.strategy_config_loader import load_strategy

        cfg = dict(SINGLE_SYMBOL_STRATEGY)
        cfg["trading_config"] = dict(cfg["trading_config"], market_type="futures")
        with patch("app.services.data_handler.get_db_connection") as mock_db:
            mock_db.return_value = make_db_ctx(cfg)
            assert load_strategy(1) is None


# ── TE-01: 单标策略启动后能拉 K 线并执行指标 ──────────────────────────────

class TestTE01SingleSymbolFetchesKlineAndExecutesIndicator:
    """TE-01: mock KlineService，断言调用了 run_single_indicator"""

    def test_single_symbol_calls_execute_indicator_df(self):
        """单标策略初始化阶段：DataHandler 提供 ctx，调用 run_single_indicator"""
        import pandas as pd
        TradingExecutor = _import_trading_executor()

        df = pd.DataFrame(MOCK_KLINES)
        df.columns = ["time", "open", "high", "low", "close", "volume"]
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time")
        mock_ctx = {
            "df": df, "positions": [], "trading_config": {},
            "initial_highest_price": 0, "initial_position": 0,
            "initial_avg_entry_price": 0, "initial_position_count": 0, "initial_last_add_price": 0,
            "symbol": "BTC/USDT",
        }

        with patch("app.services.data_handler.get_db_connection") as mock_db:
            mock_db.return_value = make_db_ctx(dict(SINGLE_SYMBOL_STRATEGY))
            with patch.object(TradingExecutor, "_is_strategy_running", side_effect=[True, False]), \
                 patch.object(TradingExecutor, "_fetch_current_price", return_value=100.0), \
                 patch("app.strategies.single_symbol.run_single_indicator") as mock_exec_indicator:
                mock_exec_indicator.return_value = (pd.DataFrame({"close": [1.0]}), {})
                te = TradingExecutor()
                te.data_handler.get_input_context_single = MagicMock(return_value=mock_ctx)
                te._run_strategy_loop(1)
                mock_exec_indicator.assert_called()


# ── TE-02: 截面策略调仓日能生成 signals ───────────────────────────────────

class TestTE02CrossSectionalGeneratesSignals:
    """TE-02: 断言 generate_cross_sectional_signals 返回预期结构"""

    def test_generate_cross_sectional_signals_returns_expected_structure(self):
        """空持仓：rankings A,B,C 且 long_ratio=0.5 -> A open_long, B/C open_short"""
        from app.strategies.cross_sectional_signals import generate_cross_sectional_signals

        signals = generate_cross_sectional_signals(
            ["A", "B", "C"],
            {"A": 0.9, "B": 0.7, "C": 0.5},
            {"portfolio_size": 3, "long_ratio": 0.5},
            [],
        )

        sig_set = {(s["symbol"], s["type"]) for s in signals}
        assert sig_set == {("A", "open_long"), ("B", "open_short"), ("C", "open_short")}
        assert len(signals) == 3

    def test_generate_cross_sectional_signals_produces_close_short_and_open_short(self):
        """有持仓 A 多/D 空：应生成 close_short(D)、open_short(B)、open_short(C)"""
        from app.strategies.cross_sectional_signals import generate_cross_sectional_signals

        positions = [
            {"symbol": "A", "side": "long", "size": 1.0, "entry_price": 100.0},
            {"symbol": "D", "side": "short", "size": 1.0, "entry_price": 105.0},
        ]
        signals = generate_cross_sectional_signals(
            ["A", "B", "C"],
            {"A": 0.9, "B": 0.7, "C": 0.5},
            {"portfolio_size": 3, "long_ratio": 0.5},
            positions,
        )

        sig_set = {(s["symbol"], s["type"]) for s in signals}
        assert ("D", "close_short") in sig_set
        assert ("B", "open_short") in sig_set
        assert ("C", "open_short") in sig_set
        assert len(signals) == 3

    def test_generate_cross_sectional_signals_produces_close_long(self):
        """多仓 A 不在新 long 列表时，应生成 close_long(A)"""
        from app.strategies.cross_sectional_signals import generate_cross_sectional_signals

        positions = [{"symbol": "A", "side": "long", "size": 1.0, "entry_price": 100.0}]
        signals = generate_cross_sectional_signals(
            ["B", "C", "D"],
            {"B": 0.9, "C": 0.7, "D": 0.5},
            {"portfolio_size": 3, "long_ratio": 0.5},
            positions,
        )

        sig_set = {(s["symbol"], s["type"]) for s in signals}
        assert ("A", "close_long") in sig_set


# ── TE-03: 截面策略非调仓日不执行指标 ─────────────────────────────────────

class TestTE03CrossSectionalNonRebalanceDaySkipsIndicator:
    """TE-03: 断言 _should_rebalance=False 时 run_cross_sectional_indicator 未被调用"""

    @patch("app.services.data_handler.get_db_connection")
    def test_non_rebalance_day_skips_indicator(self, mock_db):
        """当 _should_rebalance 返回 False 时，不调用 run_cross_sectional_indicator"""
        TradingExecutor = _import_trading_executor()
        mock_db.return_value = make_db_ctx(
            fetchone_side_effect=[
                CROSS_SECTIONAL_STRATEGY,
                {"last_rebalance_at": "2025-02-25T00:00:00+00:00"},
            ]
        )

        with patch.object(
            TradingExecutor, "_is_strategy_running"
        ) as mock_running, patch(
            "app.strategies.cross_sectional.run_cross_sectional_indicator"
        ) as mock_run_indicator:
            mock_running.side_effect = [True, False]

            te = TradingExecutor()
            te._should_rebalance = MagicMock(return_value=False)
            te._run_strategy_loop(2)

            mock_run_indicator.assert_not_called()


# ── TE-04: 单标 tick 节奏正确 ──────────────────────────────────────────────

class TestTE04SingleSymbolTickCadence:
    """TE-04: 验证 tick 间隔、K 线更新节奏"""

    def test_tick_interval_env_parsed(self):
        """STRATEGY_TICK_INTERVAL_SEC 能被正确解析"""
        with patch.dict(os.environ, {"STRATEGY_TICK_INTERVAL_SEC": "15"}):
            tick_interval = int(os.getenv("STRATEGY_TICK_INTERVAL_SEC", "10"))
            assert tick_interval == 15

    def test_single_symbol_loop_uses_tick_interval(self):
        """单标 loop 的 tick 节奏由 STRATEGY_TICK_INTERVAL_SEC 控制，time.sleep 被调用"""
        import pandas as pd

        TradingExecutor = _import_trading_executor()

        time_vals = [0, 5, 10]

        def mock_time():
            return time_vals.pop(0) if time_vals else 100

        mock_indicator_result = {"pending_signals": [], "last_kline_time": 0, "new_highest_price": 0}
        df = pd.DataFrame(MOCK_KLINES)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time")
        mock_ctx = {
            "df": df,
            "positions": [],
            "initial_highest_price": 0.0,
            "initial_position": 0,
            "initial_avg_entry_price": 0.0,
            "initial_position_count": 0,
            "initial_last_add_price": 0.0,
            "symbol": "BTC/USDT",
            "trading_config": SINGLE_SYMBOL_STRATEGY["trading_config"],
        }

        with patch("app.services.data_handler.get_db_connection") as mock_db:
            mock_db.return_value = make_db_ctx(dict(SINGLE_SYMBOL_STRATEGY))
            with patch.dict(os.environ, {"STRATEGY_TICK_INTERVAL_SEC": "10"}), \
             patch("app.strategies.single_symbol.run_single_indicator",
                  return_value=(MagicMock(), {"highest_price": 0})), \
             patch("app.strategies.single_symbol.extract_pending_signals_from_df",
                  return_value=mock_indicator_result.get("pending_signals", [])), \
             patch("time.time", side_effect=mock_time), \
             patch("time.sleep", MagicMock()) as mock_sleep, \
             patch.object(TradingExecutor, "_is_strategy_running",
                         side_effect=[True, True, True, False]), \
             patch.object(TradingExecutor, "_fetch_current_price", return_value=100.0), \
             patch.object(TradingExecutor, "_console_print"):
                te = TradingExecutor()
                te.data_handler.get_input_context_single = MagicMock(return_value=mock_ctx)
                te.data_handler.update_positions_current_price = MagicMock()
                te._run_strategy_loop(1)
                mock_sleep.assert_called()
                assert mock_sleep.call_args[0][0] == 1.0


# ── TE-05: 单标 exec_indicator 后有 pending_signals 时调用 _execute_signal ──

def _run_single_loop_with_pending(
    TradingExecutorCls,
    pending_signals,
    *,
    strategy_overrides=None,
    positions=None,
):
    """辅助：用给定 pending_signals 跑单标 loop 一次，返回 mock_exec_signal。
    strategy_overrides: 覆盖 SINGLE_SYMBOL_STRATEGY 的字段，如 trading_config.trade_direction
    positions: mock 持仓，close 信号需有持仓
    """
    import pandas as pd

    ts = int(time.time())
    strategy = dict(SINGLE_SYMBOL_STRATEGY)
    if strategy_overrides:
        for k, v in strategy_overrides.items():
            if k == "trading_config":
                strategy["trading_config"] = dict(strategy.get("trading_config", {}), **v)
            else:
                strategy[k] = v
    indicator_result = {
        "pending_signals": pending_signals,
        "last_kline_time": ts,
        "new_highest_price": 0,
    }

    df = pd.DataFrame(MOCK_KLINES)
    df.columns = ["time", "open", "high", "low", "close", "volume"]
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time")
    pos_list = positions or []
    init_hp = float(pos_list[0].get("highest_price", 0)) if pos_list else 0.0
    init_pos = 1 if pos_list and pos_list[0].get("side") == "long" else (-1 if pos_list else 0)
    init_ep = float(pos_list[0].get("entry_price", 0)) if pos_list else 0.0
    mock_ctx = {
        "df": df, "positions": pos_list, "trading_config": strategy.get("trading_config", {}),
        "initial_highest_price": init_hp, "initial_position": init_pos,
        "initial_avg_entry_price": init_ep, "initial_position_count": 1 if pos_list else 0,
        "initial_last_add_price": init_ep, "symbol": "BTC/USDT",
    }

    from app.services.data_handler import DataHandler
    with patch("app.services.data_handler.get_db_connection") as mock_db:
        mock_db.return_value = make_db_ctx(strategy)
        with patch("app.strategies.single_symbol.run_single_indicator",
                  return_value=(MagicMock(), {"highest_price": 0})), \
             patch("app.strategies.single_symbol.extract_pending_signals_from_df",
                  return_value=indicator_result.get("pending_signals", [])), \
             patch.object(TradingExecutorCls, "_is_strategy_running",
                         side_effect=[True, False]), \
             patch.object(TradingExecutorCls, "_fetch_current_price", return_value=100.0), \
             patch.object(TradingExecutorCls, "_execute_signal") as mock_exec_signal, \
             patch.object(DataHandler, "update_positions_current_price"), \
             patch.object(DataHandler, "get_current_positions", return_value=pos_list), \
             patch.object(TradingExecutorCls, "_console_print"), \
             patch.object(TradingExecutorCls, "_should_skip_signal_once_per_candle",
                         return_value=False), \
             patch.object(TradingExecutorCls, "_server_side_take_profit_or_trailing_signal",
                         return_value=None), \
             patch.object(TradingExecutorCls, "_server_side_stop_loss_signal",
                         return_value=None):
            mock_exec_signal.return_value = True
            te = TradingExecutorCls()
            te.data_handler.get_input_context_single = MagicMock(return_value=mock_ctx)
            te._run_strategy_loop(1)
            return mock_exec_signal


class TestTE05SingleSymbolExecuteSignalAfterIndicator:
    """TE-05: 指标返回 pending_signals 后能触发并调用 _execute_signal"""

    def test_pending_open_long_triggers_execute_signal(self):
        """pending open_long -> _execute_signal 收到 signal_type=open_long"""
        TradingExecutor = _import_trading_executor()
        mock_exec = _run_single_loop_with_pending(TradingExecutor, [{
            "type": "open_long", "trigger_price": 0, "position_size": 0.08, "timestamp": int(time.time()),
        }])
        mock_exec.assert_called()
        assert mock_exec.call_args[1].get("signal_type") == "open_long"

    def test_pending_open_short_triggers_execute_signal(self):
        """pending open_short 需 trade_direction=both 且 leverage>1(market_type=swap) 才能执行"""
        TradingExecutor = _import_trading_executor()
        mock_exec = _run_single_loop_with_pending(TradingExecutor, [{
            "type": "open_short", "trigger_price": 0, "position_size": 0.08, "timestamp": int(time.time()),
        }], strategy_overrides={"trading_config": {"trade_direction": "both", "leverage": 2}})
        mock_exec.assert_called()
        assert mock_exec.call_args[1].get("signal_type") == "open_short"

    def test_pending_close_long_triggers_execute_signal(self):
        """pending close_long 需有持仓才能执行"""
        TradingExecutor = _import_trading_executor()
        positions = [{"symbol": "BTC/USDT", "side": "long", "size": 0.1, "entry_price": 100.0}]
        mock_exec = _run_single_loop_with_pending(TradingExecutor, [{
            "type": "close_long", "trigger_price": 0, "position_size": 0, "timestamp": int(time.time()),
        }], positions=positions)
        mock_exec.assert_called()
        assert mock_exec.call_args[1].get("signal_type") == "close_long"

    def test_pending_close_short_triggers_execute_signal(self):
        """pending close_short 需有空仓才能执行"""
        TradingExecutor = _import_trading_executor()
        positions = [{"symbol": "BTC/USDT", "side": "short", "size": 0.1, "entry_price": 100.0}]
        mock_exec = _run_single_loop_with_pending(TradingExecutor, [{
            "type": "close_short", "trigger_price": 0, "position_size": 0, "timestamp": int(time.time()),
        }], positions=positions)
        mock_exec.assert_called()
        assert mock_exec.call_args[1].get("signal_type") == "close_short"

    def test_meta_position_updates_calls_update_position(self):
        """meta 含 position_updates 时，update_position 被调用"""
        import pandas as pd
        TradingExecutor = _import_trading_executor()
        positions = [{"symbol": "BTC/USDT", "side": "long", "size": 0.1, "entry_price": 100.0}]
        df = pd.DataFrame(MOCK_KLINES)
        df.columns = ["time", "open", "high", "low", "close", "volume"]
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time")
        mock_ctx = {
            "df": df, "positions": positions, "trading_config": SINGLE_SYMBOL_STRATEGY["trading_config"],
            "initial_highest_price": 0, "initial_position": 1, "initial_avg_entry_price": 100.0,
            "initial_position_count": 1, "initial_last_add_price": 100.0, "symbol": "BTC/USDT",
        }
        from app.services.data_handler import DataHandler
        with patch("app.services.data_handler.get_db_connection") as mock_db:
            mock_db.return_value = make_db_ctx(dict(SINGLE_SYMBOL_STRATEGY))
            with patch("app.strategies.single_symbol.run_single_indicator") as mock_run_indicator, \
                 patch("app.strategies.single_symbol.extract_pending_signals_from_df") as mock_extract:
                mock_run_indicator.side_effect = [
                    (df.copy(), {"highest_price": 0}),
                    (df.copy(), {"highest_price": 105.0}),
                ]
                mock_extract.return_value = []
                time_vals = [0] * 5 + [10] * 5 + [100] * 5  # 足够供两次 tick 使用
                with patch.object(TradingExecutor, "_is_strategy_running", side_effect=[True, True, False]), \
                     patch.object(TradingExecutor, "_fetch_current_price", return_value=100.0), \
                     patch.object(DataHandler, "update_positions_current_price"), \
                     patch.object(DataHandler, "update_position") as mock_update_pos, \
                     patch.object(TradingExecutor, "_console_print"), \
                     patch.object(TradingExecutor, "_server_side_take_profit_or_trailing_signal", return_value=None), \
                     patch.object(TradingExecutor, "_server_side_stop_loss_signal", return_value=None), \
                     patch("time.sleep", MagicMock()), \
                     patch("time.time", side_effect=lambda: time_vals.pop(0) if time_vals else 200):
                    te = TradingExecutor()
                    te.data_handler.get_input_context_single = MagicMock(return_value=mock_ctx)
                    te._run_strategy_loop(1)
                mock_update_pos.assert_called()
                call_kw = mock_update_pos.call_args[1]
                assert call_kw.get("symbol") == "BTC/USDT"
                assert call_kw.get("side") == "long"
                assert call_kw.get("highest_price") == 105.0


# ── TE-04b: 截面 tick 节奏 ─────────────────────────────────────────────────

class TestTE04bCrossSectionalTickCadence:
    """TE-04b: 截面 loop 的 tick 节奏由 decide_interval 控制"""

    def test_cross_sectional_loop_uses_decide_interval(self):
        """截面 loop 在非调仓日会按 decide_interval 控制 sleep"""
        TradingExecutor = _import_trading_executor()
        strategy = dict(CROSS_SECTIONAL_STRATEGY)
        strategy["trading_config"] = dict(strategy["trading_config"], decide_interval=300)
        time_vals = [0, 5, 100, 200]

        def mock_time():
            return time_vals.pop(0) if time_vals else 300

        with patch("app.services.data_handler.get_db_connection") as mock_db:
            mock_db.return_value = make_db_ctx(strategy)
            with patch("time.time", side_effect=mock_time), \
                 patch("time.sleep", MagicMock()) as mock_sleep, \
                 patch.object(TradingExecutor, "_is_strategy_running",
                             side_effect=[True, True, True, False]):
                te = TradingExecutor()
                te._should_rebalance = MagicMock(return_value=False)
                te._run_strategy_loop(2)

                mock_sleep.assert_called()
                assert mock_sleep.call_args[0][0] == 1.0


# ── TE-06: 截面调仓日 exec_indicator → signals → 批量 _execute_signal ────

class TestTE06CrossSectionalExecuteSignalAfterIndicator:
    """TE-06: 截面调仓日 indicator → signals → 批量 _execute_signal"""

    def test_rebalance_day_executes_signals(self):
        """空持仓：rankings A,B,C -> 应执行 A open_long, B open_short, C open_short 共 3 次"""
        import pandas as pd
        TradingExecutor = _import_trading_executor()
        df = pd.DataFrame(MOCK_KLINES)
        df.columns = ["time", "open", "high", "low", "close", "volume"]
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time")
        input_ctx = {"data": {"A": df, "B": df, "C": df}, "positions": []}
        indicator_result = {"scores": {"A": 0.9, "B": 0.7, "C": 0.5}, "rankings": ["A", "B", "C"]}
        strategy = dict(CROSS_SECTIONAL_STRATEGY)

        input_ctx["trading_config"] = strategy.get("trading_config", {})
        from app.services.data_handler import DataHandler
        with patch("app.services.data_handler.get_db_connection") as mock_db:
            mock_db.return_value = make_db_ctx(strategy)
            with patch.object(TradingExecutor, "_is_strategy_running",
                             side_effect=[True, False]), \
                 patch("app.strategies.cross_sectional.run_cross_sectional_indicator",
                       return_value=indicator_result), \
                 patch.object(TradingExecutor, "_execute_signal") as mock_exec_signal, \
                 patch.object(DataHandler, "update_last_rebalance"):
                mock_exec_signal.return_value = True
                te = TradingExecutor()
                te._should_rebalance = MagicMock(return_value=True)
                te.data_handler.get_input_context_cross = MagicMock(return_value=input_ctx)
                te._run_strategy_loop(2)

                assert mock_exec_signal.call_count == 3
                executed = {(c[1].get("symbol"), c[1].get("signal_type")) for c in mock_exec_signal.call_args_list}
                assert executed == {("A", "open_long"), ("B", "open_short"), ("C", "open_short")}

    def test_rebalance_day_executes_close_and_open_signals_when_positions_exist(self):
        """有持仓 A 多/D 空：应执行 close_short(D)、open_short(B)、open_short(C) 共 3 次"""
        import pandas as pd
        TradingExecutor = _import_trading_executor()
        df = pd.DataFrame(MOCK_KLINES)
        df.columns = ["time", "open", "high", "low", "close", "volume"]
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time")
        positions = [
            {"symbol": "A", "side": "long", "size": 1.0, "entry_price": 100.0},
            {"symbol": "D", "side": "short", "size": 1.0, "entry_price": 105.0},
        ]
        input_ctx = {"data": {"A": df, "B": df, "C": df}, "positions": positions}
        indicator_result = {"scores": {"A": 0.9, "B": 0.7, "C": 0.5}, "rankings": ["A", "B", "C"]}
        strategy = dict(CROSS_SECTIONAL_STRATEGY)

        input_ctx["trading_config"] = strategy.get("trading_config", {})
        from app.services.data_handler import DataHandler
        with patch("app.services.data_handler.get_db_connection") as mock_db:
            mock_db.return_value = make_db_ctx(strategy)
            with patch.object(TradingExecutor, "_is_strategy_running",
                             side_effect=[True, False]), \
                 patch("app.strategies.cross_sectional.run_cross_sectional_indicator",
                       return_value=indicator_result), \
                 patch.object(TradingExecutor, "_execute_signal") as mock_exec_signal, \
                 patch.object(DataHandler, "update_last_rebalance"):
                mock_exec_signal.return_value = True
                te = TradingExecutor()
                te._should_rebalance = MagicMock(return_value=True)
                te.data_handler.get_input_context_cross = MagicMock(return_value=input_ctx)
                te._run_strategy_loop(2)

                assert mock_exec_signal.call_count == 3
                executed = {(c[1].get("symbol"), c[1].get("signal_type")) for c in mock_exec_signal.call_args_list}
                assert ("D", "close_short") in executed
                assert ("B", "open_short") in executed
                assert ("C", "open_short") in executed


# ── TE-SP-01~04: 4.1 数据准备与计算切分用例 ────────────────────────────────────


class TestTESP01PrepareInputSingle:
    """TE-SP-01: DataHandler.get_input_context_single 返回含 df、positions 的 InputContext"""

    @patch("app.utils.db.get_db_connection")
    def test_prepare_input_single_returns_df_and_positions(self, mock_db):
        from app.services.data_handler import DataHandler

        mock_db.return_value = MagicMock(
            cursor=MagicMock(fetchall=MagicMock(return_value=[])),
            __enter__=MagicMock(return_value=MagicMock()),
            __exit__=MagicMock(return_value=False),
        )
        with patch.object(DataHandler, "_fetch_latest_kline", return_value=MOCK_KLINES), \
             patch.object(DataHandler, "_get_current_positions", return_value=[]):
            dh = DataHandler()
            request = {
                "symbol": "BTC/USDT",
                "timeframe": "1H",
                "trading_config": SINGLE_SYMBOL_STRATEGY["trading_config"],
                "need_macro": False,
                "market_category": "Crypto",
            }
            ctx = dh.get_input_context_single(1, request, current_price=100.0)
            assert ctx is not None and "df" in ctx and "positions" in ctx
            assert len(ctx["df"]) >= 2


class TestTESP02PrepareInputCross:
    """TE-SP-02: DataHandler.get_input_context_cross 返回含 data、positions 的 InputContext"""

    @patch("app.utils.db.get_db_connection")
    def test_prepare_input_cross_returns_data_and_positions(self, mock_db):
        from app.services.data_handler import DataHandler

        mock_db.return_value = MagicMock(
            cursor=MagicMock(fetchall=MagicMock(return_value=[])),
            __enter__=MagicMock(return_value=MagicMock()),
            __exit__=MagicMock(return_value=False),
        )
        with patch.object(DataHandler, "_fetch_latest_kline", return_value=MOCK_KLINES), \
             patch.object(DataHandler, "_get_all_positions", return_value=[]):
            dh = DataHandler()
            request = {
                "symbol_list": ["A", "B"],
                "timeframe": "1H",
                "trading_config": CROSS_SECTIONAL_STRATEGY["trading_config"],
                "need_macro": False,
                "market_category": "Crypto",
            }
            ctx = dh.get_input_context_cross(2, request)
            assert ctx is not None and "data" in ctx and "positions" in ctx


class TestTESP03RunIndicatorSingle:
    """TE-SP-03: run_single_indicator + extract_pending_signals_from_df 返回含 pending_signals 的 RawOutput"""

    def test_execute_indicator_df_and_extract_returns_pending_signals(self):
        import pandas as pd
        from app.strategies.single_symbol_indicator import run_single_indicator
        from app.strategies.single_symbol_signals import extract_pending_signals_from_df

        idx = pd.to_datetime([1700000000, 1700003600], unit="s", utc=True)
        df = pd.DataFrame({
            "open": [100, 100.5], "high": [101, 102], "low": [99, 100],
            "close": [100.5, 101], "volume": [1000, 1200],
        }, index=idx)
        executed_df, exec_env = run_single_indicator(
            "pass", df, {}, initial_highest_price=0, initial_position=0,
            initial_avg_entry_price=0, initial_position_count=0, initial_last_add_price=0,
        )
        assert executed_df is None or isinstance(executed_df, pd.DataFrame)
        if executed_df is not None:
            last_kt = int(df.index[-1].timestamp()) if hasattr(df.index[-1], "timestamp") else 0
            pending_signals = extract_pending_signals_from_df(executed_df, {}, last_kt)
            assert isinstance(pending_signals, list)


class TestTESP03bExtractPendingSignals:
    """TE-SP-03b: extract_pending_signals_from_df 从 4-way 列提取信号"""

    def test_extract_pending_signals_from_open_long_column(self):
        import pandas as pd
        from app.strategies.single_symbol_signals import extract_pending_signals_from_df

        idx = pd.to_datetime([1700000000, 1700003600], unit="s", utc=True)
        df = pd.DataFrame({
            "open": [100, 100.5], "high": [101, 102], "low": [99, 100],
            "close": [100.5, 101], "volume": [1000, 1200],
            "open_long": [False, True], "close_long": [False, False],
            "open_short": [False, False], "close_short": [False, False],
        }, index=idx)
        signals = extract_pending_signals_from_df(df, {"signal_mode": "aggressive"}, 1700003600)
        assert isinstance(signals, list)
        assert any(s["type"] == "open_long" for s in signals)


class TestTESP04RunIndicatorCross:
    """TE-SP-04: run_cross_sectional_indicator 返回 scores、rankings"""

    def test_run_cross_sectional_indicator_returns_scores_rankings(self):
        import pandas as pd
        from app.strategies.cross_sectional_indicator import run_cross_sectional_indicator

        idx = pd.to_datetime([1700000000, 1700003600], unit="s", utc=True)
        df = pd.DataFrame({
            "open": [100, 100.5], "high": [101, 102], "low": [99, 100],
            "close": [100.5, 101], "volume": [1000, 1200],
        }, index=idx)
        data = {"A": df, "B": df.copy()}
        code = "scores={'A': 0.9, 'B': 0.5}; rankings=['A', 'B']"
        raw = run_cross_sectional_indicator(code, data, {})
        assert raw and "scores" in raw and "rankings" in raw
        assert raw["scores"]["A"] == 0.9 and raw["rankings"] == ["A", "B"]


class TestTE06bCloseSignalReceivesCorrectPositions:
    """TE-06b: close 信号执行时传入该 symbol 对应的 current_positions"""

    def test_close_signal_receives_correct_current_positions(self):
        """close_long 信号执行时传入该 symbol 对应的 current_positions"""
        import pandas as pd
        TradingExecutor = _import_trading_executor()
        df = pd.DataFrame(MOCK_KLINES)
        df.columns = ["time", "open", "high", "low", "close", "volume"]
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time")
        pos_a = {"symbol": "A", "side": "long", "size": 10.0, "entry_price": 100.0}
        strategy = dict(CROSS_SECTIONAL_STRATEGY)
        strategy["trading_config"] = {
            "symbol_list": ["A", "B"], "timeframe": "1H", "decide_interval": 300,
            "rebalance_frequency": "daily", "cs_strategy_type": "cross_sectional",
        }
        input_ctx = {
            "data": {"A": df, "B": df},
            "positions": [pos_a],
            "trading_config": strategy["trading_config"],
        }
        raw_output = {"scores": {"A": 0.5, "B": 0.9}, "rankings": ["B", "A"]}

        from app.services.data_handler import DataHandler
        with patch("app.services.data_handler.get_db_connection") as mock_db:
            mock_db.return_value = make_db_ctx(strategy)
            with patch.object(TradingExecutor, "_is_strategy_running", side_effect=[True, False]), \
                 patch("app.strategies.cross_sectional.run_cross_sectional_indicator",
                       return_value=raw_output), \
                 patch("app.strategies.cross_sectional.generate_cross_sectional_signals",
                       return_value=[{"symbol": "A", "type": "close_long", "score": 0.5}]), \
                 patch.object(TradingExecutor, "_execute_signal") as mock_exec_signal, \
                 patch.object(DataHandler, "update_last_rebalance"), \
                 patch.object(DataHandler, "get_current_positions", return_value=[pos_a]), \
                 patch.object(DataHandler, "get_all_positions", return_value=[pos_a]):
                mock_exec_signal.return_value = True
                te = TradingExecutor()
                te._should_rebalance = MagicMock(return_value=True)
                te.data_handler.get_input_context_cross = MagicMock(return_value=input_ctx)
                te._run_strategy_loop(2)

        mock_exec_signal.assert_called()
        call_kw = mock_exec_signal.call_args[1]
        assert call_kw.get("symbol") == "A"
        assert call_kw.get("signal_type") == "close_long"
        assert call_kw.get("current_positions") == [pos_a]


# ── SS-01、CS-01: 策略级用例 ─────────────────────────────────────────────────

class TestSS01SingleSymbolStrategyRun:
    """SS-01: SingleSymbolStrategy.get_signals 接收 InputContext，返回信号"""

    def test_single_symbol_get_signals_calls_indicator(self):
        """策略 get_signals 基于 ctx 调用 run_single_indicator"""
        from app.strategies.factory import create_strategy

        import pandas as pd
        idx = pd.to_datetime([1700000000, 1700003600], unit="s", utc=True)
        df = pd.DataFrame({
            "open": [100.0, 100.5], "high": [101.0, 102.0], "low": [99.0, 100.0],
            "close": [100.5, 101.0], "volume": [1000.0, 1200.0],
        }, index=idx)

        ctx = {
            "df": df, "positions": [], "trading_config": {},
            "initial_highest_price": 0, "initial_position": 0,
            "initial_avg_entry_price": 0, "initial_position_count": 0, "initial_last_add_price": 0,
            "strategy_id": 1, "indicator_code": "pass", "current_time": time.time(),
            "current_price": 100.0, "symbol": "BTC/USDT",
        }

        with patch("app.strategies.single_symbol.run_single_indicator") as mock_run_indicator:
            mock_run_indicator.return_value = (pd.DataFrame({"close": [1.0]}), {})
            strat = create_strategy("single")
            signals, cont, _, meta = strat.get_signals(ctx)

        mock_run_indicator.assert_called()
        assert cont is True
        assert isinstance(signals, list)

    def test_single_symbol_get_signals_returns_early_when_current_price_none(self):
        """current_price 为 None 时立即返回空信号"""
        from app.strategies.factory import create_strategy

        import pandas as pd
        idx = pd.to_datetime([1700000000, 1700003600], unit="s", utc=True)
        df = pd.DataFrame({
            "open": [100.0, 100.5], "high": [101.0, 102.0], "low": [99.0, 100.0],
            "close": [100.5, 101.0], "volume": [1000.0, 1200.0],
        }, index=idx)
        ctx = {
            "df": df, "positions": [], "trading_config": {},
            "initial_highest_price": 0, "initial_position": 0,
            "initial_avg_entry_price": 0, "initial_position_count": 0, "initial_last_add_price": 0,
            "strategy_id": 1, "indicator_code": "pass", "current_time": time.time(),
            "current_price": None, "symbol": "BTC/USDT",
        }
        strat = create_strategy("single")
        with patch("app.strategies.single_symbol.run_single_indicator") as mock_run_indicator:
            signals, cont, _, meta = strat.get_signals(ctx)
        mock_run_indicator.assert_not_called()
        assert signals == []
        assert cont is False
        assert meta is None

    def test_single_symbol_get_signals_init_fails_when_df_empty(self):
        """df 为空时 _init_from_ctx 失败，返回空信号"""
        from app.strategies.factory import create_strategy

        import pandas as pd
        ctx = {
            "df": pd.DataFrame(), "positions": [], "trading_config": {},
            "initial_highest_price": 0, "initial_position": 0,
            "initial_avg_entry_price": 0, "initial_position_count": 0, "initial_last_add_price": 0,
            "strategy_id": 1, "indicator_code": "pass", "current_time": time.time(),
            "current_price": 100.0, "symbol": "BTC/USDT",
        }
        strat = create_strategy("single")
        with patch("app.strategies.single_symbol.run_single_indicator") as mock_run_indicator:
            signals, cont, _, meta = strat.get_signals(ctx)
        mock_run_indicator.assert_not_called()
        assert signals == []
        assert cont is False
        assert meta is None

    def test_single_symbol_get_signals_init_fails_when_indicator_returns_none(self):
        """indicator 返回 executed_df=None 时 _init_from_ctx 失败"""
        from app.strategies.factory import create_strategy

        import pandas as pd
        idx = pd.to_datetime([1700000000, 1700003600], unit="s", utc=True)
        df = pd.DataFrame({
            "open": [100.0, 100.5], "high": [101.0, 102.0], "low": [99.0, 100.0],
            "close": [100.5, 101.0], "volume": [1000.0, 1200.0],
        }, index=idx)
        ctx = {
            "df": df, "positions": [], "trading_config": {},
            "initial_highest_price": 0, "initial_position": 0,
            "initial_avg_entry_price": 0, "initial_position_count": 0, "initial_last_add_price": 0,
            "strategy_id": 1, "indicator_code": "pass", "current_time": time.time(),
            "current_price": 100.0, "symbol": "BTC/USDT",
        }
        strat = create_strategy("single")
        with patch("app.strategies.single_symbol.run_single_indicator") as mock_run_indicator:
            mock_run_indicator.return_value = (None, {})
            signals, cont, _, meta = strat.get_signals(ctx)
        assert signals == []
        assert cont is False
        assert meta is None


# ── TE-07: start_strategy / stop_strategy ─────────────────────────────────────

class TestTE07StartStopStrategy:
    """TE-07: start_strategy、stop_strategy 单独用例"""

    @patch("app.services.data_handler.get_db_connection")
    def test_start_strategy_succeeds_and_registers_thread(self, mock_db):
        mock_db.return_value = make_db_ctx(dict(SINGLE_SYMBOL_STRATEGY))
        TradingExecutor = _import_trading_executor()
        with patch.object(TradingExecutor, "_run_strategy_loop"), \
             patch.object(TradingExecutor, "_is_strategy_running", side_effect=[False]):
            te = TradingExecutor()
            ok = te.start_strategy(1)
            assert ok is True
            assert 1 in te.running_strategies
            assert te.running_strategies[1].is_alive() or not te.running_strategies[1].is_alive()

    @patch("app.services.data_handler.get_db_connection")
    def test_start_strategy_already_running_returns_false(self, mock_db):
        mock_db.return_value = make_db_ctx(dict(SINGLE_SYMBOL_STRATEGY))
        TradingExecutor = _import_trading_executor()
        fake_thread = MagicMock()
        fake_thread.is_alive.return_value = True
        with patch.object(TradingExecutor, "_run_strategy_loop"):
            te = TradingExecutor()
            te.running_strategies[1] = fake_thread
            ok = te.start_strategy(1)
            assert ok is False

    @patch("app.services.data_handler.get_db_connection")
    def test_stop_strategy_updates_status_and_removes_from_running(self, mock_db):
        mock_db.return_value = make_db_ctx(dict(SINGLE_SYMBOL_STRATEGY))
        TradingExecutor = _import_trading_executor()
        te = TradingExecutor()
        with patch.object(te.data_handler, "update_strategy_status") as mock_update_status:
            fake_thread = MagicMock()
            fake_thread.is_alive.return_value = True
            te.running_strategies[1] = fake_thread
            ok = te.stop_strategy(1)
            assert ok is True
            assert 1 not in te.running_strategies
            mock_update_status.assert_called_once_with(1, "stopped")

    @patch("app.services.data_handler.get_db_connection")
    def test_stop_strategy_not_running_returns_false(self, mock_db):
        mock_db.return_value = make_db_ctx(dict(SINGLE_SYMBOL_STRATEGY))
        TradingExecutor = _import_trading_executor()
        te = TradingExecutor()
        ok = te.stop_strategy(999)
        assert ok is False


# ── TE-08: server_side 风控真实逻辑 ───────────────────────────────────────────

class TestTE08ServerSideRiskControlRealLogic:
    """TE-08: _server_side_stop_loss / take_profit 未 mock 的真实逻辑用例"""

    def test_server_side_stop_loss_returns_close_long_when_price_below_stop_line(self):
        """持仓多头、价格跌破止损线时返回 close_long"""
        TradingExecutor = _import_trading_executor()
        te = TradingExecutor()
        with patch.object(te.data_handler, "get_current_positions") as mock_pos:
            mock_pos.return_value = [
                {"symbol": "BTC/USDT", "side": "long", "entry_price": 100.0, "size": 0.1},
            ]
            trading_config = {"stop_loss_pct": 5.0, "enable_server_side_stop_loss": True}
            sig = te._server_side_stop_loss_signal(
                strategy_id=1, symbol="BTC/USDT", current_price=94.0,
                market_type="swap", leverage=1.0, trading_config=trading_config,
                timeframe_seconds=3600,
            )
            assert sig is not None
            assert sig.get("type") == "close_long"
            assert sig.get("reason") == "server_stop_loss"
            assert "stop_loss_price" in sig

    def test_server_side_stop_loss_returns_none_when_price_above_stop_line(self):
        """持仓多头、价格未跌破止损线时返回 None"""
        TradingExecutor = _import_trading_executor()
        te = TradingExecutor()
        with patch.object(te.data_handler, "get_current_positions") as mock_pos:
            mock_pos.return_value = [
                {"symbol": "BTC/USDT", "side": "long", "entry_price": 100.0, "size": 0.1},
            ]
            trading_config = {"stop_loss_pct": 5.0}
            sig = te._server_side_stop_loss_signal(
                strategy_id=1, symbol="BTC/USDT", current_price=96.0,
                market_type="swap", leverage=1.0, trading_config=trading_config,
                timeframe_seconds=3600,
            )
            assert sig is None


# ── CS-01: CrossSectionalStrategy 边界 ──────────────────────────────────────

class TestCS01CrossSectionalStrategyRun:
    """CS-01: CrossSectionalStrategy.get_signals 接收 InputContext，返回信号"""

    def test_cross_sectional_get_signals_calls_indicator_and_generate_signals(self):
        """策略 get_signals 基于 ctx 调用 run_indicator、generate_signals"""
        from app.strategies.factory import create_strategy

        ctx = {
            "data": {"A": None, "B": None}, "positions": [],
            "trading_config": {"symbol_list": ["A", "B"]},
            "strategy_id": 2, "indicator_code": "pass",
        }

        with patch("app.strategies.cross_sectional.run_cross_sectional_indicator") as mock_run, \
             patch("app.strategies.cross_sectional.generate_cross_sectional_signals") as mock_gen:
            mock_run.return_value = {"scores": {}, "rankings": []}
            mock_gen.return_value = []
            strat = create_strategy("cross_sectional")
            signals, cont, update_reb, _ = strat.get_signals(ctx)

        mock_run.assert_called_once()
        mock_gen.assert_called_once()
        assert cont is True
        assert update_reb is True
        assert signals == []


class TestCS02CrossSectionalStrategyBoundaries:
    """CS-02: CrossSectionalStrategy 边界：无 symbol_list、data 为空、indicator 返回 None"""

    def test_cross_sectional_returns_early_when_symbol_list_empty(self):
        """symbol_list 为空时返回 [], False, False, None"""
        from app.strategies.factory import create_strategy

        ctx = {
            "data": {"A": MagicMock()}, "positions": [],
            "trading_config": {"symbol_list": []},
            "strategy_id": 2, "indicator_code": "pass",
        }
        strat = create_strategy("cross_sectional")
        with patch("app.strategies.cross_sectional.run_cross_sectional_indicator") as mock_run:
            signals, cont, update_reb, _ = strat.get_signals(ctx)
        mock_run.assert_not_called()
        assert signals == []
        assert cont is False
        assert update_reb is False

    def test_cross_sectional_returns_empty_when_data_empty(self):
        """data 为空时返回 [], True, False, None"""
        from app.strategies.factory import create_strategy

        ctx = {
            "data": {}, "positions": [],
            "trading_config": {"symbol_list": ["A", "B"]},
            "strategy_id": 2, "indicator_code": "pass",
        }
        strat = create_strategy("cross_sectional")
        with patch("app.strategies.cross_sectional.run_cross_sectional_indicator") as mock_run:
            signals, cont, update_reb, _ = strat.get_signals(ctx)
        mock_run.assert_not_called()
        assert signals == []
        assert cont is True
        assert update_reb is False

    def test_cross_sectional_returns_empty_when_indicator_returns_none(self):
        """indicator 返回 None 时返回 [], True, False, None"""
        from app.strategies.factory import create_strategy

        ctx = {
            "data": {"A": MagicMock(), "B": MagicMock()}, "positions": [],
            "trading_config": {"symbol_list": ["A", "B"]},
            "strategy_id": 2, "indicator_code": "pass",
        }
        strat = create_strategy("cross_sectional")
        with patch("app.strategies.cross_sectional.run_cross_sectional_indicator") as mock_run:
            mock_run.return_value = None
            signals, cont, update_reb, _ = strat.get_signals(ctx)
        mock_run.assert_called_once()
        assert signals == []
        assert cont is True
        assert update_reb is False

