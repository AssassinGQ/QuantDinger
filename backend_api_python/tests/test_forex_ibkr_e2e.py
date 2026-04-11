"""UC-SA-E2E: Full-chain Forex + IBKR Flask API → Worker → Client → IBKR Callback tests.

Chain: Flask API create → PendingOrderWorker._execute_live_order → StatefulClientRunner
→ IBKRClient.place_market_order → mock placeOrder → simulated IBKR callbacks
  (orderStatus → execDetails → position → pnlSingle).

Only ib_insync, DB and notification are mocked; runner and client are REAL.
"""

from __future__ import annotations

import importlib
import sys
import types
import uuid
from contextlib import contextmanager
from functools import wraps
from unittest.mock import MagicMock, patch

import pytest

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

from app.services.live_trading.ibkr_trading.client import IBKRClient
from app.services.pending_order_worker import PendingOrderWorker

from tests.test_ibkr_client import (
    _make_client_with_mock_ib,
    _make_mock_ib_insync,
    _make_trade_mock,
)
from tests.test_ibkr_forex_paper_smoke import (
    _FakeEvent,
    _fire_callbacks_after_fill,
    _make_qualify_for_pair,
    _wire_ib_events,
)

strategy_bp = strategy_mod.strategy_bp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _make_qualify_for_stock(symbol: str, con_id: int):
    """qualifyContractsAsync for equity: sets secType=STK."""

    async def _mock_qualify(*contracts):
        for c in contracts:
            c.conId = con_id
            c.localSymbol = symbol
            c.secType = "STK"
        return list(contracts)

    return _mock_qualify


def _make_ibkr_client_for_e2e(
    symbol: str, con_id: int, local_symbol: str, *, sec_type: str = "CASH"
):
    """Real IBKRClient with mock ib_insync; wired events + qualify stub."""
    client = _make_client_with_mock_ib()
    _wire_ib_events(client._ib)
    if sec_type == "STK":
        client._ib.qualifyContractsAsync = _make_qualify_for_stock(symbol, con_id)
    else:
        client._ib.qualifyContractsAsync = _make_qualify_for_pair(symbol, con_id, local_symbol)
    client._events_registered = False
    client._register_events()

    place_calls: list[MagicMock] = []

    def _place_side_effect(contract, order):
        oid = 60000 + len(place_calls)
        t = _make_trade_mock(status="Submitted", filled=0, avg_price=0, order_id=oid)
        t.contract = contract
        t.order.action = order.action
        t.order.totalQuantity = order.totalQuantity
        place_calls.append(t)
        return t

    client._ib.placeOrder.side_effect = _place_side_effect
    return client, place_calls


@pytest.fixture
def patched_records():
    """Mock DB persistence for position/pnl so callbacks don't hit real DB."""
    with patch(
        "app.services.live_trading.records.ibkr_save_position",
        return_value=True,
    ), patch(
        "app.services.live_trading.records.ibkr_save_pnl",
        return_value=True,
    ):
        yield


# ---------------------------------------------------------------------------
# 1. Flask API — strategy creation (unchanged)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 2. Full-chain: Worker → real StatefulClientRunner → real IBKRClient → callbacks
# ---------------------------------------------------------------------------

_FOREX_SIGNAL_CASES = [
    ("open_long", "UC-SA-E2E-F1", "EURUSD", 12087792, "EUR.USD"),
    ("close_long", "UC-SA-E2E-F2", "EURUSD", 12087792, "EUR.USD"),
    ("open_short", "UC-SA-E2E-F3", "GBPJPY", 12345678, "GBP.JPY"),
    ("close_short", "UC-SA-E2E-F4", "GBPJPY", 12345678, "GBP.JPY"),
]


@pytest.mark.parametrize(
    "signal_type,uc_tag,symbol,con_id,local_sym",
    _FOREX_SIGNAL_CASES,
)
@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_uc_sa_e2e_forex_full_chain(
    mock_load_cfg,
    mock_failed,
    mock_sent,
    _mock_notify,
    patched_records,
    signal_type,
    uc_tag,
    symbol,
    con_id,
    local_sym,
):
    """UC-SA-E2E-F1–F4: Worker → real runner → real IBKRClient.place_market_order → IBKR callbacks."""
    mock_load_cfg.return_value = {
        "market_category": "Forex",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "forex",
    }

    ibkr_client, place_calls = _make_ibkr_client_for_e2e(symbol, con_id, local_sym)

    with patch(
        "app.services.pending_order_worker.create_client",
        return_value=ibkr_client,
    ):
        w = PendingOrderWorker()
        order_id = 201 + _FOREX_SIGNAL_CASES.index(
            (signal_type, uc_tag, symbol, con_id, local_sym)
        )
        order_row = {
            "strategy_id": 1,
            "symbol": symbol,
            "signal_type": signal_type,
            "amount": 10000.0,
        }
        w._execute_live_order(
            order_id=order_id,
            order_row=order_row,
            payload=dict(order_row),
        )

    mock_failed.assert_not_called()
    mock_sent.assert_called_once()
    assert mock_sent.call_args[1].get("order_id") == order_id

    assert len(place_calls) == 1, "placeOrder should be called exactly once"
    trade = place_calls[0]

    is_open = signal_type.startswith("open_")
    position_after = 10000.0 if is_open else 0.0
    _fire_callbacks_after_fill(
        ibkr_client, trade, 10000.0, position_after=position_after, fill_tag=uc_tag
    )

    assert uc_tag.startswith("UC-SA-E2E-F")


