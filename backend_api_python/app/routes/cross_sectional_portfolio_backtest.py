"""
截面组合回测 HTTP API（BT-01 / Phase 22 plan 02）。

POST ``/api/indicator/cross-sectional-portfolio-backtest`` — 与单标的回测一致的成功包络 ``code==1, msg=='OK'``；
校验 ``symbolList`` 与 ``universe`` 互斥（D-03）；错误响应不返回 Python 栈文本。
"""

from __future__ import annotations

import hashlib
import json
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Tuple

from flask import Blueprint, jsonify, request

from app.services.backtest import BacktestService
from app.services.cross_sectional_portfolio_backtest import CrossSectionalPortfolioBacktestService
from app.utils.auth import login_required
from app.utils.logger import get_logger

logger = get_logger(__name__)

cross_sectional_portfolio_bt_bp = Blueprint("cross_sectional_portfolio_bt", __name__)

_MAX_BODY_BYTES = 3 * 1024 * 1024
_MAX_INDICATOR_CHARS = 400_000


def _pool_validation_error(data: Mapping[str, Any]) -> Optional[Tuple[int, str]]:
    """
    校验 symbolList 与 universe 恰好其一非空。
    返回 (http_status, msg) 或 None 表示通过。
    """
    raw_list = data.get("symbolList")
    if raw_list is None:
        raw_list = data.get("symbol_list")
    symbol_list: List[str] = []
    if isinstance(raw_list, list):
        symbol_list = [str(x).strip() for x in raw_list if str(x).strip()]
    universe = str(data.get("universe") or "").strip()

    list_nonempty = len(symbol_list) > 0
    universe_nonempty = len(universe) > 0

    if list_nonempty and universe_nonempty:
        return 400, "BT01_POOL: symbolList and universe are mutually exclusive (D-03)"
    if not list_nonempty and not universe_nonempty:
        return 400, "BT01_POOL: provide exactly one of symbolList (non-empty) or universe (non-empty)"
    return None


def _fetch_panel_for_symbols(
    market: str,
    timeframe: str,
    symbols: List[str],
    start_date: datetime,
    end_date: datetime,
) -> Dict[str, Any]:
    """拉取多标的 OHLCV，组装 CrossSectionalPortfolioBacktestService 所需的 panel。"""
    bt = BacktestService()
    panel: Dict[str, Any] = {}
    for sym in symbols:
        df = bt._fetch_kline_data(market, sym, timeframe, start_date, end_date)  # pylint: disable=protected-access
        if df is not None and not df.empty:
            panel[str(sym).strip().upper()] = df
    return panel


def _build_repro_block(
    *,
    symbol_list: Optional[List[str]],
    universe: str,
    indicator_code: str,
    trading_config: Dict[str, Any],
    industry_by_symbol: Mapping[str, str],
    service_digest: str,
) -> Dict[str, Any]:
    uni_key = json.dumps(
        {"symbolList": symbol_list or [], "universe": universe},
        sort_keys=True,
        ensure_ascii=False,
    )
    universe_digest = hashlib.sha256(uni_key.encode("utf-8")).hexdigest()[:32]
    ind_hash = hashlib.sha256(indicator_code.encode("utf-8")).hexdigest()[:32]
    execution_profile = {
        "timeframe": trading_config.get("timeframe", "1D"),
        "rebalance_frequency": trading_config.get("rebalance_frequency", "daily"),
        "fallback_mode": trading_config.get("fallback_mode", "strict"),
        "min_liquidity_usd": trading_config.get("min_liquidity_usd", 1_000_000.0),
        "long_halt_days": trading_config.get("long_halt_days", 5),
    }
    return {
        "universe_digest": universe_digest,
        "indicator_config_hash": ind_hash,
        "execution_profile": execution_profile,
        "industry_neutral_available": bool(industry_by_symbol),
        "digest": service_digest,
    }


