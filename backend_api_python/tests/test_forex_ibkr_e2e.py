"""UC-SA-E2E: Full-chain Forex + IBKR Flask API → Worker → Client → IBKR Callback tests.

Chain: Flask API create → PendingOrderWorker._execute_live_order → StatefulClientRunner
→ IBKRClient.place_market_order → mock placeOrder → simulated IBKR callbacks
  (orderStatus → execDetails → position → pnlSingle).

Only ib_insync, DB and notification are mocked; runner and client are REAL.
"""

from __future__ import annotations

import sys
import types
import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

for mod in ("jwt", "psycopg2", "psycopg2.pool", "psycopg2.extras"):
    sys.modules.setdefault(mod, types.ModuleType(mod))

from app.services.live_trading.ibkr_trading.client import IBKRClient
from app.services.pending_order_worker import PendingOrderWorker

from tests.helpers.ibkr_mocks import (
    _fire_callbacks_after_fill,
    _make_ibkr_client_for_e2e,
    _make_mock_ib_insync,
    _make_trade_mock,
)


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


# ---------------------------------------------------------------------------
# 1. Flask API — strategy creation (unchanged)
# ---------------------------------------------------------------------------


def test_uc_sa_e2e_api_forex_create_returns_200(strategy_client):
    """UC-SA-E2E: POST /api/strategies/create — Forex + ibkr-paper + EURUSD."""
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
        res = strategy_client.post("/api/strategies/create", json=payload)
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
    """UC-SA-E2E-XAGUSD / UC-16-T7-01: Metals + CMDTY; Worker → runner → placeOrder XAGUSD SMART."""
    mock_load_cfg.return_value = {
        "market_category": "Metals",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "metals",
    }

    ibkr_client, place_calls = _make_ibkr_client_for_e2e(
        "XAGUSD", 77124483, "XAGUSD", sec_type="CMDTY"
    )

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
    assert t_open.contract.secType == "CMDTY"
    assert getattr(t_open.contract, "symbol", None) == "XAGUSD"
    assert getattr(t_open.contract, "exchange", None) == "SMART"
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
    assert t_close.contract.secType == "CMDTY"
    assert getattr(t_close.contract, "symbol", None) == "XAGUSD"
    assert getattr(t_close.contract, "exchange", None) == "SMART"
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


# ---------------------------------------------------------------------------
# 5. Forex LIMIT order E2E — full chain with minTick snap + DAY TIF
# ---------------------------------------------------------------------------


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_e2e_forex_limit_buy_full_chain(
    mock_load_cfg,
    mock_failed,
    mock_sent,
    _mock_notify,
    patched_records,
):
    """E2E: Forex limit BUY — Worker → runner (order_type=limit) → IBKRClient.place_limit_order
    → minTick snap (BUY floor) → LimitOrder DAY TIF → placeOrder + Filled callback."""
    mock_load_cfg.return_value = {
        "market_category": "Forex",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "forex",
    }

    ibkr_client, place_calls = _make_ibkr_client_for_e2e(
        "EURUSD", 12087792, "EUR.USD", min_tick=0.00005,
    )

    with patch(
        "app.services.pending_order_worker.create_client",
        return_value=ibkr_client,
    ):
        w = PendingOrderWorker()
        w._execute_live_order(
            order_id=501,
            order_row={
                "strategy_id": 1,
                "symbol": "EURUSD",
                "signal_type": "open_long",
                "amount": 20000.0,
                "price": 1.13456,
                "order_type": "limit",
            },
            payload={
                "strategy_id": 1,
                "symbol": "EURUSD",
                "signal_type": "open_long",
                "amount": 20000.0,
                "price": 1.13456,
                "order_type": "limit",
                "limit_price": 1.13456,
            },
        )

    mock_failed.assert_not_called()
    mock_sent.assert_called_once()
    assert len(place_calls) == 1

    t = place_calls[0]
    assert t.order.action == "BUY"
    placed_order = ibkr_client._ib.placeOrder.call_args[0][1]
    assert placed_order.tif == "DAY"
    import math
    expected_snap = math.floor(1.13456 / 0.00005) * 0.00005
    assert abs(placed_order.lmtPrice - expected_snap) < 1e-9

    _fire_callbacks_after_fill(
        ibkr_client, t, 20000.0, position_after=20000.0, fill_tag="eur_limit_buy"
    )


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_e2e_forex_limit_sell_full_chain(
    mock_load_cfg,
    mock_failed,
    mock_sent,
    _mock_notify,
    patched_records,
):
    """E2E: Forex limit SELL — minTick snap uses SELL ceil; TIF = DAY."""
    mock_load_cfg.return_value = {
        "market_category": "Forex",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "forex",
    }

    ibkr_client, place_calls = _make_ibkr_client_for_e2e(
        "GBPJPY", 12345678, "GBP.JPY", min_tick=0.005,
    )

    with patch(
        "app.services.pending_order_worker.create_client",
        return_value=ibkr_client,
    ):
        w = PendingOrderWorker()
        w._execute_live_order(
            order_id=502,
            order_row={
                "strategy_id": 1,
                "symbol": "GBPJPY",
                "signal_type": "close_long",
                "amount": 10000.0,
                "price": 192.123,
                "order_type": "limit",
            },
            payload={
                "strategy_id": 1,
                "symbol": "GBPJPY",
                "signal_type": "close_long",
                "amount": 10000.0,
                "price": 192.123,
                "order_type": "limit",
                "limit_price": 192.123,
            },
        )

    mock_failed.assert_not_called()
    mock_sent.assert_called_once()
    assert len(place_calls) == 1

    t = place_calls[0]
    assert t.order.action == "SELL"
    placed_order = ibkr_client._ib.placeOrder.call_args[0][1]
    assert placed_order.tif == "DAY"
    import math
    expected_snap = math.ceil(192.123 / 0.005) * 0.005
    assert abs(placed_order.lmtPrice - expected_snap) < 1e-9

    _fire_callbacks_after_fill(
        ibkr_client, t, 10000.0, position_after=0.0, fill_tag="gbpjpy_limit_sell"
    )


