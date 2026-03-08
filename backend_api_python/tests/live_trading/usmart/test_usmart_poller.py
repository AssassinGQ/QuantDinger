import pytest
from unittest.mock import Mock, patch, MagicMock
import threading

from app.services.live_trading.usmart_trading.client import USmartClient
from app.services.live_trading.usmart_trading.poller import OrderStatusPoller


class TestOrderStatusPoller:
    def test_poller_creation(self, config):
        client = USmartClient(config)
        poller = OrderStatusPoller(client, interval=1.0)
        assert poller.client == client
        assert poller.interval == 1.0
        assert poller._running is False

    def test_register_callback(self, config):
        client = USmartClient(config)
        poller = OrderStatusPoller(client)
        callback = Mock()
        poller.register_callback("order_filled", callback)
        assert "order_filled" in poller._callbacks
        assert poller._callbacks["order_filled"] == callback

    def test_poller_creation_with_default_interval(self, config):
        client = USmartClient(config)
        poller = OrderStatusPoller(client)
        assert poller.interval == 5.0

    def test_callback_registration_multiple(self, config):
        client = USmartClient(config)
        poller = OrderStatusPoller(client)
        cb1 = Mock()
        cb2 = Mock()
        poller.register_callback("order_filled", cb1)
        poller.register_callback("order_cancelled", cb2)
        assert poller._callbacks["order_filled"] == cb1
        assert poller._callbacks["order_cancelled"] == cb2

    def test_callback_overwrite(self, config):
        client = USmartClient(config)
        poller = OrderStatusPoller(client)
        cb1 = Mock()
        cb2 = Mock()
        poller.register_callback("order_filled", cb1)
        poller.register_callback("order_filled", cb2)
        assert poller._callbacks["order_filled"] == cb2
