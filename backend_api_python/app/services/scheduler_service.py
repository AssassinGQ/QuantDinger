"""
定时任务服务：仅有一个定时任务，可注册多个品类；触发时按品类顺序拉取，品类间延时防限流；
拉取所有周期 (1m/5m/15m/30m/1H/4H/1D/1W) 的 K 线数据并缓存到数据库。
支持：每市场独立延时 / 周期优先级 / RateLimitError 熔断 / 自适应退避。
"""
import time
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from threading import Lock

from app.data_sources.base import RateLimitError
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 延时与限流参数
# ---------------------------------------------------------------------------
DELAY_BETWEEN_CATEGORIES_SECONDS = 10

# 每市场独立延时（秒）——Tiingo(Forex) 限流最严格，给予最大间隔
MARKET_DELAYS: Dict[str, Dict[str, float]] = {
    "Crypto":  {"between_symbols": 0.5, "between_timeframes": 0.3},
    "Forex":   {"between_symbols": 5.0, "between_timeframes": 3.0},
    "USStock": {"between_symbols": 1.5, "between_timeframes": 0.8},
    "AShare":  {"between_symbols": 1.0, "between_timeframes": 0.5},
    "HShare":  {"between_symbols": 1.0, "between_timeframes": 0.5},
    "Futures": {"between_symbols": 1.5, "between_timeframes": 0.8},
}
_DEFAULT_SYMBOL_DELAY = 1.5
_DEFAULT_TF_DELAY = 0.8

# 熔断：连续失败 N 次后，对该市场的后续标的执行长冷却
CIRCUIT_BREAK_THRESHOLD = 3          # 连续失败次数触发冷却
CIRCUIT_COOLDOWN_SECONDS = 60        # 冷却等待（秒）
CIRCUIT_SKIP_THRESHOLD = 6           # 连续失败次数超过此值 → 跳过整个市场后续标的

# 各周期同步的目标条数（兼顾数据量和 API 限流）
SYNC_LIMITS = {
    "1m":  5000,
    "5m":  2000,
    "15m": 1000,
    "30m": 1000,
    "1H":  2000,
    "4H":  1000,
    "1D":  750,
    "1W":  200,
}

# 每市场需要同步的周期列表（按优先级排序：重要周期在前，限流时至少保障常用数据）
MARKET_TIMEFRAMES = {
    "Crypto":  ["1D", "1H", "4H", "1W", "30m", "15m", "5m", "1m"],
    "Forex":   ["1D", "1H", "4H", "1W", "30m", "15m", "5m"],
    "USStock": ["1D", "1H", "4H", "1W", "30m", "15m", "5m", "1m"],
    "AShare":  ["1D", "1H", "4H", "1W", "30m", "15m", "5m", "1m"],
    "HShare":  ["1D", "1H", "4H", "1W", "30m", "15m", "5m", "1m"],
    "Futures": ["1D", "1H", "4H", "1W", "30m", "15m", "5m", "1m"],
}

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


def get_job_status() -> Dict[str, Any]:
    """返回定时任务是否存在及下次运行时间，不依赖日志。"""
    try:
        sched = get_scheduler()
        job = sched.get_job(SCHEDULER_JOB_ID)
        if job is None:
            return {"job_id": SCHEDULER_JOB_ID, "exists": False, "next_run_time": None}
        next_run = job.next_run_time
        return {
            "job_id": SCHEDULER_JOB_ID,
            "exists": True,
            "next_run_time": next_run.isoformat() if next_run else None,
        }
    except Exception as e:
        logger.exception("get_job_status: %s", e)
        return {"job_id": SCHEDULER_JOB_ID, "exists": False, "next_run_time": None, "error": str(e)}


