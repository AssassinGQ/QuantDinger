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


def parse_ibkr_mode(broker_id: str = None) -> str:
    """从 broker_id 解析 IBKR Gateway 模式"""
    if not broker_id:
        return 'paper'
    if broker_id.endswith('-live'):
        return 'live'
    if broker_id.endswith('-paper'):
        return 'paper'
    return 'paper'


def _broker_id_to_exchange_ids(broker_id: str) -> List[str]:
    """Map broker_id to the set of exchange_ids that belong to it.

    ibkr-paper matches both 'ibkr-paper' and legacy 'ibkr'.
    ibkr-live matches only 'ibkr-live'.
    """
    if broker_id == 'ibkr-live':
        return ['ibkr-live']
    return ['ibkr-paper', 'ibkr']


# ==================== Connection Management ====================

@ibkr_bp.route('/status', methods=['GET'])
def get_status():
    """GET /api/ibkr/status?broker_id=ibkr-paper|ibkr-live"""
    try:
        broker_id = request.args.get('broker_id')
        mode = parse_ibkr_mode(broker_id)
        client = get_ibkr_client(mode=mode)
        return jsonify({
            "success": True,
            "data": client.get_connection_status()
        })
    except Exception as e:
        logger.error(f"Get status failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@ibkr_bp.route('/status-all', methods=['GET'])
def get_status_all():
    """GET /api/ibkr/status-all - 返回所有 Gateway 的状态"""
    try:
        paper_client = get_ibkr_client(mode='paper')
        live_client = get_ibkr_client(mode='live')

        return jsonify({
            "success": True,
            "data": {
                "paper": paper_client.get_connection_status(),
                "live": live_client.get_connection_status()
            }
        })
    except Exception as e:
        logger.error(f"Get all status failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@ibkr_bp.route('/connect', methods=['POST'])
def connect():
    """POST /api/ibkr/connect"""
    try:
        data = request.get_json() or {}
        broker_id = data.get('broker_id', 'ibkr-paper')
        mode = parse_ibkr_mode(broker_id)

        has_custom = data.get('host') or data.get('port')
        if has_custom:
            reset_ibkr_client(mode=mode)
            config = IBKRConfig(
                host=data.get('host', '127.0.0.1'),
                port=int(data.get('port', 7497)),
                client_id=int(data.get('clientId', 1)),
                account=data.get('account', ''),
                readonly=data.get('readonly', False),
            )
            client = get_ibkr_client(config, mode=mode)
        else:
            client = get_ibkr_client(mode=mode)

        if not client.connected:
            success = client.connect()
        else:
            success = True

        if success:
            return jsonify({
                "success": True,
                "message": f"Connected to {mode} Gateway successfully",
                "data": client.get_connection_status()
            })
        else:
            return jsonify({
                "success": False,
                "error": "Connection failed. Please check if IB Gateway is running."
            }), 400

    except ImportError:
        return jsonify({
            "success": False,
            "error": "ib_insync not installed. Run: pip install ib_insync"
        }), 500
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@ibkr_bp.route('/disconnect', methods=['POST'])
def disconnect():
    """POST /api/ibkr/disconnect"""
    try:
        data = request.get_json() or {}
        mode = data.get('mode')
        if not mode and data.get('broker_id'):
            mode = parse_ibkr_mode(data.get('broker_id'))
        reset_ibkr_client(mode=mode)
        return jsonify({"success": True, "message": "Disconnected"})
    except Exception as e:
        logger.error(f"Disconnect failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== Account Queries ====================

@ibkr_bp.route('/account', methods=['GET'])
def get_account():
    """GET /api/ibkr/account?broker_id=ibkr-paper|ibkr-live"""
    try:
        broker_id = request.args.get('broker_id', 'ibkr-paper')
        mode = parse_ibkr_mode(broker_id)
        client = get_ibkr_client(mode=mode)
        if not client.connected:
            return jsonify({"success": False, "error": f"Not connected to {mode} Gateway"}), 400

        return jsonify({"success": True, "data": client.get_account_summary()})
    except Exception as e:
        logger.error(f"Get account info failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@ibkr_bp.route('/positions', methods=['GET'])
def get_positions():
    """GET /api/ibkr/positions?broker_id=ibkr-paper|ibkr-live"""
    try:
        broker_id = request.args.get('broker_id', 'ibkr-paper')
        mode = parse_ibkr_mode(broker_id)
        client = get_ibkr_client(mode=mode)
        if not client.connected:
            return jsonify({"success": False, "error": f"Not connected to {mode} Gateway"}), 400

        return jsonify({"success": True, "data": client.get_positions()})
    except Exception as e:
        logger.error(f"Get positions failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@ibkr_bp.route('/orders', methods=['GET'])
def get_orders():
    """GET /api/ibkr/orders?broker_id=ibkr-paper|ibkr-live"""
    try:
        broker_id = request.args.get('broker_id', 'ibkr-paper')
        mode = parse_ibkr_mode(broker_id)
        client = get_ibkr_client(mode=mode)
        if not client.connected:
            return jsonify({"success": False, "error": f"Not connected to {mode} Gateway"}), 400

        return jsonify({"success": True, "data": client.get_open_orders()})
    except Exception as e:
        logger.error(f"Get orders failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== Trading ====================

@ibkr_bp.route('/order', methods=['POST'])
def place_order():
    """POST /api/ibkr/order"""
    try:
        data = request.get_json() or {}
        broker_id = data.get('broker_id', 'ibkr-paper')
        mode = parse_ibkr_mode(broker_id)

        client = get_ibkr_client(mode=mode)
        if not client.connected:
            return jsonify({"success": False, "error": f"Not connected to {mode} Gateway"}), 400

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

        is_open, reason = client.is_market_open(symbol, market_type)
        if not is_open:
            return jsonify({"success": False, "error": f"Market closed: {reason}"}), 400

        if order_type == 'limit':
            price = data.get('price')
            if not price or float(price) <= 0:
                return jsonify({"success": False, "error": "Limit order requires price"}), 400
            result = client.place_limit_order(
                symbol=symbol, side=side,
                quantity=float(quantity), price=float(price),
                market_type=market_type,
            )
        else:
            result = client.place_market_order(
                symbol=symbol, side=side,
                quantity=float(quantity),
                market_type=market_type,
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
                    "raw": result.raw,
                }
            })
        else:
            return jsonify({"success": False, "error": result.message}), 400

    except Exception as e:
        logger.error(f"Place order failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@ibkr_bp.route('/order/<int:order_id>', methods=['DELETE'])
def cancel_order(order_id: int):
    """DELETE /api/ibkr/order/<order_id>"""
    try:
        data = request.get_json() or {}
        broker_id = data.get('broker_id', 'ibkr-paper')
        mode = parse_ibkr_mode(broker_id)

        client = get_ibkr_client(mode=mode)
        if not client.connected:
            return jsonify({"success": False, "error": f"Not connected to {mode} Gateway"}), 400

        success = client.cancel_order(order_id)

        if success:
            return jsonify({"success": True, "message": f"Order {order_id} cancelled"})
        else:
            return jsonify({"success": False, "error": f"Order {order_id} not found"}), 404

    except Exception as e:
        logger.error(f"Cancel order failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== Market Data ====================

@ibkr_bp.route('/quote', methods=['GET'])
def get_quote():
    """GET /api/ibkr/quote?symbol=AAPL&marketType=USStock&broker_id=ibkr-paper|ibkr-live"""
    try:
        broker_id = request.args.get('broker_id', 'ibkr-paper')
        mode = parse_ibkr_mode(broker_id)
        client = get_ibkr_client(mode=mode)
        if not client.connected:
            return jsonify({"success": False, "error": f"Not connected to {mode} Gateway"}), 400

        symbol = request.args.get('symbol')
        market_type = request.args.get('marketType', 'USStock')

        if not symbol:
            return jsonify({"success": False, "error": "Missing symbol"}), 400

        return jsonify(client.get_quote(symbol, market_type))

    except Exception as e:
        logger.error(f"Get quote failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


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

    closed_trades = [
        t for t in trades
        if (t.get("type") or "").startswith(("close_", "reduce_"))
        or (t.get("profit") is not None and _safe_float(t.get("profit"), 0.0) != 0.0)
    ]
    closed_profits = [_safe_float(t.get("profit"), 0.0) for t in closed_trades]
    wins = [p for p in closed_profits if p > 0]
    losses = [p for p in closed_profits if p < 0]

    winning = len(wins)
    losing = len(losses)
    closed_count = len(closed_trades)
    win_rate = (winning / closed_count * 100) if closed_count > 0 else 0.0
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
    Query params:
        broker_id: 'ibkr-paper' or 'ibkr-live' (default: ibkr-paper)
    """
    broker_id = request.args.get('broker_id', 'ibkr-paper')
    mode = parse_ibkr_mode(broker_id)
    exchange_ids = _broker_id_to_exchange_ids(broker_id)

    data: Dict[str, Any] = {
        "connected": False,
        "connection": {},
        "account": {},
        "positions": [],
        "open_orders": [],
        "performance": {},
        "recent_trades": [],
        "executions": [],
        "strategy_pnl": [],
    }

    user_id = g.user_id
    client = None
    is_connected = False
    try:
        client = get_ibkr_client(mode=mode)
        is_connected = client.connected
        data["connected"] = is_connected
        data["connection"] = client.get_connection_status()
    except Exception as e:
        logger.warning("IBKR connection check failed: %s", e)

    if is_connected and client:
        # Account summary + PnL
        try:
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

                pnl = {}
                try:
                    pnl_result = client.get_pnl()
                    if pnl_result:
                        pnl = pnl_result
                except Exception as pnl_err:
                    logger.warning("IBKR PnL query failed: %s", pnl_err)
                parsed["UnrealizedPnL"] = {"value": pnl.get("unrealizedPnL", 0.0), "currency": currency}
                parsed["RealizedPnL"] = {"value": pnl.get("realizedPnL", 0.0), "currency": currency}
                parsed["DailyPnL"] = {"value": pnl.get("dailyPnL", 0.0), "currency": currency}

                data["account"] = {
                    "account_id": acct.get("account", "") if acct else "",
                    "items": parsed,
                    "net_liquidation": _safe_float(
                        (parsed.get("NetLiquidation") or {}).get("value")
                    ),
                    "currency": currency,
                }
        except Exception as e:
            logger.warning("IBKR account summary failed: %s", e)

        # Positions
        try:
            data["positions"] = client.get_positions()

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
        except Exception as e:
            logger.warning("IBKR positions failed: %s", e)

        # Open orders
        try:
            data["open_orders"] = client.get_open_orders()
        except Exception as e:
            logger.warning("IBKR open orders failed: %s", e)

    # DB-sourced trade history — filter by strategy exchange_id instead of gateway_mode
    _eid_placeholders = ','.join(['%s'] * len(exchange_ids))
    _strategy_filter_sql = f"""
        SELECT id FROM qd_strategies_trading
        WHERE user_id = %s
          AND market_category IN ('USStock', 'HShare')
          AND COALESCE(
            CASE WHEN exchange_config IS NOT NULL AND exchange_config != ''
                 THEN exchange_config::jsonb->>'exchange_id'
                 ELSE NULL END,
            'ibkr'
          ) IN ({_eid_placeholders})
    """
    _strategy_filter_params = tuple([user_id] + exchange_ids)

    try:
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                f"""
                SELECT t.*, s.strategy_name
                FROM qd_strategy_trades t
                LEFT JOIN qd_strategies_trading s ON s.id = t.strategy_id
                WHERE t.user_id = %s
                  AND t.strategy_id IN ({_strategy_filter_sql})
                ORDER BY t.created_at DESC
                LIMIT 200
                """,
                (user_id,) + _strategy_filter_params,
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

        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                f"""
                SELECT o.*, s.strategy_name
                FROM pending_orders o
                LEFT JOIN qd_strategies_trading s ON s.id = o.strategy_id
                WHERE o.user_id = %s
                  AND o.strategy_id IN ({_strategy_filter_sql})
                ORDER BY o.id DESC
                LIMIT 100
                """,
                (user_id,) + _strategy_filter_params,
            )
            exec_rows = cur.fetchall() or []

            cur.execute(
                f"""
                SELECT 
                    t.strategy_id,
                    s.strategy_name,
                    s.initial_capital,
                    COUNT(*) as total_trades,
                    s.initial_capital as total_value,
                    SUM(t.commission) as total_commission,
                    SUM(t.profit) as total_profit,
                    SUM(CASE WHEN t.profit > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(CASE WHEN t.profit < 0 THEN 1 ELSE 0 END) as losing_trades,
                    SUM(CASE WHEN t.type LIKE 'close_%%' OR t.type LIKE 'reduce_%%'
                             OR (t.profit IS NOT NULL AND t.profit != 0)
                        THEN 1 ELSE 0 END) as closed_trades
                FROM qd_strategy_trades t
                LEFT JOIN qd_strategies_trading s ON s.id = t.strategy_id
                WHERE t.user_id = %s
                  AND t.strategy_id IN ({_strategy_filter_sql})
                GROUP BY t.strategy_id, s.strategy_name, s.initial_capital
                ORDER BY total_profit DESC
                """,
                (user_id,) + _strategy_filter_params,
            )
            strategy_rows = cur.fetchall() or []
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

        strategy_pnl = []
        for row in strategy_rows:
            total_trades = row.get("total_trades") or 0
            winning_trades = row.get("winning_trades") or 0
            closed_trades = row.get("closed_trades") or 0
            total_profit = float(row.get("total_profit") or 0)
            initial_capital = float(row.get("initial_capital") or 0)
            profit_rate = round(total_profit / initial_capital * 100, 2) if initial_capital > 0 else 0
            strategy_pnl.append({
                "strategy_id": row.get("strategy_id"),
                "strategy_name": row.get("strategy_name") or f"Strategy_{row.get('strategy_id')}",
                "total_trades": total_trades,
                "total_value": round(float(row.get("total_value") or 0), 2),
                "total_commission": round(float(row.get("total_commission") or 0), 2),
                "total_profit": round(total_profit, 2),
                "profit_rate": profit_rate,
                "winning_trades": winning_trades,
                "losing_trades": row.get("losing_trades") or 0,
                "win_rate": round(winning_trades / closed_trades * 100, 2) if closed_trades > 0 else 0,
            })
        data["strategy_pnl"] = strategy_pnl

    except Exception as e:
        logger.error("IBKR dashboard DB query failed: %s", e, exc_info=True)

    return jsonify({"code": 1, "msg": "success", "data": data})
