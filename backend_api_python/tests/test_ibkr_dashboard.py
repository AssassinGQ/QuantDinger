"""
Tests for IBKR broker dashboard API endpoint and helper functions.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.routes.ibkr import (
    _safe_float,
    _safe_int,
    _format_dt,
    _compute_ibkr_trade_stats,
)


def _auth_headers():
    """Return a valid Authorization header by mocking verify_token."""
    return {"Authorization": "Bearer test-token"}


# ===========================================================================
# _safe_float / _safe_int / _format_dt unit tests
# ===========================================================================

class TestSafeFloat:
    def test_normal_float(self):
        assert _safe_float(3.14) == 3.14

    def test_string_number(self):
        assert _safe_float("123.45") == 123.45

    def test_none_returns_default(self):
        assert _safe_float(None) == 0.0

    def test_invalid_returns_default(self):
        assert _safe_float("abc", 99.0) == 99.0

    def test_int_input(self):
        assert _safe_float(42) == 42.0


class TestSafeInt:
    def test_normal_int(self):
        assert _safe_int(7) == 7

    def test_string_number(self):
        assert _safe_int("42") == 42

    def test_none_returns_default(self):
        assert _safe_int(None) == 0

    def test_invalid_returns_default(self):
        assert _safe_int("xyz", 5) == 5

    def test_float_input(self):
        assert _safe_int(3.9) == 3


class TestFormatDt:
    def test_none(self):
        assert _format_dt(None) is None

    def test_datetime_object(self):
        dt = datetime(2025, 6, 15, 10, 30, 0)
        assert _format_dt(dt) == dt.isoformat()

    def test_string_passthrough(self):
        assert _format_dt("2025-01-01T00:00:00") == "2025-01-01T00:00:00"

    def test_int_passthrough(self):
        assert _format_dt(1700000000) == 1700000000


# ===========================================================================
# _compute_ibkr_trade_stats unit tests
# ===========================================================================

class TestComputeTradeStats:

    def test_empty_trades(self):
        stats = _compute_ibkr_trade_stats([])
        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0.0
        assert stats["profit_factor"] == 0.0
        assert stats["total_realized_pnl"] == 0.0

    def test_all_winners(self):
        trades = [
            {"profit": 100.0},
            {"profit": 200.0},
            {"profit": 50.0},
        ]
        stats = _compute_ibkr_trade_stats(trades)
        assert stats["total_trades"] == 3
        assert stats["winning_trades"] == 3
        assert stats["losing_trades"] == 0
        assert stats["win_rate"] == 100.0
        assert stats["total_profit"] == 350.0
        assert stats["total_loss"] == 0.0
        assert stats["profit_factor"] == 350.0  # no losses → returns total_profit
        assert stats["avg_win"] == round(350 / 3, 2)

    def test_all_losers(self):
        trades = [
            {"profit": -50.0},
            {"profit": -30.0},
        ]
        stats = _compute_ibkr_trade_stats(trades)
        assert stats["total_trades"] == 2
        assert stats["winning_trades"] == 0
        assert stats["losing_trades"] == 2
        assert stats["win_rate"] == 0.0
        assert stats["total_profit"] == 0.0
        assert stats["total_loss"] == 80.0
        assert stats["profit_factor"] == 0.0  # no wins → 0
        assert stats["avg_loss"] == 40.0

    def test_mixed_trades(self):
        trades = [
            {"profit": 100.0},
            {"profit": -50.0},
            {"profit": 200.0},
            {"profit": -25.0},
            {"profit": 0.0},  # breakeven
        ]
        stats = _compute_ibkr_trade_stats(trades)
        assert stats["total_trades"] == 5
        assert stats["winning_trades"] == 2
        assert stats["losing_trades"] == 2
        assert stats["win_rate"] == 50.0  # 2 wins / 4 closed (excl. breakeven) = 50%
        assert stats["total_profit"] == 300.0
        assert stats["total_loss"] == 75.0
        assert stats["profit_factor"] == 4.0  # 300/75
        assert stats["avg_win"] == 150.0  # 300/2
        assert stats["avg_loss"] == 37.5   # 75/2
        assert stats["total_realized_pnl"] == 225.0  # 100-50+200-25+0

    def test_string_profit_values(self):
        trades = [
            {"profit": "100.0"},
            {"profit": "-30"},
        ]
        stats = _compute_ibkr_trade_stats(trades)
        assert stats["total_trades"] == 2
        assert stats["winning_trades"] == 1
        assert stats["losing_trades"] == 1

    def test_missing_profit_key(self):
        trades = [
            {"symbol": "AAPL"},
            {"profit": 50.0},
        ]
        stats = _compute_ibkr_trade_stats(trades)
        assert stats["total_trades"] == 2
        assert stats["winning_trades"] == 1

    def test_single_trade(self):
        stats = _compute_ibkr_trade_stats([{"profit": 42.0}])
        assert stats["total_trades"] == 1
        assert stats["winning_trades"] == 1
        assert stats["win_rate"] == 100.0
        assert stats["profit_factor"] == 42.0
        assert stats["avg_win"] == 42.0


# ===========================================================================
# IBKR dashboard endpoint tests (Flask app context)
# ===========================================================================

def _make_flask_app():
    """Create a minimal Flask app with ibkr_bp registered."""
    from flask import Flask, g
    from app.routes.ibkr import ibkr_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(ibkr_bp, url_prefix="/api/ibkr")

    @app.before_request
    def _set_test_user():
        g.user_id = 1

    return app


_MOCK_TOKEN_PAYLOAD = {
    "sub": "testuser", "user_id": 1, "role": "admin", "token_version": 1
}


class TestIbkrDashboardEndpoint:

    @patch("app.utils.auth.verify_token", return_value=_MOCK_TOKEN_PAYLOAD)
    @patch("app.routes.ibkr.get_ibkr_client")
    @patch("app.routes.ibkr.get_db_connection")
    def test_disconnected_returns_data(self, mock_db, mock_client, _vt):
        """When IBKR is disconnected, endpoint still returns DB data."""
        client = MagicMock()
        client.connected = False
        client.get_connection_status.return_value = {
            "connected": False, "engine_id": "ibkr"
        }
        mock_client.return_value = client

        from tests.conftest import make_db_ctx
        mock_db.return_value = make_db_ctx(fetchall_result=[])

        app = _make_flask_app()
        with app.test_client() as tc:
            resp = tc.get("/api/ibkr/dashboard", headers=_auth_headers())
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["code"] == 1
            data = body["data"]
            assert data["connected"] is False
            assert data["positions"] == []
            assert data["open_orders"] == []
            assert isinstance(data["performance"], dict)
            assert isinstance(data["executions"], list)

    @patch("app.utils.auth.verify_token", return_value=_MOCK_TOKEN_PAYLOAD)
    @patch("app.routes.ibkr.get_ibkr_client")
    @patch("app.routes.ibkr.get_db_connection")
    def test_connected_returns_account_data(self, mock_db, mock_client, _vt):
        """When IBKR is connected, endpoint returns account + positions."""
        client = MagicMock()
        client.connected = True
        client.get_connection_status.return_value = {
            "connected": True, "engine_id": "ibkr", "account": "DU123"
        }
        client.get_account_summary.return_value = {
            "success": True,
            "account": "DU123",
            "summary": {
                "NetLiquidation": {"value": "150000.50", "currency": "USD"},
                "AvailableFunds": {"value": "80000.00", "currency": "USD"},
                "BuyingPower": {"value": "320000.00", "currency": "USD"},
            },
        }
        client.get_pnl.return_value = {
            "success": True,
            "dailyPnL": -350.0,
            "unrealizedPnL": 1200.0,
            "realizedPnL": 850.0,
        }
        client.get_positions.return_value = [
            {"symbol": "AAPL", "quantity": 100, "avgCost": 150.0}
        ]
        client.get_open_orders.return_value = [
            {"orderId": 1, "symbol": "MSFT", "action": "BUY", "quantity": 50}
        ]
        mock_client.return_value = client

        from tests.conftest import make_db_ctx
        mock_db.return_value = make_db_ctx(fetchall_result=[])

        app = _make_flask_app()
        with app.test_client() as tc:
            resp = tc.get("/api/ibkr/dashboard", headers=_auth_headers())
            assert resp.status_code == 200
            body = resp.get_json()
            data = body["data"]
            assert data["connected"] is True
            assert data["account"]["account_id"] == "DU123"
            assert data["account"]["net_liquidation"] == 150000.50
            assert data["account"]["currency"] == "USD"
            items = data["account"]["items"]
            assert items["UnrealizedPnL"]["value"] == 1200.0
            assert items["RealizedPnL"]["value"] == 850.0
            assert items["DailyPnL"]["value"] == -350.0
            assert len(data["positions"]) == 1
            assert data["positions"][0]["symbol"] == "AAPL"
            assert len(data["open_orders"]) == 1

    @patch("app.utils.auth.verify_token", return_value=_MOCK_TOKEN_PAYLOAD)
    @patch("app.routes.ibkr.get_ibkr_client")
    @patch("app.routes.ibkr.get_db_connection")
    def test_ibkr_exception_still_returns_db_data(self, mock_db, mock_client, _vt):
        """If IBKR client throws, the endpoint should still return DB data."""
        mock_client.side_effect = Exception("IB Gateway unreachable")

        from tests.conftest import make_db_ctx
        mock_db.return_value = make_db_ctx(fetchall_result=[])

        app = _make_flask_app()
        with app.test_client() as tc:
            resp = tc.get("/api/ibkr/dashboard", headers=_auth_headers())
            assert resp.status_code == 200
            body = resp.get_json()
            data = body["data"]
            assert data["connected"] is False
            assert isinstance(data["performance"], dict)

    @patch("app.utils.auth.verify_token", return_value=_MOCK_TOKEN_PAYLOAD)
    @patch("app.routes.ibkr.get_ibkr_client")
    @patch("app.routes.ibkr.get_db_connection")
    def test_execution_status_normalization(self, mock_db, mock_client, _vt):
        """Status 'sent' → 'completed', 'deferred' → 'pending'."""
        client = MagicMock()
        client.connected = False
        client.get_connection_status.return_value = {"connected": False}
        mock_client.return_value = client

        from tests.conftest import make_db_ctx

        trades_ctx = make_db_ctx(fetchall_result=[])
        exec_ctx = make_db_ctx(fetchall_result=[
            {
                "id": 1, "strategy_id": 10, "strategy_name": "S1",
                "status": "sent", "filled": 5.0, "avg_price": 100.0,
                "price": 99.0, "last_error": None, "symbol": "AAPL",
                "signal_type": "open_long", "amount": 5,
                "created_at": None, "updated_at": None,
                "executed_at": None, "processed_at": None, "sent_at": None,
            },
            {
                "id": 2, "strategy_id": 10, "strategy_name": "S1",
                "status": "deferred", "filled": 0, "avg_price": 0,
                "price": 50.0, "last_error": "timeout", "symbol": "MSFT",
                "signal_type": "close_long", "amount": 3,
                "created_at": None, "updated_at": None,
                "executed_at": None, "processed_at": None, "sent_at": None,
            },
        ])

        call_count = {"n": 0}
        def side_effect_db():
            call_count["n"] += 1
            if call_count["n"] <= 1:
                return trades_ctx
            return exec_ctx

        mock_db.side_effect = side_effect_db

        app = _make_flask_app()
        with app.test_client() as tc:
            resp = tc.get("/api/ibkr/dashboard", headers=_auth_headers())
            assert resp.status_code == 200
            data = resp.get_json()["data"]
            execs = data["executions"]
            assert len(execs) == 2
            assert execs[0]["status"] == "completed"
            assert execs[0]["filled_amount"] == 5.0
            assert execs[0]["filled_price"] == 100.0
            assert execs[1]["status"] == "pending"
            assert execs[1]["error_message"] == "timeout"
            assert execs[1]["filled_price"] == 50.0

    @patch("app.utils.auth.verify_token", return_value=_MOCK_TOKEN_PAYLOAD)
    @patch("app.routes.ibkr.get_ibkr_client")
    @patch("app.routes.ibkr.get_db_connection")
    def test_trade_datetime_conversion(self, mock_db, mock_client, _vt):
        """datetime objects in created_at are converted to unix timestamps."""
        client = MagicMock()
        client.connected = False
        client.get_connection_status.return_value = {"connected": False}
        mock_client.return_value = client

        dt = datetime(2026, 3, 1, 12, 0, 0)
        from tests.conftest import make_db_ctx
        mock_db.return_value = make_db_ctx(fetchall_result=[
            {
                "id": 1, "strategy_id": 10, "strategy_name": "TestStrat",
                "symbol": "AAPL", "type": "open_long", "price": 150.0,
                "profit": 25.0, "created_at": dt,
            },
        ])

        app = _make_flask_app()
        with app.test_client() as tc:
            resp = tc.get("/api/ibkr/dashboard", headers=_auth_headers())
            data = resp.get_json()["data"]
            assert len(data["recent_trades"]) == 1
            ts = data["recent_trades"][0]["created_at"]
            assert isinstance(ts, int)
            assert ts == int(dt.timestamp())

    @patch("app.utils.auth.verify_token", return_value=_MOCK_TOKEN_PAYLOAD)
    @patch("app.routes.ibkr.get_ibkr_client")
    @patch("app.routes.ibkr.get_db_connection")
    def test_performance_stats_from_db(self, mock_db, mock_client, _vt):
        """Performance stats are computed from DB trade data."""
        client = MagicMock()
        client.connected = False
        client.get_connection_status.return_value = {"connected": False}
        mock_client.return_value = client

        from tests.conftest import make_db_ctx
        mock_db.return_value = make_db_ctx(fetchall_result=[
            {"id": 1, "profit": 100.0, "created_at": 1700000000},
            {"id": 2, "profit": -40.0, "created_at": 1700000100},
            {"id": 3, "profit": 60.0, "created_at": 1700000200},
        ])

        app = _make_flask_app()
        with app.test_client() as tc:
            resp = tc.get("/api/ibkr/dashboard", headers=_auth_headers())
            perf = resp.get_json()["data"]["performance"]
            assert perf["total_trades"] == 3
            assert perf["winning_trades"] == 2
            assert perf["losing_trades"] == 1
            assert perf["win_rate"] == round(2 / 3 * 100, 2)
            assert perf["total_profit"] == 160.0
            assert perf["total_loss"] == 40.0
            assert perf["profit_factor"] == 4.0

    @patch("app.utils.auth.verify_token", return_value=_MOCK_TOKEN_PAYLOAD)
    @patch("app.routes.ibkr.get_ibkr_client")
    @patch("app.routes.ibkr.get_db_connection")
    def test_position_commission_uses_dict_rows(self, mock_db, mock_client, _vt):
        """Commission aggregation query uses dict-style row access (not tuple index)."""
        client = MagicMock()
        client.connected = True
        client.get_connection_status.return_value = {"connected": True, "engine_id": "ibkr", "account": "DU123"}
        client.get_account_summary.return_value = {
            "success": True, "account": "DU123",
            "summary": {"NetLiquidation": {"value": "100000", "currency": "USD"}},
        }
        client.get_pnl.return_value = {"success": True, "dailyPnL": 0, "unrealizedPnL": 0, "realizedPnL": 0}
        client.get_positions.return_value = [
            {"symbol": "AAPL", "ib_symbol": "AAPL", "quantity": 10, "avgCost": 150.0},
        ]
        client.get_open_orders.return_value = []
        mock_client.return_value = client

        from tests.conftest import make_db_ctx

        call_count = {"n": 0}
        commission_rows = [{"symbol": "AAPL", "commission": 12.5}]

        def _side_effect_db():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return make_db_ctx(fetchall_result=commission_rows)
            return make_db_ctx(fetchall_result=[])

        mock_db.side_effect = _side_effect_db

        app = _make_flask_app()
        with app.test_client() as tc:
            resp = tc.get("/api/ibkr/dashboard", headers=_auth_headers())
            assert resp.status_code == 200
            data = resp.get_json()["data"]
            assert data["positions"][0]["commission"] == 12.5