# 与 qd_market_symbols 种子一致的市场及 task_type 后缀；无 DB 时的回退列表
_DEFAULT_MARKETS = [
    ("Crypto", "kline_1m_sync_crypto", [
        "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
        "ADA/USDT", "DOGE/USDT", "DOT/USDT", "MATIC/USDT", "AVAX/USDT",
        "LINK/USDT", "UNI/USDT", "ATOM/USDT", "LTC/USDT", "ETC/USDT",
        "NEAR/USDT", "APT/USDT", "OP/USDT", "ARB/USDT", "FIL/USDT",
        "AAVE/USDT", "INJ/USDT", "SUI/USDT", "SEI/USDT", "TIA/USDT",
        "PEPE/USDT", "WIF/USDT", "FET/USDT", "RENDER/USDT", "MKR/USDT",
    ]),
    ("Forex", "kline_1m_sync_forex", [
        "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY",
        "AUDUSD", "USDCAD", "NZDUSD", "USDCHF", "EURJPY",
        "GBPJPY", "EURGBP", "EURAUD", "AUDJPY", "CADJPY",
        "CHFJPY", "EURCHF", "GBPAUD", "GBPCAD", "NZDJPY",
    ]),
    ("USStock", "kline_1m_sync_us", [
        "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "JPM", "V", "JNJ",
        "AMD", "INTC", "CRM", "NFLX", "ORCL", "ADBE", "AVGO", "QCOM", "PEP", "KO",
        "WMT", "DIS", "PYPL", "BA", "GS", "MS", "C", "BAC", "UNH", "PFE",
        "MRK", "ABBV", "LLY", "XOM", "CVX", "HD", "MCD", "NKE", "COST", "MA",
    ]),
    ("AShare", "kline_1m_sync_ashare", [
        "000001", "000002", "600000", "600036", "600519", "000858", "002415", "300059", "000725", "002594",
        "601318", "600276", "601012", "300750", "600900", "601166", "000333", "600030", "601888", "000568",
        "002714", "600887", "300015", "002475", "601899", "600809", "002304", "600585", "601398", "600031",
    ]),
    ("HShare", "kline_1m_sync_hshare", [
        "00700", "09988", "03690", "01810", "02318", "01398", "00939", "01299", "02020", "01024",
        "09618", "09999", "01211", "02382", "00388", "00005", "02628", "00941", "00883", "01928",
        "06098", "09961", "01179", "02269", "00027",
    ]),
    ("Futures", "kline_1m_sync_futures", [
        "CL", "GC", "SI", "NG", "HG", "ZC", "ZS", "ZW", "ES", "NQ",
        "YM", "RTY", "ZN", "ZB", "6E", "6J", "PL", "PA", "CT", "KC",
    ]),
]


def ensure_default_task_types() -> None:
    """若尚未注册任何品类，则从 qd_market_symbols 读取 init 种子标的并注册（含 Crypto/Forex/US/AShare/HShare/Futures）。"""
    with _task_lock:
        if _task_types:
            return
        try:
            from app.data.market_symbols_seed import get_all_symbols
            for market, task_type, fallback_symbols in _DEFAULT_MARKETS:
                rows = get_all_symbols(market)
                symbols = [r["symbol"] for r in rows] if rows else fallback_symbols
                _task_types[task_type] = {
                    "market": market,
                    "symbols": list(symbols),
                    "interval_minutes": 400,
                }
        except Exception as e:
            logger.warning("Scheduler load symbols from qd_market_symbols failed: %s, use fallback", e)
            for market, task_type, fallback_symbols in _DEFAULT_MARKETS:
                _task_types[task_type] = {
                    "market": market,
                    "symbols": list(fallback_symbols),
                    "interval_minutes": 400,
                }
        logger.info("Scheduler default task-types registered: %d categories", len(_task_types))


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


