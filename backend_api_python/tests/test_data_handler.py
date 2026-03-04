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

    @patch("app.services.data_handler.DataHandler._fetch_all")
    def test_returns_df_and_positions(self, mock_fetch_all):
        mock_fetch_all.return_value = [{"side": "long", "highest_price": 105.0, "entry_price": 100.0}]
        with patch.object(DataHandler, "_fetch_latest_kline", return_value=MOCK_KLINES):
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
            assert ctx["initial_highest_price"] == 105.0
            assert ctx["initial_position"] == 1
            assert ctx["initial_avg_entry_price"] == 100.0
            assert ctx["initial_position_count"] == 1
            assert ctx["initial_last_add_price"] == 100.0

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_none_when_klines_empty(self, mock_db):
        with patch.object(DataHandler, "_fetch_latest_kline", return_value=[]):
            dh = DataHandler()
            ctx = dh.get_input_context_single(1, {"symbol": "X", "timeframe": "1H"}, current_price=100.0)
            assert ctx is None

    def test_get_input_context_single_empty_df(self):
        dh = DataHandler()
        with patch.object(dh, "_fetch_latest_kline", return_value=[{"time": 1}, {"time": 2}]):
            with patch.object(dh, "_klines_to_dataframe", return_value=pd.DataFrame()):
                request = {"symbol": "BTC/USDT", "timeframe": "1H"}
                ctx = dh.get_input_context_single(1, request)
                assert ctx is None

    @patch("app.services.data_handler.DataHandler._fetch_all")
    def test_uses_df_override_when_provided(self, mock_fetch_all):
        mock_fetch_all.return_value = []
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

    @patch("app.services.data_handler.DataHandler._fetch_all")
    def test_returns_data_and_positions(self, mock_fetch_all):
        mock_fetch_all.return_value = [{"symbol": "A", "side": "short", "highest_price": 105.0, "entry_price": 100.0}]
        with patch.object(DataHandler, "_fetch_latest_kline", return_value=MOCK_KLINES):
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
            assert ctx["positions"][0]["symbol"] == "A"
            assert ctx["positions"][0]["side"] == "short"

    @patch("app.services.data_handler.get_db_connection")
    def test_returns_none_when_symbol_list_empty(self, mock_db):
        dh = DataHandler()
        ctx = dh.get_input_context_cross(2, {"symbol_list": [], "trading_config": {}})
        assert ctx is None

    @patch("app.services.data_handler.MacroDataService.enrich_dataframe_realtime")
    @patch("app.services.data_handler.DataHandler._fetch_all")
    def test_get_input_context_cross_macro_fail(self, mock_fetch_all, mock_macro):
        mock_fetch_all.return_value = []
        mock_macro.side_effect = Exception("Macro API down")
        with patch.object(DataHandler, "_fetch_latest_kline", return_value=MOCK_KLINES):
            dh = DataHandler()
            request = {"symbol_list": ["BTC"], "need_macro": True}
            ctx = dh.get_input_context_cross(2, request)
            assert ctx is not None
            mock_macro.assert_called_once()

    @patch("app.services.data_handler.DataHandler._fetch_latest_kline")
    def test_get_input_context_cross_fetch_exception(self, mock_fetch):
        mock_fetch.side_effect = Exception("Network Error")
        dh = DataHandler()
        request = {"symbol_list": ["BTC", "ETH"]}
        ctx = dh.get_input_context_cross(2, request)
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

    @patch("app.services.data_handler.get_db_connection")
    def test_postgresql_runs_alter_when_columns_missing(self, mock_db):
        mock_db.return_value = make_db_ctx(fetchall_result=[{"column_name": "id"}])
        with patch.dict(os.environ, {"DB_TYPE": "postgresql"}):
            dh = DataHandler()
            dh.ensure_db_columns()
        cursor = mock_db.return_value.__enter__.return_value.cursor.return_value
        assert cursor.execute.call_count >= 2

    @patch("app.services.data_handler.get_db_connection")
    def test_postgresql_exception(self, mock_db):
        mock_db.return_value.__enter__.return_value.cursor.return_value.execute.side_effect = Exception("PG Error")
        with patch.dict(os.environ, {"DB_TYPE": "postgresql"}):
            dh = DataHandler()
            dh.ensure_db_columns()

    @patch("app.services.data_handler.get_db_connection")
    def test_sqlite_exception(self, mock_db):
        mock_db.return_value.__enter__.return_value.cursor.return_value.execute.side_effect = Exception("SQLite Error")
        with patch.dict(os.environ, {"DB_TYPE": "sqlite"}):
            dh = DataHandler()
            dh.ensure_db_columns()

    @patch("app.services.data_handler.get_db_connection")
    def test_ensure_db_columns_outer_exception(self, mock_db):
        mock_db.side_effect = Exception("Outer DB Error")
        dh = DataHandler()
        dh.ensure_db_columns()


