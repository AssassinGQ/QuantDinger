"""
Tests for app.services.entry_ai_filter module.
"""
from unittest.mock import patch, MagicMock

from app.services.entry_ai_filter import (
    is_entry_ai_filter_enabled,
    entry_ai_filter_allows,
    extract_ai_trade_decision,
)


class TestEntryAIFilter:
    """Test suite for entry_ai_filter module."""

    def test_is_enabled_true_variants(self):
        """Test is_enabled returns True for different truthy config values."""
        assert is_entry_ai_filter_enabled(
            ai_model_config={"entry_ai_filter_enabled": True}, trading_config={}
        )
        assert is_entry_ai_filter_enabled(
            ai_model_config={"entryAiFilterEnabled": "yes"}, trading_config={}
        )
        assert is_entry_ai_filter_enabled(
            ai_model_config={"ai_filter_enabled": "1"}, trading_config={}
        )
        assert is_entry_ai_filter_enabled(
            ai_model_config={}, trading_config={"enable_ai_filter": "on"}
        )

    def test_is_enabled_false_variants(self):
        """Test is_enabled returns False for different falsy config values."""
        assert not is_entry_ai_filter_enabled(
            ai_model_config={"entry_ai_filter_enabled": False}, trading_config={}
        )
        assert not is_entry_ai_filter_enabled(
            ai_model_config={"entryAiFilterEnabled": "no"}, trading_config={}
        )
        assert not is_entry_ai_filter_enabled(
            ai_model_config={"ai_filter_enabled": "0"}, trading_config={}
        )
        assert not is_entry_ai_filter_enabled(
            ai_model_config={}, trading_config={"enable_ai_filter": "off"}
        )
        assert not is_entry_ai_filter_enabled(ai_model_config={}, trading_config={})
        assert not is_entry_ai_filter_enabled(ai_model_config=None, trading_config=None)

    @patch("app.services.entry_ai_filter.get_fast_analysis_service")
    def test_check_signal_match(self, mock_get_service):
        """Test entry_ai_filter_allows when AI decision matches signal type."""
        mock_service = MagicMock()
        mock_service.analyze.return_value = {
            "decision": "BUY",
            "confidence": 80,
            "summary": "Good",
        }
        mock_get_service.return_value = mock_service

        allowed, info = entry_ai_filter_allows(
            symbol="BTC/USDT",
            signal_type="open_long",
            ai_model_config={},
            trading_config={},
        )
        assert allowed is True
        assert info["reason"] == "match"
        assert info["ai_decision"] == "BUY"
        assert info["confidence"] == 80
        assert info["summary"] == "Good"

    @patch("app.services.entry_ai_filter.get_fast_analysis_service")
    def test_check_signal_hold(self, mock_get_service):
        """Test entry_ai_filter_allows when AI decision is HOLD."""
        mock_service = MagicMock()
        mock_service.analyze.return_value = {"decision": "HOLD"}
        mock_get_service.return_value = mock_service

        allowed, info = entry_ai_filter_allows(
            symbol="BTC/USDT",
            signal_type="open_long",
            ai_model_config={},
            trading_config={},
        )
        assert allowed is False
        assert info["reason"] == "ai_hold"
        assert info["ai_decision"] == "HOLD"

    @patch("app.services.entry_ai_filter.get_fast_analysis_service")
    def test_check_signal_mismatch(self, mock_get_service):
        """Test entry_ai_filter_allows when AI decision mismatches signal type."""
        mock_service = MagicMock()
        mock_service.analyze.return_value = {"decision": "SELL"}
        mock_get_service.return_value = mock_service

        allowed, info = entry_ai_filter_allows(
            symbol="BTC/USDT",
            signal_type="open_long",
            ai_model_config={},
            trading_config={},
        )
        assert allowed is False
        assert info["reason"] == "direction_mismatch"
        assert info["ai_decision"] == "SELL"

    @patch("app.services.entry_ai_filter.get_fast_analysis_service")
    def test_check_signal_analysis_error(self, mock_get_service):
        """Test entry_ai_filter_allows when AI service returns an error."""
        mock_service = MagicMock()
        mock_service.analyze.return_value = {"error": "API down"}
        mock_get_service.return_value = mock_service

        allowed, info = entry_ai_filter_allows(
            symbol="BTC/USDT",
            signal_type="open_long",
            ai_model_config={},
            trading_config={},
        )
        assert allowed is False
        assert info["reason"] == "analysis_error"
        assert info["analysis_error"] == "API down"

    @patch("app.services.entry_ai_filter.get_fast_analysis_service")
    def test_check_signal_missing_decision(self, mock_get_service):
        """Test entry_ai_filter_allows when AI service returns no decision."""
        mock_service = MagicMock()
        mock_service.analyze.return_value = {}
        mock_get_service.return_value = mock_service

        allowed, info = entry_ai_filter_allows(
            symbol="BTC/USDT",
            signal_type="open_long",
            ai_model_config={},
            trading_config={},
        )
        assert allowed is False
        assert info["reason"] == "missing_ai_decision"
        assert info["ai_decision"] == ""

    @patch("app.services.entry_ai_filter.get_fast_analysis_service")
    def test_check_signal_exception(self, mock_get_service):
        """Test entry_ai_filter_allows when AI service raises an exception."""
        mock_get_service.side_effect = ValueError("System Error")

        allowed, info = entry_ai_filter_allows(
            symbol="BTC/USDT",
            signal_type="open_long",
            ai_model_config={},
            trading_config={},
        )
        assert allowed is False
        assert info["reason"] == "analysis_exception"
        assert "System Error" in info["analysis_error"]


class TestExtractAiTradeDecision:
    """extract_ai_trade_decision 解析 AI 输出"""

    def test_empty_input_returns_empty(self):
        """Test empty input handling."""
        assert extract_ai_trade_decision({}) == ""
        assert extract_ai_trade_decision(None) == ""

    def test_extracts_decision_field(self):
        """Test decision extraction from various paths."""
        assert extract_ai_trade_decision({"decision": "BUY"}) == "BUY"
        assert extract_ai_trade_decision({"decision": "SELL"}) == "SELL"
        assert extract_ai_trade_decision({"decision": "HOLD"}) == "HOLD"
        assert extract_ai_trade_decision({"final_decision": {"decision": "BUY"}}) == "BUY"
        assert extract_ai_trade_decision({"trader_decision": {"decision": "SHORT"}}) == "SELL"
        assert extract_ai_trade_decision({"final": {"decision": "WAIT"}}) == "HOLD"
        assert extract_ai_trade_decision({"decision": "LONG"}) == "BUY"
        assert extract_ai_trade_decision({"decision": "unknown_value"}) == ""
