"""
DataHandler 直接覆盖用例：每个 public/private 方法至少有一个用例。
"""

import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import pandas as pd

from app.services.data_handler import DataHandler
from tests.conftest import make_db_ctx


MOCK_KLINES = [
    {"time": 1700000000, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0},
    {"time": 1700003600, "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.0, "volume": 1200.0},
]


class TestDataHandlerGetInputContextSingle:
    """get_input_context_single 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_df_and_positions(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchall_result=[])
        with patch.object(DataHandler, "_fetch_latest_kline", return_value=MOCK_KLINES), \
             patch.object(DataHandler, "_get_current_positions", return_value=[]):
            dh = DataHandler()
            request = {
                "symbol": "BTC/USDT",
                "timeframe": "1H",
                "trading_config": {},
                "need_macro": False,
                "market_category": "Crypto",
            }
            ctx = dh.get_input_context_single(1, request, current_price=100.0)
            assert ctx is not None
            assert "df" in ctx and "positions" in ctx
            assert len(ctx["df"]) >= 2
            assert ctx["initial_highest_price"] == 0.0
            assert ctx["initial_position"] == 0

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_none_when_klines_empty(self, mock_db):
        with patch.object(DataHandler, "_fetch_latest_kline", return_value=[]):
            dh = DataHandler()
            ctx = dh.get_input_context_single(1, {"symbol": "X", "timeframe": "1H"}, current_price=100.0)
            assert ctx is None

    @patch("app.services.data_handler.get_db_connection")
    def test_uses_df_override_when_provided(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchall_result=[])
        df_override = pd.DataFrame(MOCK_KLINES)
        df_override["time"] = pd.to_datetime(df_override["time"], unit="s", utc=True)
        df_override = df_override.set_index("time")
        with patch.object(DataHandler, "_get_current_positions", return_value=[]), \
             patch.object(DataHandler, "_update_dataframe_with_current_price", side_effect=lambda df, *a, **kw: df):
            dh = DataHandler()
            request = {
                "symbol": "BTC/USDT",
                "timeframe": "1H",
                "trading_config": {},
                "df_override": df_override,
                "market_category": "Crypto",
            }
            ctx = dh.get_input_context_single(1, request, current_price=100.0)
            assert ctx is not None
            assert len(ctx["df"]) == 2


class TestDataHandlerGetInputContextCross:
    """get_input_context_cross 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_data_and_positions(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchall_result=[])
        with patch.object(DataHandler, "_fetch_latest_kline", return_value=MOCK_KLINES), \
             patch.object(DataHandler, "_get_all_positions", return_value=[]):
            dh = DataHandler()
            request = {
                "symbol_list": ["A", "B"],
                "timeframe": "1H",
                "trading_config": {},
                "need_macro": False,
                "market_category": "Crypto",
            }
            ctx = dh.get_input_context_cross(2, request)
            assert ctx is not None
            assert "data" in ctx and "positions" in ctx
            assert "A" in ctx["data"] and "B" in ctx["data"]

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_none_when_symbol_list_empty(self, mock_db):
        dh = DataHandler()
        ctx = dh.get_input_context_cross(2, {"symbol_list": [], "trading_config": {}})
        assert ctx is None


class TestDataHandlerEnsureDbColumns:
    """ensure_db_columns 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_postgresql_skips_alter_when_columns_exist(self, mock_db):
        mock_db.return_value = make_db_ctx(
            fetchall_result=[{"column_name": "highest_price"}, {"column_name": "lowest_price"}]
        )
        with patch.dict(os.environ, {"DB_TYPE": "postgresql"}):
            dh = DataHandler()
            dh.ensure_db_columns()
        cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
        assert cursor.execute.call_count >= 1

    @patch("app.services.data_handler.get_db_connection")
    def test_sqlite_runs_alter_when_columns_missing(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchall_result=[{"name": "id"}])
        with patch.dict(os.environ, {"DB_TYPE": "sqlite"}):
            dh = DataHandler()
            dh.ensure_db_columns()
        cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
        assert cursor.execute.call_count >= 2


class TestDataHandlerUpdateStrategyStatus:
    """update_strategy_status 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_executes_update(self, mock_db):
        mock_db.return_value = make_db_ctx()
        dh = DataHandler()
        dh.update_strategy_status(1, "stopped")
        cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
        cursor.execute.assert_called_once()
        call_args = cursor.execute.call_args[0]
        assert "UPDATE" in call_args[0]
        assert "stopped" in call_args[1]
        assert 1 in call_args[1]


class TestDataHandlerGetStrategyRow:
    """get_strategy_row 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_strategy_dict(self, mock_db):
        row = {"id": 1, "strategy_name": "test", "strategy_type": "IndicatorStrategy"}
        mock_db.return_value = make_db_ctx(fetchone_result=row)
        dh = DataHandler()
        result = dh.get_strategy_row(1)
        assert result == row
        cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
        cursor.execute.assert_called_once()
        assert "qd_strategies_trading" in cursor.execute.call_args[0][0]

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_none_when_not_found(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchone_result=None)
        dh = DataHandler()
        assert dh.get_strategy_row(999) is None


class TestDataHandlerGetIndicatorCode:
    """get_indicator_code 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_code(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchone_result={"code": "scores={}; rankings=[]"})
        dh = DataHandler()
        result = dh.get_indicator_code(1)
        assert result == "scores={}; rankings=[]"
        cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
        cursor.execute.assert_called_once()
        assert "qd_indicator_codes" in cursor.execute.call_args[0][0]

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_none_when_not_found(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchone_result=None)
        dh = DataHandler()
        assert dh.get_indicator_code(999) is None


class TestDataHandlerGetStrategyStatus:
    """get_strategy_status 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_running(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchone_result={"status": "running"})
        dh = DataHandler()
        status = dh.get_strategy_status(1)
        assert status == "running"

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_none_when_no_row(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchone_result=None)
        dh = DataHandler()
        status = dh.get_strategy_status(1)
        assert status is None


class TestDataHandlerGetUserId:
    """get_user_id 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_user_id(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchone_result={"user_id": 42})
        dh = DataHandler()
        uid = dh.get_user_id(1)
        assert uid == 42

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_1_on_exception(self, mock_db):
        mock_db.return_value = MagicMock()
        mock_db.return_value.__enter__.side_effect = Exception("db error")
        mock_db.return_value.__exit__.return_value = False
        dh = DataHandler()
        uid = dh.get_user_id(1)
        assert uid == 1


class TestDataHandlerGetCurrentPositions:
    """get_current_positions / _get_current_positions 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_matched_positions(self, mock_db):
        pos = {"symbol": "BTC/USDT", "side": "long", "size": 0.1}
        mock_db.return_value = make_db_ctx(fetchall_result=[pos])
        dh = DataHandler()
        result = dh.get_current_positions(1, "BTC/USDT")
        assert result == [pos]

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_empty_on_exception(self, mock_db):
        mock_db.return_value = make_db_ctx()
        mock_db.return_value.__enter__.return_value.cursor.side_effect = Exception("db error")
        dh = DataHandler()
        result = dh._get_current_positions(1, "X")
        assert result == []


class TestDataHandlerGetAllPositions:
    """get_all_positions / _get_all_positions 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_positions(self, mock_db):
        positions = [{"symbol": "A", "side": "long"}, {"symbol": "B", "side": "short"}]
        mock_db.return_value = make_db_ctx(fetchall_result=positions)
        dh = DataHandler()
        result = dh.get_all_positions(1)
        assert result == positions


class TestDataHandlerPersistNotification:
    """persist_notification 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_inserts_notification(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchone_result={"user_id": 1})
        dh = DataHandler()
        dh.persist_notification(1, "BTC/USDT", "open_long", "title", "msg")
        cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args[0]
        assert "INSERT" in call_args[0]
        assert "open_long" in call_args[1]


class TestDataHandlerRecordTrade:
    """record_trade 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_inserts_trade(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchone_result={"user_id": 1})
        dh = DataHandler()
        dh.record_trade(1, "BTC/USDT", "buy", 100.0, 0.1, 10.0)
        cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args[0]
        assert "INSERT" in call_args[0]


class TestDataHandlerUpdatePosition:
    """update_position 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_executes_upsert(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchone_result={"user_id": 1})
        dh = DataHandler()
        dh.update_position(1, "BTC/USDT", "long", 0.1, 100.0, 101.0, 102.0, 99.0)
        cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
        cursor.execute.assert_called()


class TestDataHandlerClosePosition:
    """close_position 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_executes_delete(self, mock_db):
        mock_db.return_value = make_db_ctx()
        dh = DataHandler()
        dh.close_position(1, "BTC/USDT", "long")
        cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args[0]
        assert "DELETE" in call_args[0]
        assert "BTC/USDT" in str(call_args[1])
        assert "long" in str(call_args[1])


class TestDataHandlerUpdatePositionsCurrentPrice:
    """update_positions_current_price 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_executes_update(self, mock_db):
        mock_db.return_value = make_db_ctx()
        dh = DataHandler()
        dh.update_positions_current_price(1, "BTC/USDT", 105.0)
        cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args[0]
        assert "UPDATE" in call_args[0]


class TestDataHandlerUpdateLastRebalance:
    """update_last_rebalance 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_executes_update(self, mock_db):
        mock_db.return_value = make_db_ctx()
        dh = DataHandler()
        dh.update_last_rebalance(1)
        cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
        cursor.execute.assert_called()
        assert "last_rebalance_at" in str(cursor.execute.call_args)


class TestDataHandlerFindRecentPendingOrder:
    """find_recent_pending_order 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_order_when_found(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchone_result={"id": 10, "status": "pending"})
        dh = DataHandler()
        result = dh.find_recent_pending_order(1, "BTC/USDT", "open_long", signal_ts=12345)
        assert result == {"id": 10, "status": "pending"}

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_none_when_not_found(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchone_result=None)
        dh = DataHandler()
        result = dh.find_recent_pending_order(1, "BTC/USDT", "open_long")
        assert result is None


class TestDataHandlerInsertPendingOrder:
    """insert_pending_order 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_pending_id(self, mock_db):
        ctx = make_db_ctx(lastrowid=99)
        mock_db.return_value = ctx
        dh = DataHandler()
        pid = dh.insert_pending_order(
            user_id=1, strategy_id=1, symbol="BTC/USDT", signal_type="open_long",
            signal_ts=0, market_type="swap", order_type="market", amount=0.1, price=100.0,
            execution_mode="signal", status="pending", priority=0, attempts=0, max_attempts=3,
            payload_json="{}",
        )
        assert pid == 99
        cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
        cursor.execute.assert_called()


class TestDataHandlerGetLastRebalanceAt:
    """get_last_rebalance_at 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_datetime(self, mock_db):
        dt = datetime(2025, 2, 26, 0, 0, 0)
        mock_db.return_value = make_db_ctx(fetchone_result={"last_rebalance_at": dt})
        dh = DataHandler()
        result = dh.get_last_rebalance_at(1)
        assert result == dt

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_none_when_no_record(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchone_result=None)
        dh = DataHandler()
        result = dh.get_last_rebalance_at(1)
        assert result is None


class TestDataHandlerKlinesToDataframe:
    """_klines_to_dataframe 直接覆盖"""

    def test_converts_klines_to_df(self):
        dh = DataHandler()
        df = dh._klines_to_dataframe(MOCK_KLINES)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "close" in df.columns

    def test_returns_empty_when_klines_empty(self):
        dh = DataHandler()
        df = dh._klines_to_dataframe([])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]


class TestDataHandlerFetchLatestKline:
    """_fetch_latest_kline 直接覆盖"""

    def test_returns_klines_from_kline_service(self):
        dh = DataHandler()
        with patch.object(dh.kline_service, "get_kline", return_value=MOCK_KLINES):
            result = dh._fetch_latest_kline("BTC/USDT", "1H", limit=100)
            assert result == MOCK_KLINES

    def test_returns_empty_on_exception(self):
        dh = DataHandler()
        with patch.object(dh.kline_service, "get_kline", side_effect=Exception("network error")):
            result = dh._fetch_latest_kline("X", "1H")
            assert result == []


class TestDataHandlerUpdateDataframeWithCurrentPrice:
    """_update_dataframe_with_current_price 直接覆盖"""

    @patch("app.services.data_handler.time")
    def test_updates_last_row_when_same_period(self, mock_time):
        # 最后一根 K 线在 1H 周期边界，且 now 在同一周期内，则更新最后一行的 close
        period_start = 1700002800  # 1H 周期起点
        mock_time.time.return_value = float(period_start) + 1.0
        df = pd.DataFrame([
            {"time": period_start - 3600, "open": 99.0, "high": 100.0, "low": 98.0, "close": 99.5, "volume": 500.0},
            {"time": period_start, "open": 99.5, "high": 101.0, "low": 99.0, "close": 101.0, "volume": 1000.0},
        ])
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time")
        dh = DataHandler()
        out = dh._update_dataframe_with_current_price(df.copy(), 102.0, "1H")
        assert float(out.iloc[-1]["close"]) == 102.0

    def test_returns_df_unchanged_when_empty(self):
        dh = DataHandler()
        empty = pd.DataFrame()
        result = dh._update_dataframe_with_current_price(empty, 100.0, "1H")
        assert len(result) == 0
