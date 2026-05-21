from datetime import date
from unittest.mock import patch

from flask import Flask

from app.routes.universe import universe_bp


def _make_app():
    app = Flask(__name__)
    app.register_blueprint(universe_bp, url_prefix="/api/universe")
    return app


@patch("app.routes.universe.get_constituents_as_of", return_value=["MSFT"])
def test_get_nq100_without_date_returns_success_envelope(_mock_get):
    app = _make_app()
    client = app.test_client()
    resp = client.get("/api/universe/nq100")
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["code"] == 1
    assert "MSFT" in payload["data"]["symbols"]


@patch("app.routes.universe.get_constituents_as_of", return_value=["AAPL"])
def test_get_nq100_with_date_calls_pit(mock_get):
    app = _make_app()
    client = app.test_client()
    resp = client.get("/api/universe/nq100?date=2020-06-01")
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["code"] == 1
    mock_get.assert_called_once_with(date(2020, 6, 1))


@patch(
    "app.routes.universe.get_eiv_as_of",
    return_value={
        "date": date(2020, 6, 1),
        "index_symbol": "NDX",
        "eod_index_value": 12345.67,
        "source": "NDX_EIV.csv",
    },
)
def test_get_nq100_eiv_with_date_returns_eod_index_value(_mock_get_eiv):
    app = _make_app()
    client = app.test_client()
    resp = client.get("/api/universe/nq100/eiv?date=2020-06-01")
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["code"] == 1
    assert payload["data"]["eod_index_value"] == 12345.67


@patch("app.routes.universe.sync_nq100_from_csv", return_value={"success": True, "ic_rows_inserted": 10})
def test_post_refresh_calls_sync(mock_sync):
    app = _make_app()
    client = app.test_client()
    resp = client.post("/api/universe/nq100/refresh")
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["code"] == 1
    assert payload["data"]["success"] is True
    mock_sync.assert_called_once()


@patch("app.routes.universe.get_constituents_as_of", return_value=[])
def test_get_nq100_empty_symbols_returns_hint_message(_mock_get):
    app = _make_app()
    client = app.test_client()
    resp = client.get("/api/universe/nq100")
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["code"] == 1
    assert payload["msg"] == "NQ100 成分列表为空，请先运行成分同步"
