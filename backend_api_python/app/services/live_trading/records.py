"""
DB helpers for live trading: pending-order lifecycle, trade recording,
and local position snapshots.

Important:
- This is a local DB snapshot, not the source of truth (exchange is).
- We keep it best-effort to support UI display and strategy state.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ── pending_orders lifecycle ─────────────────────────────────────────


def fetch_pending_orders(*, limit: int = 50, stale_processing_sec: int = 0) -> List[Dict[str, Any]]:
    try:
        if stale_processing_sec > 0:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(
                    """
                    UPDATE pending_orders
                    SET status = 'pending',
                        updated_at = NOW(),
                        dispatch_note = CASE
                            WHEN dispatch_note IS NULL OR dispatch_note = '' THEN 'requeued_stale_processing'
                            ELSE dispatch_note
                        END
                    WHERE status = 'processing'
                      AND (updated_at IS NULL OR updated_at < NOW() - INTERVAL '%s seconds')
                      AND (attempts < max_attempts)
                    """,
                    (stale_processing_sec,),
                )
                db.commit()
                cur.close()

        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """
                SELECT *
                FROM pending_orders
                WHERE status = 'pending'
                  AND (attempts < max_attempts)
                ORDER BY priority DESC, id ASC
                LIMIT %s
                """,
                (int(limit),),
            )
            rows = cur.fetchall() or []
            cur.close()
        return rows
    except Exception as e:
        logger.warning(f"fetch_pending_orders failed: {e}")
        return []


def mark_order_processing(order_id: int) -> bool:
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """
                UPDATE pending_orders
                SET status = 'processing',
                    attempts = COALESCE(attempts, 0) + 1,
                    processed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s AND status = 'pending'
                """,
                (int(order_id),),
            )
            claimed = getattr(cur, "rowcount", None)
            db.commit()
            cur.close()
        if claimed is None:
            return True
        return int(claimed) > 0
    except Exception as e:
        logger.warning(f"mark_order_processing failed: id={order_id}, err={e}")
        return False


def mark_order_sent(
    order_id: int,
    note: str = "",
    exchange_id: str = "",
    exchange_order_id: str = "",
    exchange_response_json: str = "",
    filled: float = 0.0,
    avg_price: float = 0.0,
    executed_at: Optional[int] = None,
) -> None:
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            UPDATE pending_orders
            SET status = 'sent',
                last_error = %s,
                dispatch_note = %s,
                sent_at = NOW(),
                executed_at = CASE WHEN %s THEN NOW() ELSE NULL END,
                exchange_id = %s,
                exchange_order_id = %s,
                exchange_response_json = %s,
                filled = %s,
                avg_price = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                "",
                str(note or ""),
                executed_at is not None,
                str(exchange_id or ""),
                str(exchange_order_id or ""),
                str(exchange_response_json or ""),
                float(filled or 0.0),
                float(avg_price or 0.0),
                int(order_id),
            ),
        )
        db.commit()
        cur.close()


def mark_order_failed(
    order_id: int,
    error: str,
    *,
    strategy_id: int = 0,
    symbol: str = "",
    signal_type: str = "",
    signal_ts: int = 0,
) -> None:
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            UPDATE pending_orders
            SET status = 'failed',
                last_error = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (str(error or "failed"), int(order_id)),
        )
        db.commit()
        cur.close()
    if strategy_id and signal_ts and symbol and signal_type:
        try:
            from app.services.signal_deduplicator import get_signal_deduplicator as _get_dedup1
            _get_dedup1().remove_key(int(strategy_id), str(symbol), str(signal_type), int(signal_ts))
        except Exception:
            pass
        try:
            from app.services.signal_processor import get_signal_deduplicator as _get_dedup2
            _get_dedup2().remove_key(int(strategy_id), str(symbol), str(signal_type), int(signal_ts))
        except Exception:
            pass


# ── strategy metadata lookups ────────────────────────────────────────


def load_notification_config(strategy_id: int) -> Dict[str, Any]:
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                "SELECT notification_config FROM qd_strategies_trading WHERE id = %s",
                (int(strategy_id),),
            )
            row = cur.fetchone() or {}
            cur.close()
        s = row.get("notification_config") or ""
        if isinstance(s, dict):
            return s
        if isinstance(s, str) and s.strip():
            try:
                obj = json.loads(s)
                return obj if isinstance(obj, dict) else {}
            except Exception:
                return {}
        return {}
    except Exception:
        return {}


def load_strategy_name(strategy_id: int) -> str:
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute("SELECT strategy_name FROM qd_strategies_trading WHERE id = %s", (int(strategy_id),))
            row = cur.fetchone() or {}
            cur.close()
        return str(row.get("strategy_name") or "").strip()
    except Exception:
        return ""


def load_position_opened_at(strategy_id: int, symbol: str, signal_type: str) -> str:
    side = "long" if "long" in signal_type else ("short" if "short" in signal_type else "")
    if not side:
        return ""
    open_types = ("open_long", "add_long") if side == "long" else ("open_short", "add_short")
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """SELECT MIN(created_at) AS opened_at FROM qd_strategy_trades
                   WHERE strategy_id = %s AND symbol = %s AND type IN (%s, %s)
                """,
                (int(strategy_id), str(symbol), open_types[0], open_types[1]),
            )
            row = cur.fetchone() or {}
            cur.close()
        opened = row.get("opened_at")
        if opened is None:
            return ""
        if hasattr(opened, "strftime"):
            return opened.strftime("%Y-%m-%d %H:%M")
        return str(opened)[:16]
    except Exception:
        return ""


# ── position sync helpers ────────────────────────────────────────────


def fetch_local_positions(target_strategy_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_db_connection() as db:
        cur = db.cursor()
        if target_strategy_id:
            cur.execute(
                "SELECT id, strategy_id, symbol, side, size, entry_price FROM qd_strategy_positions WHERE strategy_id = %s ORDER BY updated_at DESC",
                (int(target_strategy_id),)
            )
        else:
            cur.execute("SELECT id, strategy_id, symbol, side, size, entry_price FROM qd_strategy_positions ORDER BY updated_at DESC")
        rows = cur.fetchall() or []
        cur.close()
    return rows


def fetch_strategy_traded_symbols(strategy_id: int) -> set:
    """Return the set of symbols that a strategy has actually traded (pending_orders + local positions)."""
    symbols: set = set()
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                "SELECT DISTINCT symbol FROM qd_pending_orders WHERE strategy_id = %s AND symbol IS NOT NULL",
                (strategy_id,)
            )
            for row in (cur.fetchall() or []):
                s = str(row.get("symbol") or "").strip()
                if s:
                    symbols.add(s)
            cur.execute(
                "SELECT DISTINCT symbol FROM qd_strategy_positions WHERE strategy_id = %s AND symbol IS NOT NULL",
                (strategy_id,)
            )
            for row in (cur.fetchall() or []):
                s = str(row.get("symbol") or "").strip()
                if s:
                    symbols.add(s)
            cur.close()
    except Exception as e:
        logger.error("fetch_strategy_traded_symbols failed for strategy %s: %s", strategy_id, e)
    return symbols


def fetch_active_live_strategy_ids() -> List[int]:
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute("SELECT id FROM qd_strategies_trading WHERE status = 'running' AND execution_mode = 'live'")
            active_rows = cur.fetchall() or []
            cur.close()
        return [int(r.get("id") or 0) for r in active_rows if int(r.get("id") or 0) > 0]
    except Exception as e:
        logger.error(f"Failed to load active strategies for sync: {e}", exc_info=True)
        return []


def reconcile_positions(
    *,
    to_delete_ids: List[int],
    to_update: List[Dict[str, Any]],
    to_insert: List[Dict[str, Any]],
) -> None:
    if not to_delete_ids and not to_update and not to_insert:
        return
    with get_db_connection() as db:
        cur = db.cursor()
        for rid in to_delete_ids:
            cur.execute("DELETE FROM qd_strategy_positions WHERE id = %s", (int(rid),))
        for u in to_update:
            cur.execute(
                "UPDATE qd_strategy_positions SET size = %s, entry_price = %s, updated_at = NOW() WHERE id = %s",
                (float(u["size"]), float(u["entry_price"]), int(u["id"]))
            )
        for ins in to_insert:
            ins_user_id = 1
            try:
                cur.execute("SELECT user_id FROM qd_strategies_trading WHERE id = %s", (int(ins["strategy_id"]),))
                strategy_row = cur.fetchone()
                if strategy_row and strategy_row.get("user_id"):
                    ins_user_id = int(strategy_row["user_id"])
            except Exception:
                pass
            cur.execute(
                """INSERT INTO qd_strategy_positions (user_id, strategy_id, symbol, side, size, entry_price, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, NOW())""",
                (ins_user_id, int(ins["strategy_id"]), str(ins["symbol"]), str(ins["side"]), float(ins["size"]), float(ins["entry_price"]))
            )
        db.commit()
        cur.close()


# ── trade & position recording ───────────────────────────────────────


def _get_user_id_from_strategy(strategy_id: int) -> int:
    """Get user_id from strategy table. Defaults to 1 if not found."""
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute("SELECT user_id FROM qd_strategies_trading WHERE id = %s", (strategy_id,))
            row = cur.fetchone()
            cur.close()
        return int((row or {}).get('user_id') or 1)
    except Exception:
        return 1


def record_trade(
    *,
    strategy_id: int,
    symbol: str,
    trade_type: str,
    price: float,
    amount: float,
    commission: float = 0.0,
    commission_ccy: str = "",
    profit: Optional[float] = None,
    user_id: int = None,
) -> None:
    value = float(amount or 0.0) * float(price or 0.0)
    if user_id is None:
        user_id = _get_user_id_from_strategy(strategy_id)
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO qd_strategy_trades
            (user_id, strategy_id, symbol, type, price, amount, value, commission, commission_ccy, profit, created_at)
            VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                int(user_id),
                int(strategy_id),
                str(symbol),
                str(trade_type),
                float(price or 0.0),
                float(amount or 0.0),
                float(value),
                float(commission or 0.0),
                str(commission_ccy or ""),
                profit,
            ),
        )
        db.commit()
        cur.close()


def _fetch_position(strategy_id: int, symbol: str, side: str) -> Dict[str, Any]:
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT * FROM qd_strategy_positions WHERE strategy_id = %s AND symbol = %s AND side = %s",
            (int(strategy_id), str(symbol), str(side)),
        )
        row = cur.fetchone() or {}
        cur.close()
    return row if isinstance(row, dict) else {}


def _delete_position(strategy_id: int, symbol: str, side: str) -> None:
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            "DELETE FROM qd_strategy_positions WHERE strategy_id = %s AND symbol = %s AND side = %s",
            (int(strategy_id), str(symbol), str(side)),
        )
        db.commit()
        cur.close()


def upsert_position(
    *,
    strategy_id: int,
    symbol: str,
    side: str,
    size: float,
    entry_price: float,
    current_price: float,
    highest_price: float = 0.0,
    lowest_price: float = 0.0,
    user_id: int = None,
) -> None:
    if user_id is None:
        user_id = _get_user_id_from_strategy(strategy_id)
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO qd_strategy_positions
            (user_id, strategy_id, symbol, side, size, entry_price, current_price, highest_price, lowest_price, updated_at)
            VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT(strategy_id, symbol, side) DO UPDATE SET
                size = excluded.size,
                entry_price = excluded.entry_price,
                current_price = excluded.current_price,
                highest_price = CASE WHEN excluded.highest_price > 0 THEN excluded.highest_price ELSE qd_strategy_positions.highest_price END,
                lowest_price = CASE WHEN excluded.lowest_price > 0 THEN excluded.lowest_price ELSE qd_strategy_positions.lowest_price END,
                updated_at = NOW()
            """,
            (int(user_id), int(strategy_id), str(symbol), str(side), float(size or 0.0), float(entry_price or 0.0), float(current_price or 0.0), float(highest_price or 0.0), float(lowest_price or 0.0)),
        )
        db.commit()
        cur.close()


