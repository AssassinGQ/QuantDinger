"""
Interface contract and lifecycle tests for EFClient.
"""

from app.services.live_trading.ef_trading.client import EFClient
from app.services.live_trading.ef_trading.config import EFConfig
from app.services.live_trading.ef_trading.fsm import OrderEvent, OrderStateMachine


class TestEFClientInterfaceContract:
    """Verify EFClient implements the required BaseStatefulClient contract."""

    def test_ef_client_has_required_interface(self):
        """Test EFClient implements all required BaseStatefulClient methods."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)

        required_methods = [
            "connect",
            "disconnect",
            "place_market_order",
            "place_limit_order",
            "cancel_order",
            "get_positions",
            "get_positions_normalized",
            "get_open_orders",
            "get_account_summary",
            "get_connection_status",
            "is_market_open",
            "get_quote",
        ]

        for method in required_methods:
            assert hasattr(client, method), f"EFClient missing method: {method}"
            assert callable(getattr(client, method)), f"EFClient.{method} is not callable"

    def test_ef_client_supported_markets(self):
        """Test EFClient supports required market categories."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)

        required_markets = {"AShare", "HKStock", "Bond", "ETF"}
        assert required_markets.issubset(client.supported_market_categories)

    def test_ef_client_engine_id(self):
        """Test EFClient has correct engine_id."""
        config = EFConfig(account_id="123", password="456")
        client = EFClient(config)

        assert client.engine_id == "eastmoney"

    def test_ef_client_order_lifecycle(self):
        """Test order lifecycle with state machine integration."""
        fsm = OrderStateMachine("test_order_001")

        assert fsm.state.value == "pending"

        fsm.transition(OrderEvent.SUBMIT)
        assert fsm.state.value == "submitted"

        fsm.transition(OrderEvent.ACCEPT)
        assert fsm.state.value == "accepted"

        fsm.transition(OrderEvent.FILL)
        assert fsm.state.value == "partial"

        fsm.transition(OrderEvent.FULL_FILL)
        assert fsm.state.value == "filled"
        assert fsm.is_terminal is True
