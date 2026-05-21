"""NQ100 universe ingest: normalization, parsers and CSV->DB ingest."""

from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, patch

import requests

from app.services.nq100_sources import (
    fetch_nq100_symbols_current,
    parse_nasdaq_nq100_html,
    parse_wikipedia_nq100_html,
)
from app.services.nq100_csv_ingest_service import (
    import_eiv_csv,
    import_ic_csv,
    import_nq100_csv_bundle,
)
from app.utils.symbol_normalize import normalize_us_stock_symbol

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "nq100"
_MIGRATION_0056 = (
    Path(__file__).resolve().parent.parent / "migrations" / "0056_qd_nq100_index_eiv_and_ic_raw.sql"
)


def test_normalize_us_stock_symbol_brk_class_b_to_brk_dash_b():
    assert normalize_us_stock_symbol("BRK.B") == "BRK-B"
    assert normalize_us_stock_symbol("brk.b") == "BRK-B"


def test_normalize_us_stock_symbol_strips_whitespace():
    assert normalize_us_stock_symbol("  MSFT  ") == "MSFT"
    assert normalize_us_stock_symbol("") == ""
    assert normalize_us_stock_symbol("   ") == ""


def test_normalize_us_stock_symbol_plain_ticker_uppercase():
    assert normalize_us_stock_symbol("aapl") == "AAPL"


def test_parse_nasdaq_fixture_contains_msft_aapl_googl():
    html = (_FIXTURE_DIR / "nasdaq_listing_sample.html").read_text(encoding="utf-8")
    syms = parse_nasdaq_nq100_html(html)
    assert {"MSFT", "AAPL", "GOOGL"}.issubset(syms)


def test_parse_wikipedia_fixture_contains_msft_aapl_googl():
    html = (_FIXTURE_DIR / "wikipedia_table_sample.html").read_text(encoding="utf-8")
    syms = parse_wikipedia_nq100_html(html)
    assert {"MSFT", "AAPL", "GOOGL"}.issubset(syms)


@patch("app.services.nq100_sources.requests.get")
def test_fetch_chain_uses_primary_when_requests_returns_fixture_html(mock_get):
    html = (_FIXTURE_DIR / "nasdaq_listing_sample.html").read_text(encoding="utf-8")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.text = html
    mock_get.return_value = mock_resp

    syms, src, _ts = fetch_nq100_symbols_current()
    assert src == "nasdaq.com"
    assert {"MSFT", "AAPL", "GOOGL"}.issubset(syms)
    mock_get.assert_called_once()


@patch("nasdaq_100_ticker_history.tickers_as_of")
@patch("app.services.nq100_sources.requests.get")
def test_fetch_chain_falls_back_to_package_when_http_fails(mock_get, mock_tickers):
    mock_get.side_effect = [
        requests.RequestException("nasdaq down"),
        requests.RequestException("wiki down"),
    ]
    mock_tickers.return_value = frozenset({"MSFT", "AAPL"})

    syms, src, _ts = fetch_nq100_symbols_current()
    assert mock_get.call_count == 2
    mock_tickers.assert_called_once()
    assert src == "nasdaq-100-ticker-history"
    assert syms == {"MSFT", "AAPL"}


def test_migration_0056_contains_qd_nq100_index_eiv_schema():
    sql = _MIGRATION_0056.read_text(encoding="utf-8").lower()
    assert "create table if not exists qd_nq100_index_eiv" in sql
    assert "trade_date date primary key" in sql
    assert "eod_index_value numeric(20,6) not null" in sql
    assert "raw_payload jsonb not null" in sql


def test_migration_0056_contains_ic_raw_preservation_schema():
    sql = _MIGRATION_0056.read_text(encoding="utf-8").lower()
    assert "create table if not exists qd_nq100_ic_raw" in sql
    assert "raw_payload jsonb not null" in sql
    assert "component_symbol varchar(32) not null" in sql
    assert "constraint uq_qd_nq100_ic_raw_key unique (index_symbol, trade_date, component_symbol)" in sql


def _mocked_conn():
    cursor = MagicMock()
    cursor.rowcount = 1
    conn = MagicMock()
    conn.cursor.return_value = cursor
    ctx = MagicMock()
    ctx.__enter__.return_value = conn
    ctx.__exit__.return_value = False
    return cursor, conn, ctx


