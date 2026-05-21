"""
Test strategy routes for cross-sectional configuration validation.
Covers STRAT-01/STRAT-02: delisting_policy, force_exit_symbols, mutual exclusion.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestConfigValidation:
    """D-04: Mutual exclusion of symbol_list and universe."""

    def test_mutual_exclusion_symbol_list_and_universe(self, strategy_client):
        """D-04: Both symbol_list and universe configured should return HTTP 400."""
        payload = {
            "strategy_name": "Test-Mutual-Exclusion",
            "strategy_type": "CrossSectionalStrategy",
            "trading_config": {
                "symbol_list": ["AAPL"],
                "universe": "NQ100",
            },
        }
        res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 400
        body = res.get_json()
        assert body["code"] == 0
        assert "mutually exclusive" in body["msg"].lower()


class TestDelistingPolicyValidation:
    """D-10/D-11/D-12/D-13: delisting_policy configuration validation."""

    def test_valid_delisting_policy_immediate(self, strategy_client):
        """D-12: Valid immediate mode should be accepted."""
        mock_svc = MagicMock()
        mock_svc.create_strategy.return_value = 1
        with patch("app.routes.strategy.get_strategy_service", return_value=mock_svc):
            payload = {
                "strategy_name": "Test-Immediate",
                "strategy_type": "NQ100Strategy",
                "trading_config": {
                    "delisting_policy": {"mode": "immediate"},
                },
            }
            res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 200
        body = res.get_json()
        assert body["code"] == 1

    def test_valid_delisting_policy_delayed(self, strategy_client):
        """D-13: Valid delayed mode with months should be accepted."""
        mock_svc = MagicMock()
        mock_svc.create_strategy.return_value = 2
        with patch("app.routes.strategy.get_strategy_service", return_value=mock_svc):
            payload = {
                "strategy_name": "Test-Delayed",
                "strategy_type": "NQ100Strategy",
                "trading_config": {
                    "delisting_policy": {"mode": "delayed", "months": 6},
                },
            }
            res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 200
        body = res.get_json()
        assert body["code"] == 1

    def test_valid_delisting_policy_hold_until_signal_exit(self, strategy_client):
        """Hold until signal exit mode should be accepted."""
        mock_svc = MagicMock()
        mock_svc.create_strategy.return_value = 3
        with patch("app.routes.strategy.get_strategy_service", return_value=mock_svc):
            payload = {
                "strategy_name": "Test-Hold",
                "strategy_type": "NQ100Strategy",
                "trading_config": {
                    "delisting_policy": {"mode": "hold_until_signal_exit"},
                },
            }
            res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 200
        body = res.get_json()
        assert body["code"] == 1

    def test_invalid_delisting_policy_mode(self, strategy_client):
        """Invalid mode value should return HTTP 400."""
        payload = {
            "strategy_name": "Test-Invalid-Mode",
            "strategy_type": "NQ100Strategy",
            "trading_config": {
                "delisting_policy": {"mode": "invalid_mode"},
            },
        }
        res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 400
        body = res.get_json()
        assert body["code"] == 0
        assert "invalid delisting_policy.mode" in body["msg"].lower()

    def test_delayed_mode_months_range_validation(self, strategy_client):
        """D-11: months out of range (15) should return HTTP 400."""
        payload = {
            "strategy_name": "Test-Months-Range",
            "strategy_type": "NQ100Strategy",
            "trading_config": {
                "delisting_policy": {"mode": "delayed", "months": 15},
            },
        }
        res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 400
        body = res.get_json()
        assert body["code"] == 0
        assert "must be integer 1-12" in body["msg"].lower()

    def test_delayed_mode_months_negative(self, strategy_client):
        """D-11: months = 0 should return HTTP 400."""
        payload = {
            "strategy_name": "Test-Months-Negative",
            "strategy_type": "NQ100Strategy",
            "trading_config": {
                "delisting_policy": {"mode": "delayed", "months": 0},
            },
        }
        res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 400
        body = res.get_json()
        assert body["code"] == 0
        assert "must be integer 1-12" in body["msg"].lower()

    def test_delayed_mode_missing_months_defaults_to_3(self, strategy_client):
        """D-11: Missing months field should default to 3."""
        mock_svc = MagicMock()
        mock_svc.create_strategy.return_value = 4
        with patch("app.routes.strategy.get_strategy_service", return_value=mock_svc):
            payload = {
                "strategy_name": "Test-Default-Months",
                "strategy_type": "NQ100Strategy",
                "trading_config": {
                    "delisting_policy": {"mode": "delayed"},
                },
            }
            res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 200
        body = res.get_json()
        assert body["code"] == 1
        # Verify the service was called with default months=3
        call_args = mock_svc.create_strategy.call_args[0][0]
        assert call_args["trading_config"]["delisting_policy"]["months"] == 3

    def test_delayed_mode_months_string_type(self, strategy_client):
        """Type validation: months as string should return HTTP 400."""
        payload = {
            "strategy_name": "Test-Months-String",
            "strategy_type": "NQ100Strategy",
            "trading_config": {
                "delisting_policy": {"mode": "delayed", "months": "six"},
            },
        }
        res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 400
        body = res.get_json()
        assert body["code"] == 0
        assert "must be integer" in body["msg"].lower()


class TestForceExitSymbols:
    """D-16: force_exit_symbols validation."""

    def test_force_exit_symbols_valid_list(self, strategy_client):
        """D-16: Valid list should be accepted."""
        mock_svc = MagicMock()
        mock_svc.create_strategy.return_value = 5
        with patch("app.routes.strategy.get_strategy_service", return_value=mock_svc):
            payload = {
                "strategy_name": "Test-Force-Exit",
                "strategy_type": "NQ100Strategy",
                "trading_config": {
                    "force_exit_symbols": ["ENRN", "WCOM"],
                },
            }
            res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 200
        body = res.get_json()
        assert body["code"] == 1

    def test_force_exit_symbols_empty_list(self, strategy_client):
        """Valid empty list should be accepted."""
        mock_svc = MagicMock()
        mock_svc.create_strategy.return_value = 6
        with patch("app.routes.strategy.get_strategy_service", return_value=mock_svc):
            payload = {
                "strategy_name": "Test-Empty-Force-Exit",
                "strategy_type": "NQ100Strategy",
                "trading_config": {
                    "force_exit_symbols": [],
                },
            }
            res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 200
        body = res.get_json()
        assert body["code"] == 1

    def test_force_exit_symbols_invalid_type_string(self, strategy_client):
        """D-16: Non-list (string) should return HTTP 400."""
        payload = {
            "strategy_name": "Test-Force-Exit-String",
            "strategy_type": "NQ100Strategy",
            "trading_config": {
                "force_exit_symbols": "ENRN",
            },
        }
        res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 400
        body = res.get_json()
        assert body["code"] == 0
        assert "must be a list" in body["msg"].lower()

    def test_force_exit_symbols_invalid_type_dict(self, strategy_client):
        """D-16: Dict instead of list should return HTTP 400."""
        payload = {
            "strategy_name": "Test-Force-Exit-Dict",
            "strategy_type": "NQ100Strategy",
            "trading_config": {
                "force_exit_symbols": {"symbol": "ENRN"},
            },
        }
        res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 400
        body = res.get_json()
        assert body["code"] == 0
        assert "must be a list" in body["msg"].lower()

    def test_force_exit_symbols_contains_empty_string(self, strategy_client):
        """D-16: Empty string in list should return HTTP 400."""
        payload = {
            "strategy_name": "Test-Force-Exit-Empty",
            "strategy_type": "NQ100Strategy",
            "trading_config": {
                "force_exit_symbols": ["ENRN", ""],
            },
        }
        res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 400
        body = res.get_json()
        assert body["code"] == 0
        assert "non-empty strings" in body["msg"].lower()

    def test_force_exit_symbols_contains_non_string(self, strategy_client):
        """D-16: Non-string in list should return HTTP 400."""
        payload = {
            "strategy_name": "Test-Force-Exit-Non-String",
            "strategy_type": "NQ100Strategy",
            "trading_config": {
                "force_exit_symbols": ["ENRN", 123],
            },
        }
        res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 400
        body = res.get_json()
        assert body["code"] == 0
        assert "strings only" in body["msg"].lower()

    def test_mag7_fields_reserved_no_validation(self, strategy_client):
        """D-17/D-18: Mag7 fields should be accepted without validation (reserved)."""
        mock_svc = MagicMock()
        mock_svc.create_strategy.return_value = 7
        with patch("app.routes.strategy.get_strategy_service", return_value=mock_svc):
            payload = {
                "strategy_name": "Test-Mag7",
                "strategy_type": "NQ100Strategy",
                "trading_config": {
                    "mag7_min_count": 3,
                    "mag7_max_weight": 0.15,
                },
            }
            res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 200
        body = res.get_json()
        assert body["code"] == 1

    def test_force_exit_symbols_duplicates_accepted(self, strategy_client):
        """Duplicates are accepted (Runner normalizes with set())."""
        mock_svc = MagicMock()
        mock_svc.create_strategy.return_value = 8
        with patch("app.routes.strategy.get_strategy_service", return_value=mock_svc):
            payload = {
                "strategy_name": "Test-Force-Exit-Duplicates",
                "strategy_type": "NQ100Strategy",
                "trading_config": {
                    "force_exit_symbols": ["AAPL", "AAPL"],
                },
            }
            res = strategy_client.post("/api/strategies/create", json=payload)
        assert res.status_code == 200
        body = res.get_json()
        assert body["code"] == 1