"""UC-SA-E2E: Forex + IBKR paper Flask API and pending worker chain (plan 11-02)."""

from __future__ import annotations

import importlib
import sys
import types
import uuid
from contextlib import contextmanager
from functools import wraps
from unittest.mock import MagicMock, patch

import pytest

# Mock heavy deps before importing app modules (same as test_strategy_exchange_validation)
for mod in ("jwt", "psycopg2", "psycopg2.pool", "psycopg2.extras"):
    sys.modules.setdefault(mod, types.ModuleType(mod))


def _noop_decorator(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)

    return decorated


import app.utils.auth as _auth_mod

_auth_mod.login_required = _noop_decorator

import app.routes.strategy as strategy_mod

importlib.reload(strategy_mod)

from flask import Flask, g

from app.services.live_trading.base import ExecutionResult
from app.services.live_trading.ibkr_trading.client import IBKRClient
from app.services.live_trading.runners.base import PreCheckResult
from app.services.pending_order_worker import PendingOrderWorker

strategy_bp = strategy_mod.strategy_bp


@contextmanager
def _mock_db(insert_rowid: int = 1):
    mock_cur = MagicMock()
    mock_cur.lastrowid = insert_rowid
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_conn.__enter__ = lambda self: mock_conn
    mock_conn.__exit__ = lambda *args: None
    with patch("app.services.strategy.get_db_connection", return_value=mock_conn):
        yield mock_cur


@pytest.fixture
def client_fixture():
    """Minimal Flask app with strategy routes; g.user_id set for UC-SA-E2E API tests."""
    app = Flask(__name__)
    app.register_blueprint(strategy_bp, url_prefix="/api/strategy")

    @app.before_request
    def set_g():
        g.user_id = 1

    with app.test_client() as c:
        yield c


def test_uc_sa_e2e_api_forex_create_returns_200(client_fixture):
    """UC-SA-E2E: POST /api/strategy/strategies/create — Forex + ibkr-paper + EURUSD."""
    unique = uuid.uuid4().hex[:10]
    payload = {
        "strategy_name": f"UC-SA-E2E-API-forex-{unique}",
        "market_category": "Forex",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "indicator_config": {},
        "trading_config": {"symbol": "EURUSD", "market_type": "forex"},
        "notification_config": {},
    }
    with _mock_db(insert_rowid=501) as mock_cur:
        res = client_fixture.post("/api/strategy/strategies/create", json=payload)
    assert res.status_code == 200
    body = res.get_json()
    assert body["code"] == 1
    assert body["data"]["id"] == 501
    assert mock_cur.execute.called


@pytest.mark.parametrize(
    "signal_type,uc_tag,order_id",
    [
        ("open_long", "UC-SA-E2E-F1", 201),
        ("close_long", "UC-SA-E2E-F2", 202),
        ("open_short", "UC-SA-E2E-F3", 203),
        ("close_short", "UC-SA-E2E-F4", 204),
    ],
)
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.get_runner")
@patch("app.services.pending_order_worker.create_client")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_uc_sa_e2e_forex_worker_chain(
    mock_load_cfg,
    mock_create,
    mock_get_runner,
    mock_failed,
    mock_sent,
    _mock_notify,
    signal_type,
    uc_tag,
    order_id,
):
    """UC-SA-E2E-F1–F4: worker _execute_live_order reaches StatefulClientRunner.execute (mocked)."""
    mock_load_cfg.return_value = {
        "market_category": "Forex",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "forex",
    }
    mock_create.return_value = IBKRClient.__new__(IBKRClient)

    runner = MagicMock()
    runner.pre_check.return_value = PreCheckResult(ok=True)
    runner.execute.return_value = ExecutionResult(
        success=True,
        exchange_id="ibkr",
        exchange_order_id="e2e-test",
        note="live_order_submitted",
    )
    mock_get_runner.return_value = runner

    w = PendingOrderWorker()
    order_row = {
        "strategy_id": 1,
        "symbol": "EURUSD",
        "signal_type": signal_type,
        "amount": 10000.0,
    }
    payload = dict(order_row)
    w._execute_live_order(order_id=order_id, order_row=order_row, payload=payload)

    mock_failed.assert_not_called()
    mock_sent.assert_called_once()
    assert mock_sent.call_args[1].get("order_id") == order_id
    runner.execute.assert_called_once()
    assert uc_tag.startswith("UC-SA-E2E-F")


@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.get_runner")
@patch("app.services.pending_order_worker.create_client")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_uc_sa_e2e_regr_usstock_open_long(
    mock_load_cfg,
    mock_create,
    mock_get_runner,
    mock_failed,
    mock_sent,
    _mock_notify,
):
    """UC-SA-E2E-REGR: USStock + ibkr-paper + AAPL open_long — equity path still reaches runner.execute."""
    mock_load_cfg.return_value = {
        "market_category": "USStock",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "usstock",
    }
    mock_create.return_value = IBKRClient.__new__(IBKRClient)

    runner = MagicMock()
    runner.pre_check.return_value = PreCheckResult(ok=True)
    runner.execute.return_value = ExecutionResult(
        success=True,
        exchange_id="ibkr",
        exchange_order_id="e2e-regr",
        note="live_order_submitted",
    )
    mock_get_runner.return_value = runner

    w = PendingOrderWorker()
    order_row = {
        "strategy_id": 2,
        "symbol": "AAPL",
        "signal_type": "open_long",
        "amount": 10.0,
    }
    payload = dict(order_row)
    w._execute_live_order(order_id=310, order_row=order_row, payload=payload)

    mock_failed.assert_not_called()
    mock_sent.assert_called_once()
    mock_create.assert_called()
    runner.execute.assert_called_once()