def test_import_ic_csv_preserves_all_source_fields_in_raw_payload():
    csv_text = (
        "index_symbol,date,component_symbol,component_isin,component_mic,component_name,extra_flag\n"
        "NDX,2026-01-02,MSFT,US5949181045,XNAS,Microsoft Corp,Y\n"
    )
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".csv", delete=False) as tmp:
        tmp.write(csv_text)
        csv_path = tmp.name

    cursor, _conn, ctx = _mocked_conn()
    with patch("app.services.nq100_csv_ingest_service.db.get_db_connection", return_value=ctx):
        summary = import_ic_csv(csv_path)

    raw_calls = [c for c in cursor.execute.call_args_list if "qd_nq100_ic_raw" in c.args[0]]
    assert len(raw_calls) == 1
    raw_payload = raw_calls[0].args[1][4]
    assert raw_payload["index_symbol"] == "NDX"
    assert raw_payload["date"] == "2026-01-02"
    assert raw_payload["component_symbol"] == "MSFT"
    assert raw_payload["component_isin"] == "US5949181045"
    assert raw_payload["component_mic"] == "XNAS"
    assert raw_payload["component_name"] == "Microsoft Corp"
    assert raw_payload["extra_flag"] == "Y"
    assert summary["ic_rows_read"] == 1
    assert summary["ic_rows_inserted"] == 1


def test_import_eiv_csv_writes_eod_index_value_and_trade_date():
    csv_text = (
        "date,index_symbol,eod_index_value,high,low\n"
        "2026-01-02,NDX,19999.12,20000.00,19888.88\n"
    )
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".csv", delete=False) as tmp:
        tmp.write(csv_text)
        csv_path = tmp.name

    cursor, _conn, ctx = _mocked_conn()
    with patch("app.services.nq100_csv_ingest_service.db.get_db_connection", return_value=ctx):
        summary = import_eiv_csv(csv_path)

    eiv_calls = [c for c in cursor.execute.call_args_list if "qd_nq100_index_eiv" in c.args[0]]
    assert len(eiv_calls) == 1
    params = eiv_calls[0].args[1]
    assert params[0] == date(2026, 1, 2)
    assert str(params[2]) == "19999.12"
    assert summary["eiv_rows_read"] == 1
    assert summary["eiv_rows_upserted"] == 1


def test_import_bundle_is_idempotent_for_duplicate_runs():
    ic_csv = (
        "index_symbol,date,component_symbol\n"
        "NDX,2026-01-02,MSFT\n"
    )
    eiv_csv = (
        "date,index_symbol,eod_index_value\n"
        "2026-01-02,NDX,19999.12\n"
    )
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".csv", delete=False) as ic_tmp:
        ic_tmp.write(ic_csv)
        ic_path = ic_tmp.name
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".csv", delete=False) as eiv_tmp:
        eiv_tmp.write(eiv_csv)
        eiv_path = eiv_tmp.name

    cursor, _conn, ctx = _mocked_conn()
    seen_membership_keys = set()

    def execute_side_effect(sql, params):
        if "INSERT INTO qd_nq100_membership" in sql:
            key = (params[0], params[1], params[3])
            if key in seen_membership_keys:
                cursor.rowcount = 0
            else:
                seen_membership_keys.add(key)
                cursor.rowcount = 1
        else:
            cursor.rowcount = 1

    cursor.execute.side_effect = execute_side_effect

    with patch("app.services.nq100_csv_ingest_service.db.get_db_connection", return_value=ctx):
        first = import_nq100_csv_bundle(ic_path, eiv_path)
        second = import_nq100_csv_bundle(ic_path, eiv_path)

    assert first["ic_rows_inserted"] == 1
    assert second["ic_rows_inserted"] == 0
    assert second["ic_rows_upserted_or_skipped"] == 1
    assert first["eiv_rows_upserted"] == 1
    assert second["eiv_rows_upserted"] == 1


def test_import_ic_csv_symbol_date_key_prevents_duplicates():
    csv_text = (
        "index_symbol,date,component_symbol\n"
        "NDX,2026-01-02,MSFT\n"
        "NDX,2026-01-02,MSFT\n"
    )
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".csv", delete=False) as tmp:
        tmp.write(csv_text)
        csv_path = tmp.name

    cursor, _conn, ctx = _mocked_conn()
    with patch("app.services.nq100_csv_ingest_service.db.get_db_connection", return_value=ctx):
        summary = import_ic_csv(csv_path)

    membership_calls = [c for c in cursor.execute.call_args_list if "INSERT INTO qd_nq100_membership" in c.args[0]]
    raw_calls = [c for c in cursor.execute.call_args_list if "qd_nq100_ic_raw" in c.args[0]]
    assert len(membership_calls) == 1
    assert len(raw_calls) == 1
    assert summary["ic_rows_read"] == 2
    assert summary["ic_rows_inserted"] == 1
    assert summary["ic_rows_upserted_or_skipped"] == 1
