"""Tests for strategy API routes, specifically force-close-all."""

import sys
import types
import importlib
from functools import wraps
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask, g

for mod in ("jwt", "psycopg2", "psycopg2.pool", "psycopg2.extras"):
    sys.modules.setdefault(mod, types.ModuleType(mod))


def _noop_decorator(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated


import app.utils.auth as _auth_mod  # noqa: E402
_auth_mod.login_required = _noop_decorator

import app.routes.strategy as strategy_mod  # noqa: E402
importlib.reload(strategy_mod)

strategy_bp = strategy_mod.strategy_bp


@pytest.fixture
def client_fixture():
    """Fixture to provide a test client for the Flask app."""
    app = Flask(__name__)
    app.register_blueprint(strategy_bp, url_prefix='/api/strategy')

    @app.before_request
    def set_g():
        g.user_id = 1

    with app.test_client() as c:
        yield c


def test_force_close_all_missing_id(client_fixture):
    """Test missing id returns 400."""
    res = client_fixture.post('/api/strategy/strategies/force-close-all')
    assert res.status_code == 400
    assert res.json['msg'] == 'Missing strategy id parameter'


@patch('app.routes.strategy.get_strategy_service')
def test_force_close_all_not_found(mock_service, client_fixture):
    """Test non-existent strategy returns 404."""
    mock_service.return_value.get_strategy.return_value = None
    res = client_fixture.post('/api/strategy/strategies/force-close-all?id=999')
    assert res.status_code == 404
    assert res.json['msg'] == 'Strategy not found'


@patch('app.routes.strategy.get_strategy_service')
@patch('app.services.data_handler.DataHandler.get_all_positions')
def test_force_close_all_no_positions(mock_get_positions, mock_service, client_fixture):
    """Test when strategy has no positions."""
    mock_service.return_value.get_strategy.return_value = {"id": 1, "trading_config": {}}
    mock_get_positions.return_value = []

    res = client_fixture.post('/api/strategy/strategies/force-close-all?id=1')
    assert res.status_code == 200
    assert res.json['code'] == 1
    assert res.json['msg'] == 'No positions to close'
    assert res.json['data']['closed_count'] == 0


@patch('app.routes.strategy.get_strategy_service')
@patch('app.services.data_handler.DataHandler.get_all_positions')
def test_force_close_all_success(mock_get_positions, mock_service, client_fixture):
    """Test successful close all positions."""
    mock_service.return_value.get_strategy.return_value = {
        "id": 1,
        "trading_config": {"leverage": 2.0, "market_type": "swap"}
    }
    mock_get_positions.return_value = [
        {"symbol": "BTC/USDT", "side": "long", "size": 0.5, "entry_price": 50000},
        {"symbol": "ETH/USDT", "side": "short", "size": 2.0, "entry_price": 3000}
    ]

    mock_enqueuer = MagicMock()
    mock_enqueuer.enqueue_pending_order.side_effect = [111, 222]

    mock_price_fetcher = MagicMock()
    mock_price_fetcher.get_price.return_value = 51000

    with patch('app.services.pending_order_enqueuer.PendingOrderEnqueuer',
               return_value=mock_enqueuer), \
         patch('app.services.price_fetcher.get_price_fetcher',
               return_value=mock_price_fetcher):
        res = client_fixture.post('/api/strategy/strategies/force-close-all?id=1')

    assert res.status_code == 200
    assert res.json['code'] == 1
    assert res.json['data']['closed_count'] == 2
    assert len(res.json['data']['positions']) == 2

    assert mock_enqueuer.enqueue_pending_order.call_count == 2

    calls = mock_enqueuer.enqueue_pending_order.call_args_list
    assert calls[0][1]['signal_type'] == 'close_long'
    assert calls[0][1]['symbol'] == 'BTC/USDT'
    assert calls[1][1]['signal_type'] == 'close_short'
    assert calls[1][1]['symbol'] == 'ETH/USDT'


@patch('app.routes.strategy.get_strategy_service')
@patch('app.services.data_handler.DataHandler.get_all_positions')
def test_force_close_all_partial_failure(mock_get_positions, mock_service, client_fixture):
    """Test when some positions fail to enqueue."""
    mock_service.return_value.get_strategy.return_value = {
        "id": 1,
        "trading_config": {"leverage": 1.0, "market_type": "swap"}
    }
    mock_get_positions.return_value = [
        {"symbol": "BTC/USDT", "side": "long", "size": 0.5, "entry_price": 50000},
        {"symbol": "ETH/USDT", "side": "short", "size": 2.0, "entry_price": 3000}
    ]

    mock_enqueuer = MagicMock()
    mock_enqueuer.enqueue_pending_order.side_effect = [111, None]

    mock_price_fetcher = MagicMock()
    mock_price_fetcher.get_price.return_value = 51000

    with patch('app.services.pending_order_enqueuer.PendingOrderEnqueuer',
               return_value=mock_enqueuer), \
         patch('app.services.price_fetcher.get_price_fetcher',
               return_value=mock_price_fetcher):
        res = client_fixture.post('/api/strategy/strategies/force-close-all?id=1')

    assert res.status_code == 200
    assert res.json['code'] == 1
    assert res.json['data']['closed_count'] == 1
