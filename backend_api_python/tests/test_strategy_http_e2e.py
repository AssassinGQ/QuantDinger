"""TEST-02: Flask test_client HTTP integration for strategy create/update/delete/batch-create.

Mocks ``get_strategy_service`` only — no PostgreSQL. Covers Vue wizard API contract.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

_FOREX_IBKR_PAYLOAD = {
    "strategy_name": "HTTP-E2E-Forex-IBKR",
    "market_category": "Forex",
    "exchange_config": {"exchange_id": "ibkr-paper"},
    "indicator_config": {},
    "trading_config": {"symbol": "EURUSD", "market_type": "forex"},
    "notification_config": {},
}


def _mock_strategy_service() -> MagicMock:
    svc = MagicMock()
    svc.create_strategy.return_value = 501
    svc.update_strategy.return_value = True
    svc.delete_strategy.return_value = True
    svc.batch_create_strategies.return_value = {
        "success": True,
        "total_created": 2,
        "success_ids": [1, 2],
    }
    return svc


def test_test02_post_strategies_create_forex_ibkr_returns_code_1(strategy_client):
    """POST /api/strategies/create — Forex + IBKR; service returns id 501."""
    mock_svc = _mock_strategy_service()
    with patch("app.routes.strategy.get_strategy_service", return_value=mock_svc):
        res = strategy_client.post("/api/strategies/create", json=_FOREX_IBKR_PAYLOAD)
    assert res.status_code == 200
    body = res.get_json()
    assert body["code"] == 1
    assert body["data"]["id"] == 501
    mock_svc.create_strategy.assert_called_once()


def test_test02_put_strategies_update_returns_code_1(strategy_client):
    """PUT /api/strategies/update?id=12 — mocked update returns success."""
    mock_svc = _mock_strategy_service()
    with patch("app.routes.strategy.get_strategy_service", return_value=mock_svc):
        res = strategy_client.put(
            "/api/strategies/update?id=12",
            json={"strategy_name": "x"},
        )
    assert res.status_code == 200
    body = res.get_json()
    assert body["code"] == 1
    mock_svc.update_strategy.assert_called_once()


def test_test02_delete_strategies_returns_code_1(strategy_client):
    """DELETE /api/strategies/delete?id=12 — mocked delete returns success."""
    mock_svc = _mock_strategy_service()
    with patch("app.routes.strategy.get_strategy_service", return_value=mock_svc):
        res = strategy_client.delete("/api/strategies/delete?id=12")
    assert res.status_code == 200
    body = res.get_json()
    assert body["code"] == 1
    mock_svc.delete_strategy.assert_called_once()


def test_test02_batch_create_multi_symbol_returns_code_1(strategy_client):
    """POST /api/strategies/batch-create — two Forex symbols; batch result surfaced."""
    mock_svc = _mock_strategy_service()
    payload = {
        "strategy_name": "HTTP-E2E-Batch",
        "symbols": ["Forex:EURUSD", "Forex:GBPUSD"],
        "market_category": "Forex",
        "exchange_config": {"exchange_id": "ibkr-paper"},
        "indicator_config": {},
        "trading_config": {"market_type": "forex"},
        "notification_config": {},
    }
    with patch("app.routes.strategy.get_strategy_service", return_value=mock_svc):
        res = strategy_client.post("/api/strategies/batch-create", json=payload)
    assert res.status_code == 200
    body = res.get_json()
    assert body["code"] == 1
    assert body["data"]["total_created"] >= 2
    assert "2" in body["msg"] or body["data"]["total_created"] >= 2
    mock_svc.batch_create_strategies.assert_called_once()
