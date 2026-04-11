"""
pytest 配置与共享 fixtures。
"""
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "Forex: Forex liquidHours unit tests (phase 09)")
    config.addinivalue_line("markers", "ForexRTH: Forex is_market_open integration tests (phase 09)")
from unittest.mock import MagicMock
from app.services.signal_processor import get_signal_deduplicator


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

@pytest.fixture(autouse=True)
def reset_signal_deduplicator():
    """每个测试前清空内存去重缓存，避免互相干扰。"""
    get_signal_deduplicator().clear()

