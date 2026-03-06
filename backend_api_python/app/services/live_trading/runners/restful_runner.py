"""
RESTful crypto exchange order execution runner.

RestfulClientRunner: crypto REST exchanges (BaseRestfulClient / BaseRestClient)
"""

from __future__ import annotations

import os
from typing import Any, Dict, Tuple

from app.services.live_trading.base import (
    BaseRestfulClient,
    ExecutionResult,
    LiveTradingError,
    OrderContext,
)
from app.services.live_trading.runners.base import OrderRunner
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RestfulClientRunner(OrderRunner):
    """Crypto exchange execution — all isinstance branches preserved as-is."""

    def execute(self, *, client: BaseRestfulClient, order_context: OrderContext) -> ExecutionResult:
        from app.services.live_trading.crypto_trading.binance import BinanceFuturesClient
        from app.services.live_trading.crypto_trading.binance_spot import BinanceSpotClient
        from app.services.live_trading.crypto_trading.okx import OkxClient
        from app.services.live_trading.crypto_trading.bitget import BitgetMixClient
        from app.services.live_trading.crypto_trading.bitget_spot import BitgetSpotClient
        from app.services.live_trading.crypto_trading.bybit import BybitClient
        from app.services.live_trading.crypto_trading.coinbase_exchange import CoinbaseExchangeClient
        from app.services.live_trading.crypto_trading.kraken import KrakenClient
        from app.services.live_trading.crypto_trading.kraken_futures import KrakenFuturesClient
        from app.services.live_trading.crypto_trading.kucoin import KucoinSpotClient, KucoinFuturesClient
        from app.services.live_trading.crypto_trading.gate import GateSpotClient, GateUsdtFuturesClient
        from app.services.live_trading.crypto_trading.bitfinex import BitfinexClient, BitfinexDerivativesClient
        from app.services.live_trading.crypto_trading.symbols import to_okx_swap_inst_id, to_gate_currency_pair

        ctx = order_context
        exchange_config = ctx.exchange_config
        exchange_id = str(exchange_config.get("exchange_id") or "").strip().lower()
        strategy_id = ctx.strategy_id
        order_id = ctx.order_id
        symbol = ctx.symbol
        signal_type = ctx.signal_type
        amount = ctx.amount
        market_type = ctx.market_type
        payload = ctx.payload
        order_row = ctx.order_row

        def _make_client_oid(phase: str = "") -> str:
            ph = str(phase or "").strip().lower()
            if exchange_id == "okx":
                base = f"qd{int(strategy_id)}{int(order_id)}{ph}"
                base = "".join([c for c in base if c.isalnum()])
                if not base:
                    base = f"qd{int(strategy_id)}{int(order_id)}"
                return base[:32]
            return f"qd_{int(strategy_id)}_{int(order_id)}{('_' + ph) if ph else ''}"

        sig = str(signal_type or "").strip().lower()

        if market_type == "spot" and "short" in sig:
            return ExecutionResult(success=False, error="spot_market_does_not_support_short_signals")

        _default_order_mode = os.getenv("ORDER_MODE", "maker").strip().lower()
        _default_maker_wait_sec = float(os.getenv("MAKER_WAIT_SEC", "10"))
        _default_maker_offset_bps = float(os.getenv("MAKER_OFFSET_BPS", "2"))

        order_mode = str(payload.get("order_mode") or payload.get("orderMode") or _default_order_mode).strip().lower()
        maker_wait_sec = float(payload.get("maker_wait_sec") or payload.get("makerWaitSec") or _default_maker_wait_sec)
        maker_offset_bps = float(payload.get("maker_offset_bps") or payload.get("makerOffsetBps") or _default_maker_offset_bps)
        if maker_wait_sec <= 0:
            maker_wait_sec = _default_maker_wait_sec if _default_maker_wait_sec > 0 else 10.0
        if maker_offset_bps < 0:
            maker_offset_bps = 0.0
        maker_offset = maker_offset_bps / 10000.0

        ref_price = float(payload.get("ref_price") or payload.get("price") or order_row.get("price") or 0.0)

        def _signal_to_side_pos_reduce(sig_type: str):
            st = (sig_type or "").strip().lower()
            if st in ("open_long", "add_long"):
                return "buy", "long", False
            if st in ("open_short", "add_short"):
                return "sell", "short", False
            if st in ("close_long", "reduce_long"):
                return "sell", "long", True
            if st in ("close_short", "reduce_short"):
                return "buy", "short", True
            raise LiveTradingError(f"Unsupported signal_type: {sig_type}")

        side, pos_side, reduce_only = _signal_to_side_pos_reduce(signal_type)

        cfg = {}
        try:
            from app.services.exchange_execution import load_strategy_configs
            cfg = load_strategy_configs(strategy_id)
        except Exception:
            pass

        leverage = payload.get("leverage")
        if leverage is None:
            leverage = cfg.get("leverage")
        try:
            leverage = float(leverage or 1.0)
        except Exception:
            leverage = 1.0
        if leverage <= 0:
            leverage = 1.0

        # Auto-correct amount for close/reduce signals based on DB position
        if reduce_only:
            try:
                from app.services.live_trading.records import _fetch_position
                qry_sym = str(symbol or "").strip().upper()
                if qry_sym.endswith("USDT") and "/" not in qry_sym:
                    qry_sym = f"{qry_sym[:-4]}/USDT"
                row = _fetch_position(strategy_id, qry_sym, pos_side)
                if row:
                    held_size = float(row.get("size") or 0.0)
                    if amount > held_size:
                        logger.warning(f"[RiskControl] Adjusting Close amount from {amount} to {held_size} (Held) for {symbol}")
                        amount = held_size
                else:
                    logger.warning(f"[RiskControl] Close signal for {symbol} but NO position found in DB. Setting amount=0.")
                    amount = 0.0
            except Exception as e:
                logger.error(f"[RiskControl] Failed to check DB position logic: {e}")

        phases: Dict[str, Any] = {}

        if ref_price <= 0:
            try:
                if isinstance(client, BinanceFuturesClient):
                    ref_price = float(client.get_mark_price(symbol=str(symbol)) or 0.0)
            except Exception:
                pass

        if isinstance(client, BinanceFuturesClient) and market_type == "swap":
            try:
                client.set_leverage(symbol=str(symbol), leverage=float(leverage or 1.0))
                phases["set_leverage"] = {"exchange": "binance", "symbol": str(symbol), "leverage": float(leverage or 1.0)}
            except Exception as e:
                return ExecutionResult(success=False, error=f"binance_set_leverage_failed:{e}")

        total_base = 0.0
        total_quote = 0.0
        total_fee = 0.0
        fee_ccy = ""

        def _apply_fill(filled_qty: float, avg_px: float) -> None:
            nonlocal total_base, total_quote
            fq = float(filled_qty or 0.0)
            px = float(avg_px or 0.0)
            if fq > 0 and px > 0:
                total_base += fq
                total_quote += fq * px

        def _apply_fee(fee: float, ccy: str = "") -> None:
            nonlocal total_fee, fee_ccy
            try:
                fv = float(fee or 0.0)
            except Exception:
                fv = 0.0
            if fv > 0:
                total_fee += fv
                if (not fee_ccy) and ccy:
                    fee_ccy = str(ccy or "")

        def _fetch_fee_best_effort(*, order_id0: str, client_order_id0: str) -> Tuple[float, str]:
            oid = str(order_id0 or "").strip()
            if not oid:
                return 0.0, ""
            try:
                if isinstance(client, BinanceFuturesClient):
                    return client.get_fee_for_order(symbol=str(symbol), order_id=oid)
                if isinstance(client, BinanceSpotClient):
                    return client.get_fee_for_order(symbol=str(symbol), order_id=oid)
            except Exception:
                return 0.0, ""
            return 0.0, ""

        def _current_avg() -> float:
            return float(total_quote / total_base) if total_base > 0 else 0.0

        # For close/reduce, query actual exchange position to avoid insufficient balance
        if reduce_only and market_type == "swap":
            try:
                actual_pos_size = 0.0
                if isinstance(client, OkxClient):
                    inst_id = to_okx_swap_inst_id(str(symbol))
                    pos_resp = client.get_positions(inst_id=inst_id)
                    pos_data = (pos_resp.get("data") or []) if isinstance(pos_resp, dict) else []
                    for pos in pos_data:
                        if not isinstance(pos, dict):
                            continue
                        pos_inst = str(pos.get("instId") or "").strip()
                        pos_ps = str(pos.get("posSide") or "").strip().lower()
                        if pos_inst == inst_id and pos_ps == pos_side:
                            pos_qty = abs(float(pos.get("pos") or 0.0))
                            ct_val = float(pos.get("ctVal") or 0.0)
                            if ct_val > 0:
                                actual_pos_size = pos_qty * ct_val
                            else:
                                actual_pos_size = pos_qty
                            break
                elif isinstance(client, BinanceFuturesClient):
                    pos_resp = client.get_positions() or []
                    pos_list = pos_resp if isinstance(pos_resp, list) else []
                    norm_sym = str(symbol or "").replace("/", "").replace("-", "").upper()
                    for pos in pos_list:
                        if not isinstance(pos, dict):
                            continue
                        pos_sym = str(pos.get("symbol") or "").upper()
                        if pos_sym != norm_sym:
                            continue
                        p_side = str(pos.get("positionSide") or "").strip().lower()
                        if p_side == pos_side or (p_side == "both" and pos_side in ("long", "short")):
                            pos_amt = abs(float(pos.get("positionAmt") or 0.0))
                            if pos_amt > 0:
                                actual_pos_size = pos_amt
                                break
                elif isinstance(client, BybitClient):
                    pos_resp = client.get_positions() or {}
                    pos_list = (pos_resp.get("result") or {}).get("list") or [] if isinstance(pos_resp, dict) else []
                    for pos in pos_list:
                        if not isinstance(pos, dict):
                            continue
                        pos_sym = str(pos.get("symbol") or "")
                        if pos_sym != str(symbol or "").replace("/", ""):
                            continue
                        p_side = str(pos.get("side") or "").strip().lower()
                        if (p_side == "buy" and pos_side == "long") or (p_side == "sell" and pos_side == "short"):
                            pos_sz = abs(float(pos.get("size") or 0.0))
                            if pos_sz > 0:
                                actual_pos_size = pos_sz
                                break
                elif isinstance(client, BitgetMixClient):
                    product_type = str(exchange_config.get("product_type") or exchange_config.get("productType") or "USDT-FUTURES")
                    pos_resp = client.get_positions(product_type=product_type) or {}
                    pos_list = (pos_resp.get("data") or []) if isinstance(pos_resp, dict) else []
                    for pos in pos_list:
                        if not isinstance(pos, dict):
                            continue
                        pos_sym = str(pos.get("symbol") or "")
                        if pos_sym != str(symbol or ""):
                            continue
                        p_side = str(pos.get("holdSide") or "").strip().lower()
                        if p_side == pos_side:
                            pos_sz = abs(float(pos.get("total") or pos.get("available") or 0.0))
                            if pos_sz > 0:
                                actual_pos_size = pos_sz
                                break

                if actual_pos_size > 0 and actual_pos_size < float(amount or 0.0):
                    logger.info(
                        f"Close position adjustment: order_id={order_id}, strategy_id={strategy_id}, "
                        f"requested={amount}, actual_pos={actual_pos_size}, using actual"
                    )
                    phases["pos_adjustment"] = {
                        "requested": float(amount or 0.0),
                        "actual_position": actual_pos_size,
                        "using": actual_pos_size,
                    }
                    amount = actual_pos_size
            except Exception as e:
                logger.warning(f"Failed to query position for close adjustment: order_id={order_id}, err={e}")
                phases["pos_query_error"] = str(e)

        use_limit_first = order_mode in ("maker", "limit", "limit_first", "maker_then_market")

        remaining = float(amount or 0.0)
        if remaining <= 0:
            return ExecutionResult(success=False, error="invalid_amount")

        # Phase 1: limit (hang order)
        limit_order_id = ""
        if use_limit_first:
            try:
                limit_price = float(ref_price or 0.0)
                if limit_price <= 0:
                    raise LiveTradingError("missing_ref_price_for_limit_order")
                if side == "buy":
                    limit_price = limit_price * (1.0 - maker_offset)
                else:
                    limit_price = limit_price * (1.0 + maker_offset)

                limit_client_oid = _make_client_oid("lmt")
                if isinstance(client, BinanceFuturesClient):
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side="BUY" if side == "buy" else "SELL",
                        quantity=remaining, price=limit_price,
                        reduce_only=reduce_only, position_side=pos_side, client_order_id=limit_client_oid,
                    )
                elif isinstance(client, BinanceSpotClient):
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side="BUY" if side == "buy" else "SELL",
                        quantity=remaining, price=limit_price, client_order_id=limit_client_oid,
                    )
                elif isinstance(client, OkxClient):
                    td_mode = str(payload.get("margin_mode") or payload.get("td_mode") or "cross")
                    if market_type == "swap":
                        try:
                            inst_id = to_okx_swap_inst_id(str(symbol))
                            client.set_leverage(inst_id=inst_id, lever=leverage, mgn_mode=td_mode, pos_side=pos_side)
                        except Exception:
                            pass
                    res1 = client.place_limit_order(
                        market_type=market_type, symbol=str(symbol), side=side,
                        size=remaining, price=limit_price, pos_side=pos_side,
                        td_mode=td_mode, reduce_only=reduce_only, client_order_id=limit_client_oid,
                    )
                elif isinstance(client, BitgetMixClient):
                    product_type = str(exchange_config.get("product_type") or exchange_config.get("productType") or "USDT-FUTURES")
                    margin_coin = str(exchange_config.get("margin_coin") or exchange_config.get("marginCoin") or "USDT")
                    margin_mode = str(payload.get("margin_mode") or payload.get("marginMode") or exchange_config.get("margin_mode") or exchange_config.get("marginMode") or "cross")
                    try:
                        if market_type == "swap":
                            client.set_leverage(
                                symbol=str(symbol), leverage=leverage, margin_coin=margin_coin,
                                product_type=product_type, margin_mode=margin_mode, hold_side=pos_side,
                            )
                    except Exception:
                        pass
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side=side, size=remaining, price=limit_price,
                        margin_coin=margin_coin, product_type=product_type, margin_mode=margin_mode,
                        reduce_only=reduce_only,
                        post_only=(order_mode in ("maker", "maker_then_market", "limit_first", "limit")),
                        client_order_id=limit_client_oid,
                    )
                elif isinstance(client, BitgetSpotClient):
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side=side, size=remaining,
                        price=limit_price, client_order_id=limit_client_oid,
                    )
                elif isinstance(client, BybitClient):
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side=side, qty=remaining,
                        price=limit_price, reduce_only=reduce_only, client_order_id=limit_client_oid,
                    )
                elif isinstance(client, CoinbaseExchangeClient):
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side=side, size=remaining,
                        price=limit_price, client_order_id=limit_client_oid,
                    )
                elif isinstance(client, KrakenClient):
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side=side, size=remaining,
                        price=limit_price, client_order_id=limit_client_oid,
                    )
                elif isinstance(client, KrakenFuturesClient):
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side=side, size=remaining,
                        price=limit_price, reduce_only=reduce_only,
                        post_only=(order_mode in ("maker", "maker_then_market", "limit_first", "limit")),
                        client_order_id=limit_client_oid,
                    )
                elif isinstance(client, KucoinSpotClient):
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side=side, size=remaining,
                        price=limit_price, client_order_id=limit_client_oid,
                    )
                elif isinstance(client, KucoinFuturesClient):
                    try:
                        if market_type == "swap":
                            client.set_leverage(symbol=str(symbol), leverage=leverage)
                    except Exception:
                        pass
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side=side, size=remaining,
                        price=limit_price, reduce_only=reduce_only,
                        post_only=(order_mode in ("maker", "maker_then_market", "limit_first", "limit")),
                        client_order_id=limit_client_oid,
                    )
                elif isinstance(client, GateSpotClient):
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side=side, size=remaining,
                        price=limit_price, client_order_id=limit_client_oid,
                    )
                elif isinstance(client, GateUsdtFuturesClient):
                    try:
                        client.set_leverage(contract=to_gate_currency_pair(str(symbol)), leverage=leverage)
                    except Exception:
                        pass
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side=side, size=remaining,
                        price=limit_price, reduce_only=reduce_only, client_order_id=limit_client_oid,
                    )
                elif isinstance(client, BitfinexClient):
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side=side, size=remaining,
                        price=limit_price, client_order_id=limit_client_oid,
                    )
                elif isinstance(client, BitfinexDerivativesClient):
                    res1 = client.place_limit_order(
                        symbol=str(symbol), side=side, size=remaining,
                        price=limit_price, client_order_id=limit_client_oid,
                    )
                else:
                    raise LiveTradingError(f"Unsupported client type: {type(client)}")

                limit_order_id = str(res1.exchange_order_id or "")
                phases["limit_place"] = res1.raw

                # Wait for fills
                if isinstance(client, BinanceFuturesClient):
                    q = client.wait_for_fill(symbol=str(symbol), order_id=limit_order_id, client_order_id=limit_client_oid, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    fee_v, fee_c = _fetch_fee_best_effort(order_id0=limit_order_id, client_order_id0=limit_client_oid)
                    _apply_fee(float(fee_v or 0.0), str(fee_c or ""))
                elif isinstance(client, BinanceSpotClient):
                    q = client.wait_for_fill(symbol=str(symbol), order_id=limit_order_id, client_order_id=limit_client_oid, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    fee_v, fee_c = _fetch_fee_best_effort(order_id0=limit_order_id, client_order_id0=limit_client_oid)
                    _apply_fee(float(fee_v or 0.0), str(fee_c or ""))
                elif isinstance(client, OkxClient):
                    q = client.wait_for_fill(symbol=str(symbol), ord_id=limit_order_id, cl_ord_id=limit_client_oid, market_type=market_type, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    _apply_fee(float(q.get("fee") or 0.0), str(q.get("fee_ccy") or ""))
                elif isinstance(client, BitgetMixClient):
                    product_type = str(exchange_config.get("product_type") or exchange_config.get("productType") or "USDT-FUTURES")
                    q = client.wait_for_fill(symbol=str(symbol), product_type=product_type, order_id=limit_order_id, client_oid=limit_client_oid, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    _apply_fee(float(q.get("fee") or 0.0), str(q.get("fee_ccy") or ""))
                elif isinstance(client, BitgetSpotClient):
                    q = client.wait_for_fill(symbol=str(symbol), order_id=limit_order_id, client_order_id=limit_client_oid, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    _apply_fee(float(q.get("fee") or 0.0), str(q.get("fee_ccy") or ""))
                elif isinstance(client, BybitClient):
                    q = client.wait_for_fill(symbol=str(symbol), order_id=limit_order_id, client_order_id=limit_client_oid, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    _apply_fee(float(q.get("fee") or 0.0), str(q.get("fee_ccy") or ""))
                elif isinstance(client, CoinbaseExchangeClient):
                    q = client.wait_for_fill(order_id=limit_order_id, client_order_id=limit_client_oid, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    _apply_fee(float(q.get("fee") or 0.0), str(q.get("fee_ccy") or ""))
                elif isinstance(client, KrakenClient):
                    q = client.wait_for_fill(order_id=limit_order_id, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    _apply_fee(float(q.get("fee") or 0.0), str(q.get("fee_ccy") or ""))
                elif isinstance(client, KrakenFuturesClient):
                    q = client.wait_for_fill(order_id=limit_order_id, client_order_id=limit_client_oid, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    _apply_fee(float(q.get("fee") or 0.0), str(q.get("fee_ccy") or ""))
                elif isinstance(client, KucoinSpotClient):
                    q = client.wait_for_fill(order_id=limit_order_id, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    _apply_fee(float(q.get("fee") or 0.0), str(q.get("fee_ccy") or ""))
                elif isinstance(client, KucoinFuturesClient):
                    q = client.wait_for_fill(order_id=limit_order_id, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    _apply_fee(float(q.get("fee") or 0.0), str(q.get("fee_ccy") or ""))
                elif isinstance(client, GateSpotClient):
                    q = client.wait_for_fill(order_id=limit_order_id, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    _apply_fee(float(q.get("fee") or 0.0), str(q.get("fee_ccy") or ""))
                elif isinstance(client, GateUsdtFuturesClient):
                    q = client.wait_for_fill(order_id=limit_order_id, contract=to_gate_currency_pair(str(symbol)), max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    _apply_fee(float(q.get("fee") or 0.0), str(q.get("fee_ccy") or ""))
                elif isinstance(client, BitfinexClient):
                    q = client.wait_for_fill(order_id=limit_order_id, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    _apply_fee(float(q.get("fee") or 0.0), str(q.get("fee_ccy") or ""))
                elif isinstance(client, BitfinexDerivativesClient):
                    q = client.wait_for_fill(order_id=limit_order_id, max_wait_sec=maker_wait_sec)
                    phases["limit_query"] = q
                    _apply_fill(float(q.get("filled") or 0.0), float(q.get("avg_price") or 0.0))
                    _apply_fee(float(q.get("fee") or 0.0), str(q.get("fee_ccy") or ""))

                remaining = max(0.0, float(amount or 0.0) - total_base)

                # Tail guard for OKX
                if remaining > 0 and isinstance(client, OkxClient) and market_type == "swap":
                    try:
                        inst_id = to_okx_swap_inst_id(str(symbol))
                        inst = client.get_instrument(inst_type="SWAP", inst_id=inst_id) or {}
                        lot_sz = float(inst.get("lotSz") or 0.0)
                        min_sz = float(inst.get("minSz") or 0.0)
                        ct_val = float(inst.get("ctVal") or 0.0)
                        min_contract = min_sz if min_sz > 0 else (lot_sz if lot_sz > 0 else 0.0)
                        min_base = (min_contract * ct_val) if (min_contract > 0 and ct_val > 0) else 0.0
                        if min_base > 0 and remaining < (min_base * 0.999999):
                            phases["tail_guard"] = {"exchange": "okx", "inst_id": inst_id, "remaining": remaining, "min_base": min_base}
                            remaining = 0.0
                    except Exception:
                        pass

                # Cancel if not fully filled
                if remaining > max(0.0, float(amount or 0.0) * 0.001):
                    try:
                        if isinstance(client, BinanceFuturesClient):
                            phases["limit_cancel"] = client.cancel_order(symbol=str(symbol), order_id=limit_order_id, client_order_id=limit_client_oid)
                        elif isinstance(client, BinanceSpotClient):
                            phases["limit_cancel"] = client.cancel_order(symbol=str(symbol), order_id=limit_order_id, client_order_id=limit_client_oid)
                        elif isinstance(client, OkxClient):
                            phases["limit_cancel"] = client.cancel_order(market_type=market_type, symbol=str(symbol), ord_id=limit_order_id, cl_ord_id=limit_client_oid)
                        elif isinstance(client, BitgetMixClient):
                            product_type = str(exchange_config.get("product_type") or exchange_config.get("productType") or "USDT-FUTURES")
                            margin_coin = str(exchange_config.get("margin_coin") or exchange_config.get("marginCoin") or "USDT")
                            phases["limit_cancel"] = client.cancel_order(symbol=str(symbol), product_type=product_type, margin_coin=margin_coin, order_id=limit_order_id, client_oid=limit_client_oid)
                        elif isinstance(client, BitgetSpotClient):
                            phases["limit_cancel"] = client.cancel_order(symbol=str(symbol), client_order_id=limit_client_oid)
                        elif isinstance(client, BybitClient):
                            phases["limit_cancel"] = client.cancel_order(symbol=str(symbol), order_id=limit_order_id, client_order_id=limit_client_oid)
                        elif isinstance(client, CoinbaseExchangeClient):
                            phases["limit_cancel"] = client.cancel_order(order_id=limit_order_id, client_order_id=limit_client_oid)
                        elif isinstance(client, KrakenClient):
                            phases["limit_cancel"] = client.cancel_order(order_id=limit_order_id)
                        elif isinstance(client, KrakenFuturesClient):
                            phases["limit_cancel"] = client.cancel_order(order_id=limit_order_id, client_order_id=limit_client_oid)
                        elif isinstance(client, KucoinSpotClient):
                            phases["limit_cancel"] = client.cancel_order(order_id=limit_order_id)
                        elif isinstance(client, KucoinFuturesClient):
                            phases["limit_cancel"] = client.cancel_order(order_id=limit_order_id)
                        elif isinstance(client, GateSpotClient):
                            phases["limit_cancel"] = client.cancel_order(order_id=limit_order_id)
                        elif isinstance(client, GateUsdtFuturesClient):
                            phases["limit_cancel"] = client.cancel_order(order_id=limit_order_id)
                        elif isinstance(client, BitfinexClient):
                            phases["limit_cancel"] = client.cancel_order(order_id=limit_order_id, client_order_id=limit_client_oid)
                        elif isinstance(client, BitfinexDerivativesClient):
                            phases["limit_cancel"] = client.cancel_order(order_id=limit_order_id, client_order_id=limit_client_oid)
                    except Exception:
                        pass
            except LiveTradingError as e:
                logger.warning(f"live limit phase failed: order_id={order_id}, strategy_id={strategy_id}, err={e}")
                remaining = float(amount or 0.0)
                phases["limit_error"] = str(e)
            except Exception as e:
                logger.warning(f"live limit phase unexpected error: order_id={order_id}, strategy_id={strategy_id}, err={e}")
                remaining = float(amount or 0.0)
                phases["limit_error"] = str(e)

        # Phase 2: market for remaining
        market_order_id = ""
        market_client_oid = _make_client_oid("mkt")
        if remaining > 0:
            try:
                if isinstance(client, BinanceFuturesClient):
                    res2 = client.place_market_order(
                        symbol=str(symbol), side="BUY" if side == "buy" else "SELL",
                        quantity=remaining, reduce_only=reduce_only,
                        position_side=pos_side, client_order_id=market_client_oid,
                    )
                elif isinstance(client, BinanceSpotClient):
                    res2 = client.place_market_order(
                        symbol=str(symbol), side="BUY" if side == "buy" else "SELL",
                        quantity=remaining, client_order_id=market_client_oid,
                    )
                elif isinstance(client, OkxClient):
                    td_mode = str(payload.get("margin_mode") or payload.get("td_mode") or "cross")
                    if market_type == "swap":
                        try:
                            inst_id = to_okx_swap_inst_id(str(symbol))
                            client.set_leverage(inst_id=inst_id, lever=leverage, mgn_mode=td_mode, pos_side=pos_side)
                        except Exception:
                            pass
                    res2 = client.place_market_order(
                        symbol=str(symbol), side=side, size=remaining,
                        market_type=market_type, pos_side=pos_side, td_mode=td_mode,
                        reduce_only=reduce_only, client_order_id=market_client_oid,
                    )
                elif isinstance(client, BitgetMixClient):
                    product_type = str(exchange_config.get("product_type") or exchange_config.get("productType") or "USDT-FUTURES")
                    margin_coin = str(exchange_config.get("margin_coin") or exchange_config.get("marginCoin") or "USDT")
                    margin_mode = str(payload.get("margin_mode") or payload.get("marginMode") or exchange_config.get("margin_mode") or exchange_config.get("marginMode") or "cross")
                    try:
                        if market_type == "swap":
                            client.set_leverage(
                                symbol=str(symbol), leverage=leverage, margin_coin=margin_coin,
                                product_type=product_type, margin_mode=margin_mode, hold_side=pos_side,
                            )
                    except Exception:
                        pass
                    res2 = client.place_market_order(
                        symbol=str(symbol), side=side, size=remaining,
                        margin_coin=margin_coin, product_type=product_type, margin_mode=margin_mode,
                        reduce_only=reduce_only, client_order_id=market_client_oid,
                    )
                elif isinstance(client, BitgetSpotClient):
                    mkt_size = remaining
                    if side == "buy" and ref_price > 0:
                        mkt_size = remaining * ref_price
                    res2 = client.place_market_order(
                        symbol=str(symbol), side=side, size=mkt_size,
                        client_order_id=market_client_oid,
                    )
                elif isinstance(client, BybitClient):
                    res2 = client.place_market_order(
                        symbol=str(symbol), side=side, qty=remaining,
                        reduce_only=reduce_only, client_order_id=market_client_oid,
                    )
                elif isinstance(client, CoinbaseExchangeClient):
                    res2 = client.place_market_order(
                        symbol=str(symbol), side=side, size=remaining,
                        client_order_id=market_client_oid,
                    )
                elif isinstance(client, KrakenClient):
                    res2 = client.place_market_order(
                        symbol=str(symbol), side=side, size=remaining,
                        client_order_id=market_client_oid,
                    )
                elif isinstance(client, KrakenFuturesClient):
                    res2 = client.place_market_order(
                        symbol=str(symbol), side=side, size=remaining,
                        reduce_only=reduce_only, client_order_id=market_client_oid,
                    )
                elif isinstance(client, KucoinSpotClient):
                    if side == "buy" and ref_price > 0:
                        res2 = client.place_market_order(
                            symbol=str(symbol), side=side,
                            size=float(remaining) * float(ref_price),
                            quote_size=True, client_order_id=market_client_oid,
                        )
                    else:
                        res2 = client.place_market_order(
                            symbol=str(symbol), side=side, size=remaining,
                            quote_size=False, client_order_id=market_client_oid,
                        )
                elif isinstance(client, KucoinFuturesClient):
                    try:
                        if market_type == "swap":
                            client.set_leverage(symbol=str(symbol), leverage=leverage)
                    except Exception:
                        pass
                    res2 = client.place_market_order(
                        symbol=str(symbol), side=side, size=remaining,
                        reduce_only=reduce_only, client_order_id=market_client_oid,
                    )
                elif isinstance(client, GateSpotClient):
                    res2 = client.place_market_order(
                        symbol=str(symbol), side=side, size=remaining,
                        client_order_id=market_client_oid,
                    )
                elif isinstance(client, GateUsdtFuturesClient):
                    try:
                        client.set_leverage(contract=to_gate_currency_pair(str(symbol)), leverage=leverage)
                    except Exception:
                        pass
                    res2 = client.place_market_order(
                        symbol=str(symbol), side=side, size=remaining,
                        reduce_only=reduce_only, client_order_id=market_client_oid,
                    )
                elif isinstance(client, BitfinexClient):
                    res2 = client.place_market_order(
                        symbol=str(symbol), side=side, size=remaining,
                        client_order_id=market_client_oid,
                    )
                elif isinstance(client, BitfinexDerivativesClient):
                    res2 = client.place_market_order(
                        symbol=str(symbol), side=side, size=remaining,
                        client_order_id=market_client_oid,
                    )
                else:
                    raise LiveTradingError(f"Unsupported client type: {type(client)}")

                market_order_id = str(res2.exchange_order_id or "")
                phases["market_place"] = res2.raw

                # Query fills (short wait)
                if isinstance(client, BinanceFuturesClient):
                    q2 = client.wait_for_fill(symbol=str(symbol), order_id=market_order_id, client_order_id=market_client_oid, max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    fee_v, fee_c = _fetch_fee_best_effort(order_id0=market_order_id, client_order_id0=market_client_oid)
                    _apply_fee(float(fee_v or 0.0), str(fee_c or ""))
                elif isinstance(client, BinanceSpotClient):
                    q2 = client.wait_for_fill(symbol=str(symbol), order_id=market_order_id, client_order_id=market_client_oid, max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    fee_v, fee_c = _fetch_fee_best_effort(order_id0=market_order_id, client_order_id0=market_client_oid)
                    _apply_fee(float(fee_v or 0.0), str(fee_c or ""))
                elif isinstance(client, OkxClient):
                    q2 = client.wait_for_fill(symbol=str(symbol), ord_id=market_order_id, cl_ord_id=market_client_oid, market_type=market_type, max_wait_sec=12.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    _apply_fee(float(q2.get("fee") or 0.0), str(q2.get("fee_ccy") or ""))
                elif isinstance(client, BitgetMixClient):
                    product_type = str(exchange_config.get("product_type") or exchange_config.get("productType") or "USDT-FUTURES")
                    q2 = client.wait_for_fill(symbol=str(symbol), product_type=product_type, order_id=market_order_id, client_oid=market_client_oid, max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    _apply_fee(float(q2.get("fee") or 0.0), str(q2.get("fee_ccy") or ""))
                elif isinstance(client, BitgetSpotClient):
                    q2 = client.wait_for_fill(symbol=str(symbol), order_id=market_order_id, client_order_id=market_client_oid, max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    _apply_fee(float(q2.get("fee") or 0.0), str(q2.get("fee_ccy") or ""))
                elif isinstance(client, BybitClient):
                    q2 = client.wait_for_fill(symbol=str(symbol), order_id=market_order_id, client_order_id=market_client_oid, max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    _apply_fee(float(q2.get("fee") or 0.0), str(q2.get("fee_ccy") or ""))
                elif isinstance(client, CoinbaseExchangeClient):
                    q2 = client.wait_for_fill(order_id=market_order_id, client_order_id=market_client_oid, max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    _apply_fee(float(q2.get("fee") or 0.0), str(q2.get("fee_ccy") or ""))
                elif isinstance(client, KrakenClient):
                    q2 = client.wait_for_fill(order_id=market_order_id, max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    _apply_fee(float(q2.get("fee") or 0.0), str(q2.get("fee_ccy") or ""))
                elif isinstance(client, KrakenFuturesClient):
                    q2 = client.wait_for_fill(order_id=market_order_id, client_order_id=market_client_oid, max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    _apply_fee(float(q2.get("fee") or 0.0), str(q2.get("fee_ccy") or ""))
                elif isinstance(client, KucoinSpotClient):
                    q2 = client.wait_for_fill(order_id=market_order_id, max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    _apply_fee(float(q2.get("fee") or 0.0), str(q2.get("fee_ccy") or ""))
                elif isinstance(client, KucoinFuturesClient):
                    q2 = client.wait_for_fill(order_id=market_order_id, max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    _apply_fee(float(q2.get("fee") or 0.0), str(q2.get("fee_ccy") or ""))
                elif isinstance(client, GateSpotClient):
                    q2 = client.wait_for_fill(order_id=market_order_id, max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    _apply_fee(float(q2.get("fee") or 0.0), str(q2.get("fee_ccy") or ""))
                elif isinstance(client, GateUsdtFuturesClient):
                    q2 = client.wait_for_fill(order_id=market_order_id, contract=to_gate_currency_pair(str(symbol)), max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    _apply_fee(float(q2.get("fee") or 0.0), str(q2.get("fee_ccy") or ""))
                elif isinstance(client, BitfinexClient):
                    q2 = client.wait_for_fill(order_id=market_order_id, max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    _apply_fee(float(q2.get("fee") or 0.0), str(q2.get("fee_ccy") or ""))
                elif isinstance(client, BitfinexDerivativesClient):
                    q2 = client.wait_for_fill(order_id=market_order_id, max_wait_sec=3.0)
                    phases["market_query"] = q2
                    _apply_fill(float(q2.get("filled") or 0.0), float(q2.get("avg_price") or 0.0))
                    _apply_fee(float(q2.get("fee") or 0.0), str(q2.get("fee_ccy") or ""))
            except LiveTradingError as e:
                logger.warning(f"live market phase failed: order_id={order_id}, strategy_id={strategy_id}, err={e}")
                phases["market_error"] = str(e)
                if float(total_base or 0.0) > 0:
                    remaining = 0.0
                else:
                    return ExecutionResult(success=False, error=str(e))
            except Exception as e:
                logger.warning(f"live market phase unexpected error: order_id={order_id}, strategy_id={strategy_id}, err={e}")
                return ExecutionResult(success=False, error=str(e))

        # Build final result
        filled_final = float(total_base or 0.0)
        avg_final = float(_current_avg() or 0.0)
        if filled_final <= 0 and ref_price > 0:
            filled_final = float(amount or 0.0)
            avg_final = float(ref_price or 0.0)

        return ExecutionResult(
            success=True,
            exchange_id=str(exchange_config.get("exchange_id") or ""),
            exchange_order_id=str(market_order_id or limit_order_id),
            filled=filled_final,
            avg_price=avg_final,
            fee=float(total_fee or 0.0),
            fee_ccy=str(fee_ccy or ""),
            note="live_order_sent",
            raw=phases,
        )

    def sync_positions(
        self, *, client, exchange_config: Dict[str, Any], market_type: str = "swap"
    ) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]:
        from app.services.live_trading.crypto_trading.binance import BinanceFuturesClient
        from app.services.live_trading.crypto_trading.okx import OkxClient
        from app.services.live_trading.crypto_trading.bitget import BitgetMixClient
        from app.services.live_trading.crypto_trading.bybit import BybitClient
        from app.services.live_trading.crypto_trading.gate import GateUsdtFuturesClient
        from app.services.live_trading.crypto_trading.kucoin import KucoinFuturesClient
        from app.services.live_trading.crypto_trading.kraken_futures import KrakenFuturesClient
        from app.services.live_trading.crypto_trading.bitfinex import BitfinexDerivativesClient
        from app.services.live_trading.crypto_trading.symbols import to_okx_swap_inst_id, to_gate_currency_pair

        exch_size: Dict[str, Dict[str, float]] = {}
        exch_entry_price: Dict[str, Dict[str, float]] = {}

        if isinstance(client, BinanceFuturesClient) and market_type == "swap":
            all_pos = client.get_positions() or []
            if isinstance(all_pos, dict) and "raw" in all_pos:
                all_pos = all_pos["raw"]
            if isinstance(all_pos, list):
                for p in all_pos:
                    sym = str(p.get("symbol") or "").strip().upper()
                    try:
                        amt = float(p.get("positionAmt") or 0.0)
                        ep = float(p.get("entryPrice") or 0.0)
                    except Exception:
                        amt, ep = 0.0, 0.0
                    if not sym or abs(amt) <= 0:
                        continue
                    hb_sym = sym
                    if hb_sym.endswith("USDT") and len(hb_sym) > 4 and "/" not in hb_sym:
                        hb_sym = f"{hb_sym[:-4]}/USDT"
                    side = "long" if amt > 0 else "short"
                    exch_size.setdefault(hb_sym, {"long": 0.0, "short": 0.0})[side] = abs(float(amt))
                    exch_entry_price.setdefault(hb_sym, {"long": 0.0, "short": 0.0})[side] = abs(float(ep))

        elif isinstance(client, OkxClient) and market_type == "swap":
            resp = client.get_positions()
            data = (resp.get("data") or []) if isinstance(resp, dict) else []
            if isinstance(data, list):
                for p in data:
                    inst_id = str(p.get("instId") or "")
                    p_side = str(p.get("posSide") or "").lower()
                    try:
                        pos = float(p.get("pos") or 0.0)
                    except Exception:
                        pos = 0.0
                    if not inst_id or abs(pos) <= 0:
                        continue
                    hb_sym = inst_id.replace("-SWAP", "").replace("-", "/")
                    side = "long" if p_side == "long" else ("short" if p_side == "short" else ("long" if pos > 0 else "short"))
                    qty_base = abs(float(pos))
                    try:
                        inst = client.get_instrument(inst_type="SWAP", inst_id=inst_id) or {}
                        ct_val = float(inst.get("ctVal") or 0.0)
                        if ct_val > 0:
                            qty_base = qty_base * ct_val
                    except Exception:
                        pass
                    exch_size.setdefault(hb_sym, {"long": 0.0, "short": 0.0})[side] = float(qty_base)

        elif isinstance(client, BitgetMixClient) and market_type == "swap":
            product_type = str(exchange_config.get("product_type") or exchange_config.get("productType") or "USDT-FUTURES")
            resp = client.get_positions(product_type=product_type)
            data = resp.get("data") if isinstance(resp, dict) else None
            if isinstance(data, list):
                for p in data:
                    sym = str(p.get("symbol") or "")
                    hold_side = str(p.get("holdSide") or "").lower()
                    try:
                        total = float(p.get("total") or 0.0)
                    except Exception:
                        total = 0.0
                    if not sym or abs(total) <= 0:
                        continue
                    hb_sym = sym.upper()
                    if hb_sym.endswith("USDT") and len(hb_sym) > 4 and "/" not in hb_sym:
                        hb_sym = f"{hb_sym[:-4]}/USDT"
                    side = "long" if hold_side == "long" else "short"
                    exch_size.setdefault(hb_sym, {"long": 0.0, "short": 0.0})[side] = abs(float(total))

        elif isinstance(client, BybitClient) and market_type == "swap":
            resp = client.get_positions()
            lst = (((resp.get("result") or {}).get("list")) if isinstance(resp, dict) else None) or []
            if isinstance(lst, list):
                for p in lst:
                    if not isinstance(p, dict):
                        continue
                    sym = str(p.get("symbol") or "").strip().upper()
                    side0 = str(p.get("side") or "").strip().lower()
                    try:
                        sz = float(p.get("size") or 0.0)
                    except Exception:
                        sz = 0.0
                    if not sym or abs(sz) <= 0:
                        continue
                    hb_sym = sym
                    if hb_sym.endswith("USDT") and len(hb_sym) > 4 and "/" not in hb_sym:
                        hb_sym = f"{hb_sym[:-4]}/USDT"
                    side = "long" if side0 == "buy" else ("short" if side0 == "sell" else ("long" if sz > 0 else "short"))
                    exch_size.setdefault(hb_sym, {"long": 0.0, "short": 0.0})[side] = abs(float(sz))

        elif isinstance(client, GateUsdtFuturesClient) and market_type == "swap":
            resp = client.get_positions()
            items = resp if isinstance(resp, list) else []
            if isinstance(items, list):
                for p in items:
                    if not isinstance(p, dict):
                        continue
                    contract = str(p.get("contract") or "").strip()
                    try:
                        sz_ct = float(p.get("size") or 0.0)
                    except Exception:
                        sz_ct = 0.0
                    if not contract or abs(sz_ct) <= 0:
                        continue
                    hb_sym = contract.replace("_", "/")
                    side = "long" if sz_ct > 0 else "short"
                    qty_base = abs(sz_ct)
                    try:
                        meta = client.get_contract(contract=contract) or {}
                        qm = float(meta.get("quanto_multiplier") or meta.get("contract_size") or 0.0)
                        if qm > 0:
                            qty_base = qty_base * qm
                    except Exception:
                        pass
                    exch_size.setdefault(hb_sym, {"long": 0.0, "short": 0.0})[side] = float(qty_base)

        elif isinstance(client, KucoinFuturesClient) and market_type == "swap":
            resp = client.get_positions()
            data = (resp.get("data") if isinstance(resp, dict) else None) or []
            if isinstance(data, list):
                for p in data:
                    if not isinstance(p, dict):
                        continue
                    sym = str(p.get("symbol") or "").strip()
                    try:
                        qty_ct = float(p.get("currentQty") or p.get("quantity") or 0.0)
                    except Exception:
                        qty_ct = 0.0
                    if not sym or abs(qty_ct) <= 0:
                        continue
                    side = "long" if qty_ct > 0 else "short"
                    qty_base = abs(qty_ct)
                    try:
                        meta = client.get_contract(symbol=sym) or {}
                        mult = float(meta.get("multiplier") or meta.get("lotSize") or 0.0)
                        if mult > 0:
                            qty_base = qty_base * mult
                    except Exception:
                        pass
                    exch_size.setdefault(sym, {"long": 0.0, "short": 0.0})[side] = float(qty_base)

        elif isinstance(client, KrakenFuturesClient) and market_type == "swap":
            resp = client.get_open_positions()
            positions = (resp.get("openPositions") if isinstance(resp, dict) else None) or (resp.get("open_positions") if isinstance(resp, dict) else None) or []
            if isinstance(positions, list):
                for p in positions:
                    if not isinstance(p, dict):
                        continue
                    sym = str(p.get("symbol") or p.get("instrument") or "").strip()
                    try:
                        sz = float(p.get("size") or p.get("positionSize") or 0.0)
                    except Exception:
                        sz = 0.0
                    if not sym or abs(sz) <= 0:
                        continue
                    side = "long" if sz > 0 else "short"
                    exch_size.setdefault(sym, {"long": 0.0, "short": 0.0})[side] = abs(float(sz))

        elif isinstance(client, BitfinexDerivativesClient) and market_type == "swap":
            resp = client.get_positions()
            items = resp if isinstance(resp, list) else []
            if isinstance(items, list):
                for p in items:
                    try:
                        if isinstance(p, list) and len(p) >= 3:
                            sym = str(p[0] or "")
                            amt = float(p[2] or 0.0)
                            if not sym or abs(amt) <= 0:
                                continue
                            side = "long" if amt > 0 else "short"
                            exch_size.setdefault(sym, {"long": 0.0, "short": 0.0})[side] = abs(float(amt))
                    except Exception:
                        continue

        elif hasattr(client, 'get_positions_normalized'):
            for pr in client.get_positions_normalized():
                if pr.symbol and pr.quantity > 0:
                    exch_size.setdefault(pr.symbol, {"long": 0.0, "short": 0.0})[pr.side] = pr.quantity
                    if pr.entry_price > 0:
                        exch_entry_price.setdefault(pr.symbol, {"long": 0.0, "short": 0.0})[pr.side] = pr.entry_price

        return exch_size, exch_entry_price