class TestDataHandlerUpdateStrategyStatus:
    """update_strategy_status 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._execute_query")
    def test_executes_update(self, mock_exec):
        dh = DataHandler()
        dh.update_strategy_status(1, "stopped")
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args[0]
        assert "UPDATE" in call_args[0]
        assert "stopped" in call_args[1]
        assert 1 in call_args[1]


class TestDataHandlerGetStrategyRow:
    """get_strategy_row 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_strategy_dict(self, mock_fetch_one):
        row = {"id": 1, "strategy_name": "test", "strategy_type": "IndicatorStrategy"}
        mock_fetch_one.return_value = row
        dh = DataHandler()
        result = dh.get_strategy_row(1)
        assert result == row
        mock_fetch_one.assert_called_once()

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_none_when_not_found(self, mock_fetch_one):
        mock_fetch_one.return_value = None
        dh = DataHandler()
        assert dh.get_strategy_row(999) is None

class TestDataHandlerGetIndicatorCode:
    """get_indicator_code 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_code(self, mock_fetch_one):
        mock_fetch_one.return_value = {"code": "scores={}; rankings=[]"}
        dh = DataHandler()
        result = dh.get_indicator_code(1)
        assert result == "scores={}; rankings=[]"

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_none_when_not_found(self, mock_fetch_one):
        mock_fetch_one.return_value = None
        dh = DataHandler()
        assert dh.get_indicator_code(999) is None


class TestDataHandlerGetStrategyStatus:
    """get_strategy_status 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_running(self, mock_fetch_one):
        mock_fetch_one.return_value = {"status": "running"}
        dh = DataHandler()
        status = dh.get_strategy_status(1)
        assert status == "running"

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_none_when_no_row(self, mock_fetch_one):
        mock_fetch_one.return_value = None
        dh = DataHandler()
        status = dh.get_strategy_status(1)
        assert status is None


class TestDataHandlerGetUserId:
    """get_user_id 直接覆盖"""

    @patch("app.services.data_handler.get_db_connection")
    def test_db_methods_success(self, mock_db):
        mock_ctx = make_db_ctx()
        mock_db.return_value = mock_ctx
        cursor = mock_ctx.__enter__.return_value.cursor.return_value
        cursor.lastrowid = 123
        cursor.fetchone.return_value = {"id": 1}
        cursor.fetchall.return_value = [{"id": 1}, {"id": 2}]

        dh = DataHandler()
        assert dh._execute_query("INSERT") == 123
        assert dh._fetch_one("SELECT") == {"id": 1}
        assert dh._fetch_all("SELECT") == [{"id": 1}, {"id": 2}]

    @patch("app.services.data_handler.get_db_connection")
    def test_db_methods_exceptions(self, mock_db):
        mock_db.side_effect = Exception("DB Connection Error")
        dh = DataHandler()
        assert dh._execute_query("SELECT 1") is None
        assert dh._fetch_one("SELECT 1") is None
        assert dh._fetch_all("SELECT 1") == []
    """get_user_id 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_user_id(self, mock_fetch_one):
        mock_fetch_one.return_value = {"user_id": 42}
        dh = DataHandler()
        uid = dh.get_user_id(1)
        assert uid == 42

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_1_on_exception(self, mock_fetch_one):
        mock_fetch_one.return_value = None
        dh = DataHandler()
        uid = dh.get_user_id(1)
        assert uid == 1


class TestDataHandlerGetCurrentPositions:
    """get_current_positions / _get_current_positions 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._fetch_all")
    def test_returns_matched_positions(self, mock_fetch_all):
        pos = {"symbol": "BTC/USDT", "side": "long", "size": 0.1}
        mock_fetch_all.return_value = [pos]
        dh = DataHandler()
        result = dh.get_current_positions(1, "BTC/USDT")
        assert result == [pos]

    @patch("app.services.data_handler.DataHandler._fetch_all")
    def test_returns_empty_on_exception(self, mock_fetch_all):
        mock_fetch_all.return_value = []
        dh = DataHandler()
        result = dh._get_current_positions(1, "X")
        assert result == []


