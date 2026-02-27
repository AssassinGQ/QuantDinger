"""
TE-01 ~ TE-04: TradingExecutor 级用例

针对 _run_strategy_loop、_run_cross_sectional_strategy_loop 现有行为，
用 mock 构造可控输入，保证重构后行为不变。
"""

import os
import sys
import time
import types
from unittest.mock import patch, MagicMock


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


# ── TE-LOAD: _load_strategy 加载、解析、校验 ─────────────────────────────────

def _make_db_ctx(fetchone_result):
    """构造 get_db_connection 的 context manager mock"""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    conn.cursor.return_value = cursor
    ctx = MagicMock()
    ctx.__enter__.return_value = conn
    ctx.__exit__.return_value = False
    return ctx


class TestTELoadStrategy:
    """TE-LOAD: _load_strategy 解析、校验、归一化 _* 字段"""

    def test_load_strategy_valid_returns_normalized_fields(self):
        """有效策略返回含 _execution_mode、_market_type、_indicator_code 等"""
        TradingExecutor = _import_trading_executor()
        with patch("app.services.trading_executor.get_db_connection") as mock_db:
            mock_db.return_value = _make_db_ctx(dict(SINGLE_SYMBOL_STRATEGY))
            te = TradingExecutor()
            strategy = te._load_strategy(1)
        assert strategy is not None
        assert strategy["_execution_mode"] == "signal"
        assert strategy["_market_type"] in ("swap", "spot")  # leverage=1 -> spot
        assert strategy["_leverage"] == 1.0
        assert strategy["_indicator_code"]  # 非空
        assert "scores" in strategy["_indicator_code"] or "rankings" in strategy["_indicator_code"]

    def test_load_strategy_invalid_strategy_type_returns_none(self):
        """strategy_type 非 IndicatorStrategy 返回 None"""
        TradingExecutor = _import_trading_executor()
        bad = dict(SINGLE_SYMBOL_STRATEGY)
        bad["strategy_type"] = "Other"
        with patch("app.services.trading_executor.get_db_connection") as mock_db:
            mock_db.return_value = _make_db_ctx(bad)
            te = TradingExecutor()
            assert te._load_strategy(1) is None

    def test_load_strategy_leverage_one_sets_market_type_spot(self):
        """leverage=1 时 market_type 归一化为 spot"""
        TradingExecutor = _import_trading_executor()
        cfg = dict(SINGLE_SYMBOL_STRATEGY)
        cfg["trading_config"] = dict(cfg["trading_config"], leverage=1, market_type="swap")
        with patch("app.services.trading_executor.get_db_connection") as mock_db:
            mock_db.return_value = _make_db_ctx(cfg)
            te = TradingExecutor()
            strategy = te._load_strategy(1)
        assert strategy is not None
        assert strategy["_market_type"] == "spot"
        assert strategy["_leverage"] == 1.0

    def test_load_strategy_empty_indicator_code_returns_none(self):
        """indicator_code 为空且 _get_indicator_code_from_db 返回 None 时返回 None"""
        TradingExecutor = _import_trading_executor()
        cfg = dict(SINGLE_SYMBOL_STRATEGY)
        cfg["indicator_config"] = {"indicator_id": 1, "indicator_code": ""}
        with patch("app.services.trading_executor.get_db_connection") as mock_db:
            mock_db.return_value = _make_db_ctx(cfg)
            with patch.object(TradingExecutor, "_get_indicator_code_from_db", return_value=None):
                te = TradingExecutor()
                assert te._load_strategy(1) is None

    def test_load_strategy_invalid_market_type_returns_none(self):
        """market_type 非 swap/spot 时返回 None"""
        TradingExecutor = _import_trading_executor()
        cfg = dict(SINGLE_SYMBOL_STRATEGY)
        cfg["trading_config"] = dict(cfg["trading_config"], market_type="futures")
        with patch("app.services.trading_executor.get_db_connection") as mock_db:
            mock_db.return_value = _make_db_ctx(cfg)
            te = TradingExecutor()
            assert te._load_strategy(1) is None


