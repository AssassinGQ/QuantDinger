"""Isolated unit tests for IBKRClient._align_qty_to_contract (EXEC-04 alignment semantics)."""
import asyncio
import math
import types
from unittest.mock import AsyncMock, MagicMock

from app.services.live_trading.ibkr_trading.client import IBKRClient


class TestAlignQtyToContract:
    """UC-A1–UC-A5: _align_qty_to_contract with mocked reqContractDetailsAsync."""

    def test_uc_a1_exact_multiple_of_increment(self):
        """UC-A1: sizeIncrement 25000, qty 50000 → 50000."""
        IBKRClient._lot_size_cache.clear()
        client = IBKRClient.__new__(IBKRClient)
        client._ib = MagicMock()
        contract = types.SimpleNamespace(conId=424242)
        client._ib.reqContractDetailsAsync = AsyncMock(
            return_value=[types.SimpleNamespace(sizeIncrement=25000, minSize=1)]
        )
        aligned = asyncio.run(client._align_qty_to_contract(contract, 50000, "EURUSD"))
        assert aligned == 50000.0
        assert math.floor(50000 / 25000) * 25000 == 50000

    def test_uc_a2_floors_to_increment(self):
        """UC-A2: sizeIncrement 25000, qty 30000 → 25000."""
        IBKRClient._lot_size_cache.clear()
        client = IBKRClient.__new__(IBKRClient)
        client._ib = MagicMock()
        contract = types.SimpleNamespace(conId=424242)
        client._ib.reqContractDetailsAsync = AsyncMock(
            return_value=[types.SimpleNamespace(sizeIncrement=25000, minSize=1)]
        )
        aligned = asyncio.run(client._align_qty_to_contract(contract, 30000, "EURUSD"))
        assert aligned == 25000.0

    def test_uc_a3_unit_increment(self):
        """UC-A3: sizeIncrement 1, qty 20000 → 20000."""
        IBKRClient._lot_size_cache.clear()
        client = IBKRClient.__new__(IBKRClient)
        client._ib = MagicMock()
        contract = types.SimpleNamespace(conId=424242)
        client._ib.reqContractDetailsAsync = AsyncMock(
            return_value=[types.SimpleNamespace(sizeIncrement=1, minSize=1)]
        )
        aligned = asyncio.run(client._align_qty_to_contract(contract, 20000, "EURUSD"))
        assert aligned == 20000.0

    def test_uc_a4_req_details_failure_returns_original_qty(self):
        """UC-A4: reqContractDetailsAsync raises → passthrough quantity."""
        IBKRClient._lot_size_cache.clear()
        client = IBKRClient.__new__(IBKRClient)
        client._ib = MagicMock()
        contract = types.SimpleNamespace(conId=424242)
        client._ib.reqContractDetailsAsync = AsyncMock(side_effect=RuntimeError("boom"))
        aligned = asyncio.run(client._align_qty_to_contract(contract, 20000, "EURUSD"))
        assert aligned == 20000.0
        assert client._ib.reqContractDetailsAsync.call_count == 1

    def test_uc_a5_second_call_uses_lot_size_cache(self):
        """UC-A5: same conId → single async fetch; two aligns both floor to 0."""
        IBKRClient._lot_size_cache.clear()
        client = IBKRClient.__new__(IBKRClient)
        client._ib = MagicMock()
        contract = types.SimpleNamespace(conId=424242)
        mock_details = AsyncMock(
            return_value=[types.SimpleNamespace(sizeIncrement=25000, minSize=1)]
        )
        client._ib.reqContractDetailsAsync = mock_details

        async def run_both():
            r1 = await client._align_qty_to_contract(contract, 10000, "EURUSD")
            r2 = await client._align_qty_to_contract(contract, 15000, "EURUSD")
            return r1, r2

        r1, r2 = asyncio.run(run_both())
        assert r1 == 0.0
        assert r2 == 0.0
        assert mock_details.call_count == 1