class TestDataHandlerGetAllPositions:
    """get_all_positions / _get_all_positions 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._fetch_all")
    def test_returns_positions(self, mock_fetch_all):
        positions = [{"symbol": "A", "side": "long"}, {"symbol": "B", "side": "short"}]
        mock_fetch_all.return_value = positions
        dh = DataHandler()
        result = dh.get_all_positions(1)
        assert result == positions


class TestDataHandlerPersistNotification:
    """persist_notification 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._execute_query")
    @patch("app.services.data_handler.DataHandler.get_user_id")
    def test_inserts_notification(self, mock_get_uid, mock_exec):
        mock_get_uid.return_value = 1
        dh = DataHandler()
        dh.persist_notification(1, "BTC/USDT", "open_long", "title", "msg")
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args[0]
        assert "INSERT" in call_args[0]
        assert "open_long" in call_args[1]


class TestDataHandlerRecordTrade:
    """record_trade 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._execute_query")
    @patch("app.services.data_handler.DataHandler.get_user_id")
    def test_inserts_trade(self, mock_get_uid, mock_exec):
        mock_get_uid.return_value = 1
        dh = DataHandler()
        dh.record_trade(1, "BTC/USDT", "buy", 100.0, 0.1, 10.0)
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args[0]
        assert "INSERT" in call_args[0]


class TestDataHandlerUpdatePosition:
    """update_position 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._execute_query")
    @patch("app.services.data_handler.DataHandler.get_user_id")
    def test_executes_upsert(self, mock_get_uid, mock_exec):
        mock_get_uid.return_value = 1
        dh = DataHandler()
        dh.update_position(1, "BTC/USDT", "long", 0.1, 100.0, 101.0, 102.0, 99.0)
        mock_exec.assert_called_once()


class TestDataHandlerClosePosition:
    """close_position 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._execute_query")
    def test_executes_delete(self, mock_exec):
        dh = DataHandler()
        dh.close_position(1, "BTC/USDT", "long")
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args[0]
        assert "DELETE" in call_args[0]
        assert "BTC/USDT" in str(call_args[1])
        assert "long" in str(call_args[1])


class TestDataHandlerUpdatePositionsCurrentPrice:
    """update_positions_current_price 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._execute_query")
    def test_executes_update(self, mock_exec):
        dh = DataHandler()
        dh.update_positions_current_price(1, "BTC/USDT", 105.0)
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args[0]
        assert "UPDATE" in call_args[0]


class TestDataHandlerUpdateLastRebalance:
    """update_last_rebalance 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._execute_query")
    def test_executes_update(self, mock_exec):
        dh = DataHandler()
        dh.update_last_rebalance(1)
        mock_exec.assert_called_once()
        assert "last_rebalance_at" in str(mock_exec.call_args)


class TestDataHandlerForceRebalance:
    """force_rebalance 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._execute_query")
    def test_executes_force_rebalance(self, mock_exec):
        dh = DataHandler()
        dh.force_rebalance(1)
        mock_exec.assert_called_once()
        assert "last_rebalance_at = '1970-01-01 00:00:00'" in str(mock_exec.call_args)


class TestDataHandlerFindRecentPendingOrder:
    """find_recent_pending_order 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_order_when_found(self, mock_fetch_one):
        mock_fetch_one.return_value = {"id": 10, "status": "pending"}
        dh = DataHandler()
        result = dh.find_recent_pending_order(1, "BTC/USDT", "open_long", signal_ts=12345)
        assert result == {"id": 10, "status": "pending"}

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_none_when_not_found(self, mock_fetch_one):
        mock_fetch_one.return_value = None
        dh = DataHandler()
        result = dh.find_recent_pending_order(1, "BTC/USDT", "open_long")
        assert result is None


class TestDataHandlerInsertPendingOrder:
    """insert_pending_order 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._execute_query")
    def test_returns_pending_id(self, mock_exec):
        mock_exec.return_value = 99
        dh = DataHandler()
        pid = dh.insert_pending_order(
            user_id=1, strategy_id=1, symbol="BTC/USDT", signal_type="open_long",
            signal_ts=0, market_type="swap", order_type="market", amount=0.1, price=100.0,
            execution_mode="signal", status="pending", priority=0, attempts=0, max_attempts=3,
            payload_json="{}",
        )
        assert pid == 99
        mock_exec.assert_called_once()