# ---------------------------------------------------------------------------
# 6. Limit order with PartiallyFilled → Filled lifecycle
# ---------------------------------------------------------------------------


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.live_trading.records.update_pending_order_fill_snapshot")
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_e2e_limit_partial_fill_then_filled(
    mock_load_cfg,
    mock_failed,
    mock_sent,
    _mock_notify,
    mock_snapshot,
    patched_records,
):
    """E2E: Limit order lifecycle — Submitted → PartiallyFilled(3000) → PartiallyFilled(7000) → Filled(10000).
    Verifies cumulative overwrite on partials and _handle_fill only on terminal Filled."""
    mock_load_cfg.return_value = {
        "market_category": "Forex",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "forex",
    }

    ibkr_client, place_calls = _make_ibkr_client_for_e2e(
        "EURUSD", 12087792, "EUR.USD", min_tick=0.00005,
    )

    with patch(
        "app.services.pending_order_worker.create_client",
        return_value=ibkr_client,
    ):
        w = PendingOrderWorker()
        w._execute_live_order(
            order_id=503,
            order_row={
                "strategy_id": 5,
                "symbol": "EURUSD",
                "signal_type": "open_long",
                "amount": 10000.0,
                "price": 1.135,
                "order_type": "limit",
            },
            payload={
                "strategy_id": 5,
                "symbol": "EURUSD",
                "signal_type": "open_long",
                "amount": 10000.0,
                "price": 1.135,
                "order_type": "limit",
                "limit_price": 1.135,
            },
        )

    mock_failed.assert_not_called()
    mock_sent.assert_called_once()
    assert len(place_calls) == 1

    trade = place_calls[0]
    order_id = trade.order.orderId

    # --- PartiallyFilled #1: 3000 of 10000 ---
    trade.orderStatus.status = "PartiallyFilled"
    trade.orderStatus.filled = 3000.0
    trade.orderStatus.remaining = 7000.0
    trade.orderStatus.avgFillPrice = 1.135
    trade.order.totalQuantity = 10000.0
    ibkr_client._on_order_status(trade)

    assert mock_snapshot.call_count == 1
    call_kw = mock_snapshot.call_args
    assert call_kw[1]["filled"] == 3000.0
    assert call_kw[1]["remaining"] == 7000.0

    # --- PartiallyFilled #2: 7000 of 10000 ---
    trade.orderStatus.filled = 7000.0
    trade.orderStatus.remaining = 3000.0
    ibkr_client._on_order_status(trade)

    assert mock_snapshot.call_count == 2
    call_kw2 = mock_snapshot.call_args
    assert call_kw2[1]["filled"] == 7000.0
    assert call_kw2[1]["remaining"] == 3000.0

    # --- Terminal Filled: 10000 ---
    trade.orderStatus.status = "Filled"
    trade.orderStatus.filled = 10000.0
    trade.orderStatus.remaining = 0.0
    trade.orderStatus.avgFillPrice = 1.1348

    with patch.object(ibkr_client, "_handle_fill") as mock_handle_fill:
        ibkr_client._on_order_status(trade)
        mock_handle_fill.assert_called_once()
        args = mock_handle_fill.call_args[0]
        assert args[1] == 10000.0  # filled qty
        assert abs(args[2] - 1.1348) < 1e-9  # avg price

    # snapshot NOT called again on terminal Filled
    assert mock_snapshot.call_count == 2


