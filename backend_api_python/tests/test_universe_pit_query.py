"""PIT membership query tests (mocked DB; no live PostgreSQL required)."""
from datetime import date
from unittest.mock import patch

from app.services.universe_nq100_service import get_constituents_as_of
from tests.conftest import make_db_ctx


@patch("app.utils.db.get_db_connection")
def test_get_constituents_as_of_includes_symbol_when_date_inside_closed_interval(mock_get_db):
    mock_get_db.return_value = make_db_ctx(fetchall_result=[("AAPL",)])
    out = get_constituents_as_of(date(2020, 6, 1))
    assert "AAPL" in out


@patch("app.utils.db.get_db_connection")
def test_get_constituents_as_of_includes_open_ended_membership(mock_get_db):
    mock_get_db.return_value = make_db_ctx(fetchall_result=[("MSFT",)])
    out = get_constituents_as_of(date(2030, 1, 1))
    assert "MSFT" in out


@patch("app.utils.db.get_db_connection")
def test_get_constituents_as_of_excludes_after_valid_to(mock_get_db):
    mock_get_db.return_value = make_db_ctx(fetchall_result=[])
    out = get_constituents_as_of(date(2022, 1, 1))
    assert out == []


@patch("app.utils.db.get_db_connection")
def test_get_constituents_as_of_empty_when_no_rows(mock_get_db):
    mock_get_db.return_value = make_db_ctx(fetchall_result=[])
    out = get_constituents_as_of(date(2025, 1, 1))
    assert out == []
