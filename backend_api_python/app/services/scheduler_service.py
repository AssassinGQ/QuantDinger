"""
定时任务服务：仅有一个定时任务，可注册多个品类；触发时按品类顺序拉取，品类间延时防限流；
1m 不可用时回退 5m 并写缓存。
"""
import time
from typing import Dict, List, Any, Optional
from threading import Lock

from app.utils.logger import get_logger

logger = get_logger(__name__)

# 单次拉取 1m 根数，覆盖 400 分钟并留余量
KLINE_1M_SYNC_BARS = 500
# 品类之间延时（秒），减轻限流
DELAY_BETWEEN_CATEGORIES_SECONDS = 5

# 单一定时任务 job id
SCHEDULER_JOB_ID = "scheduler_kline_sync"

_scheduler = None
_lock = Lock()

# 任务品类配置：task_type -> { market, symbols, interval_minutes }（无 job_id，全局共用一个 job）
_task_types: Dict[str, Dict[str, Any]] = {}
_task_lock = Lock()


def get_scheduler():
    """获取 APScheduler 单例。"""
    global _scheduler
    if _scheduler is None:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler()
        _scheduler.start()
        logger.info("Scheduler started")
    return _scheduler


def _is_scheduler_running() -> bool:
    sched = get_scheduler()
    return bool(sched.get_job(SCHEDULER_JOB_ID))


def ensure_default_task_types() -> None:
    """若尚未注册任何品类，则注册常见品类（Crypto、Forex、USStock、AShare、HShare）。"""
    with _task_lock:
        if _task_types:
            return
        defaults = [
            ("kline_1m_sync_crypto", "Crypto", ["BTCUSDT", "ETHUSDT"], 400),
            ("kline_1m_sync_forex", "Forex", ["XAUUSD", "EURUSD"], 400),
            ("kline_1m_sync_us", "USStock", ["AAPL", "MSFT"], 400),
            ("kline_1m_sync_ashare", "AShare", ["600519", "000001"], 400),
            ("kline_1m_sync_hshare", "HShare", ["00700"], 400),
        ]
        for task_type, market, symbols, interval in defaults:
            _task_types[task_type] = {
                "market": market,
                "symbols": list(symbols),
                "interval_minutes": interval,
            }
        logger.info("Scheduler default task-types registered: %d categories", len(defaults))


def add_task_type(
    task_type: str,
    market: str,
    symbols: List[str],
    interval_minutes: int = 400,
) -> Dict[str, Any]:
    """添加或更新定时任务品类。"""
    if not task_type or not task_type.strip().startswith("kline_1m_sync"):
        raise ValueError("task_type must start with kline_1m_sync")
    task_type = task_type.strip()
    sym_list = list(symbols)
    with _task_lock:
        _task_types[task_type] = {
            "market": market,
            "symbols": sym_list,
            "interval_minutes": interval_minutes,
        }
    logger.info(
        "Scheduler task-type added: task_type=%s market=%s symbols_count=%d interval_min=%d",
        task_type, market, len(sym_list), interval_minutes,
    )
    return {"task_type": task_type, "market": market, "symbols": sym_list, "interval_minutes": interval_minutes}


def list_task_types() -> List[Dict[str, Any]]:
    """列出所有任务品类；running 表示唯一的定时任务是否在运行。"""
    ensure_default_task_types()
    running = _is_scheduler_running()
    with _task_lock:
        out = []
        for tt, cfg in _task_types.items():
            out.append({
                "task_type": tt,
                "market": cfg["market"],
                "symbols": cfg["symbols"],
                "interval_minutes": cfg["interval_minutes"],
                "running": running,
            })
        return out


def _run_kline_1m_sync(task_type: str) -> None:
    """执行一个品类的 1m（或回退 5m）K 线同步。"""
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
    from app.services.kline import KlineService, _write_kline_to_db
    from app.data_sources import DataSourceFactory
    svc = KlineService()
    for symbol in symbols:
        try:
            klines_1m = svc.get_kline(market, symbol, "1m", limit=KLINE_1M_SYNC_BARS)
            if klines_1m and len(klines_1m) >= 10:
                logger.info("Scheduler %s: %s %s synced 1m %d bars", task_type, market, symbol, len(klines_1m))
                continue
            klines_5m = DataSourceFactory.get_kline(market, symbol, "5m", limit=min(200, KLINE_1M_SYNC_BARS // 5))
            if klines_5m:
                from app.services.kline import _write_points_to_db
                _write_points_to_db(market, symbol, klines_5m, interval_sec=300)
                _write_kline_to_db(market, symbol, "5m", klines_5m)
                logger.info("Scheduler %s: %s %s fallback 5m %d bars (1m unavailable)", task_type, market, symbol, len(klines_5m))
            else:
                logger.warning("Scheduler %s: %s %s no data (1m and 5m)", task_type, market, symbol)
        except Exception as e:
            logger.exception("Scheduler %s: %s %s failed: %s", task_type, market, symbol, e)


def _run_all_kline_sync() -> None:
    """单一定时任务入口：按品类顺序执行，品类间延时。"""
    ensure_default_task_types()
    with _task_lock:
        types_order = list(_task_types.keys())
    if not types_order:
        logger.info("Scheduler run: no categories registered, skip")
        return
    logger.info("Scheduler run: %d categories", len(types_order))
    for i, task_type in enumerate(types_order):
        _run_kline_1m_sync(task_type)
        if i < len(types_order) - 1:
            time.sleep(DELAY_BETWEEN_CATEGORIES_SECONDS)


def start_task(task_type: Optional[str] = None) -> bool:
    """启动唯一的定时任务（会按间隔执行所有已注册品类）。task_type 可省略或传任意已注册品类。"""
    ensure_default_task_types()
    with _task_lock:
        if not _task_types:
            return False
        interval_minutes = next((c["interval_minutes"] for c in _task_types.values()), 400)
    sched = get_scheduler()
    if sched.get_job(SCHEDULER_JOB_ID):
        logger.info("Scheduler already running")
        return True
    sched.add_job(
        _run_all_kline_sync,
        "interval",
        minutes=interval_minutes,
        id=SCHEDULER_JOB_ID,
        replace_existing=True,
    )
    logger.info("Scheduler started, interval=%d min, categories=%d", interval_minutes, len(_task_types))
    return True


def stop_task(task_type: Optional[str] = None) -> bool:
    """停止唯一的定时任务。"""
    sched = get_scheduler()
    if not sched.get_job(SCHEDULER_JOB_ID):
        logger.info("Scheduler stop: was not running")
        return True
    try:
        sched.remove_job(SCHEDULER_JOB_ID)
    except Exception:
        pass
    logger.info("Scheduler stopped")
    return True
