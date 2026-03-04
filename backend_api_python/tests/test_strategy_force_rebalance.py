"""Tests for strategy API routes, specifically force-rebalance."""

import sys
import types
import importlib
from functools import wraps
from unittest.mock import patch
import pytest

# Mock heavy deps before importing app modules
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

def test_force_rebalance_missing_id(client_fixture):
    """Test missing id returns 400."""
    with patch('app.routes.strategy.login_required', lambda x: x):
        res = client_fixture.post('/api/strategy/strategies/force-rebalance')
        assert res.status_code == 400
        assert res.json['msg'] == 'Missing strategy id parameter'

@patch('app.routes.strategy.get_strategy_service')
def test_force_rebalance_not_found(mock_service, client_fixture):
    """Test non-existent strategy returns 404."""
    mock_service.return_value.get_strategy.return_value = None
    res = client_fixture.post('/api/strategy/strategies/force-rebalance?id=999')
    assert res.status_code == 404
    assert res.json['msg'] == 'Strategy not found'

@patch('app.routes.strategy.get_strategy_service')
@patch('app.services.data_handler.DataHandler.force_rebalance')
def test_force_rebalance_success(mock_force_rebalance, mock_service, client_fixture):
    """Test successful rebalance trigger."""
    mock_service.return_value.get_strategy.return_value = {"id": 1}
    res = client_fixture.post('/api/strategy/strategies/force-rebalance?id=1')
    assert res.status_code == 200
    assert res.json['code'] == 1
    assert res.json['msg'] == 'Rebalance triggered successfully'
    mock_force_rebalance.assert_called_once_with(1)

