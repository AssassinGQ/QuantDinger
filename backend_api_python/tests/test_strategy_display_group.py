"""
Tests for strategy display_group support in create_strategy and batch_create_strategies.
"""

import sys
import types
import pytest
from unittest.mock import patch, MagicMock
from contextlib import contextmanager

# Mock heavy deps
for mod in ("jwt", "psycopg2", "psycopg2.pool", "psycopg2.extras"):
    sys.modules.setdefault(mod, types.ModuleType(mod))


def _noop_decorator(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated


import app.utils.auth as _auth_mod
_auth_mod.login_required = _noop_decorator

from app.services.strategy import StrategyService


@contextmanager
def _mock_db(insert_rowid=1):
    """Mock get_db_connection for strategy service."""
    mock_cur = MagicMock()
    mock_cur.lastrowid = insert_rowid

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_conn.__enter__ = lambda self: mock_conn
    mock_conn.__exit__ = lambda *args: None

    with patch('app.services.strategy.get_db_connection', return_value=mock_conn):
        yield mock_cur


class TestCreateStrategyDisplayGroup:
    """Test create_strategy includes display_group."""

    def test_create_strategy_with_display_group(self):
        with _mock_db(insert_rowid=42) as mock_cur:
            svc = StrategyService()
            sid = svc.create_strategy({
                'user_id': 1,
                'strategy_name': 'Test Strategy',
                'display_group': 'scalping',
                'indicator_config': {},
                'trading_config': {},
                'notification_config': {},
            })
        assert sid == 42
        call_args = mock_cur.execute.call_args
        assert call_args is not None
        params = call_args[0][1]
        assert 'scalping' in params

    def test_create_strategy_defaults_display_group_ungrouped(self):
        with _mock_db(insert_rowid=43) as mock_cur:
            svc = StrategyService()
            svc.create_strategy({
                'user_id': 1,
                'strategy_name': 'Test Strategy',
                'indicator_config': {},
                'trading_config': {},
                'notification_config': {},
            })
        call_args = mock_cur.execute.call_args
        assert call_args is not None
        params = call_args[0][1]
        assert 'ungrouped' in params


class TestBatchCreateStrategiesDisplayGroup:
    """Test batch_create_strategies passes display_group to each strategy."""

    def test_batch_create_with_display_group(self):
        with _mock_db(insert_rowid=100) as mock_cur:
            svc = StrategyService()
            result = svc.batch_create_strategies({
                'user_id': 1,
                'strategy_name': 'Grid',
                'display_group': 'grid',
                'symbols': ['BTC/USDT', 'ETH/USDT'],
                'indicator_config': {'indicator_id': 1},
                'trading_config': {},
                'notification_config': {},
            })
        assert result.get('total_created') == 2
        assert result.get('success')
        # Each create_strategy call should have display_group
        assert mock_cur.execute.call_count >= 2
        for call in mock_cur.execute.call_args_list:
            params = call[0][1]
            assert 'grid' in params or 'ungrouped' in params