def apply_fill_to_local_position(
    *,
    strategy_id: int,
    symbol: str,
    signal_type: str,
    filled: float,
    avg_price: float,
) -> Tuple[Optional[float], Optional[Dict[str, Any]]]:
    """
    Apply a fill to the local position snapshot.

    Returns (profit, updated_position_row_or_none)
    - profit is only calculated on close/reduce fills (best-effort, based on local entry_price).
    """
    sig = (signal_type or "").strip().lower()
    filled_qty = float(filled or 0.0)
    px = float(avg_price or 0.0)
    if filled_qty <= 0 or px <= 0:
        return None, None

    if "long" in sig:
        side = "long"
    elif "short" in sig:
        side = "short"
    else:
        return None, None

    is_open = sig.startswith("open_") or sig.startswith("add_")
    is_close = sig.startswith("close_") or sig.startswith("reduce_")

    current = _fetch_position(strategy_id, symbol, side)
    cur_size = float(current.get("size") or 0.0)
    cur_entry = float(current.get("entry_price") or 0.0)
    cur_high = float(current.get("highest_price") or 0.0)
    cur_low = float(current.get("lowest_price") or 0.0)

    profit: Optional[float] = None

    if is_open:
        new_size = cur_size + filled_qty
        if new_size <= 0:
            return None, None
        # Weighted average entry.
        if cur_size > 0 and cur_entry > 0:
            new_entry = (cur_size * cur_entry + filled_qty * px) / new_size
        else:
            new_entry = px
        new_high = max(cur_high or px, px)
        new_low = min(cur_low or px, px)
        upsert_position(
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            size=new_size,
            entry_price=new_entry,
            current_price=px,
            highest_price=new_high,
            lowest_price=new_low,
        )
        return None, _fetch_position(strategy_id, symbol, side)

    if is_close:
        # Calculate PnL using local entry price.
        if cur_size > 0 and cur_entry > 0:
            close_qty = min(cur_size, filled_qty)
            if side == "long":
                profit = (px - cur_entry) * close_qty
            else:
                profit = (cur_entry - px) * close_qty

        new_size = cur_size - filled_qty
        if new_size <= 0:
            _delete_position(strategy_id, symbol, side)
            return profit, None
        # Keep entry price for remaining position.
        new_high = max(cur_high or px, px)
        new_low = min(cur_low or px, px)
        upsert_position(
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            size=new_size,
            entry_price=cur_entry if cur_entry > 0 else px,
            current_price=px,
            highest_price=new_high,
            lowest_price=new_low,
        )
        return profit, _fetch_position(strategy_id, symbol, side)

    return None, None


