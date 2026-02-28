"""
pytest 配置与共享 fixtures。
"""
from unittest.mock import MagicMock


def make_db_ctx(
    fetchone_result=None,
    fetchall_result=None,
    lastrowid=None,
    fetchone_side_effect=None,
):
    """构造 get_db_connection 的 context manager mock，支持 fetchone/fetchall/lastrowid/side_effect"""
    conn = MagicMock()
    cursor = MagicMock()
    if fetchone_side_effect is not None:
        cursor.fetchone.side_effect = fetchone_side_effect
    else:
        cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result if fetchall_result is not None else []
    cursor.lastrowid = lastrowid
    conn.cursor.return_value = cursor
    ctx = MagicMock()
    ctx.__enter__.return_value = conn
    ctx.__exit__.return_value = False
    return ctx
