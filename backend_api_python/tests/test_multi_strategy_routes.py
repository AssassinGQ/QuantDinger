"""
Tests for P1d: multi_strategy API routes and regime history helpers.
"""

import json
import sys
import types
import pytest
from unittest.mock import patch, MagicMock
from functools import wraps

# Mock heavy deps before importing app modules
for mod in ("jwt", "psycopg2", "psycopg2.pool", "psycopg2.extras"):
    sys.modules.setdefault(mod, types.ModuleType(mod))


def _noop_decorator(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated


# Patch login_required before importing the route module
import app.utils.auth as _auth_mod
_auth_mod.login_required = _noop_decorator

import importlib
import app.routes.multi_strategy as ms_mod
importlib.reload(ms_mod)


@pytest.fixture
def client_reloaded():
    from flask import Flask

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(ms_mod.multi_strategy_bp, url_prefix="/api/multi-strategy")
    with app.test_client() as c:
        yield c


# ── Tests ─────────────────────────────────────────────────────────────────

class TestSummaryEndpoint:
    @patch("app.routes.multi_strategy._get_config",
           return_value={"multi_strategy": {"enabled": False}})
    def test_disabled_returns_not_enabled(self, mock_cfg, client_reloaded):
        resp = client_reloaded.get("/api/multi-strategy/summary")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["msg"] == "multi-strategy not enabled"

    @patch("app.routes.multi_strategy._get_breaker")
    @patch("app.routes.multi_strategy._get_allocator")
    @patch("app.tasks.regime_switch._fetch_macro_snapshot",
           return_value={"vix": 20.0, "dxy": 100.0, "fear_greed": 50.0})
    @patch("app.routes.multi_strategy._get_config",
           return_value={"multi_strategy": {"enabled": True}})
    def test_enabled_returns_summary(self, mock_cfg, mock_macro, mock_alloc, mock_breaker, client_reloaded):
        allocator = MagicMock()
        allocator.current_regime = "normal"
        allocator.target_weights = {"conservative": 0.2, "balanced": 0.6, "aggressive": 0.2}
        allocator.effective_weights = {"conservative": 0.2, "balanced": 0.6, "aggressive": 0.2}
        allocator.regime_per_symbol = {}
        allocator.effective_weights_per_symbol = {}
        allocator.get_portfolio_summary.return_value = {
            "allocation": {}, "positions": {},
            "total_equity": 100000, "total_unrealized_pnl": 500,
        }
        mock_alloc.return_value = allocator

        breaker = MagicMock()
        breaker.get_status.return_value = {"triggered": False, "current_drawdown_pct": 2.0}
        mock_breaker.return_value = breaker

        resp = client_reloaded.get("/api/multi-strategy/summary")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["regime"] == "normal"
        assert "weights" in data
        assert "circuit_breaker" in data


class TestWeightsEndpoint:
    @patch("app.routes.multi_strategy._get_allocator")
    def test_get_weights(self, mock_alloc, client_reloaded):
        allocator = MagicMock()
        allocator.target_weights = {"a": 0.5, "b": 0.5}
        allocator.effective_weights = {"a": 0.5, "b": 0.5}
        allocator.current_regime = "normal"
        mock_alloc.return_value = allocator

        resp = client_reloaded.get("/api/multi-strategy/weights")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "target" in data
        assert "effective" in data

    @patch("app.routes.multi_strategy._get_allocator")
    def test_put_weights(self, mock_alloc, client_reloaded):
        allocator = MagicMock()
        allocator._effective_weights = {}
        allocator._target_weights = {}
        mock_alloc.return_value = allocator

        resp = client_reloaded.put(
            "/api/multi-strategy/weights",
            data=json.dumps({"weights": {"a": 0.7, "b": 0.3}}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert abs(data["a"] - 0.7) < 1e-6

    @patch("app.routes.multi_strategy._get_allocator")
    def test_put_weights_bad_input(self, mock_alloc, client_reloaded):
        resp = client_reloaded.put(
            "/api/multi-strategy/weights",
            data=json.dumps({"weights": "invalid"}),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestRegimeEndpoint:
    @patch("app.tasks.regime_switch._fetch_macro_snapshot",
           return_value={"vix": 35.0, "dxy": 105.0, "fear_greed": 15.0})
    @patch("app.routes.multi_strategy._get_allocator")
    def test_get_regime(self, mock_alloc, mock_macro, client_reloaded):
        allocator = MagicMock()
        allocator.current_regime = "panic"
        mock_alloc.return_value = allocator

        resp = client_reloaded.get("/api/multi-strategy/regime")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["regime"] == "panic"
        assert data["vix"] == 35.0


class TestAllocationEndpoint:
    @patch("app.routes.multi_strategy._get_allocator")
    def test_get_allocation(self, mock_alloc, client_reloaded):
        allocator = MagicMock()
        allocator.strategy_allocation = {101: 5000, 102: 15000}
        allocator.frozen_strategies = {102: True}
        mock_alloc.return_value = allocator

        resp = client_reloaded.get("/api/multi-strategy/allocation")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "allocation" in data
        assert "frozen" in data


class TestPositionsEndpoint:
    @patch("app.routes.multi_strategy._get_allocator")
    def test_get_positions(self, mock_alloc, client_reloaded):
        allocator = MagicMock()
        allocator.get_combined_positions.return_value = {
            "XAUUSD": {"total_long_value": 10000, "total_short_value": 0, "net_exposure": 10000},
        }
        mock_alloc.return_value = allocator

        resp = client_reloaded.get("/api/multi-strategy/positions")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "XAUUSD" in data

    @patch("app.routes.multi_strategy._get_allocator")
    def test_get_positions_filtered(self, mock_alloc, client_reloaded):
        allocator = MagicMock()
        allocator.get_combined_positions.return_value = {
            "XAUUSD": {"total_long_value": 10000},
            "NVDA": {"total_long_value": 5000},
        }
        mock_alloc.return_value = allocator

        resp = client_reloaded.get("/api/multi-strategy/positions?symbol=XAUUSD")
        data = resp.get_json()["data"]
        assert "XAUUSD" in data
        assert "NVDA" not in data


class TestCircuitBreakerEndpoint:
    @patch("app.routes.multi_strategy._get_config",
           return_value={"multi_strategy": {"circuit_breaker": {"enabled": True}}})
    @patch("app.routes.multi_strategy._get_breaker")
    def test_get_status(self, mock_breaker, mock_cfg, client_reloaded):
        breaker = MagicMock()
        breaker.get_status.return_value = {"triggered": False, "current_drawdown_pct": 3.0}
        mock_breaker.return_value = breaker

        resp = client_reloaded.get("/api/multi-strategy/circuit-breaker")
        assert resp.status_code == 200

    @patch("app.routes.multi_strategy._get_breaker")
    def test_reset(self, mock_breaker, client_reloaded):
        breaker = MagicMock()
        mock_breaker.return_value = breaker

        resp = client_reloaded.post("/api/multi-strategy/circuit-breaker/reset")
        assert resp.status_code == 200
        breaker.reset.assert_called_once()


class TestConfigEndpoint:
    @patch("app.routes.multi_strategy._get_config")
    def test_get_config(self, mock_cfg, client_reloaded):
        mock_cfg.return_value = {
            "multi_strategy": {"enabled": True, "regime_to_weights": {}},
            "regime_rules": {"vix_panic": 30},
            "user_id": 1,
        }
        resp = client_reloaded.get("/api/multi-strategy/config")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "multi_strategy" in data
        assert "user_id" not in data  # sanitized


class TestHistoryEndpoint:
    @patch("app.routes.multi_strategy._fetch_regime_history", return_value=[])
    def test_get_history_empty(self, mock_fetch, client_reloaded):
        resp = client_reloaded.get("/api/multi-strategy/history")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["events"] == []

    @patch("app.routes.multi_strategy._fetch_regime_history")
    def test_get_history_with_limit(self, mock_fetch, client_reloaded):
        mock_fetch.return_value = [{"id": 1, "to_regime": "panic"}]
        resp = client_reloaded.get("/api/multi-strategy/history?limit=10&offset=0")
        assert resp.status_code == 200
        mock_fetch.assert_called_once_with(10, 0)


# ── Regime history helper unit tests ──────────────────────────────────────

class TestRecordRegimeEvent:
    @patch("app.routes.multi_strategy.get_db_connection", create=True)
    def test_record_event_calls_db(self, mock_db):
        """Verify _record_regime_event builds correct SQL."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        with patch("app.utils.db.get_db_connection", return_value=mock_conn):
            from app.routes.multi_strategy import _record_regime_event
            _record_regime_event({
                "from_regime": "normal",
                "to_regime": "panic",
                "vix": 35.0,
                "dxy": 105.0,
                "fear_greed": 15.0,
                "weights_before": {"conservative": 0.2},
                "weights_after": {"conservative": 0.8},
                "strategies_started": [101],
                "strategies_stopped": [102],
            })
            mock_cursor.execute.assert_called_once()