# ---------------------------------------------------------------------------
# 3. XAGUSD full-chain open + close cycle via Worker
# ---------------------------------------------------------------------------


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_uc_sa_e2e_xagusd_open_close_full_chain(
    mock_load_cfg,
    mock_failed,
    mock_sent,
    _mock_notify,
    patched_records,
):
    """UC-SA-E2E-XAGUSD: Worker → real runner → real IBKRClient open_long then close_long with full IBKR callbacks."""
    mock_load_cfg.return_value = {
        "market_category": "Forex",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "forex",
    }

    ibkr_client, place_calls = _make_ibkr_client_for_e2e("XAGUSD", 87654321, "XAGUSD")

    with patch(
        "app.services.pending_order_worker.create_client",
        return_value=ibkr_client,
    ):
        w = PendingOrderWorker()

        # ---- open_long ----
        w._execute_live_order(
            order_id=401,
            order_row={
                "strategy_id": 10,
                "symbol": "XAGUSD",
                "signal_type": "open_long",
                "amount": 5000.0,
            },
            payload={
                "strategy_id": 10,
                "symbol": "XAGUSD",
                "signal_type": "open_long",
                "amount": 5000.0,
            },
        )

    assert mock_failed.call_count == 0
    assert mock_sent.call_count == 1
    assert mock_sent.call_args[1]["order_id"] == 401
    assert len(place_calls) == 1

    t_open = place_calls[0]
    assert t_open.order.action == "BUY"
    _fire_callbacks_after_fill(
        ibkr_client, t_open, 5000.0, position_after=5000.0, fill_tag="xag_open"
    )

    mock_sent.reset_mock()
    mock_failed.reset_mock()

    # ---- close_long ----
    with patch(
        "app.services.pending_order_worker.create_client",
        return_value=ibkr_client,
    ):
        w2 = PendingOrderWorker()
        w2._execute_live_order(
            order_id=402,
            order_row={
                "strategy_id": 10,
                "symbol": "XAGUSD",
                "signal_type": "close_long",
                "amount": 5000.0,
            },
            payload={
                "strategy_id": 10,
                "symbol": "XAGUSD",
                "signal_type": "close_long",
                "amount": 5000.0,
            },
        )

    assert mock_failed.call_count == 0
    assert mock_sent.call_count == 1
    assert mock_sent.call_args[1]["order_id"] == 402
    assert len(place_calls) == 2

    t_close = place_calls[1]
    assert t_close.order.action == "SELL"
    _fire_callbacks_after_fill(
        ibkr_client, t_close, 5000.0, position_after=0.0, fill_tag="xag_close"
    )

    assert ibkr_client._ib.placeOrder.call_count == 2


# ---------------------------------------------------------------------------
# 4. USStock regression — still full-chain (real runner + real client)
# ---------------------------------------------------------------------------


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_uc_sa_e2e_regr_usstock_full_chain(
    mock_load_cfg,
    mock_failed,
    mock_sent,
    _mock_notify,
    patched_records,
):
    """UC-SA-E2E-REGR: USStock + ibkr-paper + AAPL open_long — full chain including placeOrder + callbacks."""
    mock_load_cfg.return_value = {
        "market_category": "USStock",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "usstock",
    }

    ibkr_client, place_calls = _make_ibkr_client_for_e2e("AAPL", 265598, "AAPL", sec_type="STK")

    with patch(
        "app.services.pending_order_worker.create_client",
        return_value=ibkr_client,
    ):
        w = PendingOrderWorker()
        w._execute_live_order(
            order_id=310,
            order_row={
                "strategy_id": 2,
                "symbol": "AAPL",
                "signal_type": "open_long",
                "amount": 10.0,
            },
            payload={
                "strategy_id": 2,
                "symbol": "AAPL",
                "signal_type": "open_long",
                "amount": 10.0,
            },
        )

    mock_failed.assert_not_called()
    mock_sent.assert_called_once()
    assert len(place_calls) == 1

    t = place_calls[0]
    assert t.order.action == "BUY"
    _fire_callbacks_after_fill(
        ibkr_client, t, 10.0, position_after=10.0, fill_tag="aapl_open"
    )
