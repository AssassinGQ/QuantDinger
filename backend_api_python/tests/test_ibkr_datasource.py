"""
Tests for IBKRDataSource connection management.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from app.data_sources.ibkr import IBKRDataSource


class TestIBKRDataSourceInstantiation:
    """Test IBKRDataSource instantiation with default config."""

    def test_can_instantiate_with_default_config(self):
        """IBKRDataSource can be instantiated with default config."""
        ds = IBKRDataSource()
        assert ds._host == "ib-live-gateway"
        assert ds._port == 4003
        assert ds._client_id == 1
        assert ds._client is None

    def test_can_instantiate_with_custom_config(self):
        """IBKRDataSource can be instantiated with custom config."""
        ds = IBKRDataSource(host="custom-host", port=4004, client_id=5)
        assert ds._host == "custom-host"
        assert ds._port == 4004
        assert ds._client_id == 5

    def test_can_instantiate_with_env_vars(self):
        """IBKRDataSource can read config from environment variables."""
        with patch.dict("os.environ", {"IBKR_HOST": "env-host", "IBKR_PORT": "4005", "IBKR_CLIENT_ID": "10"}):
            ds = IBKRDataSource()
            assert ds._host == "env-host"
            assert ds._port == 4005
            assert ds._client_id == 10


class TestConnectionState:
    """Test connection state checks."""

    def test_is_connected_returns_false_before_connection(self):
        """is_connected() returns False before connection."""
        ds = IBKRDataSource()
        assert ds.is_connected() is False

    def test_is_connected_returns_true_when_client_connected(self):
        """is_connected() returns True when client is connected."""
        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        ds._client = mock_client
        assert ds.is_connected() is True

    def test_is_connected_returns_false_when_client_disconnected(self):
        """is_connected() returns False when client is disconnected."""
        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = False
        ds._client = mock_client
        assert ds.is_connected() is False


class TestReconnect:
    """Test reconnect behavior."""

    def test_reconnect_calls_client_reconnect(self):
        """reconnect() calls client's reconnect method."""
        ds = IBKRDataSource()
        mock_client = MagicMock()
        mock_client.reconnect.return_value = True
        ds._client = mock_client

        result = ds.reconnect(max_retries=5)

        mock_client.reconnect.assert_called_once_with(max_retries=5)
        assert result is True

    def test_reconnect_when_no_client(self):
        """reconnect() calls connect() when no client exists."""
        ds = IBKRDataSource()
        assert ds._client is None

        with patch.object(ds, "connect", return_value=True) as mock_connect:
            result = ds.reconnect(max_retries=3)
            mock_connect.assert_called_once()


class TestDisconnect:
    """Test disconnect behavior."""

    def test_disconnect_disconnects_client(self):
        """disconnect() calls client's disconnect method."""
        ds = IBKRDataSource()
        mock_client = MagicMock()
        ds._client = mock_client

        ds.disconnect()

        mock_client.disconnect.assert_called_once()
        assert ds._client is None

    def test_disconnect_when_no_client(self):
        """disconnect() does nothing when no client exists."""
        ds = IBKRDataSource()
        assert ds._client is None
        # Should not raise
        ds.disconnect()
