"""
Tests for indicator group (indicator_group) support in getIndicators and saveIndicator APIs.
"""

import sys
import types
import pytest
from unittest.mock import patch, MagicMock
from contextlib import contextmanager
from functools import wraps

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

import app.routes.indicator as ind_mod


@pytest.fixture
def client():
    from flask import Flask, g
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(ind_mod.indicator_bp, url_prefix="/api/indicator")

    @app.before_request
    def _set_g_user():
        g.user_id = 1

    with app.test_client() as c:
        yield c


@contextmanager
def _mock_db(rows=None, lastrowid=1):
    """Mock get_db_connection with controlled cursor results."""
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows or []
    mock_cur.fetchone.return_value = None
    mock_cur.lastrowid = lastrowid

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_conn.__enter__ = lambda self: mock_conn
    mock_conn.__exit__ = lambda *args: None

    with patch('app.routes.indicator.get_db_connection', return_value=mock_conn):
        yield mock_cur, mock_conn


class TestGetIndicatorsIndicatorGroup:
    """Test getIndicators returns indicator_group field."""

    def test_get_indicators_returns_indicator_group(self, client):
        rows = [
            {'id': 1, 'user_id': 1, 'name': 'Test', 'code': 'x=1', 'indicator_group': 'trend'},
            {'id': 2, 'user_id': 1, 'name': 'Test2', 'code': 'y=2', 'indicator_group': None},
        ]
        with _mock_db(rows=rows):
            resp = client.get('/api/indicator/getIndicators?userid=1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 1
        items = data['data']
        assert len(items) == 2
        assert items[0].get('indicator_group') == 'trend'
        assert items[1].get('indicator_group') == 'ungrouped'


class TestSaveIndicatorGroup:
    """Test saveIndicator accepts and persists group."""

    def test_save_indicator_creates_with_group(self, client):
        with _mock_db(rows=[], lastrowid=99) as (mock_cur, _):
            resp = client.post(
                '/api/indicator/saveIndicator',
                json={'id': 0, 'code': 'x=1', 'group': 'trend'},
                content_type='application/json'
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 1
        call_args = mock_cur.execute.call_args
        assert call_args is not None
        sql = call_args[0][0]
        params = call_args[0][1]
        assert 'indicator_group' in sql
        assert 'trend' in params

    def test_save_indicator_defaults_to_ungrouped(self, client):
        with _mock_db(rows=[], lastrowid=99) as (mock_cur, _):
            resp = client.post(
                '/api/indicator/saveIndicator',
                json={'id': 0, 'code': 'x=1'},
                content_type='application/json'
            )
        assert resp.status_code == 200
        call_args = mock_cur.execute.call_args
        assert call_args is not None
        params = call_args[0][1]
        assert 'ungrouped' in params
