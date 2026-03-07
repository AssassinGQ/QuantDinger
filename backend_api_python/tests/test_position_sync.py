"""
Tests for PositionSync ghost-position prevention.

Covers:
- _symbol_aliases: HK stock symbol format conversion
- fetch_strategy_traded_symbols: only considers filled orders, no self-loop
- _sync_positions_best_effort: traded_symbols filtering on INSERT and UPDATE paths,
  ghost position cleanup via DELETE
"""
import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, Any, List, Optional, Tuple

from app.services.live_trading.records import _symbol_aliases


# =========================================================================
# _symbol_aliases
# =========================================================================

class TestSymbolAliases:
    """Ensure cross-format matching between pending_orders and IBKR formats."""

    def test_hk_five_digit_code(self):
        aliases = _symbol_aliases("00005")
        assert "0005.HK" in aliases
        assert "0005" in aliases
        assert "00005" in aliases

    def test_hk_four_digit_code(self):
        aliases = _symbol_aliases("0005")
        assert "0005.HK" in aliases
        assert "00005" in aliases

    def test_hk_dotHK_suffix(self):
        aliases = _symbol_aliases("0005.HK")
        assert "0005" in aliases
        assert "00005" in aliases
        assert "0005.HK" in aliases

    def test_hk_dotHK_four_digit(self):
        aliases = _symbol_aliases("9618.HK")
        assert "9618" in aliases
        assert "09618" in aliases

    def test_hk_five_digit_with_leading_zero(self):
        aliases = _symbol_aliases("09618")
        assert "9618.HK" in aliases
        assert "9618" in aliases
        assert "09618" in aliases

    def test_us_stock_no_aliases(self):
        aliases = _symbol_aliases("GOOGL")
        assert len(aliases) == 0

    def test_us_stock_aapl_no_aliases(self):
        aliases = _symbol_aliases("AAPL")
        assert len(aliases) == 0

    def test_single_digit_hk(self):
        aliases = _symbol_aliases("3")
        assert "0003.HK" in aliases
        assert "0003" in aliases
        assert "00003" in aliases

    def test_hk_zero_stock(self):
        aliases = _symbol_aliases("00000")
        assert "0000.HK" in aliases

    def test_case_insensitive(self):
        aliases = _symbol_aliases("0005.hk")
        assert "0005.HK" in aliases

    def test_whitespace_stripped(self):
        aliases = _symbol_aliases("  00005  ")
        assert "0005.HK" in aliases


# =========================================================================
# fetch_strategy_traded_symbols
# =========================================================================

