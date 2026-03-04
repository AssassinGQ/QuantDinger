"""
定时任务 API：添加任务品类、启停任务。
"""
from flask import Blueprint, request, jsonify

from app.services.scheduler_service import (
    add_task_type,
    list_task_types,
    start_task,
    stop_task,
    get_job_status,
    get_all_jobs_status,
    run_kline_sync_once,
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
        if not task_type.startswith("kline_1m_sync"):
            return jsonify({"code": 0, "msg": "task_type must start with kline_1m_sync", "data": None}), 400
        if not isinstance(symbols, list):
            symbols = []
        symbols = [str(s).strip() for s in symbols if str(s).strip()]
        try:
            add_task_type(task_type, market, symbols, interval_minutes)
        except ValueError as e:
            return jsonify({"code": 0, "msg": str(e), "data": None}), 400
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
    """启动唯一的定时任务（执行所有已注册品类）。Body 可选: { "task_type": "kline_1m_sync_crypto" }"""
    try:
        data = request.get_json() or {}
        task_type = (data.get("task_type") or "").strip() or None
        ok = start_task(task_type)
        if not ok:
            return jsonify({"code": 0, "msg": "No task categories registered", "data": None}), 404
        logger.info("Scheduler API start: categories will run on interval")
        return jsonify({"code": 1, "msg": "started", "data": {}})
    except Exception as e:
        logger.exception("start task: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@scheduler_bp.route("/status", methods=["GET"])
def get_status():
    """查看定时任务是否存在及下次运行时间，不依赖日志。"""
    try:
        data = get_job_status()
        return jsonify({"code": 1, "msg": "success", "data": data})
    except Exception as e:
        logger.exception("scheduler status: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@scheduler_bp.route("/jobs", methods=["GET"])
def list_all_jobs():
    """列出所有 APScheduler 任务（含插件 task_kline_sync 等）及下次运行时间。"""
    try:
        jobs = get_all_jobs_status()
        return jsonify({"code": 1, "msg": "success", "data": jobs})
    except Exception as e:
        logger.exception("scheduler jobs: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@scheduler_bp.route("/kline-sync", methods=["POST"])
def trigger_kline_sync():
    """
    手动触发同步。

    Body:
        fetch_type: "all"(默认) 全量 K线+宏观+情绪+新闻；"macro_only" 仅宏观数据
        macro_days: 宏观数据历史天数，默认 30，可传如 360
    """
    try:
        data = request.get_json() or {}
        fetch_type = (data.get("fetch_type") or "all").strip().lower()
        if fetch_type not in ("all", "macro_only"):
            return jsonify({"code": 0, "msg": "fetch_type must be 'all' or 'macro_only'", "data": None}), 400
        try:
            macro_days = int(data.get("macro_days", 30))
        except (TypeError, ValueError):
            macro_days = 30
        macro_days = max(1, min(macro_days, 3650))

        run_kline_sync_once(fetch_type=fetch_type, macro_days=macro_days)
        logger.info("Scheduler API kline-sync: done fetch_type=%s macro_days=%d", fetch_type, macro_days)
        return jsonify({
            "code": 1, "msg": "ok",
            "data": {"fetch_type": fetch_type, "macro_days": macro_days},
        })
    except Exception as e:
        logger.exception("kline-sync failed: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500


@scheduler_bp.route("/stop", methods=["POST"])
def stop_task_route():
    """停止唯一的定时任务。Body 可选: { "task_type": "..." }"""
    try:
        data = request.get_json() or {}
        task_type = (data.get("task_type") or "").strip() or None
        stop_task(task_type)
        logger.info("Scheduler API stop")
        return jsonify({"code": 1, "msg": "stopped", "data": {}})
    except Exception as e:
        logger.exception("stop task: %s", e)
        return jsonify({"code": 0, "msg": str(e), "data": None}), 500
