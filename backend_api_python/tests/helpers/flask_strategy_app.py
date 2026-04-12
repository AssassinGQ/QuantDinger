"""Shared Flask app factory for strategy_bp E2E HTTP tests."""
from __future__ import annotations

import importlib
from functools import wraps

from flask import Flask, g


def _noop_decorator(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)

    return decorated


def patch_login_and_reload_strategy():
    import app.utils.auth as _auth_mod

    _auth_mod.login_required = _noop_decorator
    import app.routes.strategy as strategy_mod

    importlib.reload(strategy_mod)
    return strategy_mod.strategy_bp


def make_strategy_test_app() -> Flask:
    """Flask app with strategy routes at /api and g.user_id=1 (legacy E2E client_fixture)."""
    strategy_bp = patch_login_and_reload_strategy()
    app = Flask(__name__)
    app.register_blueprint(strategy_bp, url_prefix="/api")

    @app.before_request
    def _set_user():
        g.user_id = 1

    return app