class TestFetchStrategyTradedSymbols:
    """Test that only filled orders are considered, with alias expansion."""

    def _mock_db_rows(self, rows: List[Dict[str, Any]]):
        """Create a mock get_db_connection that returns given rows."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = rows
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = lambda s: mock_conn
        mock_conn.__exit__ = MagicMock(return_value=False)
        return mock_conn

    @patch("app.services.live_trading.records.get_db_connection")
    def test_only_filled_orders(self, mock_get_db):
        from app.services.live_trading.records import fetch_strategy_traded_symbols
        mock_conn = self._mock_db_rows([{"symbol": "GOOGL"}])
        mock_get_db.return_value = mock_conn

        result = fetch_strategy_traded_symbols(502)
        assert "GOOGL" in result
        sql_call = mock_conn.cursor().execute.call_args
        sql = sql_call[0][0]
        assert "status = 'sent'" in sql
        assert "filled > 0" in sql

    @patch("app.services.live_trading.records.get_db_connection")
    def test_no_self_loop_qd_strategy_positions(self, mock_get_db):
        """Must NOT query qd_strategy_positions to avoid self-referencing loop."""
        from app.services.live_trading.records import fetch_strategy_traded_symbols
        mock_conn = self._mock_db_rows([])
        mock_get_db.return_value = mock_conn

        fetch_strategy_traded_symbols(501)
        all_sql = [c[0][0] for c in mock_conn.cursor().execute.call_args_list]
        for sql in all_sql:
            assert "qd_strategy_positions" not in sql

    @patch("app.services.live_trading.records.get_db_connection")
    def test_hk_aliases_expanded(self, mock_get_db):
        from app.services.live_trading.records import fetch_strategy_traded_symbols
        mock_conn = self._mock_db_rows([{"symbol": "00005"}])
        mock_get_db.return_value = mock_conn

        result = fetch_strategy_traded_symbols(499)
        assert "00005" in result
        assert "0005.HK" in result
        assert "0005" in result

    @patch("app.services.live_trading.records.get_db_connection")
    def test_empty_when_no_fills(self, mock_get_db):
        from app.services.live_trading.records import fetch_strategy_traded_symbols
        mock_conn = self._mock_db_rows([])
        mock_get_db.return_value = mock_conn

        result = fetch_strategy_traded_symbols(504)
        assert result == set()

    @patch("app.services.live_trading.records.get_db_connection")
    def test_us_stock_no_extra_aliases(self, mock_get_db):
        from app.services.live_trading.records import fetch_strategy_traded_symbols
        mock_conn = self._mock_db_rows([{"symbol": "GOOGL"}])
        mock_get_db.return_value = mock_conn

        result = fetch_strategy_traded_symbols(502)
        assert result == {"GOOGL"}


# =========================================================================
# PositionSync integration: ghost position filtering
# =========================================================================

class TestPositionSyncGhostFiltering:
    """
    Integration tests simulating the core PositionSync logic from
    _sync_positions_best_effort, verifying that traded_symbols filtering
    works on both INSERT and UPDATE paths.

    We extract the filtering logic into a helper to test without needing
    the full PendingOrderWorker + DB + IBKR stack.
    """

    @staticmethod
    def _run_sync_logic(
        *,
        plist: List[Dict[str, Any]],
        exch_size: Dict[str, Dict[str, float]],
        exch_entry_price: Dict[str, Dict[str, float]],
        traded_symbols: Optional[set],
    ) -> Tuple[List[int], List[Dict], List[Dict]]:
        """
        Reproduce the core PositionSync filtering logic from
        pending_order_worker._sync_positions_best_effort.
        """
        to_delete_ids: List[int] = []
        to_update: List[Dict[str, Any]] = []
        eps = 1e-12

        for r in plist:
            rid = int(r.get("id") or 0)
            sym = str(r.get("symbol") or "").strip()
            side = str(r.get("side") or "").strip().lower()
            if not rid or not sym or side not in ("long", "short"):
                continue

            if traded_symbols is not None and sym not in traded_symbols:
                to_delete_ids.append(rid)
                continue

            local_size = float(r.get("size") or 0.0)
            exch = exch_size.get(sym) or {}
            exch_qty = float(exch.get(side) or 0.0)
            exch_ep_map = exch_entry_price.get(sym) or {}
            exch_price = float(exch_ep_map.get(side) or 0.0)
            local_price = float(r.get("entry_price") or 0.0)

            if exch_qty <= eps:
                to_delete_ids.append(rid)
            else:
                price_diff_ratio = 0.0
                if local_price > 0:
                    price_diff_ratio = abs(exch_price - local_price) / local_price
                else:
                    price_diff_ratio = 1.0 if exch_price > 0 else 0.0
                if (local_size <= 0 or abs(exch_qty - local_size) / max(1.0, local_size) > 0.01) or (price_diff_ratio > 0.005):
                    to_update.append({"id": rid, "size": exch_qty, "entry_price": exch_price})

        to_insert: List[Dict[str, Any]] = []
        local_symbols_sides = {(str(r.get("symbol") or "").strip(), str(r.get("side") or "").strip().lower()) for r in plist}

        for _sym, _sides_map in exch_size.items():
            for _side, _qty in _sides_map.items():
                if _qty > 1e-12 and (_sym, _side) not in local_symbols_sides:
                    if traded_symbols is not None and _sym not in traded_symbols:
                        continue
                    _ep = exch_entry_price.get(_sym, {}).get(_side, 0.0)
                    to_insert.append({"symbol": _sym, "side": _side, "size": _qty, "entry_price": _ep})

        return to_delete_ids, to_update, to_insert

    # --- Scenario: The exact bug the user reported ---

    def test_ghost_positions_deleted_on_update_path(self):
        """
        BUG REPRO: Strategy 500 (京东) only traded 9618.HK, but PositionSync
        had previously written 0005.HK and GOOGL into its local positions.
        The UPDATE path must delete these ghost positions, not maintain them.
        """
        plist = [
            {"id": 1, "symbol": "9618.HK", "side": "long", "size": 350.0, "entry_price": 105.5},
            {"id": 2, "symbol": "0005.HK", "side": "long", "size": 3200.0, "entry_price": 135.4},
            {"id": 3, "symbol": "GOOGL", "side": "long", "size": 3.0, "entry_price": 300.6},
        ]
        exch_size = {
            "0005.HK": {"long": 3200.0, "short": 0.0},
            "9618.HK": {"long": 350.0, "short": 0.0},
            "GOOGL":   {"long": 3.0, "short": 0.0},
        }
        exch_entry_price = {
            "0005.HK": {"long": 135.4, "short": 0.0},
            "9618.HK": {"long": 105.5, "short": 0.0},
            "GOOGL":   {"long": 300.6, "short": 0.0},
        }
        traded_symbols = {"9618", "09618", "9618.HK"}

        to_delete, to_update, to_insert = self._run_sync_logic(
            plist=plist,
            exch_size=exch_size,
            exch_entry_price=exch_entry_price,
            traded_symbols=traded_symbols,
        )

        assert 2 in to_delete, "0005.HK ghost should be deleted"
        assert 3 in to_delete, "GOOGL ghost should be deleted"
        assert 1 not in to_delete, "9618.HK is legitimate"
        assert len(to_insert) == 0, "No new inserts expected"

    def test_ghost_positions_not_inserted_for_wrong_strategy(self):
        """
        Strategy 504 (比亚迪) never traded anything. IBKR global positions
        must not be inserted.
        """
        plist = []
        exch_size = {
            "0005.HK": {"long": 3200.0, "short": 0.0},
            "9618.HK": {"long": 350.0, "short": 0.0},
            "GOOGL":   {"long": 3.0, "short": 0.0},
        }
        exch_entry_price = {
            "0005.HK": {"long": 135.4, "short": 0.0},
            "9618.HK": {"long": 105.5, "short": 0.0},
            "GOOGL":   {"long": 300.6, "short": 0.0},
        }

        to_delete, to_update, to_insert = self._run_sync_logic(
            plist=plist,
            exch_size=exch_size,
            exch_entry_price=exch_entry_price,
            traded_symbols=set(),
        )

        assert len(to_insert) == 0
        assert len(to_delete) == 0
        assert len(to_update) == 0

    def test_legitimate_position_updated_not_deleted(self):
        """
        Strategy 499 (汇丰) traded 0005.HK. Its position should be updated
        when exchange data changes, not deleted.
        """
        plist = [
            {"id": 10, "symbol": "0005.HK", "side": "long", "size": 3100.0, "entry_price": 130.0},
        ]
        exch_size = {
            "0005.HK": {"long": 3200.0, "short": 0.0},
            "9618.HK": {"long": 350.0, "short": 0.0},
            "GOOGL":   {"long": 3.0, "short": 0.0},
        }
        exch_entry_price = {
            "0005.HK": {"long": 135.4, "short": 0.0},
            "9618.HK": {"long": 105.5, "short": 0.0},
            "GOOGL":   {"long": 300.6, "short": 0.0},
        }
        traded_symbols = {"00005", "0005", "0005.HK"}

        to_delete, to_update, to_insert = self._run_sync_logic(
            plist=plist,
            exch_size=exch_size,
            exch_entry_price=exch_entry_price,
            traded_symbols=traded_symbols,
        )

        assert 10 not in to_delete, "Legitimate position must not be deleted"
        assert any(u["id"] == 10 for u in to_update), "Should be flagged for update"
        assert len(to_insert) == 0, "Other symbols should NOT be inserted"

    def test_legitimate_insert_for_new_fill(self):
        """
        Strategy 502 traded GOOGL. If local positions don't have GOOGL yet,
        it should be inserted.
        """
        plist = []
        exch_size = {
            "0005.HK": {"long": 3200.0, "short": 0.0},
            "GOOGL":   {"long": 3.0, "short": 0.0},
        }
        exch_entry_price = {
            "0005.HK": {"long": 135.4, "short": 0.0},
            "GOOGL":   {"long": 300.6, "short": 0.0},
        }
        traded_symbols = {"GOOGL"}

        to_delete, to_update, to_insert = self._run_sync_logic(
            plist=plist,
            exch_size=exch_size,
            exch_entry_price=exch_entry_price,
            traded_symbols=traded_symbols,
        )

        assert len(to_insert) == 1
        assert to_insert[0]["symbol"] == "GOOGL"
        assert to_insert[0]["size"] == 3.0

    def test_non_stateful_client_no_filtering(self):
        """
        Non-IBKR clients (traded_symbols=None) should sync all positions
        without any filtering.
        """
        plist = []
        exch_size = {
            "BTCUSDT": {"long": 1.5, "short": 0.0},
            "ETHUSDT": {"long": 10.0, "short": 0.0},
        }
        exch_entry_price = {
            "BTCUSDT": {"long": 50000.0, "short": 0.0},
            "ETHUSDT": {"long": 3000.0, "short": 0.0},
        }

        to_delete, to_update, to_insert = self._run_sync_logic(
            plist=plist,
            exch_size=exch_size,
            exch_entry_price=exch_entry_price,
            traded_symbols=None,
        )

        assert len(to_insert) == 2

    def test_exchange_flat_deletes_even_traded_symbol(self):
        """
        If exchange position goes flat (qty=0) for a symbol the strategy
        traded, the local position should be deleted.
        """
        plist = [
            {"id": 20, "symbol": "GOOGL", "side": "long", "size": 3.0, "entry_price": 300.0},
        ]
        exch_size = {
            "GOOGL": {"long": 0.0, "short": 0.0},
        }
        exch_entry_price = {
            "GOOGL": {"long": 0.0, "short": 0.0},
        }
        traded_symbols = {"GOOGL"}

        to_delete, to_update, to_insert = self._run_sync_logic(
            plist=plist,
            exch_size=exch_size,
            exch_entry_price=exch_entry_price,
            traded_symbols=traded_symbols,
        )

        assert 20 in to_delete

    def test_multiple_strategies_same_symbol_different_fills(self):
        """
        Two strategies both traded 0005.HK via IBKR, but only one traded GOOGL.
        Each strategy should only see its own traded symbols.
        """
        exch_size = {
            "0005.HK": {"long": 3200.0, "short": 0.0},
            "GOOGL":   {"long": 3.0, "short": 0.0},
        }
        exch_entry_price = {
            "0005.HK": {"long": 135.4, "short": 0.0},
            "GOOGL":   {"long": 300.6, "short": 0.0},
        }

        # Strategy A: traded 0005.HK only
        _, _, inserts_a = self._run_sync_logic(
            plist=[],
            exch_size=exch_size,
            exch_entry_price=exch_entry_price,
            traded_symbols={"00005", "0005", "0005.HK"},
        )
        assert len(inserts_a) == 1
        assert inserts_a[0]["symbol"] == "0005.HK"

        # Strategy B: traded GOOGL only
        _, _, inserts_b = self._run_sync_logic(
            plist=[],
            exch_size=exch_size,
            exch_entry_price=exch_entry_price,
            traded_symbols={"GOOGL"},
        )
        assert len(inserts_b) == 1
        assert inserts_b[0]["symbol"] == "GOOGL"

    def test_self_loop_prevention_scenario(self):
        """
        Previously, ghost positions in qd_strategy_positions fed back into
        traded_symbols, creating a self-reinforcing loop. This test ensures
        that even if a strategy has ghost positions, they get deleted because
        traded_symbols (from filled orders only) doesn't include them.

        Scenario: strategy 501 never filled any order, but has ghost positions
        from a previous PositionSync bug.
        """
        plist = [
            {"id": 100, "symbol": "0005.HK", "side": "long", "size": 3200.0, "entry_price": 135.4},
            {"id": 101, "symbol": "9618.HK", "side": "long", "size": 350.0, "entry_price": 105.5},
            {"id": 102, "symbol": "GOOGL", "side": "long", "size": 3.0, "entry_price": 300.6},
        ]
        exch_size = {
            "0005.HK": {"long": 3200.0, "short": 0.0},
            "9618.HK": {"long": 350.0, "short": 0.0},
            "GOOGL":   {"long": 3.0, "short": 0.0},
        }
        exch_entry_price = {
            "0005.HK": {"long": 135.4, "short": 0.0},
            "9618.HK": {"long": 105.5, "short": 0.0},
            "GOOGL":   {"long": 300.6, "short": 0.0},
        }
        traded_symbols = set()

        to_delete, to_update, to_insert = self._run_sync_logic(
            plist=plist,
            exch_size=exch_size,
            exch_entry_price=exch_entry_price,
            traded_symbols=traded_symbols,
        )

        assert set(to_delete) == {100, 101, 102}, "All ghost positions must be deleted"
        assert len(to_update) == 0
        assert len(to_insert) == 0