def _run_kline_sync(task_type: str) -> None:
    """执行一个品类的全周期 K 线同步，内含限流防护与熔断。"""
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

    timeframes = MARKET_TIMEFRAMES.get(market, ["1D"])
    delays = MARKET_DELAYS.get(market, {})
    sym_delay = delays.get("between_symbols", _DEFAULT_SYMBOL_DELAY)
    tf_delay = delays.get("between_timeframes", _DEFAULT_TF_DELAY)

    logger.info(
        "Scheduler %s: started market=%s symbols=%d timeframes=%s sym_delay=%.1fs tf_delay=%.1fs",
        task_type, market, len(symbols), timeframes, sym_delay, tf_delay,
    )

    from app.services.kline_fetcher import get_kline as fetch_kline, _write_points_to_db
    from app.data_sources import DataSourceFactory

    consecutive_failures = 0
    market_skipped = False

    for i, symbol in enumerate(symbols):
        # --- 熔断检查 ---
        if market_skipped:
            break
        if consecutive_failures >= CIRCUIT_SKIP_THRESHOLD:
            logger.warning(
                "Scheduler %s: %d consecutive failures → skip remaining %d symbols for %s",
                task_type, consecutive_failures, len(symbols) - i, market,
            )
            market_skipped = True
            break
        if consecutive_failures >= CIRCUIT_BREAK_THRESHOLD:
            logger.warning(
                "Scheduler %s: %d consecutive failures → cooldown %ds before next symbol",
                task_type, consecutive_failures, CIRCUIT_COOLDOWN_SECONDS,
            )
            time.sleep(CIRCUIT_COOLDOWN_SECONDS)

        synced_tfs = []
        symbol_had_rate_limit = False

        for tf in timeframes:
            if symbol_had_rate_limit:
                break

            limit = SYNC_LIMITS.get(tf, 500)
            try:
                if tf == "1m":
                    klines = fetch_kline(market, symbol, "1m", limit=limit)
                    if klines and len(klines) >= 10:
                        synced_tfs.append(f"1m:{len(klines)}")
                    else:
                        klines_5m = DataSourceFactory.get_kline(
                            market, symbol, "5m", limit=min(200, limit // 5))
                        if klines_5m:
                            _write_points_to_db(market, symbol, klines_5m, interval_sec=300)
                            synced_tfs.append(f"5m(fb):{len(klines_5m)}")
                else:
                    klines = fetch_kline(market, symbol, tf, limit=limit)
                    if klines:
                        synced_tfs.append(f"{tf}:{len(klines)}")

            except RateLimitError as rle:
                wait = max(rle.retry_after, tf_delay * 5)
                logger.warning(
                    "Scheduler %s: RateLimit on %s %s %s → wait %.0fs, skip remaining TFs for this symbol",
                    task_type, market, symbol, tf, wait,
                )
                time.sleep(wait)
                symbol_had_rate_limit = True
                consecutive_failures += 1
                continue

            except Exception as e:
                logger.warning("Scheduler %s: %s %s %s failed: %s", task_type, market, symbol, tf, e)

            if tf != timeframes[-1]:
                time.sleep(tf_delay)

        if synced_tfs:
            logger.info("Scheduler %s: %s %s synced [%s]", task_type, market, symbol, ", ".join(synced_tfs))
            consecutive_failures = 0
        elif not symbol_had_rate_limit:
            logger.warning("Scheduler %s: %s %s no data for any timeframe", task_type, market, symbol)
            consecutive_failures += 1

        if i < len(symbols) - 1:
            time.sleep(sym_delay)

    if market_skipped:
        logger.warning("Scheduler %s: market %s sync aborted (rate limited)", task_type, market)


def _run_macro_sync() -> None:
    """同步 VIX、VHSI、DXY、Fear&Greed 等到 qd_macro_data（基本盘）。"""
    try:
        from app.services.macro_data_service import MacroDataService
        stats = MacroDataService.sync_recent_to_db(days=30)
        if stats:
            logger.info("Macro sync done: %s", stats)
    except Exception as e:
        logger.warning("Macro sync failed: %s", e)


def _run_sentiment_sync() -> None:
    """同步基本盘情绪数据（VIX/DXY/Fear&Greed/yield 等）到 qd_sync_cache。"""
    try:
        from app.routes.global_market import (
            _fetch_vix, _fetch_dollar_index, _fetch_fear_greed_index,
            _fetch_yield_curve, _fetch_vxn, _fetch_gvz, _fetch_put_call_ratio
        )
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import json
        from app.utils.db import get_db_connection

        with ThreadPoolExecutor(max_workers=7) as ex:
            futures = {
                ex.submit(_fetch_fear_greed_index): "fear_greed",
                ex.submit(_fetch_vix): "vix",
                ex.submit(_fetch_dollar_index): "dxy",
                ex.submit(_fetch_yield_curve): "yield_curve",
                ex.submit(_fetch_vxn): "vxn",
                ex.submit(_fetch_gvz): "gvz",
                ex.submit(_fetch_put_call_ratio): "vix_term",
            }
            results = {}
            for f in as_completed(futures):
                k = futures[f]
                try:
                    results[k] = f.result()
                except Exception:
                    results[k] = None
        data = {
            "fear_greed": results.get("fear_greed") or {"value": 50, "classification": "Neutral"},
            "vix": results.get("vix") or {"value": 0, "level": "unknown"},
            "dxy": results.get("dxy") or {"value": 0, "level": "unknown"},
            "yield_curve": results.get("yield_curve") or {"spread": 0, "level": "unknown"},
            "vxn": results.get("vxn") or {"value": 0, "level": "unknown"},
            "gvz": results.get("gvz") or {"value": 0, "level": "unknown"},
            "vix_term": results.get("vix_term"),
        }
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """CREATE TABLE IF NOT EXISTS qd_sync_cache (
                    cache_key VARCHAR(64) PRIMARY KEY,
                    value_json TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                )"""
            )
            cur.execute(
                """INSERT INTO qd_sync_cache (cache_key, value_json, updated_at)
                   VALUES ('market_sentiment', %s, NOW())
                   ON CONFLICT (cache_key) DO UPDATE SET value_json = EXCLUDED.value_json, updated_at = NOW()""",
                (json.dumps(data, ensure_ascii=False),)
            )
            db.commit()
            cur.close()
        logger.info("Sentiment sync done: vix=%s dxy=%s fg=%s",
                    results.get("vix", {}).get("value"), results.get("dxy", {}).get("value"),
                    results.get("fear_greed", {}).get("value"))
    except Exception as e:
        logger.warning("Sentiment sync failed: %s", e)


def _run_news_sync() -> None:
    """同步市场新闻到 qd_sync_cache（可选，依赖 Search API）。"""
    try:
        from app.routes.global_market import _fetch_financial_news
        import json
        from app.utils.db import get_db_connection

        news = _fetch_financial_news(lang="all")
        if not news or (not news.get("cn") and not news.get("en")):
            return
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                """CREATE TABLE IF NOT EXISTS qd_sync_cache (
                    cache_key VARCHAR(64) PRIMARY KEY,
                    value_json TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                )"""
            )
            cur.execute(
                """INSERT INTO qd_sync_cache (cache_key, value_json, updated_at)
                   VALUES ('market_news', %s, NOW())
                   ON CONFLICT (cache_key) DO UPDATE SET value_json = EXCLUDED.value_json, updated_at = NOW()""",
                (json.dumps(news, ensure_ascii=False),)
            )
            db.commit()
            cur.close()
        logger.info("News sync done: cn=%d en=%d", len(news.get("cn", [])), len(news.get("en", [])))
    except Exception as e:
        logger.debug("News sync skipped (search may be unconfigured): %s", e)


