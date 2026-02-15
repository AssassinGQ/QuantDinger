"""
定时任务服务：支持按品类注册任务，并启停周期任务（如每 400 分钟拉取 1m K 线）。
"""
from typing import Dict, List, Any, Optional
from threading import Lock

from app.utils.logger import get_logger

logger = get_logger(__name__)

# 单次拉取 1m 根数，覆盖 400 分钟并留余量
KLINE_1M_SYNC_BARS = 500

_scheduler = None
_lock = Lock()


def get_scheduler():
    """获取 APScheduler 单例。"""
    global _scheduler
    if _scheduler is None:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler()
        _scheduler.start()
        logger.info("Scheduler started")
    return _scheduler


# 任务品类配置：task_type -> { market, symbols, interval_minutes, job_id? }
_task_types: Dict[str, Dict[str, Any]] = {}
_task_lock = Lock()


def add_task_type(
    task_type: str,
    market: str,
    symbols: List[str],
    interval_minutes: int = 400,
) -> Dict[str, Any]:
    """添加或更新定时任务品类。"""
    sym_list = list(symbols)
    with _task_lock:
        _task_types[task_type] = {
            "market": market,
            "symbols": sym_list,
            "interval_minutes": interval_minutes,
            "job_id": _task_types.get(task_type, {}).get("job_id"),
        }
    logger.info(
        "Scheduler task-type added: task_type=%s market=%s symbols_count=%d interval_min=%d",
        task_type, market, len(sym_list), interval_minutes,
    )
    return {"task_type": task_type, "market": market, "symbols": sym_list, "interval_minutes": interval_minutes}


def list_task_types() -> List[Dict[str, Any]]:
    """列出所有任务品类及运行状态。"""
    with _task_lock:
        out = []
        sched = get_scheduler()
        for tt, cfg in _task_types.items():
            job_id = cfg.get("job_id")
            running = bool(job_id and sched.get_job(job_id))
            out.append({
                "task_type": tt,
                "market": cfg["market"],
                "symbols": cfg["symbols"],
                "interval_minutes": cfg["interval_minutes"],
                "running": running,
            })
        return out


def _run_kline_1m_sync(task_type: str) -> None:
    """执行 1m K 线同步：对已注册的 market+symbols 拉取最近 KLINE_1M_SYNC_BARS 根并写入库。"""
    with _task_lock:
        cfg = _task_types.get(task_type)
        if not cfg:
            logger.warning("Scheduler job %s: no config, skip", task_type)
            return
        market = cfg["market"]
        symbols = cfg["symbols"]
    if not symbols:
        logger.info("Scheduler %s: no symbols, skip", task_type)
        return
    logger.info("Scheduler %s: run started market=%s symbols=%s", task_type, market, symbols)
    from app.services.kline import KlineService
    svc = KlineService()
    for symbol in symbols:
        try:
            klines = svc.get_kline(market, symbol, "1m", limit=KLINE_1M_SYNC_BARS)
            if klines:
                logger.info("Scheduler %s: %s %s synced %d bars", task_type, market, symbol, len(klines))
            else:
                logger.warning("Scheduler %s: %s %s no data", task_type, market, symbol)
        except Exception as e:
            logger.exception("Scheduler %s: %s %s failed: %s", task_type, market, symbol, e)


def start_task(task_type: str) -> bool:
    """启动定时任务。若该品类不存在则返回 False。"""
    with _task_lock:
        cfg = _task_types.get(task_type)
        if not cfg:
            return False
        if task_type != "kline_1m_sync":
            logger.warning("Unknown task_type %s, only kline_1m_sync supported", task_type)
            return False
        interval_minutes = cfg.get("interval_minutes", 400)
        job_id = cfg.get("job_id")
    sched = get_scheduler()
    if job_id and sched.get_job(job_id):
        logger.info("Task %s already running", task_type)
        return True
    if job_id:
        try:
            sched.remove_job(job_id)
        except Exception:
            pass
    job_id = f"scheduler_{task_type}"
    sched.add_job(
        _run_kline_1m_sync,
        "interval",
        minutes=interval_minutes,
        id=job_id,
        args=[task_type],
        replace_existing=True,
    )
    with _task_lock:
        if task_type in _task_types:
            _task_types[task_type]["job_id"] = job_id
    logger.info("Task %s started, interval=%d min", task_type, interval_minutes)
    return True


def stop_task(task_type: str) -> bool:
    """停止定时任务。"""
    with _task_lock:
        cfg = _task_types.get(task_type)
        job_id = cfg.get("job_id") if cfg else None
    if not job_id:
        logger.info("Task %s stop: was not running", task_type)
        return True
    sched = get_scheduler()
    try:
        sched.remove_job(job_id)
    except Exception:
        pass
    with _task_lock:
        if task_type in _task_types:
            _task_types[task_type]["job_id"] = None
    logger.info("Task %s stopped", task_type)
    return True