# ---------------------------------------------------------------------------
# 7. Metals limit order E2E (XAUUSD CMDTY/SMART)
# ---------------------------------------------------------------------------


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_e2e_metals_limit_xauusd(
    mock_load_cfg,
    mock_failed,
    mock_sent,
    _mock_notify,
    patched_records,
):
    """E2E: XAUUSD Metals limit BUY — CMDTY/SMART + minTick 0.01 + DAY TIF."""
    mock_load_cfg.return_value = {
        "market_category": "Metals",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "metals",
    }

    ibkr_client, place_calls = _make_ibkr_client_for_e2e(
        "XAUUSD", 69067924, "XAUUSD", sec_type="CMDTY", min_tick=0.01,
    )

    with patch(
        "app.services.pending_order_worker.create_client",
        return_value=ibkr_client,
    ):
        w = PendingOrderWorker()
        w._execute_live_order(
            order_id=504,
            order_row={
                "strategy_id": 10,
                "symbol": "XAUUSD",
                "signal_type": "open_long",
                "amount": 1.0,
                "price": 2345.678,
                "order_type": "limit",
            },
            payload={
                "strategy_id": 10,
                "symbol": "XAUUSD",
                "signal_type": "open_long",
                "amount": 1.0,
                "price": 2345.678,
                "order_type": "limit",
                "limit_price": 2345.678,
            },
        )

    mock_failed.assert_not_called()
    mock_sent.assert_called_once()
    assert len(place_calls) == 1

    t = place_calls[0]
    assert t.contract.secType == "CMDTY"
    assert getattr(t.contract, "exchange", None) == "SMART"
    assert t.order.action == "BUY"
    placed_order = ibkr_client._ib.placeOrder.call_args[0][1]
    assert placed_order.tif == "DAY"
    import math
    expected_snap = math.floor(2345.678 / 0.01) * 0.01
    assert abs(placed_order.lmtPrice - expected_snap) < 1e-9

    _fire_callbacks_after_fill(
        ibkr_client, t, 1.0, position_after=1.0, fill_tag="xau_limit_open"
    )


# ---------------------------------------------------------------------------
# 8. Automation limit always uses DAY (even if payload has time_in_force)
# ---------------------------------------------------------------------------


@patch("app.services.live_trading.ibkr_trading.client.ib_insync", _make_mock_ib_insync())
@patch("app.services.pending_order_worker.PendingOrderWorker._notify_live_best_effort")
@patch("app.services.pending_order_worker.records.mark_order_sent")
@patch("app.services.pending_order_worker.records.mark_order_failed")
@patch("app.services.pending_order_worker.load_strategy_configs")
def test_e2e_automation_limit_always_day_tif(
    mock_load_cfg,
    mock_failed,
    mock_sent,
    _mock_notify,
    patched_records,
):
    """E2E: Automation (worker) limit orders always use DAY TIF per 17-CONTEXT —
    time_in_force in payload is ignored (only REST route passes it through)."""
    mock_load_cfg.return_value = {
        "market_category": "Forex",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "market_type": "forex",
    }

    ibkr_client, place_calls = _make_ibkr_client_for_e2e(
        "EURUSD", 12087792, "EUR.USD", min_tick=0.00005,
    )

    with patch(
        "app.services.pending_order_worker.create_client",
        return_value=ibkr_client,
    ):
        w = PendingOrderWorker()
        w._execute_live_order(
            order_id=505,
            order_row={
                "strategy_id": 1,
                "symbol": "EURUSD",
                "signal_type": "open_long",
                "amount": 20000.0,
                "price": 1.12,
                "order_type": "limit",
            },
            payload={
                "strategy_id": 1,
                "symbol": "EURUSD",
                "signal_type": "open_long",
                "amount": 20000.0,
                "price": 1.12,
                "order_type": "limit",
                "limit_price": 1.12,
            },
        )

    mock_failed.assert_not_called()
    mock_sent.assert_called_once()
    assert len(place_calls) == 1

    placed_order = ibkr_client._ib.placeOrder.call_args[0][1]
    assert placed_order.tif == "DAY"