class TestDataHandlerGetLastRebalanceAt:
    """get_last_rebalance_at 直接覆盖"""

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_datetime(self, mock_fetch_one):
        dt = datetime(2025, 2, 26, 0, 0, 0)
        mock_fetch_one.return_value = {"last_rebalance_at": dt}
        dh = DataHandler()
        result = dh.get_last_rebalance_at(1)
        assert result == dt

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_none_when_no_record(self, mock_fetch_one):
        mock_fetch_one.return_value = None
        dh = DataHandler()
        result = dh.get_last_rebalance_at(1)
        assert result is None

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_datetime_from_string(self, mock_fetch_one):
        mock_fetch_one.return_value = {"last_rebalance_at": "2025-02-26T00:00:00Z"}
        dh = DataHandler()
        result = dh.get_last_rebalance_at(1)
        assert isinstance(result, datetime)
        assert result.year == 2025

    @patch("app.services.data_handler.DataHandler._fetch_one")
    def test_returns_none_when_invalid_type(self, mock_fetch_one):
        mock_fetch_one.return_value = {"last_rebalance_at": 123456789}
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

    def test_klines_to_dataframe_empty(self):
        dh = DataHandler()
        df = dh._klines_to_dataframe([])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_klines_to_dataframe_timestamp(self):
        dh = DataHandler()
        df = dh._klines_to_dataframe([{"timestamp": 1700000000, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0}])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1

    def test_klines_to_dataframe_missing_columns(self):
        dh = DataHandler()
        df = dh._klines_to_dataframe([{"time": 1700000000, "some_col": 1}])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    @patch("app.services.data_handler.MacroDataService.enrich_dataframe_realtime")
    @patch("app.services.data_handler.DataHandler._fetch_all")
    def test_get_input_context_single_macro_success(self, mock_fetch_all, mock_macro):
        mock_fetch_all.return_value = []
        mock_macro.side_effect = lambda df: df
        with patch.object(DataHandler, "_fetch_latest_kline", return_value=MOCK_KLINES):
            dh = DataHandler()
            request = {"symbol": "BTC", "need_macro": True}
            ctx = dh.get_input_context_single(1, request)
            assert ctx is not None
            mock_macro.assert_called_once()

    @patch("app.services.data_handler.MacroDataService.enrich_dataframe_realtime")
    @patch("app.services.data_handler.DataHandler._fetch_all")
    def test_get_input_context_single_macro_fail(self, mock_fetch_all, mock_macro):
        mock_fetch_all.return_value = []
        mock_macro.side_effect = Exception("Macro API down")
        with patch.object(DataHandler, "_fetch_latest_kline", return_value=MOCK_KLINES):
            dh = DataHandler()
            request = {"symbol": "BTC", "need_macro": True}
            ctx = dh.get_input_context_single(1, request)
            assert ctx is not None
            mock_macro.assert_called_once()


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

    @patch("app.services.data_handler.time")
    def test_appends_row_when_new_period(self, mock_time):
        period_start = 1700002800
        mock_time.time.return_value = float(period_start) + 3600 + 1.0  # Next period
        df = pd.DataFrame([
            {"time": period_start, "open": 99.5, "high": 101.0, "low": 99.0, "close": 101.0, "volume": 1000.0},
        ])
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time")
        dh = DataHandler()
        out = dh._update_dataframe_with_current_price(df.copy(), 102.0, "1H")
        assert len(out) == 2
        assert float(out.iloc[-1]["close"]) == 102.0

    def test_returns_df_unchanged_when_empty(self):
        dh = DataHandler()
        empty = pd.DataFrame()
        result = dh._update_dataframe_with_current_price(empty, 100.0, "1H")
        assert len(result) == 0

    @patch("app.services.data_handler.time")
    def test_update_dataframe_with_current_price_exception(self, mock_time):
        mock_time.time.side_effect = Exception("Time Error")
        dh = DataHandler()
        df = pd.DataFrame([{"time": 1700000000, "close": 100.0}])
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time")
        result = dh._update_dataframe_with_current_price(df, 102.0, "1H")
        assert len(result) == 1

    def test_update_dataframe_with_current_price_fallback_timeframe(self):
        dh = DataHandler()
        df = pd.DataFrame([{"time": 1700000000, "close": 100.0, "open": 100.0, "high": 100.0, "low": 100.0, "volume": 0.0}])
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time")
        result = dh._update_dataframe_with_current_price(df.copy(), 102.0, "UNKNOWN")
        assert len(result) >= 1