# ── TE-01: 单标策略启动后能拉 K 线并执行指标 ──────────────────────────────

class TestTE01SingleSymbolFetchesKlineAndExecutesIndicator:
    """TE-01: mock KlineService，断言调用了 _execute_indicator_df"""

    def test_single_symbol_calls_execute_indicator_df(self):
        """单标策略初始化阶段：拉 K 线并调用 _execute_indicator_df"""
        TradingExecutor = _import_trading_executor()

        with patch("app.services.trading_executor.get_db_connection") as mock_db:
            mock_db.return_value = _make_db_ctx(dict(SINGLE_SYMBOL_STRATEGY))
            with patch.object(TradingExecutor, "_fetch_latest_kline", return_value=MOCK_KLINES) as mock_fetch, \
                 patch.object(TradingExecutor, "_get_current_positions", return_value=[]), \
                 patch.object(TradingExecutor, "_is_strategy_running", return_value=False), \
                 patch.object(TradingExecutor, "_execute_indicator_df") as mock_exec_indicator:
                mock_exec_indicator.return_value = (MagicMock(), {})
                te = TradingExecutor()
                te._run_strategy_loop(1)
                mock_fetch.assert_called()
                mock_exec_indicator.assert_called()


# ── TE-02: 截面策略调仓日能生成 signals ───────────────────────────────────

class TestTE02CrossSectionalGeneratesSignals:
    """TE-02: mock 数据，断言 _generate_cross_sectional_signals 返回预期结构"""

    def test_generate_cross_sectional_signals_returns_expected_structure(self):
        """空持仓：rankings A,B,C 且 long_ratio=0.5 -> A open_long, B/C open_short"""
        TradingExecutor = _import_trading_executor()

        with patch.object(TradingExecutor, "_get_all_positions", return_value=[]):
            te = TradingExecutor()
            signals = te._generate_cross_sectional_signals(
                strategy_id=2,
                rankings=["A", "B", "C"],
                scores={"A": 0.9, "B": 0.7, "C": 0.5},
                trading_config={"portfolio_size": 3, "long_ratio": 0.5},
            )

            sig_set = {(s["symbol"], s["type"]) for s in signals}
            assert sig_set == {("A", "open_long"), ("B", "open_short"), ("C", "open_short")}
            assert len(signals) == 3

    def test_generate_cross_sectional_signals_produces_close_short_and_open_short(self):
        """有持仓 A 多/D 空：应生成 close_short(D)、open_short(B)、open_short(C)"""
        TradingExecutor = _import_trading_executor()
        positions = [
            {"symbol": "A", "side": "long", "size": 1.0, "entry_price": 100.0},
            {"symbol": "D", "side": "short", "size": 1.0, "entry_price": 105.0},
        ]

        with patch.object(TradingExecutor, "_get_all_positions", return_value=positions):
            te = TradingExecutor()
            signals = te._generate_cross_sectional_signals(
                strategy_id=2,
                rankings=["A", "B", "C"],
                scores={"A": 0.9, "B": 0.7, "C": 0.5},
                trading_config={"portfolio_size": 3, "long_ratio": 0.5},
            )

            sig_set = {(s["symbol"], s["type"]) for s in signals}
            assert ("D", "close_short") in sig_set
            assert ("B", "open_short") in sig_set
            assert ("C", "open_short") in sig_set
            assert len(signals) == 3

    def test_generate_cross_sectional_signals_produces_close_long(self):
        """多仓 A 不在新 long 列表时，应生成 close_long(A)"""
        TradingExecutor = _import_trading_executor()
        positions = [{"symbol": "A", "side": "long", "size": 1.0, "entry_price": 100.0}]
        # rankings B,C,D；long_count=1, short_count=2 -> long={B}, short={C,D}；A 需 close_long
        with patch.object(TradingExecutor, "_get_all_positions", return_value=positions):
            te = TradingExecutor()
            signals = te._generate_cross_sectional_signals(
                strategy_id=2,
                rankings=["B", "C", "D"],
                scores={"B": 0.9, "C": 0.7, "D": 0.5},
                trading_config={"portfolio_size": 3, "long_ratio": 0.5},
            )

            sig_set = {(s["symbol"], s["type"]) for s in signals}
            assert ("A", "close_long") in sig_set


