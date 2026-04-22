"""
IBKR records layer: UC-FP6 (ibkr_save_pnl), schema/metadata for ibkr_save_position (UC-SCHEMA).
"""
from unittest.mock import patch

import pytest

from tests.conftest import make_db_ctx


@pytest.fixture(autouse=True)
def _reset_ibkr_tables_flag():
    """Allow _ensure_tables to run against mocked connection each test."""
    import app.services.live_trading.records as records

    prev = records._IBKR_TABLES_ENSURED
    records._IBKR_TABLES_ENSURED = False
    yield
    records._IBKR_TABLES_ENSURED = prev


@patch("app.services.live_trading.records.get_db_connection")
def test_uc_fp6_ibkr_save_pnl_runs_without_nameerror(mock_get_db):
    """UC-FP6: real ibkr_save_pnl body runs; only get_db_connection is mocked."""
    import app.services.live_trading.records as records

    mock_get_db.return_value = make_db_ctx()

    ok = records.ibkr_save_pnl(
        account="DU123",
        daily_pnl=1.0,
        unrealized_pnl=2.0,
        realized_pnl=3.0,
    )
    assert ok is True
    conn = mock_get_db.return_value.__enter__.return_value
    cursor = conn.cursor.return_value
    assert cursor.execute.called
    sql_calls = [str(call[0][0]) for call in cursor.execute.call_args_list if call[0]]
    assert any("qd_ibkr_pnl" in s and "INSERT" in s.upper() for s in sql_calls)


@patch("app.services.live_trading.records.get_db_connection")
def test_uc_schema_ibkr_save_position_includes_contract_metadata(mock_get_db):
    """UC-SCHEMA: INSERT parameters include sec_type, exchange, currency for Forex."""
    import app.services.live_trading.records as records

    mock_get_db.return_value = make_db_ctx()

    ok = records.ibkr_save_position(
        account="DU1",
        con_id=4242,
        symbol="EUR.USD",
        sec_type="CASH",
        exchange="IDEALPRO",
        currency="USD",
        position=10000.0,
    )
    assert ok is True
    conn = mock_get_db.return_value.__enter__.return_value
    cursor = conn.cursor.return_value
    found = False
    for call in cursor.execute.call_args_list:
        if not call[0] or len(call[0]) < 2:
            continue
        params = call[0][1]
        if not isinstance(params, tuple):
            continue
        if "CASH" in params and "IDEALPRO" in params and "USD" in params and "EUR.USD" in params:
            found = True
            break
    assert found


@patch("app.services.live_trading.records.get_db_connection")
def test_update_trade_commission_uses_exec_id_idempotency(mock_get_db):
    """Same exec_id should not be double-counted."""
    import app.services.live_trading.records as records

    ctx = make_db_ctx()
    mock_get_db.return_value = ctx
    conn = ctx.__enter__.return_value
    cursor = conn.cursor.return_value

    # first select trade_id
    # second branch: insert commission exec row
    # then update trade commission sum
    cursor.fetchone.return_value = {"id": 123}
    cursor.rowcount = 1

    records.update_trade_commission(
        strategy_id=1,
        symbol="AAPL",
        trade_type="open_long",
        commission=0.25,
        commission_ccy="USD",
        exec_id="exec-1",
        pending_order_id=999,
    )

    sql_calls = [str(c[0][0]) for c in cursor.execute.call_args_list if c[0]]
    assert any("INSERT INTO qd_commission_execs" in s for s in sql_calls)
    assert any("ON CONFLICT (exec_id) DO NOTHING" in s for s in sql_calls)
    assert any("UPDATE qd_strategy_trades" in s for s in sql_calls)
