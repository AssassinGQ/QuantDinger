from datetime import date, datetime

from flask import Blueprint, jsonify, request

from app.services.universe_nq100_service import (
    get_constituents_as_of,
    get_eiv_as_of,
    sync_nq100_from_csv,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)
universe_bp = Blueprint("universe", __name__)


def _parse_date_or_none(raw: str):
    value = (raw or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


@universe_bp.route("/nq100", methods=["GET"])
def get_nq100_constituents():
    try:
        as_of = _parse_date_or_none(request.args.get("date"))
        if as_of is None:
            as_of = date.today()
        symbols = get_constituents_as_of(as_of)
        msg = "success"
        if not symbols:
            msg = "NQ100 成分列表为空，请先运行成分同步"
        return jsonify({"code": 1, "msg": msg, "data": {"date": as_of.isoformat(), "symbols": symbols}})
    except Exception as exc:
        logger.error("get_nq100_constituents failed: %s", exc)
        return jsonify({"code": 0, "msg": str(exc), "data": None}), 500


@universe_bp.route("/nq100/eiv", methods=["GET"])
def get_nq100_eiv():
    try:
        date_raw = request.args.get("date")
        if not (date_raw or "").strip():
            return jsonify({"code": 0, "msg": "Missing required query param: date", "data": None}), 400
        as_of = _parse_date_or_none(date_raw)
        eiv = get_eiv_as_of(as_of)
        if eiv is None:
            return jsonify({"code": 1, "msg": "success", "data": None})
        return jsonify({"code": 1, "msg": "success", "data": eiv})
    except Exception as exc:
        logger.error("get_nq100_eiv failed: %s", exc)
        return jsonify({"code": 0, "msg": str(exc), "data": None}), 500


@universe_bp.route("/nq100/refresh", methods=["POST"])
def refresh_nq100():
    try:
        summary = sync_nq100_from_csv()
        return jsonify({"code": 1, "msg": "success", "data": summary})
    except Exception as exc:
        logger.error("refresh_nq100 failed: %s", exc)
        return jsonify({"code": 0, "msg": str(exc), "data": None}), 500