def _run_all_kline_sync() -> None:
    """单一定时任务入口：按品类顺序执行 K 线 + 宏观 + 新闻同步。"""
    ensure_default_task_types()
    with _task_lock:
        types_order = list(_task_types.keys())
    if types_order:
        logger.info("Scheduler run: %d categories, all timeframes", len(types_order))
        for i, task_type in enumerate(types_order):
            _run_kline_sync(task_type)
            if i < len(types_order) - 1:
                time.sleep(DELAY_BETWEEN_CATEGORIES_SECONDS)

    time.sleep(2)
    _run_macro_sync()
    time.sleep(2)
    _run_sentiment_sync()
    time.sleep(2)
    _run_news_sync()


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


def _wait_backend_ready(max_wait_sec: float = 60, poll_interval: float = 1) -> bool:
    """轮询 DB 是否就绪，用于 run_immediately 首次执行前确认 backend 初始化完成。"""
    try:
        from app.utils.db import is_postgres_available
    except Exception:
        return False
    deadline = time.time() + max_wait_sec
    while time.time() < deadline:
        if is_postgres_available():
            return True
        time.sleep(poll_interval)
    return False


def _wrap_run_immediately(func, job_id: str, max_wait_sec: float) -> callable:
    """包装 run_immediately 任务：仅首次执行前等待 backend 就绪，后续直接执行。"""
    first_run = [True]

    def _wrapped():
        if first_run[0]:
            first_run[0] = False
            if not _wait_backend_ready(max_wait_sec=max_wait_sec):
                logger.warning("Job %s: backend not ready within %.0fs, skip", job_id, max_wait_sec)
                return
        func()
    return _wrapped


# ---------------------------------------------------------------------------
# 插件式定时任务通用接口
# ---------------------------------------------------------------------------

def register_scheduled_job(job_id: str, func, interval_minutes: int,
                           max_instances: int = 1, replace: bool = True,
                           run_immediately: bool = False) -> bool:
    """注册一个独立的 interval 定时任务到 APScheduler。

    Args:
        job_id: 唯一 job 标识
        func: 无参可调用对象
        interval_minutes: 执行间隔（分钟）
        max_instances: 最大并发实例数
        replace: 若已存在是否替换
        run_immediately: 注册后首次尽快执行；执行时先阻塞轮询 DB 就绪再跑任务。
    """
    sched = get_scheduler()
    existing = sched.get_job(job_id)
    if existing and not replace:
        logger.info("Job %s already registered, skip", job_id)
        return False

    target_func = func
    kwargs = {
        "minutes": interval_minutes,
        "id": job_id,
        "max_instances": max_instances,
        "replace_existing": replace,
    }
    if run_immediately:
        max_wait = float(os.environ.get("RUN_IMMEDIATELY_BACKEND_READY_TIMEOUT_SEC", "60"))
        target_func = _wrap_run_immediately(func, job_id, max_wait)
        kwargs["next_run_time"] = datetime.now()

    sched.add_job(target_func, "interval", **kwargs)
    logger.info(
        "Registered scheduled job: %s, interval=%d min%s",
        job_id, interval_minutes, ", run_immediately" if run_immediately else "",
    )
    return True


def unregister_scheduled_job(job_id: str) -> bool:
    """移除一个已注册的定时任务。"""
    sched = get_scheduler()
    if not sched.get_job(job_id):
        logger.info("Job %s not found, nothing to remove", job_id)
        return False
    try:
        sched.remove_job(job_id)
    except Exception:
        pass
    logger.info("Unregistered scheduled job: %s", job_id)
    return True


def get_all_jobs_status() -> List[Dict[str, Any]]:
    """返回所有已注册 job 的状态（含 kline 和插件 job）。"""
    sched = get_scheduler()
    result = []
    for job in sched.get_jobs():
        result.append({
            "job_id": job.id,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        })
    return result


def run_kline_sync_once() -> None:
    """手动触发一次完整 K 线同步（供插件或测试调用）。"""
    _run_all_kline_sync()
