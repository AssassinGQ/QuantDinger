"""
UC-SA-VAL: API-time exchange + market_category validation (plan 11-01).
"""

import sys
import types

import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

# Mock heavy deps (same pattern as test_strategy_display_group)
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
    mock_cur = MagicMock()
    mock_cur.lastrowid = insert_rowid
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_conn.__enter__ = lambda self: mock_conn
    mock_conn.__exit__ = lambda *args: None
    with patch("app.services.strategy.get_db_connection", return_value=mock_conn):
        yield mock_cur


def _forex_payload(strategy_name: str, exchange_id: str, **extra):
    return {
        "user_id": 1,
        "strategy_name": strategy_name,
        "market_category": "Forex",
        "exchange_config": {"exchange_id": exchange_id},
        "indicator_config": {},
        "trading_config": {"symbol": "EURUSD"},
        "notification_config": {},
        **extra,
    }


def _metals_payload(strategy_name: str, exchange_id: str, **extra):
    return {
        "user_id": 1,
        "strategy_name": strategy_name,
        "market_category": "Metals",
        "exchange_config": {"exchange_id": exchange_id},
        "indicator_config": {},
        "trading_config": {"symbol": "XAUUSD"},
        "notification_config": {},
        **extra,
    }


class TestUcSaValCreate:
    def test_uc_sa_val_01_ibkr_paper_forex_ok(self):
        """UC-SA-VAL-01: ibkr-paper + Forex succeeds."""
        with _mock_db(insert_rowid=101) as mock_cur:
            svc = StrategyService()
            sid = svc.create_strategy(_forex_payload("UC-SA-VAL-01-ibkr-paper", "ibkr-paper"))
        assert sid == 101
        assert mock_cur.execute.called

    def test_uc_sa_val_02_ibkr_live_forex_ok(self):
        """UC-SA-VAL-02: ibkr-live + Forex succeeds."""
        with _mock_db(insert_rowid=102):
            svc = StrategyService()
            sid = svc.create_strategy(_forex_payload("UC-SA-VAL-02-ibkr-live", "ibkr-live"))
        assert sid == 102

    def test_uc_sa_val_03_mt5_forex_ok(self):
        """UC-SA-VAL-03: mt5 + Forex succeeds."""
        with _mock_db(insert_rowid=103):
            svc = StrategyService()
            sid = svc.create_strategy(_forex_payload("UC-SA-VAL-03-mt5", "mt5"))
        assert sid == 103

    def test_uc_16_t5_03_ibkr_paper_metals_xauusd_ok(self):
        """UC-16-T5-03: ibkr-paper + Metals + XAUUSD create_strategy succeeds (mirrors Forex path)."""
        with _mock_db(insert_rowid=301) as mock_cur:
            svc = StrategyService()
            sid = svc.create_strategy(
                _metals_payload("UC-16-T5-03-ibkr-paper-metals", "ibkr-paper")
            )
        assert sid == 301
        assert isinstance(sid, int)
        assert mock_cur.execute.called

    def test_uc_sa_val_04_binance_forex_raises(self):
        """UC-SA-VAL-04: binance + Forex rejected."""
        with _mock_db():
            svc = StrategyService()
            with pytest.raises(ValueError) as exc:
                svc.create_strategy(_forex_payload("UC-SA-VAL-04-binance", "binance"))
        assert "only_supports_crypto" in str(exc.value)

    def test_uc_sa_val_05_crypto_ibkr_raises(self):
        """UC-SA-VAL-05: ibkr-paper + Crypto rejected."""
        with _mock_db():
            svc = StrategyService()
            with pytest.raises(ValueError) as exc:
                svc.create_strategy(
                    {
                        "user_id": 1,
                        "strategy_name": "UC-SA-VAL-05-crypto-ibkr",
                        "market_category": "Crypto",
                        "exchange_config": {"exchange_id": "ibkr-paper"},
                        "indicator_config": {},
                        "trading_config": {"symbol": "BTC/USDT"},
                        "notification_config": {},
                    }
                )
        msg = str(exc.value).lower()
        assert "ibkr" in msg
        assert "only supports" in msg


class TestUcSaValUpdate:
    def test_uc_sa_val_06_update_to_illegal_pair_raises(self):
        """UC-SA-VAL-06: update_strategy rejects Forex + binance."""
        existing = {
            "strategy_name": "UC-SA-VAL-06",
            "market_category": "Forex",
            "exchange_config": {"exchange_id": "ibkr-paper"},
            "notification_config": {},
            "indicator_config": {},
            "trading_config": {"symbol": "EURUSD"},
            "ai_model_config": {},
            "display_group": "ungrouped",
        }
        with _mock_db() as mock_cur:
            svc = StrategyService()
            with patch.object(StrategyService, "get_strategy", return_value=existing):
                with pytest.raises(ValueError) as exc:
                    svc.update_strategy(
                        7,
                        {
                            "exchange_config": {"exchange_id": "binance"},
                            "market_category": "Forex",
                        },
                    )
        assert "only_supports_crypto" in str(exc.value)
        mock_cur.execute.assert_not_called()


class TestUcSaValBatch:
    def test_uc_sa_val_07_batch_ibkr_paper_ok(self):
        """UC-SA-VAL-07: batch_create_strategies Forex:EURUSD + ibkr-paper."""
        with _mock_db(insert_rowid=201) as mock_cur:
            svc = StrategyService()
            result = svc.batch_create_strategies(
                {
                    "user_id": 1,
                    "strategy_name": "UC-SA-VAL-07-batch",
                    "symbols": ["Forex:EURUSD"],
                    "exchange_config": {"exchange_id": "ibkr-paper"},
                    "indicator_config": {},
                    "trading_config": {},
                    "notification_config": {},
                }
            )
        assert result.get("created_ids")
        assert mock_cur.execute.called

    def test_uc_sa_val_08_batch_binance_fails(self):
        """UC-SA-VAL-08: batch with binance + Forex yields failed_symbols."""
        with _mock_db(insert_rowid=999):
            svc = StrategyService()
            result = svc.batch_create_strategies(
                {
                    "user_id": 1,
                    "strategy_name": "UC-SA-VAL-08-batch",
                    "symbols": ["Forex:EURUSD"],
                    "exchange_config": {"exchange_id": "binance"},
                    "indicator_config": {},
                    "trading_config": {},
                    "notification_config": {},
                }
            )
        failed = result.get("failed_symbols") or []
        assert len(failed) >= 1
        err = (failed[0].get("error") or "").lower()
        assert "only_supports_crypto" in err
