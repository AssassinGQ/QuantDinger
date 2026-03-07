"""
Interactive Brokers API Routes

Standalone API endpoints for US and Hong Kong stock trading.
"""

from typing import Any, Dict, List

from flask import Blueprint, request, jsonify, g

from app.utils.logger import get_logger
from app.utils.db import get_db_connection
from app.utils.auth import login_required
from app.services.live_trading.ibkr_trading import IBKRClient, IBKRConfig
from app.services.live_trading.ibkr_trading.client import get_ibkr_client, reset_ibkr_client

logger = get_logger(__name__)

ibkr_bp = Blueprint('ibkr', __name__)

# Global client instance
_client: IBKRClient = None


def _get_client() -> IBKRClient:
    """Get current client instance."""
    global _client
    if _client is None:
        _client = get_ibkr_client()
    return _client


# ==================== Connection Management ====================

@ibkr_bp.route('/status', methods=['GET'])
def get_status():
    """
    Get connection status.
    
    GET /api/ibkr/status
    """
    try:
        client = _get_client()
        return jsonify({
            "success": True,
            "data": client.get_connection_status()
        })
    except Exception as e:
        logger.error(f"Get status failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@ibkr_bp.route('/connect', methods=['POST'])
def connect():
    """
    Connect to TWS / IB Gateway.
    
    POST /api/ibkr/connect
    Body: {
        "host": "127.0.0.1",      // Optional, default 127.0.0.1
        "port": 7497,             // Optional, TWS Live:7497, TWS Paper:7496, Gateway Live:4001, Gateway Paper:4002
        "clientId": 1,            // Optional, default 1
        "account": "",            // Optional, specify for multi-account
        "readonly": false         // Optional, readonly mode
    }
    """
    global _client
    
    try:
        data = request.get_json() or {}
        
        has_custom = data.get('host') or data.get('port')
        if has_custom:
            config = IBKRConfig(
                host=data.get('host', '127.0.0.1'),
                port=int(data.get('port', 7497)),
                client_id=int(data.get('clientId', 1)),
                account=data.get('account', ''),
                readonly=data.get('readonly', False),
            )
            if _client is not None and _client.connected:
                _client.disconnect()
            _client = IBKRClient(config)
        else:
            _client = get_ibkr_client()
        
        if not _client.connected:
            success = _client.connect()
        else:
            success = True
        
        if success:
            return jsonify({
                "success": True,
                "message": "Connected successfully",
                "data": _client.get_connection_status()
            })
        else:
            return jsonify({
                "success": False,
                "error": "Connection failed. Please check if IB Gateway is running."
            }), 400
            
    except ImportError as e:
        return jsonify({
            "success": False,
            "error": "ib_insync not installed. Run: pip install ib_insync"
        }), 500
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@ibkr_bp.route('/disconnect', methods=['POST'])
def disconnect():
    """
    Disconnect from IBKR.
    
    POST /api/ibkr/disconnect
    """
    global _client
    
    try:
        if _client is not None:
            _client.disconnect()
            _client = None
        
        reset_ibkr_client()
        
        return jsonify({
            "success": True,
            "message": "Disconnected"
        })
    except Exception as e:
        logger.error(f"Disconnect failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================== Account Queries ====================

@ibkr_bp.route('/account', methods=['GET'])
def get_account():
    """
    Get account information.
    
    GET /api/ibkr/account
    """
    try:
        client = _get_client()
        if not client.connected:
            return jsonify({
                "success": False,
                "error": "Not connected to IBKR"
            }), 400
        
        return jsonify({
            "success": True,
            "data": client.get_account_summary()
        })
    except Exception as e:
        logger.error(f"Get account info failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@ibkr_bp.route('/positions', methods=['GET'])
def get_positions():
    """
    Get positions.
    
    GET /api/ibkr/positions
    """
    try:
        client = _get_client()
        if not client.connected:
            return jsonify({
                "success": False,
                "error": "Not connected to IBKR"
            }), 400
        
        positions = client.get_positions()
        return jsonify({
            "success": True,
            "data": positions
        })
    except Exception as e:
        logger.error(f"Get positions failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@ibkr_bp.route('/orders', methods=['GET'])
def get_orders():
    """
    Get open orders.
    
    GET /api/ibkr/orders
    """
    try:
        client = _get_client()
        if not client.connected:
            return jsonify({
                "success": False,
                "error": "Not connected to IBKR"
            }), 400
        
        orders = client.get_open_orders()
        return jsonify({
            "success": True,
            "data": orders
        })
    except Exception as e:
        logger.error(f"Get orders failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================== Trading ====================

@ibkr_bp.route('/order', methods=['POST'])
def place_order():
    """
    Place an order.
    
    POST /api/ibkr/order
    Body: {
        "symbol": "AAPL",         // Required, symbol code
        "side": "buy",            // Required, buy or sell
        "quantity": 10,           // Required, number of shares
        "marketType": "USStock",  // Optional, USStock or HShare, default USStock
        "orderType": "market",    // Optional, market or limit, default market
        "price": 150.00           // Required for limit orders
    }
    """
    try:
        client = _get_client()
        if not client.connected:
            return jsonify({
                "success": False,
                "error": "Not connected to IBKR"
            }), 400
        
        data = request.get_json() or {}
        
        # Validate parameters
        symbol = data.get('symbol')
        side = data.get('side')
        quantity = data.get('quantity')
        
        if not symbol:
            return jsonify({"success": False, "error": "Missing symbol"}), 400
        if not side or side.lower() not in ('buy', 'sell'):
            return jsonify({"success": False, "error": "side must be buy or sell"}), 400
        if not quantity or float(quantity) <= 0:
            return jsonify({"success": False, "error": "quantity must be > 0"}), 400
        
        market_type = data.get('marketType', 'USStock')
        order_type = data.get('orderType', 'market').lower()
        
        # Place order
        if order_type == 'limit':
            price = data.get('price')
            if not price or float(price) <= 0:
                return jsonify({"success": False, "error": "Limit order requires price"}), 400
            
            result = client.place_limit_order(
                symbol=symbol,
                side=side,
                quantity=float(quantity),
                price=float(price),
                market_type=market_type
            )
        else:
            result = client.place_market_order(
                symbol=symbol,
                side=side,
                quantity=float(quantity),
                market_type=market_type
            )
        
        if result.success:
            return jsonify({
                "success": True,
                "message": result.message,
                "data": {
                    "orderId": result.order_id,
                    "filled": result.filled,
                    "avgPrice": result.avg_price,
                    "status": result.status,
                    "raw": result.raw
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": result.message
            }), 400
            
    except Exception as e:
        logger.error(f"Place order failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@ibkr_bp.route('/order/<int:order_id>', methods=['DELETE'])
def cancel_order(order_id: int):
    """
    Cancel an order.
    
    DELETE /api/ibkr/order/<order_id>
    """
    try:
        client = _get_client()
        if not client.connected:
            return jsonify({
                "success": False,
                "error": "Not connected to IBKR"
            }), 400
        
        success = client.cancel_order(order_id)
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Order {order_id} cancelled"
            })
        else:
            return jsonify({
                "success": False,
                "error": f"Order {order_id} not found"
            }), 404
            
    except Exception as e:
        logger.error(f"Cancel order failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================== Market Data ====================

@ibkr_bp.route('/quote', methods=['GET'])
def get_quote():
    """
    Get real-time quote.
    
    GET /api/ibkr/quote?symbol=AAPL&marketType=USStock
    """
    try:
        client = _get_client()
        if not client.connected:
            return jsonify({
                "success": False,
                "error": "Not connected to IBKR"
            }), 400
        
        symbol = request.args.get('symbol')
        market_type = request.args.get('marketType', 'USStock')
        
        if not symbol:
            return jsonify({"success": False, "error": "Missing symbol"}), 400
        
        quote = client.get_quote(symbol, market_type)
        return jsonify(quote)
        
    except Exception as e:
        logger.error(f"Get quote failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================== Dashboard ====================

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _format_dt(dt: Any) -> Any:
    if dt is None:
        return None
    if hasattr(dt, 'isoformat'):
        return dt.isoformat()
    return dt


def _compute_ibkr_trade_stats(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(trades)
    if total == 0:
        return {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "win_rate": 0.0, "profit_factor": 0.0,
            "total_profit": 0.0, "total_loss": 0.0,
            "total_realized_pnl": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0,
        }

    profits = [_safe_float(t.get("profit"), 0.0) for t in trades]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]

    winning = len(wins)
    losing = len(losses)
    win_rate = (winning / total * 100) if total > 0 else 0.0
    total_profit = sum(wins)
    total_loss = abs(sum(losses))
    total_realized_pnl = sum(profits)
    profit_factor = (total_profit / total_loss) if total_loss > 0 else (total_profit if total_profit > 0 else 0.0)
    avg_win = (total_profit / winning) if winning > 0 else 0.0
    avg_loss = (total_loss / losing) if losing > 0 else 0.0

    return {
        "total_trades": total,
        "winning_trades": winning,
        "losing_trades": losing,
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "total_profit": round(total_profit, 2),
        "total_loss": round(total_loss, 2),
        "total_realized_pnl": round(total_realized_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
    }


@ibkr_bp.route('/dashboard', methods=['GET'])
@login_required
def ibkr_dashboard():
    """
    IBKR broker dashboard: account summary, positions, open orders,
    recent trades and execution records.

    GET /api/ibkr/dashboard
    """
    data: Dict[str, Any] = {
        "connected": False,
        "connection": {},
        "account": {},
        "positions": [],
        "open_orders": [],
        "performance": {},
        "recent_trades": [],
        "executions": [],
    }

    # 1. Connection & live data from IBKR gateway
    try:
        client = _get_client()
        is_connected = client.connected
        data["connected"] = is_connected
        data["connection"] = client.get_connection_status()

        if is_connected:
            # Account summary
            acct = client.get_account_summary()
            if acct.get("success"):
                summary = acct.get("summary", {})
                key_tags = [
                    "NetLiquidation", "TotalCashValue", "StockMarketValue",
                    "AvailableFunds", "BuyingPower",
                    "GrossPositionValue", "InitMarginReq",
                    "MaintMarginReq", "AccruedCash",
                ]
                parsed = {}
                for tag in key_tags:
                    if tag in summary:
                        parsed[tag] = {
                            "value": _safe_float(summary[tag].get("value")),
                            "currency": summary[tag].get("currency", ""),
                        }

                currency = (parsed.get("NetLiquidation") or {}).get("currency", "USD")

                # PnL via dedicated reqPnL (accountSummary tags don't include PnL)
                pnl = client.get_pnl()
                parsed["UnrealizedPnL"] = {"value": pnl.get("unrealizedPnL", 0.0), "currency": currency}
                parsed["RealizedPnL"] = {"value": pnl.get("realizedPnL", 0.0), "currency": currency}
                parsed["DailyPnL"] = {"value": pnl.get("dailyPnL", 0.0), "currency": currency}

                data["account"] = {
                    "account_id": acct.get("account", ""),
                    "items": parsed,
                    "net_liquidation": _safe_float(
                        (parsed.get("NetLiquidation") or {}).get("value")
                    ),
                    "currency": currency,
                }

            # Positions
            data["positions"] = client.get_positions()

            # Add commission info to positions from trade history
            if data["positions"]:
                symbol_commission_map = {}
                with get_db_connection() as db:
                    cur = db.cursor()
                    cur.execute(
                        """
                        SELECT symbol, SUM(commission) as total_commission
                        FROM qd_strategy_trades
                        WHERE user_id = ? AND commission > 0
                        GROUP BY symbol
                        """,
                        (user_id,),
                    )
                    for row in cur.fetchall():
                        symbol_commission_map[row[0]] = float(row[1] or 0)
                    cur.close()

                for pos in data["positions"]:
                    ib_symbol = pos.get("ib_symbol") or pos.get("symbol", "")
                    pos["commission"] = symbol_commission_map.get(ib_symbol, 0.0)

            # Open orders
            data["open_orders"] = client.get_open_orders()
    except Exception as e:
        logger.warning("IBKR live data unavailable: %s", e)

    # 2. DB-sourced trade history (IBKR execution records)
    user_id = g.user_id
    try:
        with get_db_connection() as db:
            cur = db.cursor()
            # Recent trades for IBKR strategies
            cur.execute(
                """
                SELECT t.*, s.strategy_name
                FROM qd_strategy_trades t
                LEFT JOIN qd_strategies_trading s ON s.id = t.strategy_id
                WHERE t.user_id = ?
                  AND s.id IN (
                    SELECT id FROM qd_strategies_trading
                    WHERE user_id = ?
                      AND market_category IN ('USStock', 'HShare')
                  )
                ORDER BY t.created_at DESC
                LIMIT 200
                """,
                (user_id, user_id),
            )
            trades_raw = cur.fetchall() or []
            cur.close()

        trades = []
        for t in trades_raw:
            trade = dict(t)
            if trade.get("created_at") and hasattr(trade["created_at"], "timestamp"):
                trade["created_at"] = int(trade["created_at"].timestamp())
            trades.append(trade)

        data["performance"] = _compute_ibkr_trade_stats(trades)
        data["recent_trades"] = trades[:50]

        # Execution records from pending_orders for IBKR
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """
                SELECT o.*, s.strategy_name
                FROM pending_orders o
                LEFT JOIN qd_strategies_trading s ON s.id = o.strategy_id
                WHERE o.user_id = ?
                  AND s.id IN (
                    SELECT id FROM qd_strategies_trading
                    WHERE user_id = ?
                      AND market_category IN ('USStock', 'HShare')
                  )
                ORDER BY o.id DESC
                LIMIT 100
                """,
                (user_id, user_id),
            )
            exec_rows = cur.fetchall() or []
            cur.close()

        executions = []
        for r in exec_rows:
            row = dict(r)
            status = (row.get("status") or "").strip().lower()
            if status == "sent":
                status = "completed"
            if status == "deferred":
                status = "pending"
            row["status"] = status
            row["strategy_name"] = row.get("strategy_name") or ""
            row["filled_amount"] = _safe_float(row.get("filled"))
            signal_price = _safe_float(row.get("price"))
            fill_price = _safe_float(row.get("avg_price"))
            row["filled_price"] = fill_price or signal_price
            row["signal_price"] = signal_price

            slippage = None
            slippage_pct = None
            if fill_price > 0 and signal_price > 0:
                sig_type = (row.get("signal_type") or "").strip().lower()
                if sig_type in ("buy", "open_long", "close_short"):
                    slippage = round(fill_price - signal_price, 6)
                elif sig_type in ("sell", "close_long", "open_short"):
                    slippage = round(signal_price - fill_price, 6)
                if slippage is not None:
                    slippage_pct = round(slippage / signal_price * 100, 4)
            row["slippage"] = slippage
            row["slippage_pct"] = slippage_pct

            row["error_message"] = row.get("last_error") or ""
            for key in ("created_at", "updated_at", "executed_at", "processed_at", "sent_at"):
                row[key] = _format_dt(row.get(key))
            executions.append(row)

        data["executions"] = executions

    except Exception as e:
        logger.error("IBKR dashboard DB query failed: %s", e, exc_info=True)

    return jsonify({"code": 1, "msg": "success", "data": data})