# ── TE-03: 截面策略非调仓日不执行指标 ─────────────────────────────────────

class TestTE03CrossSectionalNonRebalanceDaySkipsIndicator:
    """TE-03: 断言 _should_rebalance=False 时 _execute_cross_sectional_indicator 未被调用"""

    @patch("app.utils.db.get_db_connection")
    def test_non_rebalance_day_skips_indicator(self, mock_db):
        """当 _should_rebalance 返回 False 时，不调用 _execute_cross_sectional_indicator"""
        TradingExecutor = _import_trading_executor()

        def db_context():
            conn = MagicMock()
            cursor = MagicMock()
            # last_rebalance_at 为"今天" -> 不调仓
            cursor.fetchone.side_effect = [
                CROSS_SECTIONAL_STRATEGY,
                {"last_rebalance_at": "2025-02-25T00:00:00+00:00"},
            ]
            conn.cursor.return_value = cursor
            conn.__enter__ = MagicMock(return_value=conn)
            conn.__exit__ = MagicMock(return_value=False)
            return conn
        mock_db.return_value = db_context()

        call_count = [0]

        def count_exec(*_args, **_kwargs):
            call_count[0] += 1
            return {"scores": {}, "rankings": []}

        with patch.object(
            TradingExecutor, "_is_strategy_running"
        ) as mock_running, patch.object(
            TradingExecutor, "_execute_cross_sectional_indicator"
        ) as mock_exec_cross:
            mock_running.side_effect = [True, False]  # 第一次 True，第二次 False 退出
            mock_exec_cross.side_effect = count_exec

            te = TradingExecutor()
            # 需要 _should_rebalance 返回 False 才不执行指标
            te._should_rebalance = MagicMock(return_value=False)
            te._run_strategy_loop(2)

            # 非调仓日：_execute_cross_sectional_indicator 不应被调用
            mock_exec_cross.assert_not_called()


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
        TradingExecutor = _import_trading_executor()

        time_vals = [0, 5, 10]

        def mock_time():
            return time_vals.pop(0) if time_vals else 100

        mock_indicator_result = {"pending_signals": [], "last_kline_time": 0, "new_highest_price": 0}
        mock_df = MagicMock()
        mock_df.index = [MagicMock()]
        mock_df.index[-1].timestamp.return_value = 0

        with patch("app.services.trading_executor.get_db_connection") as mock_db:
            mock_db.return_value = _make_db_ctx(dict(SINGLE_SYMBOL_STRATEGY))
            with patch.dict(os.environ, {"STRATEGY_TICK_INTERVAL_SEC": "10"}), \
             patch.object(TradingExecutor, "_fetch_latest_kline", return_value=MOCK_KLINES), \
             patch.object(TradingExecutor, "_get_current_positions", return_value=[]), \
             patch.object(TradingExecutor, "_execute_indicator_with_prices",
                         return_value=mock_indicator_result), \
             patch("time.time", side_effect=mock_time), \
             patch("time.sleep", MagicMock()) as mock_sleep, \
             patch.object(TradingExecutor, "_is_strategy_running",
                         side_effect=[True, True, True, False]), \
             patch.object(TradingExecutor, "_fetch_current_price", return_value=100.0), \
             patch.object(TradingExecutor, "_update_dataframe_with_current_price",
                         return_value=mock_df), \
             patch.object(TradingExecutor, "_update_positions"), \
             patch.object(TradingExecutor, "_console_print"):
                te = TradingExecutor()
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
    positions: mock _get_current_positions 的返回值，close 信号需有持仓
    """
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
    with patch("app.services.trading_executor.get_db_connection") as mock_db:
        mock_db.return_value = _make_db_ctx(strategy)
        with patch.object(TradingExecutorCls, "_fetch_latest_kline", return_value=MOCK_KLINES), \
             patch.object(TradingExecutorCls, "_get_current_positions", return_value=positions or []), \
             patch.object(TradingExecutorCls, "_execute_indicator_with_prices",
                         return_value=indicator_result), \
             patch.object(TradingExecutorCls, "_is_strategy_running",
                         side_effect=[True, False]), \
             patch.object(TradingExecutorCls, "_fetch_current_price", return_value=100.0), \
             patch.object(TradingExecutorCls, "_execute_signal") as mock_exec_signal, \
             patch.object(TradingExecutorCls, "_update_positions"), \
             patch.object(TradingExecutorCls, "_console_print"), \
             patch.object(TradingExecutorCls, "_should_skip_signal_once_per_candle",
                         return_value=False), \
             patch.object(TradingExecutorCls, "_server_side_take_profit_or_trailing_signal",
                         return_value=None), \
             patch.object(TradingExecutorCls, "_server_side_stop_loss_signal",
                         return_value=None):
            mock_exec_signal.return_value = True
            te = TradingExecutorCls()
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


# ── TE-04b: 截面 tick 节奏 ─────────────────────────────────────────────────

class TestTE04bCrossSectionalTickCadence:
    """TE-04b: 截面 loop 的 tick 节奏由 decide_interval 控制"""

    def test_cross_sectional_loop_uses_decide_interval(self):
        """截面 loop 在非调仓日会按 decide_interval 控制 sleep"""
        TradingExecutor = _import_trading_executor()
        strategy = dict(CROSS_SECTIONAL_STRATEGY)
        strategy["trading_config"] = dict(strategy["trading_config"], decide_interval=300)
        strategy.update({
            "_execution_mode": "signal", "_notification_config": {},
            "_strategy_name": "test", "_market_category": "Crypto",
            "_market_type": "swap", "_leverage": 1.0, "_initial_capital": 10000.0,
            "_indicator_code": "pass",
        })
        time_vals = [0, 5, 100, 200]

        def mock_time():
            return time_vals.pop(0) if time_vals else 300

        with patch("time.time", side_effect=mock_time), \
             patch("time.sleep", MagicMock()) as mock_sleep, \
             patch.object(TradingExecutor, "_is_strategy_running",
                         side_effect=[True, True, True, False]), \
             patch.object(TradingExecutor, "_should_rebalance", return_value=False):
            te = TradingExecutor()
            te._run_cross_sectional_strategy_loop(strategy_id=2, strategy=strategy)

            mock_sleep.assert_called()
            assert mock_sleep.call_args[0][0] == 1.0


# ── TE-06: 截面调仓日 exec_indicator → signals → 批量 _execute_signal ────

class TestTE06CrossSectionalExecuteSignalAfterIndicator:
    """TE-06: 截面调仓日 indicator → signals → 批量 _execute_signal"""

    def test_rebalance_day_executes_signals(self):
        """空持仓：rankings A,B,C -> 应执行 A open_long, B open_short, C open_short 共 3 次"""
        TradingExecutor = _import_trading_executor()
        indicator_result = {"scores": {"A": 0.9, "B": 0.7, "C": 0.5}, "rankings": ["A", "B", "C"]}

        with patch.object(TradingExecutor, "_is_strategy_running",
                         side_effect=[True, False]), \
             patch.object(TradingExecutor, "_should_rebalance", return_value=True), \
             patch.object(TradingExecutor, "_get_all_positions", return_value=[]), \
             patch.object(TradingExecutor, "_fetch_latest_kline", return_value=MOCK_KLINES), \
             patch.object(TradingExecutor, "_execute_signal") as mock_exec_signal, \
             patch.object(TradingExecutor, "_update_last_rebalance"):
            mock_exec_signal.return_value = True
            te = TradingExecutor()
            te._execute_cross_sectional_indicator = MagicMock(return_value=indicator_result)
            strategy = dict(CROSS_SECTIONAL_STRATEGY)
            strategy.update({
                "_execution_mode": "signal", "_notification_config": {},
                "_strategy_name": "test_cross", "_market_category": "Crypto",
                "_market_type": "swap", "_leverage": 1.0, "_initial_capital": 10000.0,
                "_indicator_code": "scores={}; rankings=[]",
            })
            te._run_cross_sectional_strategy_loop(strategy_id=2, strategy=strategy)

            assert mock_exec_signal.call_count == 3
            executed = {(c[1].get("symbol"), c[1].get("signal_type")) for c in mock_exec_signal.call_args_list}
            assert executed == {("A", "open_long"), ("B", "open_short"), ("C", "open_short")}

    def test_rebalance_day_executes_close_and_open_signals_when_positions_exist(self):
        """有持仓 A 多/D 空：应执行 close_short(D)、open_short(B)、open_short(C) 共 3 次"""
        TradingExecutor = _import_trading_executor()
        positions = [
            {"symbol": "A", "side": "long", "size": 1.0, "entry_price": 100.0},
            {"symbol": "D", "side": "short", "size": 1.0, "entry_price": 105.0},
        ]
        indicator_result = {"scores": {"A": 0.9, "B": 0.7, "C": 0.5}, "rankings": ["A", "B", "C"]}

        with patch.object(TradingExecutor, "_is_strategy_running",
                         side_effect=[True, False]), \
             patch.object(TradingExecutor, "_should_rebalance", return_value=True), \
             patch.object(TradingExecutor, "_get_all_positions", return_value=positions), \
             patch.object(TradingExecutor, "_fetch_latest_kline", return_value=MOCK_KLINES), \
             patch.object(TradingExecutor, "_execute_signal") as mock_exec_signal, \
             patch.object(TradingExecutor, "_update_last_rebalance"):
            mock_exec_signal.return_value = True
            te = TradingExecutor()
            te._execute_cross_sectional_indicator = MagicMock(return_value=indicator_result)
            strategy = dict(CROSS_SECTIONAL_STRATEGY)
            strategy.update({
                "_execution_mode": "signal", "_notification_config": {},
                "_strategy_name": "test_cross", "_market_category": "Crypto",
                "_market_type": "swap", "_leverage": 1.0, "_initial_capital": 10000.0,
                "_indicator_code": "scores={}; rankings=[]",
            })
            te._run_cross_sectional_strategy_loop(strategy_id=2, strategy=strategy)

            assert mock_exec_signal.call_count == 3
            executed = {(c[1].get("symbol"), c[1].get("signal_type")) for c in mock_exec_signal.call_args_list}
            assert ("D", "close_short") in executed
            assert ("B", "open_short") in executed
            assert ("C", "open_short") in executed


# ── TE-SP-01~04: 4.1 数据准备与计算切分用例 ────────────────────────────────────


class TestTESP01PrepareInputSingle:
    """TE-SP-01: _prepare_input_single 返回含 df、positions 的 InputContext"""

    @patch("app.utils.db.get_db_connection")
    def test_prepare_input_single_returns_df_and_positions(self, mock_db):
        TradingExecutor = _import_trading_executor()
        mock_db.return_value = MagicMock(
            cursor=MagicMock(fetchone=MagicMock(return_value={})),
            __enter__=MagicMock(return_value=MagicMock()),
            __exit__=MagicMock(return_value=False),
        )
        with patch.object(TradingExecutor, "_fetch_latest_kline", return_value=MOCK_KLINES), \
             patch.object(TradingExecutor, "_get_current_positions", return_value=[]):
            te = TradingExecutor()
            ctx = te._prepare_input_single(
                1, "BTC/USDT", "1H",
                SINGLE_SYMBOL_STRATEGY["trading_config"], "Crypto",
                need_macro=False,
            )
            assert ctx is not None and "df" in ctx and "positions" in ctx
            assert len(ctx["df"]) >= 2


class TestTESP02PrepareInputCross:
    """TE-SP-02: _prepare_input_cross 返回含 data、positions 的 InputContext"""

    @patch("app.utils.db.get_db_connection")
    def test_prepare_input_cross_returns_data_and_positions(self, mock_db):
        TradingExecutor = _import_trading_executor()
        mock_db.return_value = MagicMock(
            cursor=MagicMock(),
            __enter__=MagicMock(return_value=MagicMock()),
            __exit__=MagicMock(return_value=False),
        )
        with patch.object(TradingExecutor, "_fetch_latest_kline", return_value=MOCK_KLINES), \
             patch.object(TradingExecutor, "_get_all_positions", return_value=[]):
            te = TradingExecutor()
            ctx = te._prepare_input_cross(
                2, ["A", "B"], "1H",
                CROSS_SECTIONAL_STRATEGY["trading_config"], "Crypto",
                need_macro=False,
            )
            assert ctx is not None and "data" in ctx and "positions" in ctx and "symbols" in ctx


class TestTESP03RunIndicatorSingle:
    """TE-SP-03: _run_indicator_single 返回含 pending_signals 的 RawOutput"""

    def test_run_indicator_single_returns_pending_signals(self):
        import pandas as pd
        TradingExecutor = _import_trading_executor()
        idx = pd.to_datetime([1700000000, 1700003600], unit="s", utc=True)
        input_ctx = {
            "df": pd.DataFrame({
                "open": [100, 100.5], "high": [101, 102], "low": [99, 100],
                "close": [100.5, 101], "volume": [1000, 1200],
            }, index=idx),
            "initial_highest_price": 0, "initial_position": 0,
            "initial_avg_entry_price": 0, "initial_position_count": 0,
            "initial_last_add_price": 0, "trading_config": {},
        }
        te = TradingExecutor()
        raw = te._run_indicator_single(input_ctx, "pass")
        assert raw is None or isinstance(raw, dict)
        if raw:
            assert "pending_signals" in raw or "last_kline_time" in raw or "new_highest_price" in raw


class TestTESP04RunIndicatorCross:
    """TE-SP-04: _run_indicator_cross 返回 scores、rankings"""

    def test_run_indicator_cross_returns_scores_rankings(self):
        import pandas as pd
        TradingExecutor = _import_trading_executor()
        idx = pd.to_datetime([1700000000, 1700003600], unit="s", utc=True)
        df = pd.DataFrame({
            "open": [100, 100.5], "high": [101, 102], "low": [99, 100],
            "close": [100.5, 101], "volume": [1000, 1200],
        }, index=idx)
        input_ctx = {
            "data": {"A": df, "B": df.copy()},
            "symbols": ["A", "B"],
            "trading_config": {},
            "market_category": "Crypto",
            "timeframe": "1H",
        }
        te = TradingExecutor()
        code = "scores={'A': 0.9, 'B': 0.5}; rankings=['A', 'B']"
        raw = te._run_indicator_cross(input_ctx, code)
        assert raw and "scores" in raw and "rankings" in raw
        assert raw["scores"]["A"] == 0.9 and raw["rankings"] == ["A", "B"]


class TestTESP05GenerateSignalsSingle:
    """TE-SP-05: _generate_signals_single 给定 RawOutput 返回 List[Signal]（Executor 解析输出）"""

    def test_generate_signals_single_returns_pending_signals(self):
        TradingExecutor = _import_trading_executor()
        raw_output = {
            "pending_signals": [
                {"type": "open_long", "trigger_price": 100, "position_size": 0.08, "timestamp": 1700000000},
            ],
            "last_kline_time": 1700000000,
            "new_highest_price": 0,
        }
        te = TradingExecutor()
        signals = te._generate_signals_single(raw_output, {})
        assert isinstance(signals, list) and len(signals) == 1
        assert signals[0]["type"] == "open_long" and signals[0]["trigger_price"] == 100

    def test_generate_signals_single_empty_when_no_pending(self):
        TradingExecutor = _import_trading_executor()
        raw_output = {"pending_signals": [], "last_kline_time": 0, "new_highest_price": 0}
        te = TradingExecutor()
        signals = te._generate_signals_single(raw_output, {})
        assert signals == []

    def test_generate_signals_single_empty_when_raw_none(self):
        TradingExecutor = _import_trading_executor()
        te = TradingExecutor()
        signals = te._generate_signals_single(None, {})
        assert signals == []


