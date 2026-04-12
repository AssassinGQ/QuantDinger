"""UC-02a/UC-02b: pending_orders.remaining schema + update_pending_order_fill_snapshot."""
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_uc02a_init_sql_and_migration_define_remaining_decimal():
    init_sql = (REPO_ROOT / "migrations" / "init.sql").read_text(encoding="utf-8")
    mig = (REPO_ROOT / "migrations" / "0054_add_pending_orders_remaining.sql").read_text(
        encoding="utf-8"
    )
    assert "pending_orders" in init_sql.lower()
    assert "remaining" in init_sql
    assert "DECIMAL" in init_sql or "decimal" in init_sql.lower()
    assert "remaining" in mig
    assert "DECIMAL" in mig or "decimal" in mig.lower()


@patch("app.services.live_trading.records.get_db_connection")
def test_uc02b_snapshot_update_calls_db_with_values(mock_get_db):
    from app.services.live_trading import records

    mock_conn = mock_get_db.return_value.__enter__.return_value
    mock_cur = mock_conn.cursor.return_value

    records.update_pending_order_fill_snapshot(1, filled=3.0, remaining=7.0, avg_price=1.1)

    mock_cur.execute.assert_called_once()
    args = mock_cur.execute.call_args[0]
    sql = args[0]
    params = args[1]
    assert "UPDATE pending_orders" in sql
    assert "remaining" in sql.lower()
    assert params[0] == 3.0
    assert params[1] == 7.0
    assert params[2] == 1.1
    assert params[3] == 1


def test_uc02b_non_positive_order_id_is_no_op():
    from app.services.live_trading import records

    with patch.object(records, "get_db_connection") as mock_get_db:
        records.update_pending_order_fill_snapshot(0, filled=1.0, remaining=1.0)
        records.update_pending_order_fill_snapshot(-1, filled=1.0, remaining=1.0)
    mock_get_db.assert_not_called()
