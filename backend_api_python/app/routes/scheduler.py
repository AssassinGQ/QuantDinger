"""
定时任务 API：添加任务品类、启停任务。
"""
from flask import Blueprint, request, jsonify

from app.services.scheduler_service import (
    add_task_type,
    list_task_types,
    start_task,
    stop_task,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

scheduler_bp = Blueprint("scheduler", __name__)


@scheduler_bp.route("/task-types", methods=["GET"])
def get_task_types():
    """列出所有定时任务品类及运行状态。"""
    try:
        items = list_task_types()
        logger.info("Scheduler list task-types: count=%d", len(items))
        return jsonify({"code": 1, "msg": "success", "data": items})
    except Exception as e:
        logger.exception("list task-types: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@scheduler_bp.route("/task-types", methods=["POST"])
def post_task_type():
    """
    添加或更新定时任务品类。
    Body: { "task_type": "kline_1m_sync", "market": "Crypto", "symbols": ["BTCUSDT","ETHUSDT"], "interval_minutes": 400 }
    """
    try:
        data = request.get_json() or {}
        task_type = (data.get("task_type") or "").strip()
        market = (data.get("market") or "Crypto").strip()
        symbols = data.get("symbols")
        interval_minutes = int(data.get("interval_minutes", 400))
        if not task_type:
            return jsonify({"code": 0, "msg": "Missing task_type", "data": None}), 400
        if task_type != "kline_1m_sync":
            return jsonify({"code": 0, "msg": "Only task_type kline_1m_sync is supported", "data": None}), 400
        if not isinstance(symbols, list):
            symbols = []
        symbols = [str(s).strip() for s in symbols if str(s).strip()]
        add_task_type(task_type, market, symbols, interval_minutes)
        logger.info("Scheduler API add task-type: task_type=%s market=%s symbols=%s", task_type, market, symbols)
        return jsonify({
            "code": 1,
            "msg": "success",
            "data": {"task_type": task_type, "market": market, "symbols": symbols, "interval_minutes": interval_minutes},
        })
    except Exception as e:
        logger.exception("add task-type: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@scheduler_bp.route("/start", methods=["POST"])
def start_task_route():
    """启动定时任务。Body: { "task_type": "kline_1m_sync" }"""
    try:
        data = request.get_json() or {}
        task_type = (data.get("task_type") or "").strip()
        if not task_type:
            return jsonify({"code": 0, "msg": "Missing task_type", "data": None}), 400
        ok = start_task(task_type)
        if not ok:
            return jsonify({"code": 0, "msg": "Task type not found or not supported", "data": None}), 404
        logger.info("Scheduler API start task: task_type=%s", task_type)
        return jsonify({"code": 1, "msg": "started", "data": {"task_type": task_type}})
    except Exception as e:
        logger.exception("start task: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@scheduler_bp.route("/stop", methods=["POST"])
def stop_task_route():
    """停止定时任务。Body: { "task_type": "kline_1m_sync" }"""
    try:
        data = request.get_json() or {}
        task_type = (data.get("task_type") or "").strip()
        if not task_type:
            return jsonify({"code": 0, "msg": "Missing task_type", "data": None}), 400
        stop_task(task_type)
        logger.info("Scheduler API stop task: task_type=%s", task_type)
        return jsonify({"code": 1, "msg": "stopped", "data": {"task_type": task_type}})
    except Exception as e:
        logger.exception("stop task: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500
