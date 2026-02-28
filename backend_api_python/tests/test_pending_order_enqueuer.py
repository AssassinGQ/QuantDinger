import time
from unittest.mock import MagicMock, patch
import pytest

from app.services.pending_order_enqueuer import PendingOrderEnqueuer


@pytest.fixture
def mock_dh():
    return MagicMock()


@pytest.fixture
def enqueuer(mock_dh):
    enq = PendingOrderEnqueuer()
    enq.data_handler = mock_dh
    return enq


class TestPendingOrderEnqueuer:
    @patch("app.services.pending_order_enqueuer.get_price_fetcher")
    def test_execute_exchange_order_creates_pending_order(self, mock_get_pf, enqueuer):
        # Setup mock price fetcher
        mock_pf = MagicMock()
        mock_pf.fetch_current_price.return_value = 100.0
        mock_get_pf.return_value = mock_pf
        enqueuer._price_fetcher = mock_pf

        enqueuer.data_handler.find_recent_pending_order.return_value = None
        enqueuer.data_handler.get_user_id.return_value = 1
        enqueuer.data_handler.insert_pending_order.return_value = 123

        result = enqueuer.execute_exchange_order(
            exchange=None,
            strategy_id=1,
            symbol="BTC/USDT",
            signal_type="open_long",
            amount=0.5,
            ref_price=None,  # Will trigger price fetch
            market_type="swap",
            market_category="Crypto",
            leverage=2.0,
            margin_mode="cross",
            execution_mode="signal",
            notification_config={"enabled": True},
            signal_ts=int(time.time()),
        )

        assert result["success"] is True
        mock_pf.fetch_current_price.assert_called_once()
        enqueuer.data_handler.insert_pending_order.assert_called_once()
        
        insert_kwargs = enqueuer.data_handler.insert_pending_order.call_args[1]
        assert insert_kwargs["symbol"] == "BTC/USDT"
        assert insert_kwargs["order_type"] == "market"
        assert insert_kwargs["signal_type"] == "open_long"

    def test_execute_exchange_order_prevents_duplicate(self, enqueuer):
        # Mock recent pending order found
        enqueuer.data_handler.find_recent_pending_order.return_value = {
            "id": 456,
            "status": "pending"
        }
        
        result = enqueuer.execute_exchange_order(
            exchange=None,
            strategy_id=1,
            symbol="BTC/USDT",
            signal_type="open_long",
            amount=0.5,
            ref_price=100.0,
            market_type="swap",
            market_category="Crypto",
            leverage=2.0,
            margin_mode="cross",
            execution_mode="signal",
            notification_config={},
            signal_ts=int(time.time()),
        )

        # Should return early with success: True (simulating successful skip)
        assert result["success"] is True
        enqueuer.data_handler.insert_pending_order.assert_not_called()