@cross_sectional_portfolio_bt_bp.route("/cross-sectional-portfolio-backtest", methods=["POST"])
@login_required
def cross_sectional_portfolio_backtest_post():
    try:
        if request.content_length and request.content_length > _MAX_BODY_BYTES:
            return (
                jsonify({"code": 0, "msg": "BT01_HTTP: request body too large", "data": None}),
                400,
            )

        data = request.get_json()
        if not data or not isinstance(data, dict):
            return jsonify({"code": 0, "msg": "Request body is required", "data": None}), 400

        err = _pool_validation_error(data)
        if err:
            status, msg = err
            return jsonify({"code": 0, "msg": msg, "data": None}), status

        indicator_code = str(data.get("indicatorCode") or data.get("indicator_code") or "").strip()
        if not indicator_code:
            return jsonify({"code": 0, "msg": "indicatorCode is required", "data": None}), 400
        if len(indicator_code) > _MAX_INDICATOR_CHARS:
            return jsonify({"code": 0, "msg": "BT01_HTTP: indicatorCode exceeds size limit", "data": None}), 400

        start_date_str = str(data.get("startDate") or data.get("start_date") or "").strip()
        end_date_str = str(data.get("endDate") or data.get("end_date") or "").strip()
        if not start_date_str or not end_date_str:
            return jsonify({"code": 0, "msg": "startDate and endDate are required", "data": None}), 400

        try:
            start_date = datetime.strptime(start_date_str[:10], "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str[:10], "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            return jsonify({"code": 0, "msg": "Invalid startDate or endDate format", "data": None}), 400

        market = str(data.get("market") or "USStock")
        timeframe = str(data.get("timeframe") or "1D")
        trading_config = dict(data.get("tradingConfig") or data.get("trading_config") or {})
        trading_config.setdefault("timeframe", timeframe)
        initial_capital = float(data.get("initialCapital", trading_config.get("initialCapital", 100_000)) or 100_000)

        industry_raw = data.get("industryBySymbol") or data.get("industry_by_symbol") or {}
        industry_by_symbol = (
            {str(k).upper(): str(v) for k, v in industry_raw.items()} if isinstance(industry_raw, dict) else {}
        )

        raw_list = data.get("symbolList") or data.get("symbol_list") or []
        symbol_list = (
            [str(x).strip().upper() for x in raw_list if str(x).strip()] if isinstance(raw_list, list) else []
        )
        universe = str(data.get("universe") or "").strip()

        if symbol_list:
            symbols_to_load = symbol_list
        else:
            from app.services.universe_nq100_service import get_constituents_as_of

            symbols_to_load = [s.upper() for s in get_constituents_as_of(start_date.date())]

        panel = _fetch_panel_for_symbols(market, timeframe, symbols_to_load, start_date, end_date)
        if not panel:
            return (
                jsonify({"code": 0, "msg": "No OHLCV panel could be built for the requested pool/dates", "data": None}),
                400,
            )

        rebalance_frequency = str(
            trading_config.get("rebalanceFrequency") or trading_config.get("rebalance_frequency") or "daily"
        )
        service_req: Dict[str, Any] = {
            "panel": panel,
            "start_date": start_date_str[:10],
            "end_date": end_date_str[:10],
            "indicator_code": indicator_code,
            "trading_config": {
                "initial_capital": initial_capital,
                "timeframe": timeframe,
                "rebalance_frequency": rebalance_frequency,
                "fallback_mode": str(trading_config.get("fallbackMode") or trading_config.get("fallback_mode") or "strict"),
                "min_liquidity_usd": float(
                    trading_config.get("minLiquidityUsd") or trading_config.get("min_liquidity_usd") or 1_000_000
                ),
                "long_halt_days": int(trading_config.get("longHaltDays") or trading_config.get("long_halt_days") or 5),
            },
            "industry_by_symbol": industry_by_symbol,
        }
        if symbol_list:
            service_req["symbol_list"] = symbol_list
        if universe:
            service_req["universe"] = universe.lower()

        svc = CrossSectionalPortfolioBacktestService()
        try:
            inner = svc.run(service_req)
        except ValueError as exc:
            msg = str(exc)
            logger.warning("Cross-sectional portfolio service rejected: %s", msg)
            if (
                "CROSS_SECTIONAL_CONTRACT" in msg
                or "CROSS_SECTIONAL_LONG_ONLY" in msg
                or "CROSS_SECTIONAL_WEIGHT_SUM" in msg
            ):
                return (
                    jsonify(
                        {
                            "code": 0,
                            "msg": "Invalid cross-sectional indicator or weights for portfolio backtest",
                            "data": None,
                        }
                    ),
                    422,
                )
            return jsonify({"code": 0, "msg": "Portfolio backtest parameters rejected", "data": None}), 400

        repro = _build_repro_block(
            symbol_list=symbol_list if symbol_list else None,
            universe=universe,
            indicator_code=indicator_code,
            trading_config=service_req["trading_config"],
            industry_by_symbol=industry_by_symbol,
            service_digest=inner.get("repro_digest", ""),
        )

        payload = {
            "repro": repro,
            "neutral_off": inner.get("neutral_off"),
            "neutral_on": inner.get("neutral_on"),
        }

        return jsonify({"code": 1, "msg": "OK", "data": payload})

    except Exception as exc:
        logger.error("cross_sectional_portfolio_backtest failed: %s", exc)
        logger.error(traceback.format_exc())
        return (
            jsonify(
                {
                    "code": 0,
                    "msg": "Internal error while running cross-sectional portfolio backtest",
                    "data": None,
                }
            ),
            500,
        )
